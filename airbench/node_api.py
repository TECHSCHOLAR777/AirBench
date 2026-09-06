"""Authenticated local Node API over the deterministic AirBench core.

The API is deliberately a projection and command boundary. It does not run a
model, parse a file, execute a tool, or make a network call. Mutating routes
delegate to :class:`contracts.Orchestrator`; read routes project only the
committed local ledger.
"""

from __future__ import annotations

import hmac
import hashlib
import json
import re
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from contracts import (
    AuthorizationError,
    AuthorizationRejected,
    Clearance,
    ContractValidationError,
    LedgerEventEnvelope,
    NodeCommandEnvelope,
    NodeCommandResult,
    Orchestrator,
    PlanRejected,
    StorageFailure,
    TaskEnvelope,
    TaskPlanReview,
    TeamPlan,
    TransitionRejected,
    CancellationRequested,
)
from contracts.ids import stable_id
from contracts.ledger import LedgerError


PROTOCOL_VERSION = "0.1"
MAX_JSON_BODY_BYTES = 1_048_576
MAX_EVENT_BATCH = 128
MAX_EVIDENCE_ITEMS = 1_000
MAX_ROUTE_ITEMS = 1_000
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CLEARANCE_RANK = {
    Clearance.public: 0,
    Clearance.internal: 1,
    Clearance.restricted: 2,
    Clearance.secret: 3,
}


class LedgerView(Protocol):
    @property
    def events(self) -> tuple[LedgerEventEnvelope, ...]: ...

    @property
    def head_hash(self) -> str | None: ...


class NodeApiError(RuntimeError):
    """An intentionally bounded, non-secret HTTP error."""

    def __init__(self, status_code: int, code: str, message: str, *, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}


