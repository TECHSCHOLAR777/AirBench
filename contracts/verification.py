"""Offline verification helpers for sealed ledger and projection exports."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _signature(content_hash: str, signing_key: bytes) -> str:
    return hmac.new(signing_key, content_hash.encode(), hashlib.sha256).hexdigest()


def verify_signed_export(export: dict[str, Any], signing_key: bytes) -> bool:
    """Verify a ledger event export without opening the database or using a network."""
    if (not signing_key or not isinstance(export, dict) or not isinstance(export.get("events"), list)
            or not isinstance(export.get("content_hash"), str)
            or not isinstance(export.get("signature"), str)):
        return False
    unsigned = {key: value for key, value in export.items() if key not in {"content_hash", "signature"}}
    content_hash = hashlib.sha256(_canonical(unsigned).encode()).hexdigest()
    return hmac.compare_digest(export.get("content_hash", ""), content_hash) and hmac.compare_digest(export.get("signature", ""), _signature(content_hash, signing_key))


def verify_projection_export(export: dict[str, Any], signing_key: bytes) -> bool:
    """Verify a projection export's hash and signature from its serialized fields."""
    required = {"kind", "clearance", "source_sequence", "source_head_hash", "event_ids", "records", "content_hash", "signature"}
    if (not signing_key or not isinstance(export, dict) or not required.issubset(export)
            or not isinstance(export["content_hash"], str)
            or not isinstance(export["signature"], str)):
        return False
    unsigned = {key: export[key] for key in ("kind", "clearance", "source_sequence", "source_head_hash", "event_ids", "records")}
    content_hash = hashlib.sha256(_canonical(unsigned).encode()).hexdigest()
    return hmac.compare_digest(export["content_hash"], content_hash) and hmac.compare_digest(export["signature"], _signature(content_hash, signing_key))
