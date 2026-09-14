"""Read qualification certificates for a model target.

The qualification matrix is authored/measured by the operator.  This reader
never treats a placeholder certificate as qualified: any ``PENDING:`` or
``REPLACE_WITH_MEASURED:`` value, or a missing signature, keeps the target
unqualified or pending.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml


class QualificationReadError(RuntimeError):
    """The qualification matrix could not be read."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def load_qualification_matrix(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise QualificationReadError("matrix_unreadable", "the qualification matrix could not be read") from exc
    if not isinstance(payload, Mapping):
        raise QualificationReadError("matrix_invalid", "the qualification matrix must be a mapping")
    return dict(payload)


def _flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [item for entry in value.values() for item in _flatten_strings(entry)]
    if isinstance(value, (list, tuple)):
        return [item for entry in value for item in _flatten_strings(entry)]
    return []


def _certificate_status(certificate: Mapping[str, Any]) -> str:
    placeholders = [text for text in _flatten_strings(certificate) if "PENDING:" in text or "REPLACE_WITH_MEASURED:" in text]
    if placeholders:
        return "pending"
    if not certificate.get("signature"):
        return "unqualified"
    return "qualified"


def qualification_status(
    matrix: Mapping[str, Any], target_id: str, routing_tiers: Mapping[str, str] | None = None
) -> dict[str, Any]:
    certificates = [item for item in matrix.get("certificates", []) if str(item.get("target_id", "")) == target_id]
    if not certificates:
        return {"target_id": target_id, "status": "not_listed", "certificates": []}
    entries = [
        {
            "certificate_id": certificate.get("certificate_id"),
            "worker_role": certificate.get("worker_role"),
            "status": _certificate_status(certificate),
            "expires_at": certificate.get("expires_at"),
        }
        for certificate in certificates
    ]
    statuses = {entry["status"] for entry in entries}
    if statuses == {"qualified"}:
        overall = "qualified"
    elif "pending" in statuses:
        overall = "pending"
    else:
        overall = "unqualified"
    result: dict[str, Any] = {
        "target_id": target_id,
        "status": overall,
        "certificates": entries,
        # The routing tier is declared by the signed model roster, not by the
        # qualification certificate. It is projection metadata only and never
        # changes the qualification verdict above.
        "routing_tier": (routing_tiers or {}).get(target_id),
        "measurement_pending": overall == "pending",
    }
    return result


def qualification_roster(
    matrix: Mapping[str, Any], routing_tiers: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Return every declared target and its qualification status in one call.

    This is the Node-authoritative roster the desktop renders; the desktop must
    not hardcode the target list.
    """
    seen: list[str] = []
    for certificate in matrix.get("certificates", []):
        target_id = str(certificate.get("target_id", ""))
        if target_id and target_id not in seen:
            seen.append(target_id)
    targets = [qualification_status(matrix, target_id, routing_tiers) for target_id in seen]
    return {"count": len(targets), "targets": targets}


__all__ = ["QualificationReadError", "load_qualification_matrix", "qualification_roster", "qualification_status"]