@dataclass(frozen=True, slots=True)
class NodeApiConfig:
    node_identity: str
    protocol_version: str
    clearance_context: Clearance | str
    authenticated_subject: str
    domain_pack_ref: str
    bearer_token: str = field(repr=False)
    handshake_ledger_event_ref: str
    sovereignty_evidence_ref: str
    require_orchestrator_authorization: bool = True

    def __post_init__(self) -> None:
        try:
            clearance = self.clearance_context if isinstance(self.clearance_context, Clearance) else Clearance(self.clearance_context)
        except ValueError as exc:
            raise ValueError("clearance_context is invalid") from exc
        object.__setattr__(self, "clearance_context", clearance)
        for name in ("node_identity", "protocol_version", "authenticated_subject", "domain_pack_ref", "bearer_token", "handshake_ledger_event_ref", "sovereignty_evidence_ref"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")
        if not NODE_ID_RE.fullmatch(self.node_identity):
            raise ValueError("node_identity has an invalid shape")


class NodeApiService:
    """Owns API authentication and projections, not task authority."""

    def __init__(self, orchestrator: Orchestrator, config: NodeApiConfig):
        self.orchestrator = orchestrator
        self.config = config
        self._ledger: LedgerView = orchestrator.store
        self._lock = RLock()

    def authenticate(self, authorization: str | None) -> str:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise NodeApiError(401, "authentication_required", "A bearer credential is required.", headers={"WWW-Authenticate": "Bearer"})
        token = authorization[7:].strip()
        if not token or not hmac.compare_digest(token, self.config.bearer_token):
            raise NodeApiError(401, "invalid_token", "The bearer credential was not accepted.", headers={"WWW-Authenticate": "Bearer"})
        return self.config.authenticated_subject

    def handshake(self) -> dict[str, str]:
        return {
            "node_identity": self.config.node_identity,
            "protocol_version": self.config.protocol_version,
            "clearance_context": self.config.clearance_context.value,
            "authenticated_subject": self.config.authenticated_subject,
            "domain_pack_ref": self.config.domain_pack_ref,
            "ledger_event_ref": self.config.handshake_ledger_event_ref,
        }

    def health(self) -> dict[str, Any]:
        with self._lock:
            try:
                verify_chain = getattr(self._ledger, "verify_chain", None)
                if callable(verify_chain):
                    verify_chain()
                events = self._ledger.events
                return {
                    "status": "ready",
                    "node_identity": self.config.node_identity,
                    "protocol_version": self.config.protocol_version,
                    "clearance_context": self.config.clearance_context.value,
                    "ledger": {
                        "event_count": len(events),
                        "head_hash": self._ledger.head_hash,
                        "chain_verified": True,
                    },
                    "sovereignty_evidence_ref": self.config.sovereignty_evidence_ref,
                }
            except Exception as exc:
                raise NodeApiError(503, "ledger_unavailable", "The local ledger could not be verified.") from exc

    def create_task(self, subject: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            command = self._command(subject, payload, "task.create", None)
            existing = self._existing_command(command)
            if existing is not None:
                return self._replay_create(command, existing)
            arguments = command.arguments
            principal_id = _text(arguments, "principal_id", 256, default=subject)
            if principal_id != subject:
                raise NodeApiError(403, "principal_mismatch", "The task principal does not match the authenticated subject.")
            clearance = _clearance(arguments.get("clearance"))
            self._check_clearance(clearance)
            request = _text(arguments, "request", 65_536)
            requested_domain_pack_ref = _optional_text(arguments, "domain_pack_ref", 512)
            if requested_domain_pack_ref is not None and requested_domain_pack_ref != self.config.domain_pack_ref:
                raise NodeApiError(409, "domain_pack_mismatch", "The task domain pack must be selected by the approved Node.")
            domain_pack_ref = self.config.domain_pack_ref
            risk_class = _text(arguments, "risk_class", 128)
            autonomy_ceiling = _text(arguments, "autonomy_ceiling", 128)
            title = _text(arguments, "title", 256, default=_title(request))
            project_ref = _optional_text(arguments, "project_ref", 256)
            priority = _text(arguments, "priority", 64, default="normal")
            deadline = _optional_text(arguments, "deadline", 64)
            allowed_evidence_scope = _text_list(arguments, "allowed_evidence_scope", 100)
            permitted_worker_capabilities = _text_list(arguments, "permitted_worker_capabilities", 100)
            permitted_tools = _text_list(arguments, "permitted_tools", 100)
            output_contract = _text(arguments, "output_contract", 512, default="text")
            verification_criteria = _text_list(arguments, "verification_criteria", 100)
            input_manifest_refs = _text_list(arguments, "input_manifest_refs", 100)
            resource_budget = _int_map(arguments.get("resource_budget", {}), "resource_budget")
            if self.config.require_orchestrator_authorization and self.orchestrator.authorization is None:
                raise NodeApiError(503, "authorization_unavailable", "The local authorization service is not configured.")

            try:
                task = self.orchestrator.create_task(
                    principal_id=principal_id,
                    clearance=clearance,
                    request=request,
                    domain_pack_ref=domain_pack_ref,
                    risk_class=risk_class,
                    autonomy_ceiling=autonomy_ceiling,
                    allowed_evidence_scope=allowed_evidence_scope,
                    permitted_worker_capabilities=permitted_worker_capabilities,
                    permitted_tools=permitted_tools,
                    output_contract=output_contract,
                    verification_criteria=verification_criteria,
                    resource_budget=resource_budget,
                    title=title,
                    project_ref=project_ref,
                    priority=priority,
                    deadline=deadline,
                    input_manifest_refs=input_manifest_refs,
                    command_metadata=_command_metadata(command),
                )
            except AuthorizationError as exc:
                raise NodeApiError(403, "orchestrator_authorization_rejected", "The local authorization policy rejected the task.") from exc
            except (ContractValidationError, ValueError) as exc:
                raise NodeApiError(400, "task_contract_invalid", "The task request does not satisfy the local contract.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "task_not_committed", "The task was not committed to the local ledger.") from exc

            snapshot = self.snapshot(task.task_id)
            created = next((event for event in self._ledger.events if event.task_id == task.task_id and event.event_type == "task.created"), None)
            if created is None:
                raise NodeApiError(503, "task_commit_unreadable", "The committed task could not be read back from the ledger.")
            return {
                "task": task.to_dict(),
                "snapshot": snapshot,
                "ledger_event_ref": created.event_id,
                "command": _command_result(command, task.task_id, created, self._task_sequence(task.task_id, created.event_id), self.orchestrator.state(task.task_id), self.config),
            }

    def authorize(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            command = self._command(subject, payload, "task.authorize", task_id)
            self._visible_task(task_id)
            existing = self._existing_command(command)
            if existing is not None:
                return _command_result(command, task_id, existing, self._task_sequence(task_id, existing.event_id), self.orchestrator.state(task_id), self.config)
            self._check_expected_sequence(command, task_id)
            authorization_ref = _text(command.arguments, "authorization_ref", 512)
            try:
                result = self.orchestrator.authorize(self._visible_task(task_id).task_id, authorization_ref=authorization_ref, command_metadata=_command_metadata(command))
            except AuthorizationRejected as exc:
                raise NodeApiError(400, "authorization_invalid", "The authorization reference is invalid.") from exc
            except TransitionRejected as exc:
                raise NodeApiError(409, "transition_rejected", "The task cannot be authorized from its current state.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the transition.") from exc
            return _command_result(command, task_id, self._event_by_id(result.event_id), self._task_sequence(task_id, result.event_id), result.state, self.config)

    def approve_plan(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            command = self._command(subject, payload, "task.approve_plan", task_id)
            self._visible_task(task_id)
            existing = self._existing_command(command)
            if existing is not None:
                return _command_result(command, task_id, existing, self._task_sequence(task_id, existing.event_id), self.orchestrator.state(task_id), self.config)
            self._check_expected_sequence(command, task_id)
            review = self.plan(task_id)
            if review["plan_state"] != "ready":
                raise NodeApiError(409, "plan_not_approvable", "The Node has not produced an approvable plan and hardware admission.")
            approval_ref = _text(command.arguments, "approval_ref", 512)
            try:
                result = self.orchestrator.approve_plan(
                    self._visible_task(task_id).task_id,
                    approval_ref=approval_ref,
                    command_metadata=_command_metadata(command),
                )
            except AuthorizationRejected as exc:
                raise NodeApiError(400, "approval_invalid", "The plan approval reference is invalid.") from exc
            except PlanRejected as exc:
                raise NodeApiError(409, "plan_not_approvable", "The committed plan cannot be approved in its current state.") from exc
            except TransitionRejected as exc:
                raise NodeApiError(409, "transition_rejected", "The plan cannot be approved from its current task state.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the plan approval.") from exc
            return _command_result(command, task_id, self._event_by_id(result.event_id), self._task_sequence(task_id, result.event_id), result.state, self.config)

    def cancel(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            command = self._command(subject, payload, "task.cancel", task_id)
            self._visible_task(task_id)
            existing = self._existing_command(command)
            if existing is not None:
                return _command_result(command, task_id, existing, self._task_sequence(task_id, existing.event_id), self.orchestrator.state(task_id), self.config)
            self._check_expected_sequence(command, task_id)
            reason = _text(command.arguments, "reason", 4_096)
            try:
                result = self.orchestrator.cancel(self._visible_task(task_id).task_id, reason=reason, command_metadata=_command_metadata(command))
            except CancellationRequested as exc:
                raise NodeApiError(400, "cancellation_invalid", "A cancellation reason is required.") from exc
            except TransitionRejected as exc:
                raise NodeApiError(409, "transition_rejected", "The task cannot be stopped from its current state.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the transition.") from exc
            return _command_result(command, task_id, self._event_by_id(result.event_id), self._task_sequence(task_id, result.event_id), result.state, self.config)

    def request_review(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            command = self._command(subject, payload, "task.request_review", task_id)
            self._visible_task(task_id)
            existing = self._existing_command(command)
            if existing is not None:
                return _command_result(command, task_id, existing, self._task_sequence(task_id, existing.event_id), self.orchestrator.state(task_id), self.config)
            self._check_expected_sequence(command, task_id)
            reason = _text(command.arguments, "reason", 4_096)
            try:
                result = self.orchestrator.request_review(self._visible_task(task_id).task_id, reason=reason, command_metadata=_command_metadata(command))
            except TransitionRejected as exc:
                raise NodeApiError(409, "transition_rejected", "The task cannot request review from its current state.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the transition.") from exc
            return _command_result(command, task_id, self._event_by_id(result.event_id), self._task_sequence(task_id, result.event_id), result.state, self.config)

    def _command(self, subject: str, payload: dict[str, Any], expected_type: str, route_task_id: str | None) -> NodeCommandEnvelope:
        try:
            command = NodeCommandEnvelope.from_dict(payload)
        except ContractValidationError as exc:
            raise NodeApiError(400, "command_contract_invalid", "The command envelope does not satisfy the Node contract.") from exc
        if command.client_version != self.config.protocol_version:
            raise NodeApiError(409, "protocol_mismatch", "The command protocol version is not supported by this Node.")
        if command.actor != subject:
            raise NodeApiError(403, "command_actor_mismatch", "The command actor does not match the authenticated subject.")
        if command.command_type != expected_type:
            raise NodeApiError(400, "command_type_mismatch", "The command type does not match this endpoint.")
        if route_task_id is None:
            if command.task_id is not None or command.expected_sequence is not None:
                raise NodeApiError(400, "command_target_invalid", "Task creation commands cannot carry a task or expected sequence.")
        elif command.task_id != route_task_id or command.expected_sequence is None:
            raise NodeApiError(400, "command_target_invalid", "The command task and expected sequence are required and must match the route.")
        return command

    def _check_expected_sequence(self, command: NodeCommandEnvelope, task_id: str) -> None:
        self._visible_task(task_id)
        current = len(self._stream_events(self._visible_task(task_id)))
        if command.expected_sequence != current:
            raise NodeApiError(409, "stale_command", "The task changed after this command was prepared.")

    def _existing_command(self, command: NodeCommandEnvelope) -> LedgerEventEnvelope | None:
        fingerprint = _command_fingerprint(command)
        for event in reversed(self._ledger.events):
            metadata = event.payload.get("_command") if isinstance(event.payload, dict) else None
            if not isinstance(metadata, dict) or metadata.get("idempotency_key") != command.idempotency_key:
                continue
            if metadata.get("fingerprint") != fingerprint:
                raise NodeApiError(409, "idempotency_conflict", "The idempotency key was already used for different command content.")
            return event
        return None

    def _replay_create(self, command: NodeCommandEnvelope, event: LedgerEventEnvelope) -> dict[str, Any]:
        try:
            task = TaskEnvelope.from_dict(event.payload["task"])
        except (KeyError, ContractValidationError, TypeError) as exc:
            raise NodeApiError(503, "task_contract_corrupt", "The idempotent task result could not be verified.") from exc
        return {
            "task": task.to_dict(),
            "snapshot": self.snapshot(task.task_id),
            "ledger_event_ref": event.event_id,
            "command": _command_result(command, task.task_id, event, self._task_sequence(task.task_id, event.event_id), self.orchestrator.state(task.task_id), self.config),
        }

    def _event_by_id(self, event_id: str) -> LedgerEventEnvelope:
        event = next((candidate for candidate in self._ledger.events if candidate.event_id == event_id), None)
        if event is None:
            raise NodeApiError(503, "event_unreadable", "The committed command event could not be read back.")
        return event

    def _task_sequence(self, task_id: str, event_id: str) -> int:
        for sequence, event in enumerate(self._ledger.events, start=1):
            if event.task_id == task_id and event.event_id == event_id:
                return sum(1 for prior in self._ledger.events[:sequence] if prior.task_id == task_id)
        raise NodeApiError(503, "event_unreadable", "The committed command sequence could not be read back.")

    def snapshot(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._visible_task(task_id)
            events = self._stream_events(task)
            state = self.orchestrator.state(task.task_id)
            evidence, facts = self._evidence_and_facts(events)
            artifact_refs = sorted({
                str(event.payload.get("artifact_id"))
                for event in events
                if event.event_type in {"artifact.staged", "artifact.checked"}
                and isinstance(event.payload.get("artifact_id"), str)
            })
            unresolved = sorted({
                question
                for event in events
                for question in _string_list(event.payload.get("unresolved_questions"))
            })
            latest_ref = self._ledger.head_hash or (events[-1].event_id if events else "")
            return {
                "taskId": task.task_id,
                "schemaVersion": self.config.protocol_version,
                "snapshotId": stable_id("node-snapshot", task.task_id, len(events), latest_ref),
                "asOfSequence": len(events),
                "title": _title(task.request),
                "requestSummary": _bounded_text(task.request, 2_000),
                "status": _status_for_state(state),
                "phase": _phase_for_state(state),
                "clearanceContext": self.config.clearance_context.value,
                "inputManifestRef": _input_manifest_ref(events),
                "evidence": evidence,
                "facts": facts,
                "artifactRefs": artifact_refs,
                "unresolvedQuestions": unresolved,
                "nodeConnectionRef": self.config.node_identity,
                "ledgerHeadRef": latest_ref,
            }

    def plan(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._visible_task(task_id)
            events = self._stream_events(task)
            plan_event = next((event for event in reversed(events) if event.event_type == "task.plan.committed"), None)
            resource_event = next((event for event in reversed(events) if event.event_type in {
                "team.resource_plan.admitted", "team.resource_plan.queued", "team.resource_plan.degraded_needs_review", "team.resource_plan.rejected"
            }), None)
            authority = "operator_approval" if task.autonomy_ceiling == "review_required" else "policy_permitted"
            authority_reason = (
                "An authorized operator must approve this plan before execution."
                if authority == "operator_approval" else
                "The current autonomy policy permits execution after the Node plan is admitted."
            )
            if plan_event is None:
                return TaskPlanReview(
                    task_id=task.task_id,
                    node_identity=self.config.node_identity,
                    protocol_version=self.config.protocol_version,
                    clearance_context=self.config.clearance_context,
                    plan_state="not_ready",
                    task_sequence=len(events),
                    team_id=None,
                    assignments=(),
                    dependency_graph={},
                    concurrency_ceiling=0,
                    execution_mode="not_selected",
                    worker_capabilities={},
                    hardware_profile_ref=None,
                    hardware_reason="The Node has accepted the task but has not committed a plan yet.",
                    required_verification=True,
                    completion_criteria=task.verification_criteria,
                    required_authority=authority,
                    authority_reason=authority_reason,
                    plan_version_hash=None,
                    policy_version_hash=None,
                    ledger_event_ref=None,
                    failure_code="plan_not_ready",
                    failure_reason="The orchestration engine has not committed a validated plan.",
                ).to_dict()

            raw_plan = plan_event.payload.get("plan")
            try:
                plan = TeamPlan.from_dict(raw_plan) if isinstance(raw_plan, dict) else None
            except ContractValidationError as exc:
                raise NodeApiError(503, "plan_contract_corrupt", "The committed plan could not be verified.") from exc
            if plan is None:
                raise NodeApiError(503, "plan_contract_corrupt", "The committed plan does not contain its typed contract.")

            resource = _resource_plan_values(resource_event.payload if resource_event else None)
            admission = resource.get("admission")
            mode = resource.get("execution_mode")
            failure_code: str | None = None
            failure_reason: str | None = None
            if resource_event is None:
                plan_state = "needs_review"
                mode = "not_selected"
                hardware_reason = "Hardware admission evidence is missing, so execution mode cannot be shown safely."
                failure_code = "hardware_admission_missing"
                failure_reason = hardware_reason
            elif admission in {"rejected", "stopped"}:
                plan_state = "rejected"
                hardware_reason = resource.get("reason") or "The hardware admission policy rejected this plan."
                failure_code = "hardware_admission_rejected"
                failure_reason = hardware_reason
            elif admission == "queued":
                plan_state = "queued"
                hardware_reason = resource.get("reason") or "The plan is waiting for an available hardware reservation."
            elif admission == "degraded_needs_review":
                plan_state = "needs_review"
                hardware_reason = resource.get("reason") or "The Node admitted a degraded execution mode that requires review."
                failure_code = "degraded_hardware_mode"
                failure_reason = hardware_reason
            elif admission == "admitted" and mode in {"parallel", "pipelined", "serial_virtual_team"}:
                plan_state = "ready"
                hardware_reason = resource.get("reason") or "Hardware admission was committed by the Node."
            else:
                plan_state = "needs_review"
                mode = "not_selected"
                hardware_reason = "The hardware admission record is incomplete, so execution cannot be approved safely."
                failure_code = "hardware_admission_invalid"
                failure_reason = hardware_reason

            return TaskPlanReview(
                task_id=task.task_id,
                node_identity=self.config.node_identity,
                protocol_version=self.config.protocol_version,
                clearance_context=self.config.clearance_context,
                plan_state=plan_state,
                task_sequence=len(events),
                team_id=plan.team_id,
                assignments=plan.assignments,
                dependency_graph=plan.dependency_graph,
                concurrency_ceiling=resource.get("concurrency_ceiling", plan.concurrency_ceiling),
                execution_mode=mode,
                worker_capabilities=resource.get("worker_capabilities", {}),
                hardware_profile_ref=resource.get("hardware_profile_ref"),
                hardware_reason=hardware_reason,
                required_verification=plan.required_verification,
                completion_criteria=plan.completion_criteria,
                required_authority=authority,
                authority_reason=authority_reason,
                plan_version_hash=plan.plan_version_hash,
                policy_version_hash=plan.policy_version_hash,
                ledger_event_ref=plan_event.event_id,
                failure_code=failure_code,
                failure_reason=failure_reason,
            ).to_dict()

    def event_batch(self, task_id: str, after_sequence: int) -> dict[str, Any]:
        if after_sequence < 0:
            raise NodeApiError(400, "cursor_invalid", "The event cursor must be non-negative.")
        with self._lock:
            task = self._visible_task(task_id)
            events = self._stream_events(task)
            total = len(events)
            if after_sequence > total:
                raise NodeApiError(409, "cursor_ahead", "The event cursor is ahead of the task stream.")
            selected = events[after_sequence:after_sequence + MAX_EVENT_BATCH]
            wire_events = [self._wire_event(event, task, after_sequence + index + 1) for index, event in enumerate(selected)]
            next_sequence = after_sequence + len(selected)
            return {
                "stream_id": task.task_id,
                "node_identity": self.config.node_identity,
                "protocol_version": self.config.protocol_version,
                "clearance_context": self.config.clearance_context.value,
                "events": wire_events,
                "next_sequence": next_sequence,
                "has_more": next_sequence < total,
                "ledger_event_refs": [event["ledgerEventRef"] for event in wire_events],
            }

    def evidence(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._visible_task(task_id)
            evidence, facts = self._evidence_and_facts(self._stream_events(task))
            return {
                "taskId": task.task_id,
                "schemaVersion": self.config.protocol_version,
                "clearanceContext": self.config.clearance_context.value,
                "evidence": evidence,
                "facts": facts,
            }

    def route_trace(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._visible_task(task_id)
            entries: list[dict[str, Any]] = []
            for sequence, event in enumerate(self._stream_events(task), start=1):
                if event.event_type not in _ROUTE_EVENT_TYPES:
                    continue
                payload = event.payload
                entry: dict[str, Any] = {
                    "sequence": sequence,
                    "eventType": event.event_type,
                    "occurredAt": event.occurred_at,
                    "actor": event.actor_id,
                    "clearanceContext": self.config.clearance_context.value,
                    "ledgerEventRef": event.event_id,
                    "payloadHash": event.payload_hash,
                }
                for key in ("request_id", "worker_id", "role", "task_kind", "required_capability", "selected_target", "decision_source", "rule_or_threshold", "qualification_certificate", "fallback_target", "reason", "status"):
                    if key in payload:
                        entry[key] = _safe_value(payload[key])
                if "eligible_targets" in payload:
                    entry["eligible_targets"] = _string_list(payload["eligible_targets"])[:100]
                entries.append(entry)
                if len(entries) >= MAX_ROUTE_ITEMS:
                    break
            return {"taskId": task.task_id, "schemaVersion": self.config.protocol_version, "entries": entries}

    def review(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            task = self._visible_task(task_id)
            required = None
            signoff = None
            for event in self._stream_events(task):
                if event.event_type == "human.review.required":
                    required = event
                elif event.event_type == "human.signoff":
                    signoff = event
            if signoff is not None:
                state = "recorded"
                event = signoff
            elif required is not None:
                state = "pending"
                event = required
            else:
                state = "not_required"
                event = None
            return {
                "taskId": task.task_id,
                "schemaVersion": self.config.protocol_version,
                "state": state,
                "reason": _bounded_text((event.payload.get("reason") if event else "") or "", 4_096),
                "ledgerEventRef": event.event_id if event else None,
                "clearanceContext": self.config.clearance_context.value,
            }

    def _visible_task(self, task_id: str) -> TaskEnvelope:
        _validate_task_id(task_id)
        event = next((event for event in self._ledger.events if event.task_id == task_id and event.event_type == "task.created"), None)
        if event is None:
            raise NodeApiError(404, "task_not_found", "The requested task does not exist.")
        try:
            task = TaskEnvelope.from_dict(event.payload["task"])
        except (KeyError, ContractValidationError, TypeError) as exc:
            raise NodeApiError(503, "task_contract_corrupt", "The task contract could not be verified.") from exc
        if not self._can_read(task.clearance) or not self._can_read(event.clearance):
            raise NodeApiError(404, "task_not_found", "The requested task does not exist.")
        return task

    def _stream_events(self, task: TaskEnvelope) -> list[LedgerEventEnvelope]:
        return [event for event in self._ledger.events if event.task_id == task.task_id and self._can_read(event.clearance) and self._can_read(task.clearance)]

    def _can_read(self, clearance: Clearance) -> bool:
        return _CLEARANCE_RANK[clearance] <= _CLEARANCE_RANK[self.config.clearance_context]

    def _check_clearance(self, clearance: Clearance) -> None:
        if not self._can_read(clearance):
            raise NodeApiError(403, "clearance_exceeded", "The requested clearance exceeds this Node context.")

    def _wire_event(self, event: LedgerEventEnvelope, task: TaskEnvelope, sequence: int) -> dict[str, Any]:
        event_type, payload = self._project_event(event, task)
        return {
            "eventId": event.event_id,
            "taskId": task.task_id,
            "sequence": sequence,
            "schemaVersion": self.config.protocol_version,
            "eventType": event_type,
            "occurredAt": event.occurred_at,
            "actor": event.actor_id,
            "clearanceContext": self.config.clearance_context.value,
            "payloadHash": event.payload_hash,
            "ledgerEventRef": event.event_id,
            "payload": payload,
        }

    def _project_event(self, event: LedgerEventEnvelope, task: TaskEnvelope) -> tuple[str, dict[str, Any]]:
        p = event.payload
        if event.event_type in {"task.created", "task.authorized"}:
            return "task.accepted", {"phase": "accepted", "status": "accepted", "summary": _event_summary(event)}
        if event.event_type == "task.plan.committed":
            return "plan.created", {"phase": "planning", "status": "planning", "summary": _event_summary(event)}
        if event.event_type == "task.plan.approved":
            return "plan.approved", {"phase": "planning", "status": "planning", "summary": _event_summary(event)}
        if event.event_type in {"model.requested", "worker.started"}:
            return "worker.started", {"role": _role(p, "worker"), "label": _label(p, event.event_type), "status": "running"}
        if event.event_type in {"model.responded", "worker.completed"}:
            return "worker.completed", {"role": _role(p, "worker"), "label": _label(p, event.event_type), "status": "completed"}
        if event.event_type == "tool.requested":
            return "tool.started", {"role": _role(p, "tool"), "label": _label(p, event.event_type), "status": "running"}
        if event.event_type == "tool.result":
            if self._validated_provenance(event) is None:
                return "ledger.written", {"summary": "Ledger recorded tool.result without a safe provenance projection."}
            return "tool.completed", {"role": _role(p, "tool"), "label": _label(p, event.event_type), "status": "completed"}
        if event.event_type == "evidence.created":
            evidence = self._evidence_ref(event)
            if evidence is not None:
                return "evidence.added", {"evidence": evidence}
        if event.event_type == "verification.completed":
            if self._validated_provenance(event) is None:
                return "ledger.written", {"summary": "Ledger recorded verification without a safe provenance projection."}
            status = str(p.get("status", "needs_review"))
            passed = status == "passed"
            return ("verification.completed" if passed else "verification.failed"), {"summary": _event_summary(event), "passed": passed}
        if event.event_type == "human.review.required":
            return "approval.required", {"reason": _bounded_text(str(p.get("reason", "Review is required.")), 4_096)}
        if event.event_type == "human.signoff":
            return "approval.recorded", {"reason": _bounded_text(str(p.get("reason", "Human sign-off recorded.")), 4_096)}
        if event.event_type == "artifact.staged" and isinstance(p.get("artifact_id"), str):
            return "artifact.ready", {"artifactId": p["artifact_id"]}
        if event.event_type == "task.failed":
            return "task.failed", {"phase": "failed", "status": "failed", "summary": _event_summary(event)}
        if event.event_type == "task.cancelled":
            return "task.stopped", {"phase": "stopped", "status": "stopped", "summary": _event_summary(event)}
        if event.event_type == "completion.recorded":
            return "task.completed", {"phase": "completed", "status": "completed", "summary": _event_summary(event)}
        return "ledger.written", {"summary": f"Ledger recorded {event.event_type}."}

    def _evidence_and_facts(self, events: list[LedgerEventEnvelope]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        evidence: list[dict[str, Any]] = []
        facts: list[dict[str, Any]] = []
        for event in events:
            if event.event_type == "evidence.created":
                item = self._evidence_ref(event)
                if item is not None:
                    evidence.append(item)
            elif event.event_type in {"fact.candidate", "fact.committed"}:
                item = self._fact_ref(event)
                if item is not None:
                    facts.append(item)
            if len(evidence) >= MAX_EVIDENCE_ITEMS and len(facts) >= MAX_EVIDENCE_ITEMS:
                break
        return evidence[:MAX_EVIDENCE_ITEMS], facts[:MAX_EVIDENCE_ITEMS]

    def _evidence_ref(self, event: LedgerEventEnvelope) -> dict[str, Any] | None:
        p = event.payload
        provenance = p.get("provenance")
        validated = self._validated_provenance(event)
        if validated is None:
            return None
        evidence_id = p.get("evidence_id") or p.get("evidenceId")
        content_hash = p.get("content_hash") or p.get("contentHash")
        if not isinstance(evidence_id, str) or not evidence_id or not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", content_hash):
            return None
        clearance, taint = validated
        return {
            "evidenceId": evidence_id,
            "contentHash": content_hash.lower(),
            "source": _provenance_ref(provenance, event),
            "confidence": _confidence(provenance.get("confidence")),
            "clearance": clearance.value,
            "taint": taint,
        }

    def _fact_ref(self, event: LedgerEventEnvelope) -> dict[str, Any] | None:
        p = event.payload
        provenance = p.get("provenance")
        fact_id = p.get("fact_id") or p.get("factId")
        validated = self._validated_provenance(event)
        if validated is None or not isinstance(provenance, dict) or not isinstance(fact_id, str) or not fact_id:
            return None
        clearance, taint = validated
        return {
            "factId": fact_id,
            "schemaVersion": "1.0",
            "value": _safe_value(p.get("value")),
            "unit": p.get("unit") if isinstance(p.get("unit"), str) else None,
            "source": _provenance_ref(provenance, event),
            "confidence": _confidence(provenance.get("confidence")),
            "clearance": clearance.value,
            "taint": taint,
            "parentFactIds": _string_list(p.get("parent_fact_ids")),
            "derivation": _safe_value(p.get("derivation")) if isinstance(p.get("derivation"), dict) else None,
            "supersededBy": p.get("superseded_by") if isinstance(p.get("superseded_by"), str) else None,
        }

    def _validated_provenance(self, event: LedgerEventEnvelope) -> tuple[Clearance, str] | None:
        provenance = event.payload.get("provenance")
        if not isinstance(provenance, dict):
            return None
        source_ref = provenance.get("source_ref")
        confidence = provenance.get("confidence")
        taint = provenance.get("taint")
        if not isinstance(source_ref, str) or not source_ref.strip() or type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            return None
        if not isinstance(taint, str) or taint not in {"clean", "untrusted", "contaminated"}:
            return None
        try:
            clearance = Clearance(provenance.get("clearance"))
        except (TypeError, ValueError):
            return None
        if _CLEARANCE_RANK[clearance] > _CLEARANCE_RANK[self.config.clearance_context] or _CLEARANCE_RANK[clearance] > _CLEARANCE_RANK[event.clearance]:
            return None
        return clearance, taint


_ROUTE_EVENT_TYPES = {
    "routing.decision", "routing.fallback.selected", "routing.queued", "model.requested", "model.responded", "model.failed",
    "model.call.started", "model.call.completed", "model.call.failed", "fallback.selected",
}


def create_app(service: NodeApiService) -> FastAPI:
    """Build an API app with documentation endpoints disabled by default."""

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(NodeApiError)
    async def node_error_handler(_: Request, error: NodeApiError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": "node_api_error", "code": error.code, "message": error.message},
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def request_error_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "node_api_error", "code": "request_invalid", "message": "The request did not satisfy the Node API contract."},
        )

    def auth(request: Request) -> str:
        return service.authenticate(request.headers.get("authorization"))

    async def json_body(request: Request) -> dict[str, Any]:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if int(length) > MAX_JSON_BODY_BYTES:
                    raise NodeApiError(413, "body_too_large", "The request body exceeds the local limit.")
            except ValueError as exc:
                raise NodeApiError(400, "content_length_invalid", "The request content length is invalid.") from exc
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_JSON_BODY_BYTES:
                raise NodeApiError(413, "body_too_large", "The request body exceeds the local limit.")
        try:
            value = json.loads(bytes(data))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NodeApiError(400, "json_invalid", "The request body is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise NodeApiError(400, "json_object_required", "The request body must be a JSON object.")
        return value

    @app.get("/api/v1/node/handshake")
    async def handshake(request: Request) -> dict[str, str]:
        auth(request)
        return service.handshake()

    @app.get("/api/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        auth(request)
        return service.health()

    @app.post("/api/v1/tasks", status_code=201)
    async def create_task(request: Request) -> dict[str, Any]:
        subject = auth(request)
        return service.create_task(subject, await json_body(request))

    @app.get("/api/v1/tasks/{task_id}")
    async def task_snapshot(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return service.snapshot(task_id)

    @app.get("/api/v1/tasks/{task_id}/plan")
    async def task_plan(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return service.plan(task_id)

    @app.get("/api/v1/tasks/{task_id}/events")
    async def task_events(task_id: str, request: Request, after_sequence: int = 0) -> dict[str, Any]:
        auth(request)
        return service.event_batch(task_id, after_sequence)

    @app.get("/api/v1/tasks/{task_id}/evidence")
    async def task_evidence(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return service.evidence(task_id)

    @app.get("/api/v1/tasks/{task_id}/route-trace")
    async def task_route_trace(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return service.route_trace(task_id)

    @app.get("/api/v1/tasks/{task_id}/review")
    async def task_review(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return service.review(task_id)

    @app.post("/api/v1/tasks/{task_id}/authorize", status_code=202)
    async def authorize_task(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        return service.authorize(subject, task_id, await json_body(request))

    @app.post("/api/v1/tasks/{task_id}/approve", status_code=202)
    async def approve_task_plan(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        return service.approve_plan(subject, task_id, await json_body(request))

    @app.post("/api/v1/tasks/{task_id}/cancel", status_code=202)
    async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        return service.cancel(subject, task_id, await json_body(request))

    @app.post("/api/v1/tasks/{task_id}/review", status_code=202)
    async def review_task(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        return service.request_review(subject, task_id, await json_body(request))

    return app


def _command_fingerprint(command: NodeCommandEnvelope) -> str:
    return hashlib.sha256(command.canonical_json().encode("utf-8")).hexdigest()


def _command_metadata(command: NodeCommandEnvelope) -> dict[str, str]:
    return {
        "command_id": command.command_id,
        "actor": command.actor,
        "idempotency_key": command.idempotency_key,
        "fingerprint": _command_fingerprint(command),
    }


def _command_result(
    command: NodeCommandEnvelope,
    task_id: str,
    event: LedgerEventEnvelope,
    sequence: int,
    state: str,
    config: NodeApiConfig,
) -> dict[str, Any]:
    return NodeCommandResult(
        outcome="accepted",
        command_id=command.command_id,
        task_id=task_id,
        idempotency_key=command.idempotency_key,
        ledger_event_ref=event.event_id,
        sequence=sequence,
        state=state,
        event_type=event.event_type,
        node_identity=config.node_identity,
        protocol_version=config.protocol_version,
        clearance_context=config.clearance_context,
    ).to_dict()


def _validate_task_id(task_id: str) -> None:
    if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
        raise NodeApiError(400, "task_id_invalid", "The task identifier has an invalid shape.")


def _clearance(value: Any) -> Clearance:
    try:
        return value if isinstance(value, Clearance) else Clearance(value)
    except (TypeError, ValueError) as exc:
        raise NodeApiError(400, "clearance_invalid", "The requested clearance is invalid.") from exc


def _text(payload: dict[str, Any], name: str, maximum: int, *, default: str | None = None) -> str:
    value = payload.get(name, default)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise NodeApiError(400, "field_invalid", f"The field {name} is invalid.")
    return value.strip()


def _optional_text(payload: dict[str, Any], name: str, maximum: int) -> str | None:
    value = payload.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise NodeApiError(400, "field_invalid", f"The field {name} is invalid.")
    return value.strip()


def _text_list(payload: dict[str, Any], name: str, maximum_items: int) -> tuple[str, ...]:
    value = payload.get(name, [])
    if not isinstance(value, list) or len(value) > maximum_items:
        raise NodeApiError(400, "field_invalid", f"The field {name} is invalid.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > 512:
            raise NodeApiError(400, "field_invalid", f"The field {name} is invalid.")
        result.append(item.strip())
    return tuple(result)


def _int_map(value: Any, name: str) -> dict[str, int]:
    if not isinstance(value, dict) or len(value) > 100:
        raise NodeApiError(400, "field_invalid", f"The field {name} is invalid.")
    result: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key) or type(item) is not int or item < 0 or item > 2**31 - 1:
            raise NodeApiError(400, "field_invalid", f"The field {name} is invalid.")
        result[key] = item
    return result


def _bounded_text(value: str, maximum: int) -> str:
    return value if len(value) <= maximum else value[:maximum]


def _title(request: str) -> str:
    first_line = request.splitlines()[0] if request.splitlines() else request
    return _bounded_text(first_line.strip(), 120) or "AirBench task"


def _status_for_state(state: str) -> str:
    return {
        "created": "accepted", "authorized": "accepted", "planned": "planning", "executing": "running",
        "awaiting_check": "needs_review", "awaiting_review": "needs_review", "rendering": "running",
        "deliverable_verified": "needs_review", "complete": "completed", "needs_review": "needs_review",
        "blocked": "blocked", "failed": "failed", "cancelled": "stopped",
    }.get(state, "blocked")


def _phase_for_state(state: str) -> str:
    return {
        "created": "accepted", "authorized": "accepted", "planned": "planning", "executing": "execution",
        "awaiting_check": "verification", "awaiting_review": "review", "rendering": "rendering",
        "deliverable_verified": "review", "complete": "completed", "needs_review": "review",
        "blocked": "blocked", "failed": "failed", "cancelled": "stopped",
    }.get(state, "unknown")


def _event_summary(event: LedgerEventEnvelope) -> str:
    for key in ("summary", "reason", "failure_code", "step_id", "barrier_id"):
        value = event.payload.get(key)
        if isinstance(value, str) and value.strip():
            return _bounded_text(value.strip(), 1_000)
    return f"Ledger recorded {event.event_type}."


def _role(payload: dict[str, Any], default: str) -> str:
    for key in ("role", "worker_id", "tool_name", "capability"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _bounded_text(value.strip(), 256)
    return default


def _label(payload: dict[str, Any], default: str) -> str:
    for key in ("label", "step_id", "model_id", "tool_name", "capability"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _bounded_text(value.strip(), 256)
    return default


def _provenance_ref(provenance: dict[str, Any], event: LedgerEventEnvelope) -> dict[str, Any]:
    source_ref = str(provenance.get("source_ref", "ledger:" + event.event_id))
    return {
        "sourceDocumentId": _bounded_text(source_ref, 512),
        "sourceVersion": _bounded_text(str(provenance.get("source_version", event.event_id)), 256),
        "location": _safe_value(provenance.get("location")) if isinstance(provenance.get("location"), dict) else None,
        "extractionMethod": _bounded_text(str(provenance.get("extraction_method", "ledger-projected")), 256),
        "observedAt": provenance.get("observed_at") if isinstance(provenance.get("observed_at"), str) else None,
        "ingestedAt": provenance.get("ingested_at") if isinstance(provenance.get("ingested_at"), str) else event.occurred_at,
        "ledgerEventRef": event.event_id,
    }


def _confidence(value: Any) -> float:
    if type(value) not in (int, float) or not 0 <= value <= 1:
        return 0.0
    return float(value)


def _input_manifest_ref(events: list[LedgerEventEnvelope]) -> str:
    created = next((event for event in events if event.event_type == "task.created"), None)
    value = created.payload.get("input_manifest_ref") if created else None
    return value if isinstance(value, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_bounded_text(item, 512) for item in value if isinstance(item, str) and item.strip()]


def _resource_plan_values(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("resource_plan")
    source = nested if isinstance(nested, dict) else payload
    values: dict[str, Any] = {}
    admission = source.get("admission")
    if isinstance(admission, str):
        values["admission"] = _bounded_text(admission, 64)
    mode = source.get("execution_mode")
    if isinstance(mode, str):
        values["execution_mode"] = _bounded_text(mode, 64)
    profile_ref = source.get("hardware_profile_ref")
    if isinstance(profile_ref, str) and profile_ref.strip():
        values["hardware_profile_ref"] = _bounded_text(profile_ref, 256)
    reason = source.get("reason")
    if isinstance(reason, str) and reason.strip():
        values["reason"] = _bounded_text(reason, 4_096)
    ceiling = source.get("concurrency_ceiling")
    if type(ceiling) is int and ceiling >= 0:
        values["concurrency_ceiling"] = ceiling
    capabilities = source.get("worker_capabilities")
    if isinstance(capabilities, dict):
        values["worker_capabilities"] = {
            _bounded_text(str(worker), 256): _bounded_text(value, 256)
            for worker, value in list(capabilities.items())[:100]
            if isinstance(worker, str) and isinstance(value, str) and worker.strip() and value.strip()
        }
    return values


def _safe_value(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_text(value, 4_096)
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, depth + 1) for item in list(value)[:100]]
    if isinstance(value, dict):
        return {str(key): _safe_value(item, depth + 1) for key, item in list(value.items())[:100]}
    return "[unsupported]"
