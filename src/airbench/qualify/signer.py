"""HMAC-SHA256 signing for qualification certificates."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping


class CertificateError(RuntimeError):
    """A certificate could not be signed or verified."""


def canonical_payload(certificate: Mapping[str, Any]) -> bytes:
    body = {key: value for key, value in certificate.items() if key != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def sign_certificate(certificate: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    if not key:
        raise CertificateError("a non-empty signing key is required")
    signature = hmac.new(bytes(key), canonical_payload(certificate), hashlib.sha256).hexdigest()
    return {**certificate, "signature": signature}


def verify_certificate(certificate: Mapping[str, Any], key: bytes) -> bool:
    signature = certificate.get("signature")
    if not signature or not key:
        return False
    expected = hmac.new(bytes(key), canonical_payload(certificate), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(signature), expected)


__all__ = ["CertificateError", "canonical_payload", "sign_certificate", "verify_certificate"]
