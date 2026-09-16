"""Authenticated local Node API over the deterministic AirBench core.

The API is deliberately a projection and command boundary. It does not itself
run a model, parse a file, execute a tool, or make a network call. Mutating
routes delegate to :class:`contracts.Orchestrator`; read routes project only the
committed local ledger. A ``model.call`` command is merely translated into a
typed request and handed to the orchestrator, which routes it through the
configured backend adapter and records the decision and result.
"""

from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from threading import RLock
from typing import Any, Protocol

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from contracts import (
    AuthorizationError,
    AuthorizationRejected,
    BackendCallError,
    BackendMessage,
    BackendOutputSpec,
    BackendTool,
    CircuitOpen,
    Clearance,
    ContractValidationError,
    LedgerEventEnvelope,
    ModelCallRequest,
    NodeCommandEnvelope,
    NodeCommandResult,
    NodeEvidenceRef,
    NodeFactRef,
    NodeHandshake,
    NodeRouteTrace,
    NodeTaskEvent,
    NodeTaskEventBatch,
    NodeTaskSnapshot,
    NODE_PROTOCOL_COMPATIBILITY_ID,
    NODE_PROTOCOL_VERSION,
    Orchestrator,
    PlanRejected,
    RetryExhausted,
    StepTimeout,
    StorageFailure,
    TaskEnvelope,
    TaskPlanReview,
    TeamPlan,
    TransitionRejected,
    CancellationRequested,
)
from contracts.ids import stable_id
from contracts.provenance.ledger import LedgerError
from .intake_gateway import NodeArtifactDownload, NodeIntakeError, NodeIntakeGateway
from .deliverable_gateway import NodeDeliverableGateway


PROTOCOL_VERSION = NODE_PROTOCOL_VERSION
PROTOCOL_COMPATIBILITY_ID = NODE_PROTOCOL_COMPATIBILITY_ID
MAX_JSON_BODY_BYTES = 1_048_576
MAX_QUERY_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_MULTIPART_BODY_BYTES = MAX_QUERY_UPLOAD_BYTES + 64 * 1024
MAX_EVENT_BATCH = 128
MAX_EVIDENCE_ITEMS = 1_000
MAX_ROUTE_ITEMS = 1_000
BODY_READ_TIMEOUT_S = 120.0
KNOWLEDGE_SEARCH_TASK_ID = "task.knowledge.search"
KNOWLEDGE_SEARCH_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
logger = logging.getLogger(__name__)
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

    def __len__(self) -> int: ...

    def find_by_idempotency(self, key: str) -> LedgerEventEnvelope | None: ...

    def replay(self, task_id: str) -> Any: ...


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
    # Task creation is local intake/planning.  The consequential authority
    # check happens at plan approval; requiring an optional adapter here would
    # strand every task in planning when the adapter is not composed.
    require_orchestrator_authorization: bool = False
    authenticated_roles: tuple[str, ...] = ()

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
        if self.protocol_version != PROTOCOL_VERSION:
            raise ValueError(f"protocol_version must be {PROTOCOL_VERSION}")
        if not NODE_ID_RE.fullmatch(self.node_identity):
            raise ValueError("node_identity has an invalid shape")


def _fact_wire(fact: Any) -> dict[str, Any]:
    return {
        "fact_id": fact.fact_id,
        "value": fact.value,
        "source_ref": fact.source_ref,
        "confidence": fact.confidence,
        "clearance": fact.clearance.value,
        "taint": fact.taint.value,
        "extraction_method": fact.extraction_method,
        "unit": fact.unit,
        "observed_at": fact.observed_at,
        "ingested_at": fact.ingested_at,
        "supersedes_fact_id": fact.supersedes_fact_id,
        "parent_fact_ids": list(fact.parent_fact_ids),
    }


def _image_media_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


