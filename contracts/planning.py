"""Typed bounded plan proposals and deterministic validation."""

from __future__ import annotations

from dataclasses import dataclass

from .ids import stable_id
from .models import TaskEnvelope, TeamPlan


class PlanValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlanStep:
    step_id: str
    kind: str
    required_tools: frozenset[str]
    evidence_refs: frozenset[str]
    dependencies: tuple[str, ...]
    timeout_ms: int
    retry_budget: int


@dataclass(frozen=True, slots=True)
class PlanProposal:
    task_id: str
    team_id: str
    steps: tuple[PlanStep, ...]
    required_capabilities: frozenset[str]
    tools: frozenset[str]
    evidence_scope: frozenset[str]
    resource_budget: dict[str, int]
    completion_criteria: frozenset[str]


class PlanValidator:
    """Validates model proposals against the immutable task envelope."""

    def validate(self, task: TaskEnvelope, proposal: PlanProposal) -> TeamPlan:
        if proposal.task_id != task.task_id or not proposal.team_id or not proposal.steps:
            raise PlanValidationError("plan identity and at least one step are required")
        if not proposal.tools.issubset(task.permitted_tools):
            raise PlanValidationError("plan expands permitted tools")
        if not proposal.evidence_scope.issubset(task.allowed_evidence_scope):
            raise PlanValidationError("plan expands evidence scope")
        if not proposal.completion_criteria.issuperset(task.verification_criteria):
            raise PlanValidationError("plan removes verification criteria")
        for name, value in proposal.resource_budget.items():
            if type(value) is not int or value < 0 or value > task.resource_budget.get(name, 0):
                raise PlanValidationError(f"plan exceeds resource budget: {name}")
        ids = {step.step_id for step in proposal.steps}
        if len(ids) != len(proposal.steps):
            raise PlanValidationError("step IDs must be unique")
        for step in proposal.steps:
            if step.kind not in {"model", "retrieval", "world_model", "verification", "tool"}:
                raise PlanValidationError(f"unsupported step kind: {step.kind}")
            if step.timeout_ms <= 0 or step.retry_budget < 0:
                raise PlanValidationError("step timeout and retry budget must be bounded")
            if not step.required_tools.issubset(proposal.tools) or not step.evidence_refs.issubset(proposal.evidence_scope):
                raise PlanValidationError("step exceeds proposal scope")
            if not set(step.dependencies).issubset(ids) or step.step_id in step.dependencies:
                raise PlanValidationError("step dependency is invalid")
        self._check_acyclic(proposal.steps)
        return TeamPlan(team_id=proposal.team_id, task_id=proposal.task_id,
                        assignments=tuple(stable_id("assignment", proposal.team_id, step.step_id) for step in proposal.steps),
                        dependency_graph={step.step_id: step.dependencies for step in proposal.steps},
                        concurrency_ceiling=max(1, min(len(proposal.steps), task.resource_budget.get("max_concurrency", len(proposal.steps)))),
                        required_verification=True, completion_criteria=tuple(sorted(proposal.completion_criteria)),
                        plan_version_hash=stable_id("plan", proposal.task_id, proposal.team_id, tuple(step.step_id for step in proposal.steps)),
                        policy_version_hash=stable_id("policy", task.domain_pack_ref))

    @staticmethod
    def _check_acyclic(steps: tuple[PlanStep, ...]) -> None:
        graph = {step.step_id: set(step.dependencies) for step in steps}
        visited: set[str] = set()
        active: set[str] = set()
        def visit(node: str) -> None:
            if node in active:
                raise PlanValidationError("plan dependency graph contains a cycle")
            if node in visited:
                return
            active.add(node)
            for dependency in graph[node]:
                visit(dependency)
            active.remove(node)
            visited.add(node)
        for node in graph:
            visit(node)
