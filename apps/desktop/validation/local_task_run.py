"""Local validation composition for the real Python AirBench Node.

This module is intentionally a validation harness, not a production planner or
model adapter. It composes the existing contracts so the desktop can exercise
one complete local path: an intaken source, an admitted team, a bounded worker
run, deterministic verification, and a pack-declared DOCX artifact.

The worker and hardware records are synthetic. The source manifest, ledger,
orchestrator, scheduler, team runtime, verification runner, and deliverable
engine are real AirBench components. No model endpoint or network call is made.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from airbench.delivery import (
    DeliverableEngine,
    DeliverableRequest,
    DeterministicValue,
    LocalArtifactStore,
)
from airbench.intake import IntakeManifest, LocalIntakeStore
from airbench.orchestration.team_runtime import TeamRuntime
from airbench.orchestration.worker_context import EvidenceProvider, ScopedEvidence
from airbench.verification.runner import (
    VerificationRequest,
    VerificationRule,
    VerificationRunner,
)
from contracts import (
    AdmissionRequest,
    Clearance,
    ContractStatus,
    EventLedger,
    FactEnvelope,
    HardwareMeasurement,
    HardwareProfile,
    Orchestrator,
    ResourceScheduler,
    Taint,
    TeamPlan,
    WorkerAssignment,
    WorkerResult,
    idempotency_key,
    stable_id,
)


class LocalTaskRunError(RuntimeError):
    """The local validation composition could not proceed safely."""


@dataclass(frozen=True, slots=True)
class LocalTaskRun:
    task_id: str
    intake_id: str
    team_id: str
    assignment_id: str
    verification_id: str
    artifact_id: str


class _ManifestEvidenceProvider(EvidenceProvider):
    def __init__(self, manifest: IntakeManifest) -> None:
        self._manifest = manifest

    def get(self, evidence_ref: str) -> ScopedEvidence | None:
        if evidence_ref != "task-input":
            return None
        return ScopedEvidence(
            evidence_ref=evidence_ref,
            source_ref=self._manifest.source_ref,
            confidence=self._manifest.confidence,
            clearance=self._manifest.clearance,
            taint=self._manifest.taint,
            content_hash=self._manifest.source_hash,
        )


class LocalTaskExecutionCoordinator:
    """Compose one real local task run behind the validation Node.

    ``prepare`` is called after explicit task authorization and commits a
    typed team plan plus a synthetic, no-egress hardware admission. ``execute``
    is called only after the operator approves that plan. The coordinator does
    not accept a client-supplied plan, prose, numeric value, or artifact path.
    """

    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        ledger: EventLedger,
        intake_store: LocalIntakeStore,
        artifact_root: str | Path,
        workspace_root: str | Path,
        template_path: str | Path,
    ) -> None:
        self._orchestrator = orchestrator
        self._ledger = ledger
        self._intake_store = intake_store
        self._artifact_root = Path(artifact_root).resolve()
        self._workspace_root = Path(workspace_root).resolve()
        self._template_path = Path(template_path).resolve()
        self._runs: dict[str, LocalTaskRun] = {}
        self._prepared: dict[str, tuple[TeamPlan, WorkerAssignment, ResourceScheduler, Any, IntakeManifest]] = {}

    def prepare(self, task_id: str) -> None:
        if task_id in self._prepared:
            return
        task = self._task(task_id)
        manifest = self._manifest(task_id)
        team_id = stable_id("local-validation-team", task_id)
        assignment_id = stable_id("local-validation-assignment", task_id)
        worker_id = stable_id("local-validation-worker", task_id)
        plan = TeamPlan.from_dict({
            "team_id": team_id,
            "task_id": task_id,
            "assignments": [assignment_id],
            "dependency_graph": {assignment_id: []},
            "concurrency_ceiling": 1,
            "required_verification": True,
            "completion_criteria": list(task.verification_criteria) or ["source_check"],
            "plan_version_hash": stable_id("local-validation-plan", task_id),
            "policy_version_hash": stable_id("local-validation-policy", task.domain_pack_ref),
            "status": ContractStatus.proposed.value,
        })
        self._orchestrator.commit_plan(plan)

        deadline = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        assignment = WorkerAssignment.from_dict({
            "assignment_id": assignment_id,
            "team_id": team_id,
            "task_id": task_id,
            "worker_id": worker_id,
            "role": "local-validation-worker",
            "stage": "source-review",
            "input_schema": "WorkerInput.v1",
            "output_schema": "WorkerOutput.v1",
            "evidence_refs": ["task-input"],
            "allowed_tools": [],
            "clearance": task.clearance.value,
            "taint": manifest.taint.value,
            "capability_requirement": task.permitted_worker_capabilities[0] if task.permitted_worker_capabilities else "general",
            "deadline": deadline,
            "idempotency_key": idempotency_key("local-validation-assignment", task_id),
            "status": ContractStatus.queued.value,
        })

        profile = HardwareProfile.from_dict({
            "profile_id": stable_id("local-validation-hardware", task_id),
            "gpu_model": "synthetic-validation-gpu",
            "gpu_count": 1,
            "vram_bytes": 2_000_000_000,
            "driver_version": "synthetic-validation-driver",
            "accelerator_runtime": "synthetic-validation-runtime",
            "cpu_model": "synthetic-validation-cpu",
            "cpu_cores": 2,
            "ram_bytes": 4_000_000_000,
            "storage_bytes": 10_000_000_000,
            "scratch_bytes": 1_000_000_000,
            "model_context_tokens": 8_192,
            "kv_cache_bytes": 256_000_000,
            "safe_parallel_slots": 1,
            "egress_policy": "deny-all",
            "measurement_hash": stable_id("local-validation-measurement", task_id),
            "supported_execution_modes": ["serial_virtual_team"],
            "network_check_id": "validation-no-egress-synthetic",
            "sandbox_runtime": "validation-synthetic",
            "benchmark_result_ref": "validation-synthetic",
        })
        measurement = HardwareMeasurement(
            measurement_id=stable_id("local-validation-measurement", task_id),
            profile_id=profile.profile_id,
            measured_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            available_vram_bytes=profile.vram_bytes,
            available_ram_bytes=profile.ram_bytes,
            kv_cache_bytes=profile.kv_cache_bytes,
            model_residency_bytes=(),
            latency_ms=(),
            throughput_tokens_per_second=(),
            sandbox_limits=(),
            max_concurrency=1,
            egress_verified=True,
            available_vram_by_gpu=((0, profile.vram_bytes),),
            available_cpu_millicores=2_000,
            available_context_tokens=profile.model_context_tokens,
            available_scratch_bytes=profile.scratch_bytes,
            available_slots=1,
        )
        scheduler = ResourceScheduler(profile, measurement, ledger=self._ledger)
        reservation = (
            ("vram_bytes", 64_000_000),
            ("ram_bytes", 128_000_000),
            ("cpu_millicores", 100),
            ("kv_cache_bytes", 8_000_000),
            ("context_tokens", 1_024),
            ("scratch_bytes", 8_000_000),
            ("slots", 1),
        )
        admission = AdmissionRequest(
            task_id=task_id,
            team_id=team_id,
            worker_capabilities=((worker_id, assignment.capability_requirement),),
            reservations=((worker_id, reservation),),
            verifier_worker_id=worker_id,
            worker_roles=((worker_id, assignment.role),),
            gpu_indices=((worker_id, (0,)),),
            requested_mode="serial_virtual_team",
            model_targets=((worker_id, "validation.synthetic-worker"),),
            qualification_refs=((worker_id, "qualification.validation.synthetic"),),
            clearance=task.clearance,
            taint=Taint.clean,
            policy_version_hash=plan.policy_version_hash,
            concurrency_ceiling=1,
            execution_deadline=deadline,
        )
        schedule = scheduler.admit(admission)
        if schedule.plan.admission != "admitted":
            raise LocalTaskRunError(f"synthetic validation hardware admission was {schedule.plan.admission}")
        self._prepared[task_id] = (plan, assignment, scheduler, schedule, manifest)

    def execute(self, task_id: str) -> LocalTaskRun:
        prepared = self._prepared.get(task_id)
        if prepared is None:
            raise LocalTaskRunError("the task must be prepared after authorization before approval")
        plan, assignment, scheduler, schedule, manifest = prepared
        task = self._task(task_id)
        provider = _ManifestEvidenceProvider(manifest)

        def worker_runner(invocation, token):
            if token.cancelled:
                raise RuntimeError("validation worker cancelled before invocation")
            return WorkerResult.from_dict({
                "result_id": stable_id("local-validation-result", task_id),
                "assignment_id": assignment.assignment_id,
                "task_id": task_id,
                "status": ContractStatus.accepted.value,
                "output": {
                    "summary": "A bounded local worker reviewed the File Intake manifest. Source content remains untrusted data.",
                    "source_evidence_ref": "task-input",
                },
            })

        runtime = TeamRuntime(
            task=task,
            team_plan=plan,
            assignments={assignment.assignment_id: assignment},
            schedule=schedule,
            scheduler=scheduler,
            orchestrator=self._orchestrator,
            # TeamRuntime and WorkerContext already derive task, team, and
            # worker isolation directories.  Passing a task-prefixed root
            # here duplicates the task identity and can exceed Windows'
            # MAX_PATH under a temporary validation root.
            workspace_root=self._workspace_root,
            evidence_provider=provider,
            signing_key=b"airbench-local-validation-signing-key",
            worker_runners={assignment.assignment_id: worker_runner},
        )
        report = runtime.execute()
        if report.status != "completed":
            raise LocalTaskRunError("the bounded local worker team did not complete")

        fact_id = stable_id("local-validation-fact-page-count", task_id)
        fact = FactEnvelope.from_dict({
            "fact_id": fact_id,
            "value": manifest.page_count,
            "source_ref": manifest.source_ref,
            "confidence": manifest.confidence,
            "clearance": manifest.clearance.value,
            "taint": manifest.taint.value,
            "extraction_method": "file-intake-manifest",
            "observed_at": manifest.ingested_at,
            "ingested_at": manifest.ingested_at,
            "unit": "pages",
        })
        self._orchestrator.audit_event(
            task_id,
            "fact.candidate",
            {"fact": fact.to_dict(), "provenance": {
                "source_ref": fact.source_ref,
                "confidence": fact.confidence,
                "clearance": fact.clearance.value,
                "taint": fact.taint.value,
                "derivation": "local-validation:file-intake-manifest",
            }},
            contract="FactEnvelope",
            event_key=idempotency_key("local-validation.fact", task_id, fact_id),
        )

        verification_id = stable_id("local-validation-verification", task_id)
        verification = VerificationRunner(self._ledger, actor_id="verification.local-validation").run(
            VerificationRequest(
                verification_id=verification_id,
                task_id=task_id,
                rules=(VerificationRule(
                    rule_id=stable_id("local-validation-source-rule", task_id),
                    kind="source",
                    fact_ids=(fact_id,),
                    source_prefixes=("query-upload:",),
                ),),
                facts=(fact,),
                clearance=task.clearance,
                evidence_refs=(manifest.intake_id,),
                rule_set_version="local-validation.v1",
                idempotency_key=idempotency_key("local-validation.verification", task_id),
            )
        )
        if verification.outcome.value != "passed":
            raise LocalTaskRunError("the deterministic local source verification did not pass")

        value = DeterministicValue(
            name="page_count",
            value_text=str(manifest.page_count),
            unit="pages",
            value_origin="deterministic_calculation",
            source_refs=(manifest.source_ref,),
            evidence_refs=(manifest.intake_id,),
            verification_refs=verification.ledger_event_ids,
            confidence=min(manifest.confidence, verification.confidence),
            clearance=manifest.clearance,
            taint=manifest.taint,
            derivation={"operation": "count_pages", "input_refs": [fact_id]},
            verified=True,
        )
        artifact = DeliverableEngine(
            template_path=self._template_path,
            artifact_store=LocalArtifactStore(self._artifact_root),
            ledger=self._ledger,
            task_state_reader=self._orchestrator.state,
            actor_id="deliverable-engine.local-validation",
        ).render(DeliverableRequest(
            task_id=task_id,
            template_id="validation_approval_note_v0",
            title="AirBench local validation review note",
            prose_sections={
                "subject": "Local validation review generated from a task-bound File Intake record.",
                "findings": "The bounded worker completed without receiving executable instructions from the source. The source remains untrusted data and requires operator review.",
                "source_register": f"Source reference: {manifest.source_ref}. Intake record: {manifest.intake_id}.",
                "deterministic_calculations": "The page count below was computed from the committed intake manifest: {{page_count}} pages.",
                "review_status": "This is a verified structural draft for local review. Independent visual rendering and operator sign-off remain separate acceptance gates.",
            },
            values=(value,),
            source_refs=(manifest.source_ref,),
            evidence_refs=(manifest.intake_id,),
            verification_refs=verification.ledger_event_ids,
            clearance=manifest.clearance,
            taint=manifest.taint,
            confidence=value.confidence,
            idempotency_key=idempotency_key("local-validation.artifact", task_id),
        ))
        run = LocalTaskRun(
            task_id=task_id,
            intake_id=manifest.intake_id,
            team_id=plan.team_id,
            assignment_id=assignment.assignment_id,
            verification_id=verification_id,
            artifact_id=artifact.artifact_id,
        )
        self._runs[task_id] = run
        return run

    def run_for(self, task_id: str) -> LocalTaskRun | None:
        return self._runs.get(task_id)

    def _task(self, task_id: str):
        event = next((event for event in self._ledger.events if event.task_id == task_id and event.event_type == "task.created"), None)
        if event is None:
            raise LocalTaskRunError("the task does not exist in the local ledger")
        return self._orchestrator._task(task_id)  # validation-only composition; Orchestrator remains authoritative

    def _manifest(self, task_id: str) -> IntakeManifest:
        event = next((event for event in reversed(self._ledger.events) if event.task_id == task_id and event.event_type == "evidence.created"), None)
        if event is None or not isinstance(event.payload.get("intake_id"), str):
            raise LocalTaskRunError("task-bound File Intake must be committed before authorization")
        manifest = self._intake_store.load(event.payload["intake_id"])
        if manifest is None or manifest.task_id != task_id:
            raise LocalTaskRunError("the committed intake manifest is unavailable for this task")
        return manifest


__all__ = ["LocalTaskExecutionCoordinator", "LocalTaskRun", "LocalTaskRunError"]
