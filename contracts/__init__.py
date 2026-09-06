"""Frozen, provider-neutral AirBench contracts."""

from .errors import ContractValidationError, ValidationIssue
from .ids import idempotency_key, stable_id
from .ledger import (EVENT_TYPES, Checkpoint, CommittedTransaction, EventLedger,
                     IdempotencyConflict, LedgerStore, ProvenanceRejected,
                     ReplayRejected, ReplayState, SQLiteLedgerStore,
                     StorageFailure, TransitionRejected, build_event)
from .models import *
from .models import (TaskEnvelope, TeamPlan, TaskPlanReview, WorkerAssignment, WorkPacket, WorkerResult,
                     CompletionRecord, ModelCallRequest, RoutingDecision, TeamResourcePlan, HardwareProfile,
                     ToolAction, FactEnvelope, UntrustedEvidence, LedgerEventEnvelope,
                     NodeCommandEnvelope, NodeCommandResult)
from .projections import ProjectionBuilder, ProjectionSnapshot
from .recovery import RecoveryManager, RecoveryPoint, RetryRecord, SideEffectUncertain
from .verification import verify_projection_export, verify_signed_export
from .orchestrator import (AuthorizationRejected, OrchestrationError, Orchestrator,
                            CircuitOpen, CancellationRequested, PlanRejected, RetryExhausted, StepResult, StepTimeout,
                            TransitionResult, ModelCallExecution)
from .authorization import AuthorizationDecision, AuthorizationError, AuthorizationService, PrincipalRecord, SignedReference, sign_reference
from .planning import PlanProposal, PlanStep, PlanValidationError, PlanValidator
from .model_registry import ModelRegistry, ModelTarget, RegistryError
from .admission import AdmissionController, AdmissionDecision, AdmissionError, AdmissionRequest, HardwareMeasurement
from .backend import (BackendAdapter, BackendCallError, BackendCapabilities, BackendChunk, BackendContent,
                      BackendErrorCode, BackendFailure, BackendHealth, BackendMessage, BackendOutputSpec,
                      BackendReadiness, BackendRequest, BackendResponse, BackendTool, BackendToolCall,
                      BackendUsage, CancellationToken, FakeBackend, ResponseProvenance)
from .router import ModelRouter, ResourceAdmission, RouteResult, RoutingError, RoutingRejected

__all__ = ["ContractValidationError", "ValidationIssue", "idempotency_key", "stable_id",
           "TaskEnvelope", "TeamPlan", "TaskPlanReview", "WorkerAssignment", "WorkPacket", "WorkerResult",
           "CompletionRecord", "ModelCallRequest", "RoutingDecision", "TeamResourcePlan", "HardwareProfile",
           "ToolAction", "FactEnvelope", "UntrustedEvidence", "LedgerEventEnvelope",
           "NodeCommandEnvelope", "NodeCommandResult",
           "EVENT_TYPES", "Checkpoint", "CommittedTransaction", "EventLedger",
           "IdempotencyConflict", "LedgerStore", "ProvenanceRejected",
           "ReplayRejected", "ReplayState", "SQLiteLedgerStore", "StorageFailure",
           "TransitionRejected", "build_event", "ProjectionBuilder", "ProjectionSnapshot",
           "RecoveryManager", "RecoveryPoint", "RetryRecord", "SideEffectUncertain"]
__all__ += ["verify_signed_export", "verify_projection_export"]
__all__ += ["AuthorizationRejected", "OrchestrationError", "Orchestrator", "PlanRejected",
            "RetryExhausted", "StepResult", "StepTimeout", "TransitionResult", "CircuitOpen",
            "CancellationRequested", "AuthorizationDecision", "AuthorizationError", "AuthorizationService",
            "PrincipalRecord", "SignedReference", "PlanProposal", "PlanStep", "PlanValidationError", "PlanValidator"]
__all__ += ["sign_reference"]
__all__ += ["ModelRegistry", "ModelTarget", "RegistryError", "AdmissionController", "AdmissionDecision", "AdmissionError", "AdmissionRequest", "HardwareMeasurement"]
__all__ += ["BackendAdapter", "BackendCallError", "BackendCapabilities", "BackendChunk", "BackendContent",
            "BackendErrorCode", "BackendFailure", "BackendHealth", "BackendMessage", "BackendOutputSpec",
            "BackendReadiness", "BackendRequest", "BackendResponse", "BackendTool", "BackendToolCall",
            "BackendUsage", "CancellationToken", "FakeBackend", "ResponseProvenance"]
__all__ += ["ModelRouter", "ResourceAdmission", "RouteResult", "RoutingError", "RoutingRejected"]
__all__ += ["ModelCallExecution"]
