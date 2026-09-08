"""Typed Tool Gateway policy boundary.

The gateway validates a proposed ``ToolAction`` against a signed, scoped
capability. It never receives or forwards a raw model prompt. Executors such
as the sandbox consume the returned authorization and remain responsible for
their execution-specific result evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from contracts import (Clearance, LedgerEventEnvelope, ToolAction, build_event,
                       idempotency_key, stable_id)


class ToolGatewayError(RuntimeError):
    """A tool request cannot be admitted to an executor."""


_CLEARANCE_RANK = {
    Clearance.public: 0,
    Clearance.internal: 1,
    Clearance.restricted: 2,
    Clearance.secret: 3,
}
_SCHEMA_TYPES = {"string", "integer", "number", "boolean", "object", "array"}
_PROMPT_KEYS = {
    "prompt", "system_prompt", "user_prompt", "messages", "instructions",
    "raw_prompt", "system_message", "developer_message",
}


class GatewayLedger(Protocol):
    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]: ...

    @property
    def head_hash(self) -> str | None: ...

    def append(self, event: LedgerEventEnvelope) -> Any: ...


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    required_capability: str
    risk_classes: tuple[str, ...]
    input_schema: dict[str, str]
    required_arguments: tuple[str, ...] = ()
    allow_extra_arguments: bool = False
    output_schema: dict[str, str] | None = None

    def validate(self) -> None:
        if not self.name or not self.required_capability or not self.risk_classes:
            raise ToolGatewayError("tool definition identity and risk are required")
        if any(value not in _SCHEMA_TYPES for value in self.input_schema.values()):
            raise ToolGatewayError("tool input schema contains an unsupported type")
        if any(name not in self.input_schema for name in self.required_arguments):
            raise ToolGatewayError("tool required argument is absent from its input schema")
        if self.output_schema is not None and any(value not in _SCHEMA_TYPES for value in self.output_schema.values()):
            raise ToolGatewayError("tool output schema contains an unsupported type")


@dataclass(frozen=True, slots=True)
class CapabilityScope:
    token_id: str
    task_id: str
    team_id: str
    worker_id: str
    allowed_tools: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    allowed_risk_classes: tuple[str, ...]
    max_clearance: Clearance
    max_timeout_ms: int
    expires_at: str
    policy_version_hash: str
    signature: str

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "token_id": self.token_id,
            "task_id": self.task_id,
            "team_id": self.team_id,
            "worker_id": self.worker_id,
            "allowed_tools": list(self.allowed_tools),
            "allowed_paths": list(self.allowed_paths),
            "allowed_risk_classes": list(self.allowed_risk_classes),
            "max_clearance": self.max_clearance.value,
            "max_timeout_ms": self.max_timeout_ms,
            "expires_at": self.expires_at,
            "policy_version_hash": self.policy_version_hash,
        }

    def digest(self) -> str:
        return _sha256(_canonical(self.unsigned_payload()))

    def validate(self) -> None:
        if not self.token_id or not self.task_id or not self.team_id or not self.worker_id:
            raise ToolGatewayError("capability scope identity is incomplete")
        if not self.allowed_tools or not self.allowed_paths or not self.allowed_risk_classes:
            raise ToolGatewayError("capability scope must contain tools, paths, and risk classes")
        if self.max_timeout_ms <= 0 or self.max_timeout_ms > 86_400_000:
            raise ToolGatewayError("capability timeout is invalid")
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolGatewayError("capability expiry is not RFC3339") from exc
        if expiry.tzinfo is None:
            raise ToolGatewayError("capability expiry must include a timezone")
        if not self.policy_version_hash or not self.signature:
            raise ToolGatewayError("capability policy identity is incomplete")


@dataclass(frozen=True, slots=True)
class ToolAuthorization:
    allowed: bool
    reason: str
    action: ToolAction
    scope: CapabilityScope
    definition: ToolDefinition | None
    call_id: str
    requested_event_ref: str | None = None
    authorized_event_ref: str | None = None
    denied_event_ref: str | None = None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def issue_capability_scope(
    *,
    token_id: str,
    task_id: str,
    team_id: str,
    worker_id: str,
    allowed_tools: tuple[str, ...],
    allowed_paths: tuple[str, ...],
    allowed_risk_classes: tuple[str, ...],
    max_clearance: Clearance,
    max_timeout_ms: int,
    expires_at: str,
    policy_version_hash: str,
    signing_key: bytes,
) -> CapabilityScope:
    unsigned = CapabilityScope(
        token_id=token_id,
        task_id=task_id,
        team_id=team_id,
        worker_id=worker_id,
        allowed_tools=allowed_tools,
        allowed_paths=allowed_paths,
        allowed_risk_classes=allowed_risk_classes,
        max_clearance=max_clearance,
        max_timeout_ms=max_timeout_ms,
        expires_at=expires_at,
        policy_version_hash=policy_version_hash,
        signature="pending",
    )
    unsigned.validate()
    if not signing_key:
        raise ToolGatewayError("capability signing key is required")
    signature = hmac.new(signing_key, unsigned.digest().encode("ascii"), hashlib.sha256).hexdigest()
    return replace(unsigned, signature=signature)


class ToolGateway:
    """Admit typed actions to a registered executor or deny them."""

    def __init__(self, ledger: GatewayLedger, *, signing_key: bytes,
                 definitions: tuple[ToolDefinition, ...], actor_id: str = "tool-gateway.local") -> None:
        if not signing_key:
            raise ToolGatewayError("gateway signing key is required")
        self._ledger = ledger
        self._signing_key = bytes(signing_key)
        self._definitions = {definition.name: definition for definition in definitions}
        self._actor_id = actor_id
        for definition in definitions:
            definition.validate()
        if len(self._definitions) != len(definitions):
            raise ToolGatewayError("tool names must be unique")

    def authorize(self, action: ToolAction, scope: CapabilityScope) -> ToolAuthorization:
        validated = self._validate_action(action)
        scope.validate()
        call_id = stable_id("tool-call", validated.task_id, validated.action_id, validated.idempotency_key)
        requested_ref = self._append(
            event_type="tool.requested",
            action=validated,
            call_id=call_id,
            payload={"arguments_hash": self._arguments_hash(validated), "scope_digest": scope.digest()},
            key=idempotency_key("tool.gateway.requested", validated.task_id, validated.action_id, validated.idempotency_key),
        )
        reason = self._deny_reason(validated, scope)
        definition = self._definitions.get(validated.tool_name)
        if reason is not None:
            denied_ref = self._append(
                event_type="tool.denied",
                action=validated,
                call_id=call_id,
                payload={"reason": reason, "scope_digest": scope.digest()},
                key=idempotency_key("tool.gateway.denied", validated.task_id, validated.action_id, validated.idempotency_key),
            )
            return ToolAuthorization(False, reason, validated, scope, definition, call_id, requested_ref, denied_event_ref=denied_ref)
        authorized_ref = self._append(
            event_type="tool.authorized",
            action=validated,
            call_id=call_id,
            payload={"scope_digest": scope.digest(), "policy_version_hash": scope.policy_version_hash},
            key=idempotency_key("tool.gateway.authorized", validated.task_id, validated.action_id, validated.idempotency_key),
        )
        return ToolAuthorization(True, "authorized", validated, scope, definition, call_id, requested_ref, authorized_ref)

    def validate_output(self, authorization: ToolAuthorization, output: Any) -> None:
        if not authorization.allowed or authorization.definition is None:
            raise ToolGatewayError("output cannot be validated for a denied action")
        schema = authorization.definition.output_schema
        if schema is None:
            return
        if not isinstance(output, dict):
            raise ToolGatewayError("tool output must be an object")
        missing = [name for name in schema if name not in output]
        if missing:
            raise ToolGatewayError("tool output is missing its registered fields")
        self._validate_schema_values(output, schema, "output")

    def _validate_action(self, action: ToolAction) -> ToolAction:
        try:
            validated = ToolAction.from_dict(action.to_dict())
        except Exception as exc:
            raise ToolGatewayError("tool action failed contract validation") from exc
        if not isinstance(validated.arguments, dict):
            raise ToolGatewayError("tool arguments must be an object")
        if not validated.idempotency_key.strip():
            raise ToolGatewayError("tool idempotency key is required")
        if self._contains_prompt_key(validated.arguments):
            raise ToolGatewayError("raw prompt fields are not accepted by the Tool Gateway")
        self._arguments_hash(validated)
        return validated

    def _deny_reason(self, action: ToolAction, scope: CapabilityScope) -> str | None:
        definition = self._definitions.get(action.tool_name)
        if definition is None:
            return "tool is not registered"
        if not self._signature_valid(scope):
            return "capability signature is invalid"
        expiry = datetime.fromisoformat(scope.expires_at.replace("Z", "+00:00"))
        if expiry <= datetime.now(timezone.utc):
            return "capability has expired"
        if action.task_id != scope.task_id or action.worker_id != scope.worker_id:
            return "action identity does not match capability scope"
        if action.tool_name not in scope.allowed_tools:
            return "tool is outside the capability scope"
        if action.risk_class not in scope.allowed_risk_classes or action.risk_class not in definition.risk_classes:
            return "risk class is outside the capability scope"
        if _CLEARANCE_RANK[action.clearance] > _CLEARANCE_RANK[scope.max_clearance]:
            return "action clearance exceeds capability scope"
        if action.timeout_ms > scope.max_timeout_ms:
            return "action timeout exceeds capability scope"
        if not all(self._inside(path, scope.allowed_paths) for path in action.path_scope):
            return "action path is outside the capability scope"
        if any(name not in action.arguments for name in definition.required_arguments):
            return "required tool argument is missing"
        if not definition.allow_extra_arguments and any(name not in definition.input_schema for name in action.arguments):
            return "tool arguments exceed the registered schema"
        try:
            self._validate_schema_values(action.arguments, definition.input_schema, "arguments")
        except ToolGatewayError as exc:
            return str(exc)
        return None

    def _validate_schema_values(self, values: dict[str, Any], schema: dict[str, str], location: str) -> None:
        for name, expected in schema.items():
            if name not in values:
                continue
            value = values[name]
            valid = (
                (expected == "string" and isinstance(value, str))
                or (expected == "integer" and type(value) is int)
                or (expected == "number" and type(value) in {int, float} and not isinstance(value, bool))
                or (expected == "boolean" and type(value) is bool)
                or (expected == "object" and isinstance(value, dict))
                or (expected == "array" and isinstance(value, list))
            )
            if not valid:
                raise ToolGatewayError(f"{location}.{name} does not match its registered schema")

    @staticmethod
    def _contains_prompt_key(value: Any) -> bool:
        if isinstance(value, dict):
            return any(str(key).lower() in _PROMPT_KEYS or ToolGateway._contains_prompt_key(item) for key, item in value.items())
        if isinstance(value, list):
            return any(ToolGateway._contains_prompt_key(item) for item in value)
        return False

    @staticmethod
    def _inside(candidate: str, roots: tuple[str, ...]) -> bool:
        if not isinstance(candidate, str) or "\x00" in candidate:
            return False
        try:
            path = Path(candidate).resolve(strict=False)
            return any(path == root or root in path.parents for root in (Path(value).resolve(strict=False) for value in roots))
        except (OSError, RuntimeError, ValueError):
            return False

    def _signature_valid(self, scope: CapabilityScope) -> bool:
        expected = hmac.new(self._signing_key, scope.digest().encode("ascii"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, scope.signature)

    @staticmethod
    def _arguments_hash(action: ToolAction) -> str:
        try:
            encoded = _canonical(action.arguments).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ToolGatewayError("tool arguments are not canonicalizable") from exc
        return _sha256(encoded.decode("utf-8"))

    def _append(self, *, event_type: str, action: ToolAction, call_id: str,
                payload: dict[str, Any], key: str) -> str:
        existing = next((event for event in self._ledger.events if event.idempotency_key == key), None)
        if existing is not None:
            return existing.event_id
        event = build_event(
            event_type=event_type,
            task_id=action.task_id,
            actor_id=self._actor_id,
            actor_type="service",
            payload_contract="ToolGatewayDecision",
            payload_version="1.0",
            payload={"call_id": call_id, "action_id": action.action_id, "tool_name": action.tool_name, **payload},
            clearance=action.clearance,
            idempotency=key,
            sequence=len(self._ledger.events),
            previous_event_hash=self._ledger.head_hash,
        )
        try:
            self._ledger.append(event)
        except Exception as exc:
            raise ToolGatewayError("tool gateway ledger append failed") from exc
        return event.event_id


__all__ = [
    "ToolGatewayError",
    "ToolDefinition",
    "CapabilityScope",
    "ToolAuthorization",
    "issue_capability_scope",
    "ToolGateway",
]
