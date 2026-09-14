"""Domain pack production loader.

A domain pack is a signed bundle of YAML declarations.  The core engine stays
sector-neutral: this module only parses, validates, and carries the pack's
declarations to the engines that consume them.  It never adds sector behavior
to the core, and it fails closed on a missing, tampered, or unsigned pack
unless the operator explicitly opts into development mode.

Signature
---------
The signature is HMAC-SHA256 over the canonical JSON of the eight section
files (everything except ``manifest.yaml``, which carries the signature
itself).  The key comes from ``AIRBENCH_PACK_SIGNING_KEY`` (hex or UTF-8) or
``AIRBENCH_PACK_SIGNING_KEY_PATH``.  ``AIRBENCH_PACK_ALLOW_UNSIGNED=1``
accepts an unsigned pack for development only.

Ledger
------
Loading a signed pack is consequential.  When a ledger and a task identity are
supplied, ``pack.loaded`` is appended; otherwise the caller records the result
in the node-startup sovereignty evidence (the same M9 pattern used for the
offline bundle).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from contracts import Clearance, Taint, build_event, idempotency_key

MANIFEST_FILE = "manifest.yaml"
SECTION_FILES: dict[str, str] = {
    "world_schema": "world_schema.yaml",
    "document_profiles": "document_profiles.yaml",
    "field_rules": "field_rules.yaml",
    "decision_types": "decision_types.yaml",
    "risk_mappings": "risk_mappings.yaml",
    "clearance_roles": "clearance_roles.yaml",
    "deliverable_templates": "deliverable_templates.yaml",
    "worker_requirements": "worker_requirements.yaml",
}
SIGNATURE_ALGORITHM = "HMAC-SHA256"


class PackError(RuntimeError):
    """A domain pack could not be loaded safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Typed sections
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WorldSchema:
    objects: tuple[str, ...]
    links: tuple[tuple[str, str, str], ...] = ()
    authoritative_sources: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    profile_id: str
    formats: tuple[str, ...]
    intake: str
    authoritative_for: tuple[str, ...] = ()
    trust: str = "untrusted_until_provenance_gate"


@dataclass(frozen=True, slots=True)
class FieldRule:
    """A pack-declared check, compiled to the finite verification language.

    ``check`` names one of ``citation_required``, ``unit_check``,
    ``range_check``, or ``cross_reference``.  A rule without a ``check`` is a
    declarative policy note that cannot be executed and resolves to review.
    """

    rule_id: str
    applies_to: str
    result: str
    check: str | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    expected_unit: str | None = None
    source_prefixes: tuple[str, ...] = ()
    tolerance: float = 0.0


@dataclass(frozen=True, slots=True)
class DecisionType:
    decision_type_id: str
    required_features: tuple[str, ...]
    minimum_authority: str
    require_deviation_review: bool = False


@dataclass(frozen=True, slots=True)
class RiskMapping:
    action_kind: str
    risk_class: str
    reversibility: str
    autonomy_ceiling: str
    required_human_authority: str


@dataclass(frozen=True, slots=True)
class ClearanceRole:
    role_id: str
    maximum_clearance: str
    may_review: tuple[str, ...] = ()
    may_approve: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeliverableTemplate:
    template_id: str
    version: str
    format: str
    required_sections: tuple[str, ...]
    labels: tuple[tuple[str, str], ...] = ()
    value_bindings: tuple[tuple[str, bool], ...] = ()


@dataclass(frozen=True, slots=True)
class WorkerRequirements:
    workflow_id: str
    required_workers: tuple[str, ...]
    required_evidence: tuple[str, ...] = ()
    completion_requires: tuple[str, ...] = ()
    missing_verifier_result: str = "needs_review"


@dataclass(frozen=True, slots=True)
class PackManifest:
    pack_id: str
    pack_version: str
    signature: str | None
    signing_status: str
    compatibility_id: str = ""
    status: str = ""


@dataclass(frozen=True, slots=True)
class SectionHash:
    name: str
    sha256: str