class NodeApiService:
    """Owns API authentication and projections, not task authority."""

    def __init__(self, orchestrator: Orchestrator, config: NodeApiConfig, *, intake_gateway: NodeIntakeGateway | None = None, deliverable_gateway: NodeDeliverableGateway | None = None, model_router: Any = None, task_planner: Any = None, retrieval: Any = None, execution: Any = None, knowledge: Any = None, pack: Any = None, world_model: Any = None, consistency: Any = None, autonomy: Any = None, hardware_profile: Any = None, qualification_matrix: Any = None, routing_tiers: Any = None, pid_adapter: Any = None, pid_workspace: Any = None):
        self.orchestrator = orchestrator
        self.config = config
        self.intake_gateway = intake_gateway
        self.deliverable_gateway = deliverable_gateway
        # The router is composed by the server layer and is only consulted for
        # model-call steps.  ``None`` means model serving is not configured.
        self.model_router = model_router
        # The planner is an opt-in Node composition that commits a validated
        # plan (and hardware admission) after authorization.
        self.task_planner = task_planner
        # The retrieval runtime (local BGE embeddings + reranker) is opt-in and
        # consulted by the orchestrator for knowledge steps, never by clients.
        self.retrieval = retrieval
        # The execution coordinator is the Node-owned task runner.  When set,
        # an approved plan is executed by the Node instead of waiting for
        # client-driven model calls.
        self.execution = execution
        # The bulk knowledge ingestion service is opt-in and root-guarded.
        self.knowledge = knowledge
        # The verified domain pack declaration, or ``None`` when not configured.
        self.pack = pack
        # The committed world model graph, or ``None`` when not configured.
        self.world_model = world_model
        # The task-scoped consistency service, or ``None`` when not configured.
        self.consistency = consistency
        # The task-scoped autonomy service, or ``None`` when not configured.
        self.autonomy = autonomy
        # Hardware and qualification projections for the Node settings surface.
        self.hardware_profile = hardware_profile
        self.qualification_matrix = qualification_matrix
        # Declared routing tiers (target_id -> "capable"|"efficient") projected
        # from the signed model roster for display only.
        self.routing_tiers = routing_tiers or {}
        # The P&ID extraction adapter (offline) and its scoped workspace root.
        self.pid_adapter = pid_adapter
        self.pid_workspace = pid_workspace
        self._ledger: LedgerView = orchestrator.store
        self._lock = RLock()
        self._knowledge_search_task_id = KNOWLEDGE_SEARCH_TASK_ID

    def authenticate(self, authorization: str | None) -> str:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise NodeApiError(401, "authentication_required", "A bearer credential is required.", headers={"WWW-Authenticate": "Bearer"})
        token = authorization[7:].strip()
        if not token or not hmac.compare_digest(token, self.config.bearer_token):
            raise NodeApiError(401, "invalid_token", "The bearer credential was not accepted.", headers={"WWW-Authenticate": "Bearer"})
        return self.config.authenticated_subject

    def handshake(self) -> dict[str, Any]:
        return NodeHandshake(
            node_identity=self.config.node_identity,
            protocol_version=self.config.protocol_version,
            protocol_compatibility_id=PROTOCOL_COMPATIBILITY_ID,
            supported_protocol_versions=(PROTOCOL_VERSION,),
            clearance_context=self.config.clearance_context,
            authenticated_subject=self.config.authenticated_subject,
            domain_pack_ref=self.config.domain_pack_ref,
            ledger_event_ref=self.config.handshake_ledger_event_ref,
        ).to_dict()

    def health(self) -> dict[str, Any]:
        # Read-only ledger projection; never serialized behind the command
        # lock so health probes stay responsive during long executions.
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

    def query_upload(self, subject: str, *, task_id: str, file_name: str, content: bytes) -> dict[str, Any]:
        with self._lock:
            gateway = self._require_intake_gateway()
            try:
                return gateway.query_upload(
                    subject=subject,
                    task_id=task_id,
                    file_name=file_name,
                    content=content,
                )
            except NodeIntakeError as exc:
                raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

    def safe_preview(self, preview_ref: str) -> dict[str, Any]:
        gateway = self._require_intake_gateway()
        try:
            return gateway.preview(preview_ref=preview_ref)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

    def intake_status(self, intake_id: str) -> dict[str, Any]:
        gateway = self._require_intake_gateway()
        try:
            return gateway.status(intake_id=intake_id)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

    def pid_extract(self, subject: str, *, task_id: str, file_name: str, content: bytes) -> dict[str, Any]:
        from hashlib import sha256
        from pathlib import Path

        from contracts import Taint, build_event, idempotency_key, stable_id

        from airbench.intake.pid.adapter import PidAdapterError

        # Phase 1: acquire lock only for validation and intake — NOT for the
        # slow adapter execution (P2 audit fix: adapter.process runs outside lock).
        with self._lock:
            task = self._visible_task(task_id)
            if task.principal_id != subject:
                raise NodeApiError(403, "principal_mismatch", "The upload principal does not match the task principal.")
            adapter = self._require_pid()
            media_type = _image_media_type(content)
            if media_type is None:
                raise NodeApiError(415, "pid_unsupported_media", "The P&ID route accepts PNG or JPEG page images.")

            # Production composition must enter through the single File Intake
            # Layer. The no-gateway branch remains only for isolated adapter
            # tests that intentionally exercise the adapter seam.
            intake_manifest = None
            intake_page = None
            if self.intake_gateway is not None:
                try:
                    uploaded = self.intake_gateway.query_upload(
                        subject=subject, task_id=task_id, file_name=file_name, content=content,
                    )
                    intake_id = str(uploaded["intake_id"])
                    intake_manifest, intake_page, page_bytes = self.intake_gateway.read_rendered_page_for_adapter(
                        intake_id=intake_id,
                    )
                    content = page_bytes
                    media_type = intake_page.media_type
                    # ``PageRecord.content_hash`` is the semantic evidence hash
                    # for the extracted page.  The visual adapter validates the
                    # exact governed bytes it receives, so its contract must use
                    # the byte hash of the selected rendered/source page.
                    content_hash = sha256(content).hexdigest()
                    revision_id = intake_manifest.revision_id
                    source_ref = intake_manifest.source_ref
                except NodeIntakeError as exc:
                    raise NodeApiError(exc.status_code, exc.code, exc.message) from exc
            else:
                content_hash = sha256(content).hexdigest()
                intake_id = stable_id("pid-intake", task_id, content_hash)
                revision_id = stable_id("pid-revision", task_id, content_hash)
                source_ref = f"query-upload:{task_id}:{file_name}"
            workspace = Path(self.pid_workspace or ".").resolve() / task_id
            # Copy the task clearance before releasing the lock so the adapter
            # call below can use it without re-acquiring self._lock.
            task_clearance = task.clearance
        # ─ Phase 2: adapter.process() runs OUTSIDE self._lock ───────────────
        # The full P&ID pipeline (OCR, symbol detection, topology) can take
        # 10–60 s.  Holding self._lock during that time freezes every other
        # HTTP endpoint including health probes and event polling (P2 fix).
        try:
            record = adapter.process(
                page_bytes=content, media_type=media_type, task_id=task_id, intake_id=intake_id,
                revision_id=revision_id,
                source_ref=source_ref, content_hash=content_hash,
                clearance=task_clearance, taint=Taint.untrusted, workspace=workspace,
            )
        except PidAdapterError as exc:
            status = 503 if exc.code == "adapter_unavailable" else 422
            raise NodeApiError(status, f"pid_{exc.code}", str(exc)) from exc
        # ─ Phase 3: re-acquire lock for the ledger append ────────────────────
        with self._lock:
            payload = record.to_dict()
            event = build_event(
                event_type="pid.extracted", task_id=task_id, actor_id="node.pid", actor_type="service",
                payload_contract="PIDRecord", payload_version="1.0",
                payload={
                    **payload,
                    "provenance": {
                        "source_ref": record.source_ref, "confidence": 0.9,
                        "clearance": task_clearance.value, "taint": Taint.untrusted.value,
                    },
                },
                clearance=task_clearance,
                idempotency=idempotency_key("pid.extracted", task_id, intake_id),
                sequence=len(self._ledger), previous_event_hash=self._ledger.head_hash,
            )
            try:
                self._ledger.append(event)
            except Exception as exc:
                raise NodeApiError(503, "pid_not_committed", "The P&ID extraction record could not be committed.") from exc
            graph_projection = self._commit_pid_candidates(record)
            return {**payload, "ledger_event_ref": event.event_id, "graph": graph_projection}

    def _commit_pid_candidates(self, record: Any) -> dict[str, Any]:
        """Stage P&ID facts and commit only candidates passing local gates."""
        if self.world_model is None:
            return {"status": "unavailable", "committed": 0, "review_required": 0, "candidates": []}
        from airbench.intake.pid.records import candidate_facts_from_pid
        from airbench.knowledge.world_model import CandidateFactWriter, WorldModelError

        candidates = candidate_facts_from_pid(record)
        if not candidates:
            return {"status": "empty", "committed": 0, "review_required": 0, "candidates": []}
        candidate_ids = {candidate.fact.fact_id for candidate in candidates}
        known_ids = {fact.fact_id for fact in self.world_model.facts}

        def consistency_gate(candidate: Any) -> bool:
            return all(
                relation.source_fact_id in candidate_ids | known_ids
                and relation.target_fact_id in candidate_ids | known_ids
                for relation in candidate.relations
            )

        def verification_gate(candidate: Any) -> bool:
            # The adapter may propose facts, but graph visibility requires a
            # bounded confidence floor and explicit source provenance. Taint
            # remains untrusted even after this gate.
            return bool(
                candidate.fact.source_ref
                and candidate.fact.confidence >= 0.65
                and candidate.fact.taint.value == "untrusted"
            )

        writer = CandidateFactWriter(
            self.world_model,
            consistency_gate=consistency_gate,
            verification_gate=verification_gate,
            ledger=self._ledger,
        )
        committed: list[str] = []
        review_required: list[str] = []
        failed: list[dict[str, str]] = []
        for candidate in candidates:
            writer.stage(candidate)
        for candidate in candidates:
            try:
                writer.reconcile(candidate.candidate_id, review_floor=0.65)
                committed.append(candidate.fact.fact_id)
            except WorldModelError as exc:
                if exc.code == "review_required":
                    review_required.append(candidate.candidate_id)
                else:
                    failed.append({"candidate_id": candidate.candidate_id, "code": exc.code})
        status = "committed" if committed and not review_required and not failed else "needs_review" if review_required else "failed" if failed else "empty"
        return {
            "status": status,
            "committed": len(committed),
            "review_required": len(review_required),
            "failed": failed,
            "candidates": [candidate.candidate_id for candidate in candidates],
        }

    def _require_pid(self) -> Any:
        if self.pid_adapter is None:
            raise NodeApiError(503, "pid_unavailable", "The P&ID extraction adapter is not configured.")
        return self.pid_adapter

    def knowledge_status(self) -> dict[str, Any]:
        runtime = self.retrieval
        graph = self.graph_status()
        if runtime is None:
            return {"configured": graph["configured"], "status": "ready" if graph["configured"] else "disabled", "indexed_chunks": 0, "graph": graph}
        store = getattr(runtime.index, "store", None)
        response = {
            "configured": True,
            "status": "ready",
            "embedding_model": runtime.embedding_model_id,
            "embedding_qualification_reference": runtime.embedding_qualification_reference,
            "reranker_model": runtime.reranker_model_id,
            "reranker_qualification_reference": runtime.reranker_qualification_reference,
            "indexed_chunks": len(runtime.index.chunks),
            "vector_store": type(store).__name__ if store is not None else "json",
            "graph": graph,
        }
        count = getattr(store, "chunk_count", None)
        if isinstance(count, int):
            response["store_chunk_count"] = count
        return response

    def pack_status(self) -> dict[str, Any]:
        if self.pack is None:
            return {"configured": False, "status": "disabled"}
        return {"configured": True, "status": "ready", **self.pack.to_dict()}

    def graph_status(self) -> dict[str, Any]:
        world = self.world_model
        if world is None:
            return {"configured": False, "status": "disabled"}
        backend = getattr(world, "_backend", None)
        return {
            "configured": True,
            "status": "ready",
            "node_count": len(world.facts),
            "edge_count": len(world.relations),
            "review_queue_count": len(world.review_queue),
            "backend": type(backend).__name__ if backend is not None else "json",
        }

    def graph_query(self, payload: dict[str, Any]) -> dict[str, Any]:
        from airbench.knowledge.world_model import WorldModelQuery

        world = self._require_world_model()
        clearance = _clearance(payload.get("clearance")) if payload.get("clearance") is not None else self.config.clearance_context
        self._check_clearance(clearance)
        limit = payload.get("limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
            raise NodeApiError(422, "invalid_limit", "limit must be between 1 and 200.")
        max_depth = payload.get("max_depth", 1)
        if not isinstance(max_depth, int) or isinstance(max_depth, bool) or not 0 <= max_depth <= 5:
            raise NodeApiError(422, "invalid_limit", "max_depth must be between 0 and 5.")
        facts = world.query(WorldModelQuery(
            # Graph reads are consequential because they create a provenance
            # event. Reuse the Node-owned search task lifecycle so the event
            # has a valid task.created predecessor in the append-only ledger.
            task_id=self._ensure_knowledge_search_task(),
            key=str(payload.get("key", ""))[:256],
            clearance=clearance,
            limit=limit,
            entity_id=str(payload.get("entity_id", ""))[:256],
            relation=str(payload.get("relation", ""))[:128],
            max_depth=max_depth,
            as_of=str(payload["as_of"])[:64] if payload.get("as_of") else None,
        ))
        return {"result_count": len(facts), "facts": [_fact_wire(fact) for fact in facts]}

    def graph_review_queue(self) -> dict[str, Any]:
        world = self._require_world_model()
        return {
            "count": len(world.review_queue),
            "items": [
                {
                    "candidate_id": item.candidate.candidate_id,
                    "fact_id": item.candidate.fact.fact_id,
                    "reason": item.reason,
                    "enqueued_at": item.enqueued_at,
                    "confidence": item.candidate.fact.confidence,
                    "clearance": item.candidate.fact.clearance.value,
                    "source_ref": item.candidate.fact.source_ref,
                }
                for item in world.review_queue
            ],
        }

    def graph_resolve_review(self, subject: str, payload: dict[str, Any]) -> dict[str, Any]:
        world = self._require_world_model()
        candidate_id = _text(payload, "candidate_id", 256)
        accept = payload.get("accept")
        if not isinstance(accept, bool):
            raise NodeApiError(422, "invalid_decision", "accept must be a boolean.")
        item = next((entry for entry in world.review_queue if entry.candidate.candidate_id == candidate_id), None)
        if item is None:
            raise NodeApiError(404, "review_not_found", "The review item does not exist.")
        self._check_clearance(item.candidate.fact.clearance)
        fact = world.resolve_review(candidate_id, accept=accept, actor_id=subject)
        return {"candidate_id": candidate_id, "decision": "accept" if accept else "reject", "fact_id": fact.fact_id if fact else None}

    def _require_world_model(self) -> Any:
        if self.world_model is None:
            raise NodeApiError(503, "world_model_unavailable", "The world model graph is not configured.")
        return self.world_model

    def consistency_report(self, task_id: str) -> dict[str, Any]:
        self._require_task(task_id)
        return self._require_consistency().latest(task_id)

    def consistency_evaluate(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from .consistency_gateway import ConsistencyServiceError

        service = self._require_consistency()
        self._require_task(task_id)
        features_raw = payload.get("features", {})
        if not isinstance(features_raw, dict) or len(features_raw) > 100:
            raise NodeApiError(422, "invalid_features", "features must be an object of at most 100 entries.")
        material_raw = payload.get("material_features")
        material: tuple[str, ...] | None = None
        if material_raw is not None:
            if not isinstance(material_raw, list) or len(material_raw) > 100:
                raise NodeApiError(422, "invalid_features", "material_features must be a list.")
            material = tuple(str(item) for item in material_raw)
        clearance = _clearance(payload.get("clearance")) if payload.get("clearance") is not None else self.config.clearance_context
        self._check_clearance(clearance)
        try:
            return service.evaluate(
                task_id=task_id,
                decision_id=_text(payload, "decision_id", 128),
                decision_type=_text(payload, "decision_type", 128),
                object_id=_text(payload, "object_id", 256),
                features={str(key): str(value) for key, value in features_raw.items()},
                decision=_text(payload, "decision", 256),
                rule_ref=_text(payload, "rule_ref", 256, default=""),
                authority=_text(payload, "authority", 128, default=""),
                clearance=clearance,
                material_features=material,
            )
        except ConsistencyServiceError as exc:
            raise NodeApiError(409, exc.code, str(exc)) from exc

    def consistency_justify(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from .consistency_gateway import ConsistencyServiceError

        service = self._require_consistency()
        self._require_task(task_id)
        try:
            return service.justify(
                task_id=task_id, operator_id=subject, justification=_text(payload, "justification", 4_000),
            )
        except ConsistencyServiceError as exc:
            raise NodeApiError(409, exc.code, str(exc)) from exc
        except (StorageFailure, LedgerError) as exc:
            raise NodeApiError(503, "transition_not_committed", "The justification could not be committed to the ledger.") from exc

    def _require_consistency(self) -> Any:
        if self.consistency is None:
            raise NodeApiError(503, "consistency_unavailable", "The consistency service is not configured.")
        return self.consistency

    def autonomy_records(self, task_id: str) -> dict[str, Any]:
        self._require_task(task_id)
        service = self._require_autonomy()
        return {"task_id": task_id, "decisions": list(service.decisions(task_id)), "is_blocked": service.is_blocked(task_id)}

    def autonomy_score(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Score an autonomy action.  ``subject`` is the authenticated caller and
        must match the task principal (M2 audit fix: unauthenticated scoring path).
        The ``worker_id`` is bound to ``subject`` rather than taken from the
        client payload to prevent privilege escalation.
        """
        from contracts import Taint

        from .autonomy_gateway import AutonomyServiceError

        with self._lock:
            service = self._require_autonomy()
            task = self._require_task(task_id)
            # Verify the authenticated caller is the task principal (M2 fix).
            if getattr(task, "principal_id", None) != subject:
                raise NodeApiError(403, "principal_mismatch", "The authenticated subject is not the task principal.")
            clearance = _clearance(payload.get("clearance")) if payload.get("clearance") is not None else self.config.clearance_context
            self._check_clearance(clearance)
            try:
                taint = Taint(str(payload.get("taint", "untrusted")))
            except ValueError as exc:
                raise NodeApiError(422, "invalid_taint", "taint is invalid.") from exc
            confidence = payload.get("confidence", 1.0)
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                raise NodeApiError(422, "invalid_confidence", "confidence must be between 0 and 1.")
            # Bind worker_id to the authenticated subject — reject a payload-supplied
            # worker_id that differs to prevent cross-task privilege escalation (M2 fix).
            worker_id = subject[:128]
            try:
                return service.score(
                    task_id=task_id,
                    action_id=_text(payload, "action_id", 128),
                    action_kind=_text(payload, "action_kind", 128),
                    source_ref=_text(payload, "source_ref", 512),
                    confidence=float(confidence),
                    clearance=clearance,
                    taint=taint,
                    worker_id=worker_id,
                    claimed_risk=str(payload["claimed_risk"])[:128] if payload.get("claimed_risk") else None,
                    target_object_id=str(payload.get("target_object_id", ""))[:256],
                )
            except AutonomyServiceError as exc:
                raise NodeApiError(409, exc.code, str(exc)) from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the score decision.") from exc

    def autonomy_authorize(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        from .autonomy_gateway import AutonomyServiceError

        with self._lock:
            service = self._require_autonomy()
            self._require_task(task_id)
            try:
                return service.authorize(
                    task_id=task_id,
                    operator_id=subject,
                    action_id=str(payload.get("action_id", ""))[:128],
                    operator_roles=self.config.authenticated_roles,
                )
            except AutonomyServiceError as exc:
                raise NodeApiError(409, exc.code, str(exc)) from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the task authorization.") from exc

    def _require_autonomy(self) -> Any:
        if self.autonomy is None:
            raise NodeApiError(503, "autonomy_unavailable", "The autonomy service is not configured.")
        return self.autonomy

    def hardware_status(self) -> dict[str, Any]:
        if self.hardware_profile is None:
            return {"configured": False, "status": "disabled"}
        from .hardware_gateway import hardware_status

        return {"configured": True, "status": "ready", **hardware_status(self.hardware_profile)}

    def qualification_status(self, target_id: str) -> dict[str, Any]:
        if self.qualification_matrix is None:
            return {"target_id": target_id, "status": "unavailable", "certificates": []}
        from .qualification_gateway import qualification_status

        return qualification_status(self.qualification_matrix, target_id, self.routing_tiers)

    def qualification_roster(self) -> dict[str, Any]:
        if self.qualification_matrix is None:
            return {"configured": False, "count": 0, "targets": []}
        from .qualification_gateway import qualification_roster

        return {"configured": True, **qualification_roster(self.qualification_matrix, self.routing_tiers)}

    def _require_task(self, task_id: str) -> str:
        self._visible_task(task_id)
        return self.orchestrator.state(task_id)

    def knowledge_search(self, payload: dict[str, Any]) -> dict[str, Any]:
        from airbench.knowledge.retrieval import RetrievalRequest
        from airbench.knowledge.retrieval_loop import RetrievalLoopRequest, run_iterative_retrieval
        from airbench.knowledge.world_model import WorldModelQuery

        mode = payload.get("mode", "text")
        if mode not in {"text", "graph", "hybrid"}:
            raise NodeApiError(422, "invalid_search_mode", "mode must be text, graph, or hybrid.")
        runtime = self.retrieval
        if mode in {"text", "hybrid"} and runtime is None:
            raise NodeApiError(503, "retrieval_unavailable", "The local retrieval service is not configured.")
        if mode in {"graph", "hybrid"} and self.world_model is None:
            raise NodeApiError(503, "world_model_unavailable", "The world model graph is not configured.")
        search_task_id = self._ensure_knowledge_search_task()
        query = _text(payload, "query", 4096)
        clearance = _clearance(payload.get("clearance")) if payload.get("clearance") is not None else self.config.clearance_context
        self._check_clearance(clearance)
        top_k = payload.get("top_k", 5)
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
            raise NodeApiError(422, "invalid_limit", "top_k must be between 1 and 20.")
        citations: tuple[Any, ...] = ()
        iterative = bool(payload.get("iterative", False)) and mode in {"text", "hybrid"}
        if iterative:
            max_rounds = payload.get("max_rounds", 2)
            if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or not 1 <= max_rounds <= 5:
                raise NodeApiError(422, "invalid_limit", "max_rounds must be between 1 and 5.")
            citations = run_iterative_retrieval(
                runtime.service,
                RetrievalLoopRequest(
                    task_id=search_task_id, query=query, clearance=clearance, top_k=top_k, max_rounds=max_rounds,
                ),
            )
        else:
            raw_min = payload.get("min_score")
            if raw_min is not None and (isinstance(raw_min, bool) or not isinstance(raw_min, (int, float))):
                raise NodeApiError(422, "invalid_limit", "min_score must be a number.")
            citations = runtime.service.search(RetrievalRequest(
                task_id=search_task_id, query=query, clearance=clearance, top_k=top_k,
                min_score=float(raw_min) if raw_min is not None else None,
            ))
        graph_results: tuple[Any, ...] = ()
        if mode in {"graph", "hybrid"}:
            graph_limit = min(top_k, 20)
            max_depth = payload.get("max_depth", 1)
            if not isinstance(max_depth, int) or isinstance(max_depth, bool) or not 0 <= max_depth <= 5:
                raise NodeApiError(422, "invalid_limit", "max_depth must be between 0 and 5.")
            graph_results = self.world_model.query(WorldModelQuery(
                task_id=search_task_id,
                key=str(payload.get("key", query))[:256],
                clearance=clearance,
                limit=graph_limit,
                entity_id=str(payload.get("entity_id", ""))[:256],
                relation=str(payload.get("relation", ""))[:128],
                max_depth=max_depth,
                as_of=str(payload["as_of"])[:64] if payload.get("as_of") else None,
            ))
        return {
            "query": query,
            "mode": mode,
            "clearance": clearance.value,
            "iterative": iterative,
            "found": len(citations) > 0,
            "result_count": len(citations),
            "results": [
                {
                    "citation_id": citation.citation_id,
                    "chunk_id": citation.chunk_id,
                    "source_ref": citation.source_ref,
                    "revision_id": citation.revision_id,
                    "page_id": citation.page_id,
                    "source_span": citation.source_span,
                    "excerpt": citation.excerpt,
                    "score": citation.score,
                    "confidence": citation.confidence,
                    "clearance": citation.clearance.value,
                    "taint": citation.taint.value,
                    "content_hash": citation.content_hash,
                    "embedding_model": citation.embedding_model,
                    "reranker_model": citation.reranker_model,
                }
                for citation in citations
            ],
            "graph_result_count": len(graph_results),
            "graph_results": [_fact_wire(fact) for fact in graph_results],
        }

    def _ensure_knowledge_search_task(self) -> str:
        """Return a resting Node-owned ledger subject for search events.

        Knowledge search is a synchronous projection rather than a resumable
        user task. A subject that was interrupted and explicitly failed by a
        previous startup is never reused, while a subject with committed
        search events remains reusable across ordinary Node restarts.
        """
        with self._lock:
            task_ids = list(dict.fromkeys(
                event.task_id for event in self._ledger.events
                if event.task_id == KNOWLEDGE_SEARCH_TASK_ID
                or event.task_id.startswith(f"{KNOWLEDGE_SEARCH_TASK_ID}.")
            ))
            for task_id in reversed(task_ids):
                if self.orchestrator.state(task_id) not in KNOWLEDGE_SEARCH_TERMINAL_STATES:
                    self._knowledge_search_task_id = task_id
                    return task_id

            if task_ids:
                suffixes = [
                    int(task_id.rsplit(".", 1)[1])
                    for task_id in task_ids
                    if task_id.rsplit(".", 1)[-1].isdigit()
                ]
                next_suffix = max(suffixes, default=0) + 1
                task_id = f"{KNOWLEDGE_SEARCH_TASK_ID}.{next_suffix}"
            else:
                task_id = KNOWLEDGE_SEARCH_TASK_ID
            try:
                self.orchestrator.create_task(
                    principal_id=self.config.authenticated_subject,
                    clearance=self.config.clearance_context,
                    request="Node-owned knowledge search",
                    domain_pack_ref=self.config.domain_pack_ref,
                    risk_class="low",
                    autonomy_ceiling="system",
                    allowed_evidence_scope=("knowledge-search",),
                    output_contract="cited-evidence",
                    task_id=task_id,
                )
            except (StorageFailure, LedgerError) as exc:
                if self._ledger.replay(task_id).state == "absent":
                    raise NodeApiError(503, "knowledge_search_not_committed", "The knowledge-search ledger subject could not be committed.") from exc
            self._knowledge_search_task_id = task_id
            return task_id

    def knowledge_ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.knowledge is None:
            raise NodeApiError(503, "knowledge_ingest_unavailable", "Bulk knowledge ingestion is not configured.")
        path = _text(payload, "path", 4096, default=".")
        try:
            return self.knowledge.ingest_directory(path=path)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

    def artifact_preview(self, artifact_id: str) -> dict[str, Any]:
        if self.deliverable_gateway is not None:
            try:
                return self.deliverable_gateway.artifact_preview(artifact_id=artifact_id)
            except NodeIntakeError as exc:
                if exc.code not in {"deliverable_not_found", "invalid_reference"}:
                    raise NodeApiError(exc.status_code, exc.code, exc.message) from exc
        gateway = self._require_intake_gateway()
        try:
            return gateway.artifact_preview(artifact_id=artifact_id)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

    def artifact_download(self, artifact_id: str) -> NodeArtifactDownload:
        if self.deliverable_gateway is not None:
            try:
                return self.deliverable_gateway.download(artifact_id=artifact_id)
            except NodeIntakeError as exc:
                if exc.code not in {"deliverable_not_found", "invalid_reference"}:
                    raise NodeApiError(exc.status_code, exc.code, exc.message) from exc
        gateway = self._require_intake_gateway()
        try:
            return gateway.download(artifact_id=artifact_id)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

    def _require_intake_gateway(self) -> NodeIntakeGateway:
        if self.intake_gateway is None:
            raise NodeApiError(503, "intake_unavailable", "The local File Intake service is not configured.")
        return self.intake_gateway

    def _require_visible_deliverable(self, task_id: str, artifact_id: str) -> None:
        """Bind a sign-off command to the task's current committed deliverable.

        M3 audit fix: when the deliverable gateway is absent we must raise
        rather than silently return, because the ownership check is a security
        gate — an operator must not be able to approve an arbitrary artifact_id
        string when no gateway is present to verify it belongs to this task.
        """
        if self.deliverable_gateway is None:
            raise NodeApiError(
                503, "deliverable_unavailable",
                "The deliverable gateway is not configured. Artifact sign-off requires a configured delivery service.",
            )
        try:
            review = self.deliverable_gateway.artifact_review(task_id=task_id)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc
        committed = review.get("artifact_id") or review.get("artifactId")
        if committed != artifact_id:
            raise NodeApiError(409, "artifact_mismatch", "The artifact does not belong to this task's current deliverable.")
        blockers = review.get("approval_blocking_reasons") or review.get("approvalBlockingReasons") or ()
        if blockers:
            raise NodeApiError(409, "artifact_blocked", "The deliverable still has unresolved verification blockers.")

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
                # A new command must create a new task even when its natural
                # language request is identical to an earlier one. Retries
                # still replay above by idempotency key, so this remains
                # deterministic for one command without colliding across
                # distinct user submissions.
                task_id=stable_id("task.command", command.idempotency_key),
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
            # Text-only requests use the same File Intake Layer as files. The
            # request is untrusted evidence and is committed before planning.
            if arguments.get("input_kind") == "text" and not input_manifest_refs:
                if self.intake_gateway is not None:
                    try:
                        self.intake_gateway.query_upload(
                            subject=subject, task_id=task.task_id, file_name="task-input.txt", content=request.encode("utf-8")
                        )
                    except NodeIntakeError as exc:
                        raise NodeApiError(exc.status_code, exc.code, exc.message) from exc
                else:
                    # Create a minimal evidence.created event directly in the ledger
                    # so that execution.prepare() can find it when File Intake is not configured.
                    from contracts import Taint, build_event, idempotency_key
                    import hashlib
                    source_hash = f"sha256:{hashlib.sha256(request.encode('utf-8')).hexdigest()}"
                    intake_id = stable_id("intake", task.task_id, source_hash, "text")
                    revision_id = stable_id("revision", task.task_id, source_hash)
                    ingested_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    key = idempotency_key("intake.evidence.created", task.task_id, intake_id)
                    existing = next((e for e in self._ledger.events if e.idempotency_key == key), None)
                    if existing is None:
                        event = build_event(
                            event_type="evidence.created",
                            task_id=task.task_id,
                            actor_id="intake.layer",
                            actor_type="service",
                            payload_contract="IntakeManifest",
                            payload_version="1.0",
                            payload={
                                "intake_id": intake_id,
                                "revision_id": revision_id,
                                "manifest_hash": hashlib.sha256(f"{intake_id}:{revision_id}:{source_hash}".encode()).hexdigest(),
                                "source_hash": source_hash,
                                "page_ids": [f"page-{intake_id}-1"],
                                "source_artifact_ref": None,
                                "manifest_artifact_ref": None,
                                "rendered_page_refs": [],
                                "destination": "query-upload",
                                "trust_profile": "standard",
                                "latency_profile": "interactive",
                                "provenance": {
                                    "source_ref": f"query-upload:{task.task_id}:task-input.txt",
                                    "confidence": 1.0,
                                    "clearance": task.clearance.value,
                                    "taint": Taint.untrusted.value,
                                },
                            },
                            clearance=task.clearance,
                            idempotency=key,
                            sequence=len(self._ledger.events),
                            previous_event_hash=self._ledger.head_hash,
                            occurred_at=ingested_at,
                        )
                        try:
                            self._ledger.append(event)
                        except Exception as exc:
                            raise NodeApiError(503, "intake_evidence_failed", "Text intake evidence could not be committed.") from exc
            snapshot = self.snapshot(task.task_id)
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
            if self.task_planner is not None:
                try:
                    self.task_planner.plan_and_admit(self._visible_task(task_id))
                except (PlanRejected, TransitionRejected) as exc:
                    raise NodeApiError(409, "task_planning_rejected", "The Node could not commit a validated plan for this task.") from exc
                except (StorageFailure, LedgerError) as exc:
                    raise NodeApiError(503, "task_planning_failed", "The local ledger did not commit the task plan.") from exc
            else:
                # No task planner configured — auto-commit a minimal plan so the task
                # can proceed to approval and execution without stalling the planning phase.
                # This is the PL1 fix: without this the UI "planning" spinner never resolves.
                try:
                    self._auto_plan_and_admit(task_id)
                except (StorageFailure, LedgerError) as exc:
                    raise NodeApiError(503, "task_planning_failed", "The auto-plan commit could not be written to the local ledger.") from exc
            if self.execution is not None:
                from .task_execution import NodeTaskExecutionError
                try:
                    self.execution.prepare(task_id)
                except NodeTaskExecutionError as exc:
                    logger.exception("Node task execution failed", extra={"task_id": task_id})
                    if self.orchestrator.state(task_id) not in {"failed", "cancelled"}:
                        self.orchestrator.transition(task_id, "task.failed", {
                            "failure_code": getattr(exc, "failure_code", "task_execution_prepare_failed")})
                    raise NodeApiError(409, "task_execution_prepare_failed", "The Node could not prepare the admitted plan for execution.") from exc
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
            if review["plan_state"] not in {"ready", "ready_no_hardware"}:
                raise NodeApiError(409, "plan_not_approvable", "The Node has not produced an approvable plan and hardware admission.")
            # Phase 1 model-lane preflight: the approval must not be committed
            # when no ready, qualified model lane can serve the worker step.
            # The task stays plan-ready so the operator can retry once the
            # remote containers and SSH tunnel are healthy.
            if self.execution is not None:
                from .task_execution import ModelLaneNotReady
                try:
                    self.execution.preflight(task_id)
                except ModelLaneNotReady as exc:
                    raise NodeApiError(
                        503, "model_lane_not_ready",
                        "The required model lane is not ready. Start the remote vLLM containers and open the SSH tunnel, "
                        f"then retry the approval. Routing reason: {exc.reason}",
                    ) from exc
            # Autonomy preflight: the operator's approval is the named human
            # authority the governor requires for work inherited from untrusted
            # input.  It is recorded BEFORE the approval is committed, so a
            # role gap is a typed authorization failure and the plan stays
            # approvable once the operator holds the required role (roadmap
            # Phase 3: commit approval only after preflight succeeds).
            # H5 audit fix: use callable(getattr(…)) instead of hasattr to
            # guard against accidental attribute presence from subclasses or
            # monkey-patching that is not a valid authorize implementation.
            if self.execution is not None and self.autonomy is not None and callable(getattr(self.execution, "authorize", None)):
                from .autonomy_gateway import AutonomyServiceError

                required_role = getattr(self.pack, "required_human_authority", "human_reviewer") if self.pack else "human_reviewer"
                if required_role not in self.config.authenticated_roles:
                    raise NodeApiError(403, "human_authority_role_required", f"The authenticated operator is not assigned the pack-required {required_role} role.")
                try:
                    self.execution.authorize(subject, task_id, operator_roles=self.config.authenticated_roles)
                except AutonomyServiceError as exc:
                    raise NodeApiError(
                        403, "autonomy_authority_insufficient",
                        f"The operator does not hold the authority this task's execution action requires ({exc}). "
                        "Restart the Node with the required operator role and retry the approval.",
                    ) from exc
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
        # The full team execution (model calls, verification, rendering) runs
        # OUTSIDE the command lock: holding it here froze every other endpoint
        # (including health/readiness) for the whole execution. The orchestrator
        # ledger remains the authority for concurrent state transitions.
        if self.execution is not None:
            from .task_execution import NodeTaskExecutionError
            try:
                self.execution.execute(task_id)
            except NodeTaskExecutionError as exc:
                logger.exception("Node task execution failed", extra={"task_id": task_id})
                # C6 audit fix: orchestrator.transition must be called under
                # self._lock even though execute() runs outside it, because a
                # concurrent cancel/stop request could otherwise race the ledger
                # append and produce two concurrent terminal transitions.
                with self._lock:
                    if self.orchestrator.state(task_id) not in {"failed", "cancelled"}:
                        self.orchestrator.transition(task_id, "task.failed", {
                            "failure_code": getattr(exc, "failure_code", "task_execution_failed")})
                raise NodeApiError(503, "task_execution_failed", "The approved plan did not produce a verified draft.") from exc
            except Exception as exc:  # noqa: BLE001 - Phase 3: unexpected failures become typed terminal states
                logger.exception("Node task execution hit an unexpected failure", extra={"task_id": task_id})
                with self._lock:
                    if self.orchestrator.state(task_id) not in {"failed", "cancelled"}:
                        self.orchestrator.transition(task_id, "task.failed", {
                            "failure_code": "task_execution_internal_error"})
                raise NodeApiError(503, "task_execution_internal_error",
                                   "The approved plan hit an unexpected internal failure. The task was moved to a "
                                   "terminal failed state instead of leaving a partial commit.") from exc
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

    def approve_artifact(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Record a human sign-off approval for a deliverable artifact.

        The command envelope must carry ``artifact_id`` and ``reason`` in its
        ``arguments`` field.  On success the orchestrator commits a
        ``human.signoff`` event and the task transitions back to
        ``deliverable_verified``.
        """
        with self._lock:
            command = self._command(subject, payload, "task.approve_artifact", task_id)
            self._visible_task(task_id)
            existing = self._existing_command(command)
            if existing is not None:
                return _command_result(command, task_id, existing, self._task_sequence(task_id, existing.event_id), self.orchestrator.state(task_id), self.config)
            self._check_expected_sequence(command, task_id)
            artifact_id = _text(command.arguments, "artifact_id", 512)
            reason = _text(command.arguments, "reason", 4_096)
            self._require_visible_deliverable(task_id, artifact_id)
            if self.consistency is not None and self.consistency.is_blocked(task_id):
                raise NodeApiError(
                    409, "consistency_review_required",
                    "A flagged consistency deviation requires an operator justification before approval.",
                )
            try:
                result = self.orchestrator.signoff(
                    self._visible_task(task_id).task_id,
                    artifact_id=artifact_id,
                    decision="approved",
                    reason=reason,
                    command_metadata=_command_metadata(command),
                )
            except TransitionRejected as exc:
                raise NodeApiError(409, "transition_rejected", "The artifact cannot be approved from the current task state.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the artifact approval.") from exc
            return _command_result(command, task_id, self._event_by_id(result.event_id), self._task_sequence(task_id, result.event_id), result.state, self.config)

    def return_artifact(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a deliverable artifact for revision.

        The command envelope must carry ``artifact_id`` and ``reason`` in its
        ``arguments`` field.  On success the orchestrator commits a second
        ``human.review.required`` event, keeping the task in ``awaiting_review``
        for another review cycle without altering any other pipeline state.
        """
        with self._lock:
            command = self._command(subject, payload, "task.return_artifact", task_id)
            self._visible_task(task_id)
            existing = self._existing_command(command)
            if existing is not None:
                return _command_result(command, task_id, existing, self._task_sequence(task_id, existing.event_id), self.orchestrator.state(task_id), self.config)
            self._check_expected_sequence(command, task_id)
            artifact_id = _text(command.arguments, "artifact_id", 512)
            reason = _text(command.arguments, "reason", 4_096)
            self._require_visible_deliverable(task_id, artifact_id)
            try:
                result = self.orchestrator.signoff(
                    self._visible_task(task_id).task_id,
                    artifact_id=artifact_id,
                    decision="revision_requested",
                    reason=reason,
                    command_metadata=_command_metadata(command),
                )
            except TransitionRejected as exc:
                raise NodeApiError(409, "transition_rejected", "The artifact cannot be returned from the current task state.") from exc
            except (StorageFailure, LedgerError) as exc:
                raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the artifact return.") from exc
            return _command_result(command, task_id, self._event_by_id(result.event_id), self._task_sequence(task_id, result.event_id), result.state, self.config)

    def _require_model_router(self) -> Any:
        if self.model_router is None:
            raise NodeApiError(503, "model_serving_unavailable", "Model serving is not configured on this Node.")
        return self.model_router

    def call_model(self, subject: str, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one typed model call through the orchestrator and router.

        The API is only the command boundary: routing, admission, retry,
        timeout, and ledger writes stay inside the orchestrator.  The model
        response is a proposal with untrusted provenance, never an approved
        result, and prompt/response text is never written to the ledger.
        """
        with self._lock:
            command = self._command(subject, payload, "model.call", task_id)
            task = self._visible_task(task_id)
            arguments = command.arguments

            raw_request = arguments.get("request")
            if not isinstance(raw_request, dict):
                raise NodeApiError(400, "model_request_invalid", "A model call request object is required.")
            try:
                request = ModelCallRequest.from_dict(dict(raw_request))
            except (ContractValidationError, TypeError) as exc:
                raise NodeApiError(400, "model_request_invalid", "The model call request does not satisfy the contract.") from exc
            if request.task_id != task_id:
                raise NodeApiError(400, "command_target_invalid", "The model request task must match the route.")
            if request.clearance != task.clearance:
                raise NodeApiError(409, "model_request_rejected", "The model request clearance must match the task clearance.")
            request = replace(
                request,
                request_id=stable_id("model-call-request", task_id, command.idempotency_key),
            )

            raw_messages = arguments.get("messages")
            if not isinstance(raw_messages, list) or not 1 <= len(raw_messages) <= 64:
                raise NodeApiError(400, "model_messages_invalid", "One to sixty-four messages are required.")
            try:
                messages = tuple(BackendMessage.from_dict(dict(item)) for item in raw_messages)
                output = BackendOutputSpec.from_dict(dict(arguments.get("output", {"mode": "text"})))
                raw_tools = arguments.get("tools", [])
                if not isinstance(raw_tools, list) or len(raw_tools) > 32:
                    raise NodeApiError(400, "model_tools_invalid", "At most thirty-two tools may be declared.")
                tools = tuple(BackendTool.from_dict(dict(item)) for item in raw_tools)
            except (ContractValidationError, TypeError) as exc:
                raise NodeApiError(400, "model_messages_invalid", "The model call messages do not satisfy the contract.") from exc
            if arguments.get("stream") not in (None, False):
                raise NodeApiError(400, "model_stream_unsupported", "Streaming model calls are not served by this route.")

            existing = self._replay_model_call(command, task_id, request.request_id)
            if existing is not None:
                return existing
            self._check_expected_sequence(command, task_id)

            hardware_profile_ref = _text(arguments, "hardware_profile_ref", 512)
            router = self._require_model_router()
        # The model HTTP call runs OUTSIDE the command lock so a slow backend
        # cannot freeze every other endpoint for the adapter timeout duration.
        # Concurrent duplicate commands are rejected by the orchestrator's
        # ledger state machine (TransitionRejected / IdempotencyConflict).
        try:
            execution = self.orchestrator.execute_model_call(
                request, router=router, pack_ref=task.domain_pack_ref,
                hardware_profile_ref=hardware_profile_ref,
                messages=messages, output=output, tools=tools, stream=False,
            )
        except PlanRejected as exc:
            raise NodeApiError(409, "model_request_rejected", "The model request conflicts with the task authority.") from exc
        except TransitionRejected as exc:
            raise NodeApiError(409, "transition_rejected", "The task is not in a state that admits a model call.") from exc
        except BackendCallError as exc:
            raise NodeApiError(502, "model_backend_failed", "The selected model backend failed.") from exc
        except StepTimeout as exc:
            raise NodeApiError(504, "model_timeout", "The model call exceeded its timeout.") from exc
        except RetryExhausted as exc:
            raise NodeApiError(502, "model_retry_exhausted", "The model call failed after its retries were exhausted.") from exc
        except CircuitOpen as exc:
            raise NodeApiError(503, "model_circuit_open", "The model dependency circuit is open.") from exc
        except (StorageFailure, LedgerError) as exc:
            raise NodeApiError(503, "transition_not_committed", "The local ledger did not commit the model call.") from exc

        if execution.response is None or execution.step is None or isinstance(execution.response, tuple):
            raise NodeApiError(503, "model_not_admitted", execution.route.decision.reason or "No qualified model target was admitted.")
        return self._model_call_result(command, task_id, execution)

    def _replay_model_call(self, command: NodeCommandEnvelope, task_id: str, request_id: str) -> dict[str, Any] | None:
        event = next(
            (
                candidate for candidate in reversed(self._ledger.events)
                if candidate.task_id == task_id
                and candidate.event_type == "model.responded"
                and isinstance(candidate.payload, dict)
                and candidate.payload.get("request_id") == request_id
            ),
            None,
        )
        if event is None:
            return None
        return {
            "command": _command_result(
                command, task_id, event, self._task_sequence(task_id, event.event_id),
                self.orchestrator.state(task_id), self.config,
            ),
            "replayed": True,
        }

    def _model_call_result(self, command: NodeCommandEnvelope, task_id: str, execution: Any) -> dict[str, Any]:
        event = self._event_by_id(execution.step.transition.event_id)
        response = execution.response
        return {
            "command": _command_result(
                command, task_id, event, self._task_sequence(task_id, event.event_id),
                self.orchestrator.state(task_id), self.config,
            ),
            "model": {
                "request_id": execution.request_id,
                "selected_target": response.target_id,
                "status": execution.route.decision.status.value,
                "output": response.output,
                "usage": response.usage.to_dict(),
                "provenance": response.provenance.to_dict(),
                "finish_reason": response.finish_reason,
                "tool_calls": [call.to_dict() for call in response.tool_calls],
                "routing_decision": execution.route.decision.to_dict(),
            },
        }

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
    def _auto_plan_and_admit(self, task_id: str) -> None:
        """Auto-commit a minimal plan and synthetic admission when no NodeTaskPlanner is configured.

        This is the PL1 fix: without a planner the task stalls in ``authorized`` state
        permanently because no ``task.plan.committed`` event is ever written and the
        frontend planning spinner never resolves.  We emit the minimum events required
        for ``plan_state`` to become ``ready_no_hardware`` so the operator can approve
        immediately in dev/demo environments.
        """
        from .task_planning import build_plan_proposal
        task = self._visible_task(task_id)
        # Commit the plan proposal through the orchestrator's PlanValidator.
        # This writes the ``task.plan.committed`` ledger event.
        self.orchestrator.commit_proposal(build_plan_proposal(task))

    def _event_by_id(self, event_id: str) -> LedgerEventEnvelope:
        event = next((candidate for candidate in self._ledger.events if candidate.event_id == event_id), None)
        if event is None:
            raise NodeApiError(503, "event_unreadable", "The committed command event could not be read back.")
        return event

    def _task_sequence(self, task_id: str, event_id: str) -> int:
        # O(N) single-pass: count task-scoped events up to and including the target.
        # The previous O(N\u00b2) implementation sliced self._ledger.events[:sequence] inside
        # the outer loop which caused quadratic scanning on large ledgers (C3 audit finding).
        sequence = 0
        for event in self._ledger.events:
            if event.task_id == task_id:
                sequence += 1
            if event.event_id == event_id:
                return sequence
        raise NodeApiError(503, "event_unreadable", "The committed command sequence could not be read back.")

    def snapshot(self, task_id: str) -> dict[str, Any]:
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
        try:
            snapshot = NodeTaskSnapshot.from_wire_dict({
                "taskId": task.task_id,
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
            })
        except ContractValidationError as exc:
            raise NodeApiError(503, "snapshot_contract_corrupt", "The task snapshot could not be verified.") from exc
        return snapshot.to_wire_dict()

    def plan(self, task_id: str) -> dict[str, Any]:
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
            # PL2 fix: a committed plan without a hardware admission event is treated
            # as "ready_no_hardware" so the operator can approve in dev/demo environments
            # that do not have AIRBENCH_HARDWARE_PROFILE_PATH configured.
            plan_state = "ready_no_hardware"
            mode = "serial_virtual_team"
            hardware_reason = "Hardware admission is not configured. The plan can be approved without a hardware profile."
            failure_code = None
            failure_reason = None
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
        task = self._visible_task(task_id)
        events = self._stream_events(task)
        total = len(events)
        if after_sequence > total:
            raise NodeApiError(409, "cursor_ahead", "The event cursor is ahead of the task stream.")
        selected = events[after_sequence:after_sequence + MAX_EVENT_BATCH]
        try:
            event_models = [self._event_model(event, task, after_sequence + index + 1) for index, event in enumerate(selected)]
        except ContractValidationError as exc:
            raise NodeApiError(503, "event_contract_corrupt", "The task event stream could not be verified.") from exc
        next_sequence = after_sequence + len(selected)
        try:
            batch = NodeTaskEventBatch.from_dict({
                "stream_id": task.task_id,
                "node_identity": self.config.node_identity,
                "protocol_version": self.config.protocol_version,
                "clearance_context": self.config.clearance_context,
                "events": tuple(event_models),
                "next_sequence": next_sequence,
                "has_more": next_sequence < total,
                "ledger_event_refs": tuple(event.ledger_event_ref for event in event_models),
            })
        except ContractValidationError as exc:
            raise NodeApiError(503, "event_batch_contract_corrupt", "The task event batch could not be verified.") from exc
        return batch.to_dict()

    def evidence(self, task_id: str) -> dict[str, Any]:
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
                source = payload
                if key not in source and isinstance(payload.get("decision"), dict):
                    source = payload["decision"]
                if key in source:
                    entry[key] = _safe_value(source[key])
            decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
            selected_target = entry.get("selected_target") or _safe_value(payload.get("target_id")) or _safe_value(decision.get("target_id"))
            if selected_target:
                entry["selected_target"] = selected_target
                model_name = self._model_display_name(selected_target)
                if model_name:
                    entry["selected_model_name"] = model_name
            if "eligible_targets" in payload:
                entry["eligible_targets"] = _string_list(payload["eligible_targets"])[:100]
            entries.append(entry)
            if len(entries) >= MAX_ROUTE_ITEMS:
                break
        try:
            trace = NodeRouteTrace.from_wire_dict({
                "taskId": task.task_id,
                "nodeIdentity": self.config.node_identity,
                "protocolVersion": self.config.protocol_version,
                "clearanceContext": self.config.clearance_context.value,
                "entries": entries,
            })
        except ContractValidationError as exc:
            raise NodeApiError(503, "route_trace_contract_corrupt", "The routing trace could not be verified.") from exc
        return trace.to_wire_dict()

    def _model_display_name(self, target_id: str) -> str | None:
        router = self.model_router
        registry = getattr(router, "registry", None)
        targets = getattr(registry, "targets", ()) if registry is not None else ()
        target = next((item for item in targets if getattr(item, "target_id", None) == target_id), None)
        name = getattr(target, "display_name", "") if target is not None else ""
        return name.strip() or None

    def review(self, task_id: str) -> dict[str, Any]:
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

    def artifact_review(self, task_id: str) -> dict[str, Any]:
        if self.deliverable_gateway is None:
            raise NodeApiError(503, "deliverable_unavailable", "The local Deliverable Engine is not configured.")
        try:
            return self.deliverable_gateway.artifact_review(task_id=task_id)
        except NodeIntakeError as exc:
            raise NodeApiError(exc.status_code, exc.code, exc.message) from exc

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

    def _event_model(self, event: LedgerEventEnvelope, task: TaskEnvelope, sequence: int) -> NodeTaskEvent:
        event_type, payload = self._project_event(event, task)
        return NodeTaskEvent.from_dict({
            "event_id": event.event_id,
            "task_id": task.task_id,
            "sequence": sequence,
            "event_type": event_type,
            "occurred_at": event.occurred_at,
            "actor": event.actor_id,
            "clearance_context": self.config.clearance_context,
            "payload_hash": event.payload_hash,
            "ledger_event_ref": event.event_id,
            "payload": payload,
        })

    def _wire_event(self, event: LedgerEventEnvelope, task: TaskEnvelope, sequence: int) -> dict[str, Any]:
        """Return one Node event for callers that still need a single item."""
        return self._event_model(event, task, sequence).to_wire_dict()

    def _project_event(self, event: LedgerEventEnvelope, task: TaskEnvelope) -> tuple[str, dict[str, Any]]:
        p = event.payload
        if event.event_type in {"task.created", "task.authorized"}:
            return "task.accepted", {"phase": "accepted", "status": "accepted", "summary": _event_summary(event)}
        if event.event_type == "task.plan.committed":
            return "plan.created", {"phase": "planning", "status": "planning", "summary": _event_summary(event)}
        if event.event_type == "task.plan.approved":
            return "plan.approved", {"phase": "planning", "status": "planning", "summary": _event_summary(event)}
        if event.event_type in {"model.requested", "worker.started"}:
            return "worker.started", _worker_projection(p, role=_role(p, "worker"), label=_label(p, event.event_type), status="running")
        if event.event_type in {"model.responded", "worker.completed"}:
            return "worker.completed", _worker_projection(p, role=_role(p, "worker"), label=_label(p, event.event_type), status="completed")
        if event.event_type in _EXECUTION_NODE_EVENT_TYPES:
            return event.event_type, _execution_projection(event)
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
            # M4 audit fix: break as soon as EITHER cap is hit, not only when both
            # are full simultaneously. The previous `and` caused wasted CPU when
            # evidence hit the cap early but facts still had items to process.
            if len(evidence) >= MAX_EVIDENCE_ITEMS or len(facts) >= MAX_EVIDENCE_ITEMS:
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
        try:
            return NodeEvidenceRef.from_wire_dict({
                "evidenceId": evidence_id,
                "contentHash": content_hash.lower(),
                "source": _provenance_ref(provenance, event),
                "confidence": _confidence(provenance.get("confidence")),
                "clearance": clearance.value,
                "taint": taint,
            }).to_wire_dict()
        except ContractValidationError:
            return None

    def _fact_ref(self, event: LedgerEventEnvelope) -> dict[str, Any] | None:
        p = event.payload
        provenance = p.get("provenance")
        fact_id = p.get("fact_id") or p.get("factId")
        validated = self._validated_provenance(event)
        if validated is None or not isinstance(provenance, dict) or not isinstance(fact_id, str) or not fact_id:
            return None
        clearance, taint = validated
        try:
            return NodeFactRef.from_wire_dict({
                "factId": fact_id,
                "value": _safe_value(p.get("value")),
                "unit": p.get("unit") if isinstance(p.get("unit"), str) else None,
                "source": _provenance_ref(provenance, event),
                "confidence": _confidence(provenance.get("confidence")),
                "clearance": clearance.value,
                "taint": taint,
                "parentFactIds": _string_list(p.get("parent_fact_ids")),
                "derivation": _safe_value(p.get("derivation")) if isinstance(p.get("derivation"), dict) else None,
                "supersededBy": p.get("superseded_by") if isinstance(p.get("superseded_by"), str) else None,
            }).to_wire_dict()
        except ContractValidationError:
            return None

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

_EXECUTION_NODE_EVENT_TYPES = {
    "team.created", "team.execution.started", "team.execution.completed", "team.execution.failed", "team.execution.cancelled",
    "lifecycle.intercepted", "lifecycle.blocked", "worker.context.compacted", "worker.assigned", "worker.failed",
    "worker.handoff", "worker.handoff.rejected", "worker.handoff.late", "worker.resource_reserved", "worker.preempted", "worker.cancelled",
    "team.resource_plan.created", "team.resource_plan.admitted", "team.resource_plan.queued", "team.resource_plan.degraded_needs_review",
    "team.resource_plan.rejected", "team.resource_plan.released", "team.resource_plan.cancelled", "execution.mode.selected", "execution.mode.changed",
    "join_barrier.waiting", "join_barrier.completed", "join_barrier.resolved", "resource.exhaustion.detected", "resource.recovered",
    "resource.queue.updated", "resource.lease.granted", "resource.lease.activated", "resource.lease.released", "resource.lease.expired",
    "resource.lease.cancelled", "resource.lease.failed", "resource.admission.degraded", "background.work.yielded",
    "resource.plan.admitted", "resource.plan.queued", "barrier.waiting", "barrier.completed",
}


def create_app(service: NodeApiService) -> FastAPI:
    """Build an API app with documentation endpoints disabled by default."""

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service

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

        async def read_all() -> None:
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_JSON_BODY_BYTES:
                    raise NodeApiError(413, "body_too_large", "The request body exceeds the local limit.")

        try:
            await asyncio.wait_for(read_all(), timeout=BODY_READ_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise NodeApiError(408, "body_read_timeout", "The request body was not received in time.") from exc
        try:
            value = json.loads(bytes(data))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise NodeApiError(400, "json_invalid", "The request body is not valid JSON.") from exc
        if not isinstance(value, dict):
            raise NodeApiError(400, "json_object_required", "The request body must be a JSON object.")
        return value

    async def multipart_document(request: Request) -> tuple[str, str, bytes]:
        """Decode only multipart framing; document interpretation stays in M7."""
        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise NodeApiError(400, "multipart_required", "The intake request must be multipart form data.")
        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            try:
                if int(declared_length) > MAX_MULTIPART_BODY_BYTES:
                    raise NodeApiError(413, "upload_too_large", "The upload exceeds the local query-upload limit.")
            except ValueError as exc:
                raise NodeApiError(400, "content_length_invalid", "The upload content length is invalid.") from exc
        data = bytearray()

        async def read_all() -> None:
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_MULTIPART_BODY_BYTES:
                    raise NodeApiError(413, "upload_too_large", "The upload exceeds the local query-upload limit.")

        try:
            await asyncio.wait_for(read_all(), timeout=BODY_READ_TIMEOUT_S)
        except asyncio.TimeoutError as exc:
            raise NodeApiError(408, "body_read_timeout", "The upload was not received in time.") from exc
        try:
            raw_message = (
                b"Content-Type: " + content_type.encode("utf-8")
                + b"\r\nMIME-Version: 1.0\r\n\r\n" + bytes(data)
            )
            message = BytesParser(policy=policy.default).parsebytes(raw_message)
        except (UnicodeEncodeError, ValueError) as exc:
            raise NodeApiError(400, "multipart_invalid", "The intake multipart envelope is invalid.") from exc
        if not message.is_multipart():
            raise NodeApiError(400, "multipart_invalid", "The intake request did not contain multipart parts.")

        fields: dict[str, str] = {}
        documents = []
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="content-disposition")
            if not isinstance(name, str) or not name:
                raise NodeApiError(400, "multipart_field_invalid", "The intake multipart field name is invalid.")
            if name == "document":
                documents.append(part)
                continue
            if name in fields:
                raise NodeApiError(400, "multipart_field_duplicate", "The intake multipart field was repeated.")
            value = part.get_payload(decode=True) or b""
            try:
                fields[name] = value.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise NodeApiError(400, "multipart_field_invalid", "The intake multipart field is not valid text.") from exc
        if fields.get("intake_mode") != "query_upload":
            raise NodeApiError(400, "intake_mode_invalid", "The intake mode must be query_upload.")
        task_id = fields.get("task_id")
        if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
            raise NodeApiError(409, "task_required", "Create the task through the Node before sending query-upload material.")
        if len(documents) != 1:
            raise NodeApiError(400, "document_part_invalid", "Exactly one document part is required.")
        document = documents[0]
        file_name = document.get_filename()
        if not isinstance(file_name, str) or not file_name.strip() or len(file_name) > 255 or any(char in file_name for char in ("/", "\\", "\0")):
            raise NodeApiError(400, "file_name_invalid", "The intake file name is invalid.")
        content = document.get_payload(decode=True) or b""
        if not content:
            raise NodeApiError(422, "empty_file", "Empty files are rejected by the File Intake Layer.")
        if len(content) > MAX_QUERY_UPLOAD_BYTES:
            raise NodeApiError(413, "upload_too_large", "The upload exceeds the local query-upload limit.")
        declared_size = fields.get("source_file_size")
        if declared_size is not None:
            try:
                if int(declared_size) != len(content):
                    raise NodeApiError(422, "source_size_mismatch", "The declared source size does not match the uploaded bytes.")
            except ValueError as exc:
                raise NodeApiError(400, "source_size_invalid", "The declared source size is invalid.") from exc
        return task_id, file_name, content

    @app.get("/api/v1/node/handshake")
    async def handshake(request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.handshake)

    @app.get("/api/v1/health")
    async def health(request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.health)

    @app.post("/api/v1/intake/query-upload", status_code=200)
    async def query_upload(request: Request) -> dict[str, Any]:
        subject = auth(request)
        task_id, file_name, content = await multipart_document(request)
        return await run_in_threadpool(service.query_upload, subject, task_id=task_id, file_name=file_name, content=content)

    @app.post("/api/v1/intake/pid", status_code=200)
    async def pid_extract(request: Request) -> dict[str, Any]:
        subject = auth(request)
        task_id, file_name, content = await multipart_document(request)
        return await run_in_threadpool(service.pid_extract, subject, task_id=task_id, file_name=file_name, content=content)

    @app.get("/api/v1/intake/{preview_ref}/preview")
    async def safe_intake_preview(preview_ref: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.safe_preview, preview_ref)

    @app.get("/api/v1/intake/status/{intake_id}")
    async def intake_status(intake_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.intake_status, intake_id)

    @app.get("/api/v1/knowledge/status")
    async def knowledge_status(request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.knowledge_status)

    @app.post("/api/v1/knowledge/search", status_code=200)
    async def knowledge_search(request: Request) -> dict[str, Any]:
        auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.knowledge_search, body)

    # L3 / P3 audit fix: the ingest implementation runs synchronously in a
    # threadpool thread and returns only after all files are processed.  HTTP
    # 202 implies async processing with a separate status-poll mechanism; using
    # it here caused Tauri to receive an apparent success before the work was
    # done (on large corpora the threadpool timed out and the frontend saw an
    # error while the Node continued happily).  Use 200 to match reality.
    @app.post("/api/v1/knowledge/ingest", status_code=200)
    async def knowledge_ingest(request: Request) -> dict[str, Any]:
        auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.knowledge_ingest, body)

    @app.get("/api/v1/knowledge/graph/stats")
    async def graph_stats(request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.graph_status)

    @app.post("/api/v1/knowledge/graph/query", status_code=200)
    async def graph_query(request: Request) -> dict[str, Any]:
        auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.graph_query, body)

    @app.get("/api/v1/knowledge/graph/review-queue")
    async def graph_review_queue(request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.graph_review_queue)

    @app.post("/api/v1/knowledge/graph/review/resolve", status_code=200)
    async def graph_resolve_review(request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.graph_resolve_review, subject, body)

    @app.get("/api/v1/tasks/{task_id}/consistency")
    async def consistency_report(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.consistency_report, task_id)

    @app.post("/api/v1/tasks/{task_id}/consistency/evaluate", status_code=200)
    async def consistency_evaluate(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.consistency_evaluate, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/consistency/justify", status_code=200)
    async def consistency_justify(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.consistency_justify, subject, task_id, body)

    @app.get("/api/v1/tasks/{task_id}/autonomy")
    async def autonomy_records(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.autonomy_records, task_id)

    @app.post("/api/v1/tasks/{task_id}/autonomy/score", status_code=200)
    async def autonomy_score(task_id: str, request: Request) -> dict[str, Any]:
        # M2 audit fix: pass the authenticated subject so autonomy_score can
        # verify task ownership and bind worker_id to the caller identity.
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.autonomy_score, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/autonomy/authorize", status_code=200)
    async def autonomy_authorize(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.autonomy_authorize, subject, task_id, body)

    @app.get("/api/v1/artifacts/{artifact_id}/preview")
    async def artifact_preview(artifact_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.artifact_preview, artifact_id)

    @app.get("/api/v1/artifacts/{artifact_id}/download")
    async def artifact_download(artifact_id: str, request: Request) -> Response:
        auth(request)
        result = await run_in_threadpool(service.artifact_download, artifact_id)
        return Response(
            content=result.content,
            media_type=result.media_type,
            headers={
                "X-AirBench-Artifact-Hash": result.content_hash,
                "X-AirBench-Ledger-Event-Ref": result.ledger_event_ref,
            },
        )

    @app.post("/api/v1/tasks", status_code=201)
    async def create_task(request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.create_task, subject, body)

    @app.get("/api/v1/tasks/{task_id}")
    async def task_snapshot(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.snapshot, task_id)

    @app.get("/api/v1/tasks/{task_id}/plan")
    async def task_plan(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.plan, task_id)

    @app.get("/api/v1/tasks/{task_id}/events")
    async def task_events(task_id: str, request: Request, after_sequence: int = 0) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.event_batch, task_id, after_sequence)

    @app.get("/api/v1/tasks/{task_id}/evidence")
    async def task_evidence(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.evidence, task_id)

    @app.get("/api/v1/tasks/{task_id}/route-trace")
    async def task_route_trace(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.route_trace, task_id)

    @app.get("/api/v1/tasks/{task_id}/review")
    async def task_review(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.review, task_id)

    @app.get("/api/v1/tasks/{task_id}/artifact-review")
    async def task_artifact_review(task_id: str, request: Request) -> dict[str, Any]:
        auth(request)
        return await run_in_threadpool(service.artifact_review, task_id)

    @app.post("/api/v1/tasks/{task_id}/authorize", status_code=202)
    async def authorize_task(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.authorize, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/approve", status_code=202)
    async def approve_task_plan(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.approve_plan, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/cancel", status_code=202)
    async def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.cancel, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/review", status_code=202)
    async def review_task(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.request_review, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/approve-artifact", status_code=202)
    async def approve_artifact(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.approve_artifact, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/return-artifact", status_code=202)
    async def return_artifact(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.return_artifact, subject, task_id, body)

    @app.post("/api/v1/tasks/{task_id}/model-call", status_code=202)
    async def model_call(task_id: str, request: Request) -> dict[str, Any]:
        subject = auth(request)
        body = await json_body(request)
        return await run_in_threadpool(service.call_model, subject, task_id, body)

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


def _execution_sources(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    sources = [payload]
    for name in ("team", "plan", "assignment", "reservation", "lease", "barrier", "handoff"):
        nested = payload.get(name)
        if isinstance(nested, dict):
            sources.append(nested)
    return tuple(sources)


def _execution_text(payload: dict[str, Any], *keys: str) -> str | None:
    for source in _execution_sources(payload):
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return _bounded_text(value.strip(), 512)
    return None


def _worker_projection(payload: dict[str, Any], *, role: str, label: str, status: str) -> dict[str, Any]:
    result: dict[str, Any] = {"role": role, "label": label, "status": status}
    fields = (
        ("team_id", "teamId"),
        ("assignment_id", "assignmentId"),
        ("worker_id", "workerId"),
        ("resource_lease_id", "resourceLeaseId"),
    )
    for source_key, wire_key in fields:
        value = _execution_text(payload, source_key)
        if value is not None:
            result[wire_key] = value
    return result


def _execution_projection(event: LedgerEventEnvelope) -> dict[str, Any]:
    payload = event.payload
    status_by_event = {
        "team.created": "created",
        "team.execution.started": "running",
        "team.execution.completed": "completed",
        "team.execution.failed": "failed",
        "team.execution.cancelled": "cancelled",
        "lifecycle.intercepted": "intercepted",
        "lifecycle.blocked": "blocked",
        "worker.assigned": "assigned",
        "worker.failed": "failed",
        "worker.handoff": "submitted",
        "worker.handoff.rejected": "rejected",
        "worker.handoff.late": "late",
        "worker.resource_reserved": "reserved",
        "worker.preempted": "preempted",
        "worker.cancelled": "cancelled",
        "team.resource_plan.created": "created",
        "team.resource_plan.admitted": "admitted",
        "team.resource_plan.queued": "queued",
        "team.resource_plan.degraded_needs_review": "needs_review",
        "team.resource_plan.rejected": "rejected",
        "team.resource_plan.released": "released",
        "team.resource_plan.cancelled": "cancelled",
        "resource.plan.admitted": "admitted",
        "resource.plan.queued": "queued",
        "execution.mode.selected": "selected",
        "execution.mode.changed": "changed",
        "join_barrier.waiting": "waiting",
        "join_barrier.completed": "completed",
        "join_barrier.resolved": "resolved",
        "barrier.waiting": "waiting",
        "barrier.completed": "completed",
        "resource.exhaustion.detected": "exhausted",
        "resource.recovered": "recovered",
        "resource.queue.updated": "queued",
        "resource.lease.granted": "granted",
        "resource.lease.activated": "active",
        "resource.lease.released": "released",
        "resource.lease.expired": "expired",
        "resource.lease.cancelled": "cancelled",
        "resource.lease.failed": "failed",
        "resource.admission.degraded": "degraded",
        "background.work.yielded": "yielded",
    }
    result: dict[str, Any] = {
        "status": _execution_text(payload, "status") or status_by_event.get(event.event_type, "recorded"),
        "summary": _execution_text(payload, "summary", "reason", "failure_code", "admission_reason", "outcome")
        or f"Node recorded {event.event_type}.",
    }
    fields = (
        ("execution_mode", "executionMode"),
        ("team_id", "teamId"),
        ("plan_id", "planId"),
        ("assignment_id", "assignmentId"),
        ("worker_id", "workerId"),
        ("role", "role"),
        ("label", "label"),
        ("barrier_id", "barrierId"),
        ("resource_lease_id", "resourceLeaseId"),
        ("hardware_profile_ref", "hardwareProfileRef"),
        ("model_target_id", "modelTargetId"),
        ("qualification_id", "qualificationId"),
    )
    aliases = {
        "execution_mode": ("execution_mode", "admitted_mode", "mode"),
        "team_id": ("team_id",),
        "plan_id": ("plan_id",),
        "assignment_id": ("assignment_id", "destination_assignment_id"),
        "worker_id": ("worker_id", "source_worker_id"),
        "role": ("role",),
        "label": ("label", "stage", "capability"),
        "barrier_id": ("barrier_id",),
        "resource_lease_id": ("resource_lease_id", "lease_id"),
        "hardware_profile_ref": ("hardware_profile_ref", "hardware_profile_id"),
        "model_target_id": ("model_target_id",),
        "qualification_id": ("qualification_id",),
    }
    for source_key, wire_key in fields:
        value = _execution_text(payload, *aliases[source_key])
        if value is not None:
            result[wire_key] = value

    dependencies: list[str] = []
    for source in _execution_sources(payload):
        for key in ("dependency_ids", "required_predecessor_assignment_ids", "missing_assignment_ids", "assignment_ids"):
            candidate = _string_list(source.get(key))
            if candidate:
                dependencies = candidate[:100]
                break
        if dependencies:
            break
    if dependencies:
        result["dependencyIds"] = dependencies

    queue_position = payload.get("queue_position")
    if type(queue_position) is int and 0 <= queue_position <= 2**31 - 1:
        result["queuePosition"] = queue_position
    return result


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
    task_payload = created.payload.get("task") if created else None
    refs = task_payload.get("input_manifest_refs") if isinstance(task_payload, dict) else None
    if isinstance(refs, list) and refs and isinstance(refs[0], str):
        return refs[0]
    # Query-upload is committed only after task.created and is linked to the
    # same task by the File Intake Layer's evidence event. This keeps the
    # upload-before-execution handoff visible without letting the API mutate
    # the task envelope or invent a second parser path.
    intake = next((event for event in reversed(events) if event.event_type == "evidence.created"), None)
    intake_id = intake.payload.get("intake_id") if intake else None
    return intake_id if isinstance(intake_id, str) else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_bounded_text(item, 512) for item in value if isinstance(item, str) and item.strip()]


def _resource_plan_values(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    # Scheduler decision events carry the authoritative TeamResourcePlan
    # under ``plan``.  Older/manual Node fixtures may expose the same fields
    # directly or under ``resource_plan``.  Project all three wire shapes
    # without weakening the typed plan contract at the API boundary.
    nested = payload.get("resource_plan")
    if not isinstance(nested, dict):
        nested = payload.get("plan")
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
