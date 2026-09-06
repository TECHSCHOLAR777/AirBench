import hashlib
import json
import uuid
from typing import Any

NAMESPACE = uuid.UUID("9b2e7e0d-4b58-4b5c-9dc2-9d5d8a4b3f71")


def stable_id(kind: str, *parts: Any) -> str:
    """Create a deterministic UUID5 from canonical, length-bounded identity parts."""
    if not kind or len(kind) > 80:
        raise ValueError("kind must be 1..80 characters")
    encoded = json.dumps([kind, *parts], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > 4096:
        raise ValueError("stable identity input exceeds 4096 bytes")
    return str(uuid.uuid5(NAMESPACE, encoded))


def idempotency_key(operation: str, *identity: Any) -> str:
    if not operation:
        raise ValueError("operation is required")
    canonical = json.dumps([operation, *identity], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
