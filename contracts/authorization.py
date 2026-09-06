"""Local principal, clearance, pack, and policy authorization checks."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from .models import Clearance


class AuthorizationError(ValueError):
    """A request exceeds the resolved principal or deployment envelope."""


@dataclass(frozen=True, slots=True)
class PrincipalRecord:
    principal_id: str
    clearance: Clearance
    allowed_evidence_scope: frozenset[str]
    permitted_tools: frozenset[str]
    allowed_risk_classes: frozenset[str]
    resource_limits: dict[str, int]


@dataclass(frozen=True, slots=True)
class SignedReference:
    reference: str
    digest: str
    signature: str


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    principal_id: str
    clearance: Clearance
    pack: SignedReference
    policy: SignedReference


class AuthorizationService:
    """Resolves preloaded local identities and signed references; no network lookup."""

    def __init__(self, principals: dict[str, PrincipalRecord], *, pack: SignedReference, policy: SignedReference, verification_key: bytes) -> None:
        self._principals = dict(principals)
        self.pack = pack
        self.policy = policy
        self._verification_key = bytes(verification_key)
        if not self._verification_key or not pack.reference or not pack.digest or not pack.signature or not policy.reference or not policy.digest or not policy.signature:
            raise AuthorizationError("pack and policy references must be signed and complete")
        if not self._verify(pack) or not self._verify(policy):
            raise AuthorizationError("pack or policy signature is invalid")

    def _verify(self, reference: SignedReference) -> bool:
        expected = hmac.new(self._verification_key, f"{reference.reference}:{reference.digest}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(reference.signature, expected)

    def authorize(self, *, principal_id: str, requested_clearance: Clearance,
                  evidence_scope: tuple[str, ...], tools: tuple[str, ...],
                  risk_class: str, resource_budget: dict[str, int]) -> AuthorizationDecision:
        principal = self._principals.get(principal_id)
        if principal is None:
            raise AuthorizationError("principal is not resolved locally")
        if _rank(requested_clearance) > _rank(principal.clearance):
            raise AuthorizationError("requested clearance exceeds principal clearance")
        if not set(evidence_scope).issubset(principal.allowed_evidence_scope):
            raise AuthorizationError("evidence scope exceeds principal authorization")
        if not set(tools).issubset(principal.permitted_tools):
            raise AuthorizationError("requested tool is not permitted")
        if risk_class not in principal.allowed_risk_classes:
            raise AuthorizationError("risk class is not permitted")
        for name, value in resource_budget.items():
            if type(value) is not int or value < 0 or value > principal.resource_limits.get(name, 0):
                raise AuthorizationError(f"resource budget exceeds principal limit: {name}")
        return AuthorizationDecision(principal_id, requested_clearance, self.pack, self.policy)


def sign_reference(reference: str, digest: str, verification_key: bytes) -> SignedReference:
    if not reference or not digest or not verification_key:
        raise AuthorizationError("reference, digest, and verification key are required")
    signature = hmac.new(verification_key, f"{reference}:{digest}".encode(), hashlib.sha256).hexdigest()
    return SignedReference(reference, digest, signature)

def _rank(clearance: Clearance) -> int:
    return {Clearance.public: 0, Clearance.internal: 1, Clearance.restricted: 2, Clearance.secret: 3}[clearance]
