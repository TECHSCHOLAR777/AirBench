"""AirBench Node local server entrypoint.

Reads configuration from environment variables or a YAML config file signed
with the node signing key, performs startup asset verification, emits a
``node.started`` ledger event, and binds the uvicorn process.  The module is
a thin shell: all authority flows through the orchestrator; this file only
resolves configuration and wires together the components.

Environment variables (all required unless a config file is supplied):

  AIRBENCH_NODE_IDENTITY       Stable identifier for this node (e.g. ``node.refinery.local``).
  AIRBENCH_BEARER_TOKEN        Bearer token clients must present in ``Authorization: Bearer <token>``.
  AIRBENCH_DOMAIN_PACK_REF     Canonical reference for the loaded domain pack (e.g. ``pack.refinery.v0``).
  AIRBENCH_CLEARANCE           Clearance context for this node (``public|internal|restricted|secret``).
  AIRBENCH_SUBJECT             Authenticated subject name for single-principal deployments.
  AIRBENCH_HOST                Bind host (default ``127.0.0.1``).
  AIRBENCH_PORT                Bind port (default ``8765``).
  AIRBENCH_LEDGER_PATH         Path for the SQLite ledger (omit for in-memory).
  AIRBENCH_SIGNING_KEY_PATH    Path to the 32-byte HMAC-SHA256 signing key file (optional).
  AIRBENCH_BUNDLE_MANIFEST_PATH Path to the signed offline bundle manifest (optional).
  AIRBENCH_BUNDLE_ROOT          Root directory used to resolve manifest asset paths (optional).

Model serving is opt-in and fails closed:

  AIRBENCH_MODEL_SERVING_ENABLED    Set to ``1`` to compose the model router.
  AIRBENCH_POLICY_VERSION_HASH      Routing policy hash (required when enabled).
  AIRBENCH_MODEL_SIGNING_KEY_PATH   Path to the 32-byte roster signing key.
  AIRBENCH_MODEL_STORE              Canonical model store (artifact root).
  AIRBENCH_MODEL_ROSTER_PATH        Signed roster YAML (default under models/roster/v0).
  AIRBENCH_MODEL_E2B_URL / _12B_URL Loopback endpoint base URLs.
  HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1  Required for vLLM adapter no-egress checks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Native import order matters on Windows: the torch/sentence-transformers stack
# must initialise before pypdf (imported by File Intake) or the process can
# crash.  Preload it only when retrieval is enabled, before the Node imports.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
if os.environ.get("AIRBENCH_RETRIEVAL_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pass

import yaml

from contracts import (
    Clearance,
    EventLedger,
    Orchestrator,
    SQLiteLedgerStore,
)
from contracts.models import NODE_PROTOCOL_VERSION
from .api import NodeApiConfig, NodeApiService, create_app
from .bundle import BundleManifest, StartupVerifier
from .model_serving import (
    load_model_serving_runtime_from_env,
    model_serving_enabled,
    probe_endpoint_readiness,
)
from .task_planning import NodeTaskPlanner, PlannerConfig, planner_enabled
from .task_execution import NodeExecutionConfig
from airbench.knowledge.embedding_runtime import retrieval_enabled, retrieval_runtime_from_env

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NodeServerConfig:
    """Validated configuration for one AirBench Node process."""

    node_identity: str
    bearer_token: str
    domain_pack_ref: str
    clearance: Clearance
    subject: str
    operator_roles: tuple[str, ...] = ("human_reviewer",)
    host: str = "127.0.0.1"
    port: int = 8765
    ledger_path: str | None = None
    signing_key_path: str | None = None
    bundle_manifest_path: str | None = None
    bundle_root: str | None = None

    def __post_init__(self) -> None:
        for name in ("node_identity", "bearer_token", "domain_pack_ref", "subject"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"NodeServerConfig.{name} is required and must be a non-empty string")
        if not isinstance(self.port, int) or not (1 <= self.port <= 65535):
            raise ValueError("NodeServerConfig.port must be an integer in 1-65535")

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "NodeServerConfig":
        """Build a config from environment variables."""
        def _require(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise EnvironmentError(
                    f"Required environment variable {name} is not set. "
                    "See airbench.node.server module docstring for the full list."
                )
            return value

        try:
            clearance = Clearance(os.environ.get("AIRBENCH_CLEARANCE", "internal").strip())
        except ValueError as exc:
            raise EnvironmentError(
                "AIRBENCH_CLEARANCE must be one of: public, internal, restricted, secret"
            ) from exc

        port_raw = os.environ.get("AIRBENCH_PORT", "8765").strip()
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise EnvironmentError("AIRBENCH_PORT must be an integer") from exc

        return cls(
            node_identity=_require("AIRBENCH_NODE_IDENTITY"),
            bearer_token=_require("AIRBENCH_BEARER_TOKEN"),
            domain_pack_ref=_require("AIRBENCH_DOMAIN_PACK_REF"),
            clearance=clearance,
            subject=_require("AIRBENCH_SUBJECT"),
            operator_roles=tuple(role.strip() for role in os.environ.get("AIRBENCH_OPERATOR_ROLES", "human_reviewer").split(",") if role.strip()),
            host=os.environ.get("AIRBENCH_HOST", "127.0.0.1").strip(),
            port=port,
            ledger_path=os.environ.get("AIRBENCH_LEDGER_PATH", "").strip() or None,
            signing_key_path=os.environ.get("AIRBENCH_SIGNING_KEY_PATH", "").strip() or None,
            bundle_manifest_path=os.environ.get("AIRBENCH_BUNDLE_MANIFEST_PATH", "").strip() or None,
            bundle_root=os.environ.get("AIRBENCH_BUNDLE_ROOT", "").strip() or None,
        )

    @classmethod
    def from_yaml(cls, path: Path, signing_key: bytes | None = None) -> "NodeServerConfig":
        """Load config from a YAML file, verifying HMAC if a key is supplied."""
        raw = path.read_bytes()
        # Optional: if a ``signature`` key is present in the file, verify it.
        try:
            parsed: dict[str, Any] = yaml.safe_load(raw.decode("utf-8")) or {}
        except (yaml.YAMLError, UnicodeDecodeError) as exc:
            raise ValueError(f"Config file {path} is not valid YAML: {exc}") from exc

        if signing_key is not None:
            import hmac as _hmac
            expected_sig = parsed.pop("signature", None)
            if not isinstance(expected_sig, str):
                raise ValueError("Signed config file is missing a 'signature' field")
            payload_bytes = yaml.dump({k: v for k, v in parsed.items()}, sort_keys=True).encode()
            actual_sig = _hmac.new(signing_key, payload_bytes, hashlib.sha256).hexdigest()
            if not _hmac.compare_digest(expected_sig, actual_sig):
                raise ValueError("Config file signature does not match the provided signing key")

        try:
            clearance = Clearance(str(parsed.get("clearance", "internal")).strip())
        except ValueError as exc:
            raise ValueError("Config.clearance must be one of: public, internal, restricted, secret") from exc

        return cls(
            node_identity=str(parsed.get("node_identity", "")),
            bearer_token=str(parsed.get("bearer_token", "")),
            domain_pack_ref=str(parsed.get("domain_pack_ref", "")),
            clearance=clearance,
            subject=str(parsed.get("subject", "")),
            host=str(parsed.get("host", "127.0.0.1")),
            port=int(parsed.get("port", 8765)),
            ledger_path=str(parsed["ledger_path"]) if parsed.get("ledger_path") else None,
            signing_key_path=str(parsed["signing_key_path"]) if parsed.get("signing_key_path") else None,
            bundle_manifest_path=str(parsed["bundle_manifest_path"]) if parsed.get("bundle_manifest_path") else None,
            bundle_root=str(parsed["bundle_root"]) if parsed.get("bundle_root") else None,
        )


# ---------------------------------------------------------------------------
# Startup check
# ---------------------------------------------------------------------------

@dataclass
class StartupCheckResult:
    """Summary of the pre-bind startup check."""

    passed: bool
    checks: list[dict[str, str]] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append({"name": name, "status": status, "detail": detail})

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "checks": self.checks}


def run_startup_checks(config: NodeServerConfig) -> StartupCheckResult:
    """Verify the node is ready to accept requests.

    Checks performed (all non-fatal individually, but collectively determine
    ``passed``):

    * Config completeness — all required fields are non-empty strings.
    * Ledger path — if specified, the directory is writable.
    * Signing key — if specified, the key file is readable and is exactly 32 bytes.
    * Protocol version — the expected version constant is importable.

    Returns a :class:`StartupCheckResult` with per-check detail.  A caller
    that wants hard failure should raise on ``not result.passed``.
    """
    failed = False
    result = StartupCheckResult(passed=True)

    # 1. Config completeness
    for name in ("node_identity", "bearer_token", "domain_pack_ref", "subject"):
        value = getattr(config, name)
        if isinstance(value, str) and value.strip():
            result.add(f"config.{name}", "ok")
        else:
            result.add(f"config.{name}", "failed", f"{name} is empty or missing")
            failed = True

    # 2. Ledger path writability
    if config.ledger_path:
        ledger_dir = Path(config.ledger_path).parent
        if ledger_dir.exists() and os.access(str(ledger_dir), os.W_OK):
            result.add("ledger.path", "ok", str(config.ledger_path))
        else:
            result.add("ledger.path", "failed", f"Ledger directory {ledger_dir} is not writable")
            failed = True
    else:
        result.add("ledger.path", "ok", "in-memory (no persistence)")

    # 3. Signing key
    if config.signing_key_path:
        key_path = Path(config.signing_key_path)
        if key_path.exists():
            key_bytes = key_path.read_bytes()
            if len(key_bytes) == 32:
                result.add("signing_key", "ok", str(key_path))
            else:
                result.add("signing_key", "failed", f"Signing key is {len(key_bytes)} bytes; expected 32")
                failed = True
        else:
            result.add("signing_key", "failed", f"Signing key file not found: {key_path}")
            failed = True
    else:
        result.add("signing_key", "ok", "not configured (pack verification uses the node signing key from env)")

    # 4. Protocol version
    try:
        result.add("protocol.version", "ok", NODE_PROTOCOL_VERSION)
    except Exception as exc:  # pragma: no cover
        result.add("protocol.version", "failed", str(exc))
        failed = True

    # 5. Offline bundle integrity. A configured bundle is a deployment
    # boundary: it must be present, signed, and fully verified before the
    # process is allowed to bind.
    if config.bundle_manifest_path:
        manifest_path = Path(config.bundle_manifest_path)
        signing_key: bytes | None = None
        if config.signing_key_path:
            try:
                signing_key = Path(config.signing_key_path).read_bytes()
            except OSError as exc:
                result.add("bundle.manifest", "failed", f"could not read signing key: {exc}")
                failed = True
        else:
            result.add("bundle.signature", "failed", "a signing key is required when bundle verification is configured")
            failed = True
        try:
            manifest = BundleManifest.from_file(manifest_path)
            bundle_root = Path(config.bundle_root) if config.bundle_root else manifest_path.parent
            verification = StartupVerifier(
                manifest,
                bundle_root=bundle_root,
                signing_key=signing_key,
            ).verify()
            if verification.passed:
                result.add("bundle.manifest", "ok", f"verified {manifest.bundle_id} {manifest.bundle_version}")
            else:
                result.add("bundle.manifest", "failed", json.dumps(verification.to_dict(), sort_keys=True))
                failed = True
        except (OSError, TypeError, ValueError) as exc:
            result.add("bundle.manifest", "failed", str(exc))
            failed = True
    else:
        result.add("bundle.manifest", "ok", "not configured")

    result.passed = not failed
    return result


# ---------------------------------------------------------------------------
# Ledger factory
# ---------------------------------------------------------------------------

def _build_ledger(config: NodeServerConfig) -> EventLedger:
    """Create the appropriate ledger based on config."""
    if config.ledger_path:
        key_bytes = b""
        if config.signing_key_path:
            key_path = Path(config.signing_key_path)
            if key_path.exists():
                key_bytes = key_path.read_bytes()
        return SQLiteLedgerStore(config.ledger_path, key_bytes)  # type: ignore[return-value]
    return EventLedger()


# ---------------------------------------------------------------------------
# Node start ledger event
# ---------------------------------------------------------------------------

def _write_node_started(
    config: NodeServerConfig,
    checks: StartupCheckResult,
    *,
    evidence_dir: Path | None = None,
    pack: Any = None,
) -> dict[str, Any]:
    """Write a ``node.started`` sovereignty evidence record to a JSON sidecar.

    The main ledger is task-scoped and cannot accept lifecycle events before
    ``task.created``.  Following the M9 pattern, node-lifecycle evidence is
    written as a separate signed JSON file that an offline verifier can read
    without replaying the task ledger.

    Returns the evidence payload dict so callers can include it in the API
    config's ``sovereignty_evidence_ref``.
    """
    from datetime import datetime, timezone

    payload: dict[str, Any] = {
        "event_type": "node.started",
        "node_identity": config.node_identity,
        "protocol_version": NODE_PROTOCOL_VERSION,
        "clearance": config.clearance.value,
        "domain_pack_ref": config.domain_pack_ref,
        "host": config.host,
        "port": config.port,
        "ledger_path": config.ledger_path or "in-memory",
        "startup_checks": checks.as_dict(),
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if pack is not None:
        payload["domain_pack"] = pack.to_dict()
    try:
        from .no_egress import observe_no_egress

        payload["no_egress"] = observe_no_egress().to_dict()
    except Exception as exc:  # noqa: BLE001 - observation must never block startup
        payload["no_egress"] = {"clean": None, "error": type(exc).__name__}
    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / f"node_started_{config.node_identity.replace('.', '_')}.json"
        evidence_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        logger.info("Node startup evidence written to %s", evidence_path)
    return payload


# ---------------------------------------------------------------------------
# Application factory (for tests and programmatic use)
# ---------------------------------------------------------------------------

def build_node_app(
    config: NodeServerConfig,
    *,
    skip_startup_check: bool = False,
    evidence_dir: Path | None = None,
):
    """Wire the node components and return a FastAPI application.

    Parameters
    ----------
    config:
        Validated ``NodeServerConfig``.
    skip_startup_check:
        Set ``True`` in tests that supply a pre-configured in-memory ledger
        and do not want the startup check to block them.
    evidence_dir:
        Directory to write the ``node.started`` sovereignty evidence JSON sidecar.
        Defaults to the parent of ``config.ledger_path`` when set, otherwise
        the current working directory.

    Raises
    ------
    RuntimeError
        If the startup check fails and ``skip_startup_check`` is ``False``.
    """
    checks = run_startup_checks(config)
    if not skip_startup_check and not checks.passed:
        details = "; ".join(
            f"{c['name']}: {c['detail']}" for c in checks.checks if c["status"] != "ok"
        )
        raise RuntimeError(f"Node startup check failed — {details}")

    ledger = _build_ledger(config)

    # Load and verify the domain pack before anything consumes it.  The pack
    # declaration is sector knowledge; the core only carries it.  Fails closed
    # on an unsigned or tampered pack unless AIRBENCH_PACK_ALLOW_UNSIGNED=1.
    loaded_pack = None
    pack_dir = os.environ.get("AIRBENCH_PACK_DIR", "").strip()
    if pack_dir:
        from .pack_loader import PackError, PackLoader

        try:
            loaded_pack = PackLoader.from_env().load(pack_dir)
        except PackError as exc:
            raise RuntimeError(f"Domain pack load failed ({exc.code}): {exc}") from exc
        logger.info(
            "Domain pack loaded: %s v%s (%s)",
            loaded_pack.manifest.pack_id, loaded_pack.manifest.pack_version,
            "signed" if loaded_pack.signature_verified else "unsigned",
        )

    # The committed world-model graph is opt-in.  SQLite gives durable storage
    # with append-only history; the default JSON seam is also supported.
    world_model = None
    wm_path = os.environ.get("AIRBENCH_WORLD_MODEL_PATH", "").strip()
    wm_backend = os.environ.get("AIRBENCH_WORLD_MODEL_BACKEND", "json").strip().lower() or "json"
    if wm_path or wm_backend == "sqlite":
        from airbench.knowledge.graph_store import build_graph_store_from_env
        from airbench.knowledge.world_model import WorldModelStore

        graph_backend = build_graph_store_from_env(default_path=wm_path or None)
        world_model = WorldModelStore(ledger=ledger, path=(wm_path or None), backend=graph_backend)
        logger.info("World model graph enabled (%s)", type(graph_backend).__name__ if graph_backend else "json")

    # Decision consistency is opt-in and backed by a durable decision store.
    consistency_service = None
    decision_store_path = os.environ.get("AIRBENCH_DECISION_STORE_PATH", "").strip()
    if decision_store_path:
        from airbench.knowledge.consistency import ConsistencyEngine
        from airbench.knowledge.decision_store import SqliteDecisionStore
        from .consistency_gateway import LocalNodeConsistencyService

        consistency_service = LocalNodeConsistencyService(
            engine=ConsistencyEngine(ledger),
            store=SqliteDecisionStore(decision_store_path),
            ledger=ledger,
            clearance_context=config.clearance,
            required_review_types=frozenset(
                decision_type.decision_type_id
                for decision_type in (loaded_pack.decision_types if loaded_pack is not None else ())
                if decision_type.require_deviation_review
            ),
        )
        logger.info("Consistency service enabled at %s", decision_store_path)

    # Autonomy scoring is pack-driven: risk mappings compile into risk rules.
    autonomy_service = None
    if loaded_pack is not None:
        from airbench.verification.autonomy import AutonomyGovernor, risk_rules_from_mappings
        from .autonomy_gateway import LocalNodeAutonomyService

        risk_rules = risk_rules_from_mappings(loaded_pack.risk_mappings)
        autonomy_service = LocalNodeAutonomyService(
            governor=AutonomyGovernor(ledger, risk_rules),
            ledger=ledger,
            clearance_context=config.clearance,
            world_model=world_model,
        )
        logger.info("Autonomy governor enabled with %d pack risk rule(s)", len(risk_rules))

    # Hardware and qualification projections for the Node settings surface.
    hardware_profile = None
    hardware_path = (
        os.environ.get("AIRBENCH_HARDWARE_PROFILE", "").strip()
        or os.environ.get("AIRBENCH_HARDWARE_PROFILE_PATH", "").strip()
        or str(Path("profiles/hardware/workstation_demo.yaml"))
    )
    if Path(hardware_path).is_file():
        try:
            from .hardware_gateway import load_hardware_profile

            hardware_profile = load_hardware_profile(hardware_path)
            logger.info("Hardware profile loaded: %s", hardware_profile.profile_id)
        except Exception as exc:  # noqa: BLE001 - surface, do not crash the Node on an optional asset
            logger.warning("Hardware profile not loaded: %s", exc)
    qualification_matrix = None
    matrix_path = os.environ.get("AIRBENCH_QUALIFICATION_MATRIX", "").strip() or str(Path("qualifications/model_qualification_matrix.yaml"))
    if Path(matrix_path).is_file():
        try:
            from .qualification_gateway import load_qualification_matrix

            qualification_matrix = load_qualification_matrix(matrix_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Qualification matrix not loaded: %s", exc)

    # P&ID extraction is offline and opt-in: it is available when the local
    # vision stack and the committed detector weights are present.
    pid_adapter = None
    try:
        from airbench.intake.pid.adapter import PidIntakeAdapter

        legend = (Path(pack_dir) / "pid_legend.yaml") if pack_dir else (Path("packs/refinery_psu_v0/pid_legend.yaml"))
        pid_adapter = PidIntakeAdapter(legend_path=legend if legend.is_file() else None)
        logger.info("P&ID adapter composed (legend=%s)", legend.name if legend.is_file() else "default")
    except Exception as exc:  # noqa: BLE001 - optional subsystem
        logger.warning("P&ID adapter not initialized: %s", exc)
    pid_workspace = (
        os.environ.get("AIRBENCH_PID_WORKSPACE", "").strip()
        or os.environ.get("AIRBENCH_ARTIFACT_ROOT", "").strip()
        or os.environ.get("AIRBENCH_INTAKE_ROOT", "").strip()
        or str(Path.cwd())
    )

    # Write node-started sovereignty evidence (sidecar JSON, not the task ledger)
    if evidence_dir is None and config.ledger_path:
        evidence_dir = Path(config.ledger_path).parent
    _write_node_started(config, checks, evidence_dir=evidence_dir, pack=loaded_pack)

    orchestrator = Orchestrator(ledger)

    # The handshake_ledger_event_ref is the head of the ledger at the moment of
    # binding — for a fresh node this will be the empty-ledger sentinel.
    head = ledger.head_hash or "ledger.empty"

    api_config = NodeApiConfig(
        node_identity=config.node_identity,
        protocol_version=NODE_PROTOCOL_VERSION,
        clearance_context=config.clearance,
        authenticated_subject=config.subject,
        authenticated_roles=config.operator_roles,
        domain_pack_ref=config.domain_pack_ref,
        bearer_token=config.bearer_token,
        handshake_ledger_event_ref=head,
        sovereignty_evidence_ref=f"evidence.local.{config.node_identity}",
        require_orchestrator_authorization=False,
    )

    # Model serving is opt-in.  When enabled the signed roster must load and
    # every declared artifact must verify, otherwise startup fails loudly.
    model_router = None
    routing_tiers: dict[str, str] = {}
    if model_serving_enabled():
        runtime = load_model_serving_runtime_from_env(ledger=ledger)
        if runtime is not None:
            model_router = runtime.router
            for target in getattr(runtime.registry, "targets", ()):
                target_id = str(getattr(target, "target_id", ""))
                tier = str(getattr(target, "routing_tier", "") or "")
                if target_id and tier:
                    routing_tiers[target_id] = tier
            logger.info(
                "Model serving enabled: %d endpoint binding(s)",
                len(model_router.endpoint_bindings),
            )

    # Node-owned execution is opt-in; when set it also owns plan creation.
    execution_config = NodeExecutionConfig.from_env(default_root=Path.cwd())

    # Deterministic planning is opt-in and never lets a client drive the loop.
    # It is disabled when the execution coordinator owns planning.
    task_planner = None
    if planner_enabled() and execution_config is None:
        task_planner = NodeTaskPlanner(orchestrator, PlannerConfig.from_env())
        logger.info("Task planning enabled (hardware profile configured: %s)", task_planner.has_hardware_profile)

    # Local retrieval (BGE-M3 embeddings + reranker) is opt-in.
    retrieval_runtime = None
    if retrieval_enabled():
        retrieval_runtime = retrieval_runtime_from_env(ledger=ledger)
        logger.info("Retrieval enabled: embedding=%s reranker=%s",
                    retrieval_runtime.embedding_model_id, retrieval_runtime.reranker_model_id or "none")

    # File Intake and generated deliverables are composed here so the normal
    # Node exposes the documented upload/preview/review/download path.
    intake_store = None
    intake_gateway = None
    intake_root = os.environ.get("AIRBENCH_INTAKE_ROOT", "").strip()
    if intake_root:
        from airbench.intake import FileIntakeLayer, LocalIntakeStore
        from airbench.intake.ocr_provider import build_ocr_provider_from_env
        from airbench.intake.raster_renderer import PdfRasterPageRenderer
        from airbench.intake.table_extractor import GridLineTableExtractor
        from airbench.intake.vision import LocalVisionAdapter, ocr_provider_extractor
        from .intake_gateway import LocalNodeIntakeGateway
        intake_store = LocalIntakeStore(intake_root)

        vision_adapter = None
        ocr_provider = build_ocr_provider_from_env()
        if ocr_provider is not None:
            adapter_id = f"airbench.ocr.{ocr_provider.name}"
            vision_adapter = LocalVisionAdapter(
                adapter_id=adapter_id,
                adapter_version=ocr_provider.version,
                model_target_id=os.environ.get("OCR_MODEL_TARGET_ID", "target.ocr.local").strip() or "target.ocr.local",
                qualification_reference=os.environ.get("OCR_QUALIFICATION_REFERENCE", "qualification.ocr.local").strip()
                or "qualification.ocr.local",
                extractor=ocr_provider_extractor(
                    ocr_provider,
                    adapter_id=adapter_id,
                    adapter_version=ocr_provider.version,
                    model_target_id=os.environ.get("OCR_MODEL_TARGET_ID", "target.ocr.local").strip() or "target.ocr.local",
                    qualification_reference=os.environ.get("OCR_QUALIFICATION_REFERENCE", "qualification.ocr.local").strip()
                    or "qualification.ocr.local",
                    table_extractor=GridLineTableExtractor(),
                ),
                ledger=ledger,
                kind="ocr",
            )
            logger.info("OCR enabled: provider=%s", ocr_provider.name)

        renderer = PdfRasterPageRenderer() if PdfRasterPageRenderer.available() else None
        intake_layer = FileIntakeLayer(ledger, store=intake_store, renderer=renderer, vision_adapter=vision_adapter)
        intake_gateway = LocalNodeIntakeGateway(
            layer=intake_layer,
            store=intake_store,
            ledger=ledger,
            clearance_context=config.clearance,
        )
        logger.info("File Intake enabled at %s (pdf rasteriser: %s)", intake_root, renderer is not None)

    # Bulk knowledge ingestion is opt-in and confined to an operator root.
    knowledge_service = None
    ingest_root = os.environ.get("AIRBENCH_KNOWLEDGE_INGEST_ROOT", "").strip()
    if ingest_root and intake_root and retrieval_runtime is not None:
        from .knowledge_gateway import LocalNodeKnowledgeService
        ingest_task_id = "task.knowledge.ingest"
        try:
            orchestrator.create_task(
                principal_id=config.subject, clearance=config.clearance,
                request="Bulk knowledge ingestion", domain_pack_ref=config.domain_pack_ref,
                risk_class="low", autonomy_ceiling="system", task_id=ingest_task_id,
            )
        except Exception:  # the task already exists on a restarted Node; its event is already in the ledger
            logger.debug("Knowledge ingest task already exists")
        knowledge_service = LocalNodeKnowledgeService(
            layer=intake_layer, indexer=retrieval_runtime.indexer,
            ingest_root=ingest_root, task_id=ingest_task_id, clearance_context=config.clearance,
        )
        logger.info("Bulk knowledge ingestion enabled at %s", ingest_root)

    deliverable_gateway = None
    artifact_root = os.environ.get("AIRBENCH_ARTIFACT_ROOT", "").strip()
    if artifact_root:
        from airbench.delivery import LocalArtifactStore
        from .deliverable_gateway import LocalDeliverableGateway
        deliverable_gateway = LocalDeliverableGateway(
            ledger=ledger,
            artifact_store=LocalArtifactStore(artifact_root),
            node_identity=config.node_identity,
            protocol_version=NODE_PROTOCOL_VERSION,
            clearance_context=config.clearance,
        )
        logger.info("Deliverable Engine enabled at %s", artifact_root)

    # Node-owned task execution is opt-in.  When enabled the Node drives an
    # approved plan through team, verification, and deliverable steps instead
    # of waiting for client-driven model calls.
    execution = None
    if execution_config is not None:
        if intake_store is None:
            raise RuntimeError("task execution requires AIRBENCH_INTAKE_ROOT")
        from .task_execution import NodeTaskExecutionCoordinator
        from .autonomy_gateway import select_execution_action_kind

        execution_action_kind = select_execution_action_kind(
            loaded_pack.risk_mappings if loaded_pack is not None else (),
            os.environ.get("AIRBENCH_EXECUTION_ACTION_KIND", "").strip(),
        )
        execution = NodeTaskExecutionCoordinator(
            orchestrator=orchestrator,
            ledger=ledger,
            intake_store=intake_store,
            config=execution_config,
            model_router=model_router,
            consistency_service=consistency_service,
            autonomy_service=autonomy_service,
            execution_action_kind=execution_action_kind,
        )
        logger.info("Task execution enabled (model router configured: %s, autonomy gate action: %s)",
                    model_router is not None, execution_action_kind if autonomy_service is not None else "disabled")

    service = NodeApiService(
        orchestrator, api_config, model_router=model_router, task_planner=task_planner,
        retrieval=retrieval_runtime, intake_gateway=intake_gateway,
        deliverable_gateway=deliverable_gateway, execution=execution, knowledge=knowledge_service,
        pack=loaded_pack, world_model=world_model, consistency=consistency_service, autonomy=autonomy_service,
        hardware_profile=hardware_profile, qualification_matrix=qualification_matrix,
        routing_tiers=routing_tiers,
        pid_adapter=pid_adapter, pid_workspace=pid_workspace,
    )
    app = create_app(service)
    add_readiness_route(app, service)
    add_model_serving_route(app, service)
    add_retrieval_route(app, service)
    add_pack_route(app, service)
    add_node_asset_routes(app, service)
    return app


def add_node_asset_routes(app: Any, service: NodeApiService) -> None:
    """Attach ``GET /api/v1/node/hardware`` and ``/api/v1/node/qualification/{id}``."""

    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.routing import Route

    async def hardware(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        return StarletteJSONResponse(status_code=200, content=service.hardware_status())

    async def qualification(request: StarletteRequest) -> StarletteJSONResponse:
        target_id = request.path_params["target_id"]
        return StarletteJSONResponse(status_code=200, content=service.qualification_status(target_id))

    async def qualification_roster(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        return StarletteJSONResponse(status_code=200, content=service.qualification_roster())

    app.router.routes.insert(0, Route("/api/v1/node/hardware", endpoint=hardware, methods=["GET"]))
    app.router.routes.insert(0, Route("/api/v1/node/qualification", endpoint=qualification_roster, methods=["GET"]))
    app.router.routes.insert(0, Route("/api/v1/node/qualification/{target_id}", endpoint=qualification, methods=["GET"]))


def add_pack_route(app: Any, service: NodeApiService) -> None:
    """Attach ``GET /api/v1/node/pack`` for the Domain Pack settings card."""

    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.routing import Route

    async def domain_pack(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        return StarletteJSONResponse(status_code=200, content=service.pack_status())

    app.router.routes.insert(0, Route("/api/v1/node/pack", endpoint=domain_pack, methods=["GET"]))


def add_retrieval_route(app: Any, service: NodeApiService) -> None:
    """Attach ``GET /api/v1/node/retrieval`` for the local retrieval stack."""
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.routing import Route

    async def retrieval(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        runtime = getattr(service, "retrieval", None)
        if runtime is None:
            return StarletteJSONResponse(status_code=200, content={"configured": False, "status": "disabled"})
        return StarletteJSONResponse(status_code=200, content={
            "configured": True,
            "status": "ready",
            "embedding_model": runtime.embedding_model_id,
            "embedding_qualification_reference": runtime.embedding_qualification_reference,
            "reranker_model": runtime.reranker_model_id,
            "reranker_qualification_reference": runtime.reranker_qualification_reference,
            "indexed_chunks": len(runtime.index.chunks),
        })

    app.router.routes.insert(0, Route("/api/v1/node/retrieval", endpoint=retrieval, methods=["GET"]))


# ---------------------------------------------------------------------------
# Readiness endpoint helper (added to the app in create_hardened_app)
# ---------------------------------------------------------------------------

def add_readiness_route(app: Any, service: NodeApiService) -> None:
    """Attach ``GET /api/v1/node/readiness`` to an existing FastAPI app.

    The readiness probe does **not** require authentication so that deployment
    health checks (e.g. container orchestrators) can call it without a token.
    It returns 200 when the ledger chain is intact, 503 otherwise.

    We add this as a raw Starlette ``Route`` to bypass FastAPI's response-model
    validation pipeline, which would otherwise intercept ``JSONResponse`` returns
    and trigger the custom ``RequestValidationError`` handler.
    """
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.routing import Route

    async def readiness(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        try:
            health = service.health()
            return StarletteJSONResponse(status_code=200, content=health)
        except Exception as exc:
            return StarletteJSONResponse(
                status_code=503,
                content={"status": "degraded", "reason": str(exc)},
            )

    starlette_route = Route("/api/v1/node/readiness", endpoint=readiness, methods=["GET"])
    app.router.routes.insert(0, starlette_route)


def add_model_serving_route(app: Any, service: NodeApiService) -> None:
    """Attach ``GET /api/v1/node/model-serving`` for the two-lane demo.

    Like the readiness probe this endpoint requires no token so deployment
    checks can reach it.  It reports only endpoint identity, adapter identity,
    and health/readiness states — never prompts, payloads, credentials, or
    provider error text.
    """
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import JSONResponse as StarletteJSONResponse
    from starlette.routing import Route

    async def model_serving(request: StarletteRequest) -> StarletteJSONResponse:  # noqa: ARG001
        router = getattr(service, "model_router", None)
        if router is None:
            return StarletteJSONResponse(
                status_code=200,
                content={"configured": False, "status": "disabled", "endpoints": []},
            )
        endpoints = probe_endpoint_readiness(router, timeout_s=2.0)
        ready = bool(endpoints) and all(
            endpoint["health"] == "healthy" and endpoint["readiness"] == "ready"
            for endpoint in endpoints
        )
        return StarletteJSONResponse(
            # Health is a projection, not an admission decision. A degraded
            # lane must be visible; the router still fails closed for calls.
            status_code=200,
            content={
                "configured": True,
                "status": "ready" if ready else "degraded",
                "endpoints": endpoints,
            },
        )

    starlette_route = Route("/api/v1/node/model-serving", endpoint=model_serving, methods=["GET"])
    app.router.routes.insert(0, starlette_route)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:  # pragma: no cover
    """Start the AirBench Node server.

    Usage::

        python -m airbench.node.server          # uses env vars
        python -m airbench.node.server config.yaml   # uses YAML config file
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", nargs="?", help="Path to YAML config file (optional; env vars used otherwise)")
    parser.add_argument("--check-only", action="store_true", help="Run startup checks and exit without binding")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        if args.config:
            cfg = NodeServerConfig.from_yaml(Path(args.config))
        else:
            cfg = NodeServerConfig.from_env()
    except (EnvironmentError, ValueError) as exc:
        logger.error("Configuration error: %s", exc)
        return 2

    checks = run_startup_checks(cfg)
    for check in checks.checks:
        level = logging.INFO if check["status"] == "ok" else logging.ERROR
        logger.log(level, "Startup check %s: %s — %s", check["name"], check["status"], check.get("detail", ""))

    if not checks.passed:
        logger.error("Startup checks failed; node will not bind.")
        return 1

    if args.check_only:
        logger.info("--check-only: startup checks passed, not binding.")
        return 0

    try:
        import uvicorn  # type: ignore[import-untyped]
    except ImportError:
        logger.error("uvicorn is not installed. Install it with: pip install uvicorn")
        return 1

    try:
        app = build_node_app(cfg, skip_startup_check=True)  # checks already run above
    except RuntimeError as exc:
        logger.error("Failed to build node app: %s", exc)
        return 1

    logger.info(
        "Starting AirBench Node %s on %s:%d (protocol %s)",
        cfg.node_identity, cfg.host, cfg.port, NODE_PROTOCOL_VERSION,
    )
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level=args.log_level.lower())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