@dataclass(frozen=True, slots=True)
class LoadedPack:
    root: Path
    manifest: PackManifest
    world_schema: WorldSchema
    document_profiles: tuple[DocumentProfile, ...]
    field_rules: tuple[FieldRule, ...]
    decision_types: tuple[DecisionType, ...]
    risk_mappings: tuple[RiskMapping, ...]
    clearance_roles: tuple[ClearanceRole, ...]
    deliverable_templates: tuple[DeliverableTemplate, ...]
    worker_requirements: tuple[WorkerRequirements, ...]
    signature_verified: bool
    section_hashes: tuple[SectionHash, ...] = ()

    def active_sections(self) -> tuple[str, ...]:
        return tuple(sorted(SECTION_FILES))

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.manifest.pack_id,
            "pack_version": self.manifest.pack_version,
            "compatibility_id": self.manifest.compatibility_id,
            "status": self.manifest.status,
            "signature_status": "signed" if self.signature_verified else "unsigned",
            "signature_verified": self.signature_verified,
            "active_sections": list(self.active_sections()),
            "counts": {
                "document_profiles": len(self.document_profiles),
                "field_rules": len(self.field_rules),
                "decision_types": len(self.decision_types),
                "risk_mappings": len(self.risk_mappings),
                "clearance_roles": len(self.clearance_roles),
                "deliverable_templates": len(self.deliverable_templates),
                "worker_requirements": len(self.worker_requirements),
                "world_objects": len(self.world_schema.objects),
            },
            "section_hashes": [{"name": item.name, "sha256": item.sha256} for item in self.section_hashes],
        }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PackError("invalid_section", f"{label} must be a mapping")
    return value


def _require_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PackError("invalid_section", f"{label} must be a list")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackError("invalid_section", f"{label} must be a non-empty string")
    return value.strip()


def _text_tuple(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(_text(item, label) for item in _require_sequence(value, label))


def _optional_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PackError("invalid_section", f"{label} must be a number")
    return float(value)


def _section_digest(sections: Mapping[str, Any]) -> bytes:
    canonical = json.dumps(
        {name: sections[name] for name in sorted(sections)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return canonical.encode("utf-8")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class PackLoader:
    """Parse, validate, and verify one domain pack directory."""

    def __init__(self, *, signing_key: bytes | None = None, allow_unsigned: bool = False) -> None:
        self._signing_key = bytes(signing_key) if signing_key else None
        self._allow_unsigned = allow_unsigned

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "PackLoader":
        values = os.environ if env is None else env
        allow_unsigned = values.get("AIRBENCH_PACK_ALLOW_UNSIGNED", "").strip().lower() in {"1", "true", "yes", "on"}
        key: bytes | None = None
        raw = values.get("AIRBENCH_PACK_SIGNING_KEY", "").strip()
        key_path = values.get("AIRBENCH_PACK_SIGNING_KEY_PATH", "").strip()
        if raw:
            key = _decode_key(raw)
        elif key_path:
            try:
                key = Path(key_path).read_bytes()
            except OSError as exc:
                raise PackError("signing_key_unreadable", "the pack signing key could not be read") from exc
        if key is not None and len(key) != 32:
            raise PackError("invalid_signing_key", "the pack signing key must be 32 bytes")
        return cls(signing_key=key, allow_unsigned=allow_unsigned)

    def load(
        self,
        pack_dir: str | Path,
        *,
        ledger: Any | None = None,
        task_id: str | None = None,
    ) -> LoadedPack:
        root = Path(pack_dir)
        if not root.is_dir():
            raise PackError("pack_not_found", "the domain pack directory does not exist")

        parsed_sections: dict[str, Any] = {}
        section_hashes: list[SectionHash] = []
        for name, file_name in SECTION_FILES.items():
            path = root / file_name
            if not path.is_file():
                raise PackError("missing_section", f"the domain pack is missing {file_name}")
            parsed_sections[name] = _load_yaml(path, file_name)
            section_hashes.append(SectionHash(name=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

        manifest_path = root / MANIFEST_FILE
        if not manifest_path.is_file():
            raise PackError("missing_manifest", "the domain pack is missing manifest.yaml")
        manifest_raw = _require_mapping(_load_yaml(manifest_path, MANIFEST_FILE), MANIFEST_FILE)

        manifest = PackManifest(
            pack_id=_text(manifest_raw.get("pack_id"), "manifest.pack_id"),
            pack_version=_text(manifest_raw.get("pack_version"), "manifest.pack_version"),
            signature=str(manifest_raw["signature"]) if manifest_raw.get("signature") else None,
            signing_status=str(manifest_raw.get("signing_status", "unsigned")),
            compatibility_id=str(manifest_raw.get("compatibility_id", "")),
            status=str(manifest_raw.get("status", "")),
        )

        signature_verified = self._verify_signature(manifest, parsed_sections)

        loaded = LoadedPack(
            root=root,
            manifest=manifest,
            world_schema=_parse_world_schema(parsed_sections["world_schema"]),
            document_profiles=_parse_document_profiles(parsed_sections["document_profiles"]),
            field_rules=_parse_field_rules(parsed_sections["field_rules"]),
            decision_types=_parse_decision_types(parsed_sections["decision_types"]),
            risk_mappings=_parse_risk_mappings(parsed_sections["risk_mappings"]),
            clearance_roles=_parse_clearance_roles(parsed_sections["clearance_roles"]),
            deliverable_templates=_parse_deliverable_templates(parsed_sections["deliverable_templates"]),
            worker_requirements=_parse_worker_requirements(parsed_sections["worker_requirements"]),
            signature_verified=signature_verified,
            section_hashes=tuple(section_hashes),
        )

        if ledger is not None and task_id is not None:
            _append_pack_event(ledger, loaded, task_id)
        return loaded

    def _verify_signature(self, manifest: PackManifest, sections: Mapping[str, Any]) -> bool:
        payload = _section_digest(sections)
        if manifest.signature:
            if self._signing_key is None:
                raise PackError("signing_key_required", "a signed domain pack requires a verification key")
            expected = hmac.new(self._signing_key, payload, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, manifest.signature):
                raise PackError("signature_mismatch", "the domain pack signature is invalid")
            return True
        if self._allow_unsigned:
            return False
        raise PackError("unsigned_pack", "the domain pack is unsigned and unsigned packs are not allowed")


def compute_pack_signature(pack_dir: str | Path, key: bytes) -> str:
    """Return the HMAC-SHA256 signature for a pack directory.

    This is the operator-facing signing helper: it canonicalises the eight
    section files exactly as :class:`PackLoader` verifies them.
    """

    root = Path(pack_dir)
    sections: dict[str, Any] = {}
    for name, file_name in SECTION_FILES.items():
        path = root / file_name
        if not path.is_file():
            raise PackError("missing_section", f"the domain pack is missing {file_name}")
        sections[name] = _load_yaml(path, file_name)
    return hmac.new(bytes(key), _section_digest(sections), hashlib.sha256).hexdigest()


def _decode_key(raw: str) -> bytes:
    try:
        candidate = bytes.fromhex(raw)
        if len(candidate) == 32:
            return candidate
    except ValueError:
        pass
    return raw.encode("utf-8")


def _load_yaml(path: Path, label: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise PackError("invalid_yaml", f"{label} is not valid YAML") from exc


def _append_pack_event(ledger: Any, pack: LoadedPack, task_id: str) -> None:
    event_type = "pack.loaded"
    status = "signed" if pack.signature_verified else "unsigned"
    payload = {
        "pack_id": pack.manifest.pack_id,
        "pack_version": pack.manifest.pack_version,
        "signature_status": status,
        "active_sections": list(pack.active_sections()),
        "provenance": {
            "source_ref": f"pack:{pack.manifest.pack_id}",
            "confidence": 1.0,
            "clearance": Clearance.internal.value,
            "taint": Taint.clean.value,
        },
    }
    ledger.append(build_event(
        event_type=event_type, task_id=task_id, actor_id="node.pack-loader", actor_type="service",
        payload_contract="LoadedPack", payload_version="1.0", payload=payload,
        clearance=Clearance.internal, idempotency=idempotency_key(event_type, task_id, pack.manifest.pack_id),
        sequence=len(ledger), previous_event_hash=ledger.head_hash,
    ))


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

def _parse_world_schema(value: Any) -> WorldSchema:
    source = _require_mapping(value, SECTION_FILES["world_schema"])
    raw_links = source.get("links") or []
    links: list[tuple[str, str, str]] = []
    for item in _require_sequence(raw_links, "world_schema.links"):
        link = _require_mapping(item, "world_schema.links[]")
        links.append((_text(link.get("id"), "link.id"), _text(link.get("from"), "link.from"), _text(link.get("to"), "link.to")))
    sources = source.get("authoritative_sources") or {}
    authoritative = tuple((_text(k, "authoritative_sources key"), _text(v, "authoritative_sources value")) for k, v in _require_mapping(sources, "authoritative_sources").items())
    return WorldSchema(objects=_text_tuple(source.get("objects"), "world_schema.objects"), links=tuple(links), authoritative_sources=authoritative)


def _parse_document_profiles(value: Any) -> tuple[DocumentProfile, ...]:
    source = _require_mapping(value, SECTION_FILES["document_profiles"])
    profiles: list[DocumentProfile] = []
    for item in _require_sequence(source.get("profiles"), "document_profiles.profiles"):
        profile = _require_mapping(item, "document_profiles.profiles[]")
        profiles.append(DocumentProfile(
            profile_id=_text(profile.get("id"), "profile.id"),
            formats=_text_tuple(profile.get("formats"), "profile.formats"),
            intake=_text(profile.get("intake"), "profile.intake"),
            authoritative_for=_text_tuple(profile.get("authoritative_for"), "profile.authoritative_for"),
            trust=str(profile.get("trust", "untrusted_until_provenance_gate")),
        ))
    return tuple(profiles)


_CHECK_KINDS = {"citation_required", "unit_check", "range_check", "cross_reference"}


def _parse_field_rules(value: Any) -> tuple[FieldRule, ...]:
    source = _require_mapping(value, SECTION_FILES["field_rules"])
    rules: list[FieldRule] = []
    for item in _require_sequence(source.get("rules"), "field_rules.rules"):
        rule = _require_mapping(item, "field_rules.rules[]")
        check = rule.get("check")
        if check is not None and check not in _CHECK_KINDS:
            raise PackError("invalid_rule_check", f"unsupported field rule check: {check!r}")
        rules.append(FieldRule(
            rule_id=_text(rule.get("id"), "rule.id"),
            applies_to=_text(rule.get("applies_to"), "rule.applies_to"),
            result=_text(rule.get("result"), "rule.result"),
            check=check,
            lower_bound=_optional_number(rule.get("lower_bound"), "rule.lower_bound"),
            upper_bound=_optional_number(rule.get("upper_bound"), "rule.upper_bound"),
            expected_unit=str(rule["expected_unit"]) if rule.get("expected_unit") else None,
            source_prefixes=_text_tuple(rule.get("source_prefixes"), "rule.source_prefixes"),
            tolerance=_optional_number(rule.get("tolerance"), "rule.tolerance") or 0.0,
        ))
    return tuple(rules)


def _parse_decision_types(value: Any) -> tuple[DecisionType, ...]:
    source = _require_mapping(value, SECTION_FILES["decision_types"])
    result: list[DecisionType] = []
    for item in _require_sequence(source.get("decision_types"), "decision_types.decision_types"):
        entry = _require_mapping(item, "decision_types[]")
        result.append(DecisionType(
            decision_type_id=_text(entry.get("id"), "decision_type.id"),
            required_features=_text_tuple(entry.get("required_features"), "decision_type.required_features"),
            minimum_authority=_text(entry.get("minimum_authority"), "decision_type.minimum_authority"),
            require_deviation_review=bool(entry.get("require_deviation_review", False)),
        ))
    return tuple(result)


def _parse_risk_mappings(value: Any) -> tuple[RiskMapping, ...]:
    source = _require_mapping(value, SECTION_FILES["risk_mappings"])
    actions = _require_mapping(source.get("actions"), "risk_mappings.actions")
    result: list[RiskMapping] = []
    for action_kind, item in actions.items():
        entry = _require_mapping(item, "risk_mappings.actions[]")
        result.append(RiskMapping(
            action_kind=_text(action_kind, "risk_mapping key"),
            risk_class=_text(entry.get("risk_class"), "risk_mapping.risk_class"),
            reversibility=_text(entry.get("reversibility"), "risk_mapping.reversibility"),
            autonomy_ceiling=_text(entry.get("autonomy_ceiling"), "risk_mapping.autonomy_ceiling"),
            required_human_authority=_text(entry.get("required_human_authority"), "risk_mapping.required_human_authority"),
        ))
    return tuple(result)


def _parse_clearance_roles(value: Any) -> tuple[ClearanceRole, ...]:
    source = _require_mapping(value, SECTION_FILES["clearance_roles"])
    roles = _require_mapping(source.get("roles"), "clearance_roles.roles")
    result: list[ClearanceRole] = []
    for role_id, item in roles.items():
        entry = _require_mapping(item, "clearance_roles.roles[]")
        result.append(ClearanceRole(
            role_id=_text(role_id, "clearance role key"),
            maximum_clearance=_text(entry.get("maximum_clearance"), "clearance_role.maximum_clearance"),
            may_review=_text_tuple(entry.get("may_review"), "clearance_role.may_review"),
            may_approve=_text_tuple(entry.get("may_approve"), "clearance_role.may_approve"),
        ))
    return tuple(result)


def _parse_deliverable_templates(value: Any) -> tuple[DeliverableTemplate, ...]:
    source = _require_mapping(value, SECTION_FILES["deliverable_templates"])
    result: list[DeliverableTemplate] = []
    for item in _require_sequence(source.get("templates"), "deliverable_templates.templates"):
        entry = _require_mapping(item, "deliverable_templates[]")
        labels = entry.get("section_labels") or {}
        bindings = entry.get("value_bindings") or []
        result.append(DeliverableTemplate(
            template_id=_text(entry.get("id"), "template.id"),
            version=_text(entry.get("version"), "template.version"),
            format=_text(entry.get("format"), "template.format"),
            required_sections=_text_tuple(entry.get("required_sections"), "template.required_sections"),
            labels=tuple((_text(k, "label key"), _text(v, "label value")) for k, v in _require_mapping(labels, "template.section_labels").items()),
            value_bindings=tuple(
                (_text(binding.get("name"), "binding.name"), bool(binding.get("required", False)))
                for binding in (
                    _require_mapping(item, "template.value_bindings[]")
                    for item in _require_sequence(bindings, "template.value_bindings")
                )
            ),
        ))
    return tuple(result)


def _parse_worker_requirements(value: Any) -> tuple[WorkerRequirements, ...]:
    source = _require_mapping(value, SECTION_FILES["worker_requirements"])
    workflows = _require_mapping(source.get("workflows"), "worker_requirements.workflows")
    result: list[WorkerRequirements] = []
    for workflow_id, item in workflows.items():
        entry = _require_mapping(item, "worker_requirements.workflows[]")
        result.append(WorkerRequirements(
            workflow_id=_text(workflow_id, "workflow key"),
            required_workers=_text_tuple(entry.get("required_workers"), "workflow.required_workers"),
            required_evidence=_text_tuple(entry.get("required_evidence"), "workflow.required_evidence"),
            completion_requires=_text_tuple(entry.get("completion_requires"), "workflow.completion_requires"),
            missing_verifier_result=str(entry.get("missing_verifier_result", "needs_review")),
        ))
    return tuple(result)


__all__ = [
    "ClearanceRole", "DecisionType", "DeliverableTemplate", "DocumentProfile", "FieldRule",
    "LoadedPack", "PackError", "PackLoader", "PackManifest", "RiskMapping", "SectionHash",
    "WorkerRequirements", "WorldSchema", "compute_pack_signature",
]
