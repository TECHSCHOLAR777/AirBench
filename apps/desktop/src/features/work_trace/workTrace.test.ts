import { describe, expect, it } from "vitest";
import type { NodeRouteTrace, TaskPlanReview } from "../../generated/core_contracts";
import type { EvidenceRef, TaskEvent, TaskProjection } from "../../platform/events/protocol";
import { buildWorkTrace } from "./workTrace";

const evidence: EvidenceRef = {
  schemaVersion: "0.1",
  compatibilityId: "airbench-node-protocol",
  evidenceId: "evidence-1",
  contentHash: "sha256:evidence",
  source: {
    schemaVersion: "0.1",
    compatibilityId: "airbench-node-protocol",
    sourceDocumentId: "inspection-report.pdf",
    sourceVersion: "revision-1",
    location: { page: 2, region: "table:1" },
    extractionMethod: "ocr",
    observedAt: null,
    ingestedAt: "2026-09-07T00:00:00Z",
    ledgerEventRef: "ledger-source-1",
  },
  confidence: 0.94,
  clearance: "restricted",
  taint: "untrusted",
};

const projection: TaskProjection = {
  taskId: "task-1",
  schemaVersion: "0.1",
  compatibilityId: "airbench-node-protocol",
  snapshotId: "snapshot-1",
  title: "Inspection approval note",
  requestSummary: "Review a scanned inspection report.",
  status: "running",
  phase: "verification",
  clearanceContext: "restricted",
  inputManifestRef: "intake-1",
  nodeConnectionRef: "node-1",
  ledgerHeadRef: "ledger-4",
  lastAppliedSequence: 12,
  evidence: [evidence],
  facts: [],
  artifactRefs: ["artifact-1"],
  unresolvedQuestions: ["Confirm the inspection date before release."],
  diagnostics: [],
  health: "current",
  activity: [],
};

const plan: TaskPlanReview = {
  schema_version: "1.0",
  compatibility_id: "airbench-core-contracts",
  task_id: "task-1",
  node_identity: "node-1",
  protocol_version: "0.1",
  clearance_context: "restricted",
  plan_state: "ready",
  task_sequence: 4,
  team_id: "team-1",
  assignments: ["plan", "verify"],
  dependency_graph: { plan: [], verify: ["plan"] },
  concurrency_ceiling: 2,
  execution_mode: "serial_virtual_team",
  worker_capabilities: { planner: "reasoning", verifier: "verification" },
  hardware_profile_ref: "gpu-profile-1",
  hardware_reason: "One qualified GPU lane is available.",
  required_verification: true,
  completion_criteria: ["verification passes"],
  required_authority: "operator_approval",
  authority_reason: "Approval note requires operator sign-off.",
  plan_version_hash: "plan-hash",
  policy_version_hash: "policy-hash",
  ledger_event_ref: "ledger-plan-1",
};

function event(sequence: number, eventType: TaskEvent["eventType"], payload: TaskEvent["payload"]): TaskEvent {
  return {
    eventId: `event-${sequence}`,
    taskId: "task-1",
    sequence,
    schemaVersion: "0.1",
    compatibilityId: "airbench-node-protocol",
    occurredAt: `2026-09-07T00:00:${String(sequence).padStart(2, "0")}Z`,
    actor: "orchestrator",
    clearanceContext: "restricted",
    payloadHash: `hash-${sequence}`,
    ledgerEventRef: `ledger-${sequence}`,
    eventType: eventType as never,
    payload: payload as never,
  };
}

describe("audit-safe work trace", () => {
  it("groups a typed team task into human-readable stages with evidence retained", () => {
    const trace = buildWorkTrace({
      ...projection,
      activity: [
        event(5, "plan.created", { phase: "planning", status: "planning", summary: "Node committed the work plan." }),
        event(6, "worker.started", { role: "planner", label: "Prepare evidence plan", status: "running" }),
        event(7, "tool.completed", { role: "file_intake", label: "Inspect report", status: "completed" }),
        event(8, "evidence.added", { evidence }),
        event(9, "verification.completed", { summary: "Required checks passed.", passed: true }),
        event(10, "approval.required", { reason: "Operator sign-off is required." }),
        event(11, "artifact.ready", { artifactId: "artifact-1" }),
        event(12, "task.completed", { phase: "complete", status: "completed", summary: "Node recorded completion." }),
      ],
    }, plan);

    expect(trace.stages.map((stage) => stage.id)).toEqual(["plan", "execution", "evidence", "verification", "review", "artifacts", "outcome"]);
    expect(trace.execution.workers[0]).toMatchObject({ label: "Worker started", summary: "planner: Prepare evidence plan (running).", sequence: 6 });
    expect(trace.execution.tools[0]).toMatchObject({ label: "Tool completed", sequence: 7 });
    expect(trace.evidence.records[0]).toMatchObject({ evidenceId: "evidence-1", confidence: 0.94, clearance: "restricted", taint: "untrusted" });
    expect(trace.verification.latest?.summary).toBe("Required checks passed.");
    expect(trace.review.questions).toEqual(["Confirm the inspection date before release."]);
    expect(trace.artifacts.ids).toEqual(["artifact-1"]);
    expect(trace.artifacts.records).toMatchObject([{ artifactId: "artifact-1", state: "ready" }]);
    expect(trace.routing).toMatchObject({ state: "plan_context", executionMode: "serial_virtual_team", selectedTarget: null, fallbackReason: null, policyReason: null });
    expect(trace.latestActivity).toMatchObject({ eventType: "task.completed", ledgerEventRef: "ledger-12", clearance: "restricted" });
  });

  it("shows M4 team coordination as recorded execution activity", () => {
    const trace = buildWorkTrace({
      ...projection,
      activity: [
        event(5, "team.created", { status: "created", summary: "Team created.", teamId: "team-1" }),
        event(6, "worker.assigned", { status: "assigned", summary: "Vision worker assigned.", teamId: "team-1", assignmentId: "assignment-vision", workerId: "worker-vision", role: "vision" }),
        event(7, "execution.mode.selected", { status: "selected", summary: "Parallel execution admitted.", executionMode: "parallel", hardwareProfileRef: "hardware-1" }),
        event(8, "join_barrier.waiting", { status: "waiting", summary: "Waiting for upstream handoff.", barrierId: "barrier-1", dependencyIds: ["assignment-vision"] }),
      ],
    }, plan);

    expect(trace.execution.coordination.map((item) => item.eventType)).toEqual([
      "team.created", "worker.assigned", "execution.mode.selected", "join_barrier.waiting",
    ]);
    expect(trace.execution.coordination[1]).toMatchObject({ label: "Worker assigned", summary: "Vision worker assigned. [team-1 · assignment-vision · worker-vision]" });
    expect(trace.stages.find((stage) => stage.id === "execution")?.events).toHaveLength(4);
  });

  it("shows Node routing proof without treating a desktop guess as a decision", () => {
    const routeTrace: NodeRouteTrace = {
      schemaVersion: "0.1",
      compatibilityId: "airbench-node-protocol",
      taskId: "task-1",
      nodeIdentity: "node-1",
      protocolVersion: "0.1",
      clearanceContext: "restricted",
      entries: [{
        schemaVersion: "0.1",
        compatibilityId: "airbench-node-protocol",
        sequence: 7,
        eventType: "routing.decision",
        occurredAt: "2026-09-07T00:00:07Z",
        actor: "orchestrator",
        clearanceContext: "restricted",
        ledgerEventRef: "ledger-route-7",
        payloadHash: "route-hash-7",
        selectedTarget: "model.local.reasoner",
        decisionSource: "qualified-capability-policy",
        ruleOrThreshold: "reasoning-required",
        qualificationCertificate: "qualification-1",
        fallbackTarget: null,
        reason: null,
        status: "selected",
        eligibleTargets: ["model.local.reasoner"],
      }],
    };

    const trace = buildWorkTrace(projection, plan, routeTrace);

    expect(trace.routing).toMatchObject({
      state: "route_context",
      selectedTarget: "model.local.reasoner",
      policyReason: "qualified-capability-policy / reasoning-required",
    });
    expect(trace.routing.routeEntries[0]).toMatchObject({ eventType: "routing.decision", ledgerEventRef: "ledger-route-7" });
  });

  it("shows an explicit attention state from a Node failure without inventing completion", () => {
    const trace = buildWorkTrace({
      ...projection,
      status: "failed",
      phase: "verification",
      activity: [event(13, "task.failed", { phase: "verification", status: "failed", summary: "Verification did not pass." })],
    }, null);

    expect(trace.stages.find((stage) => stage.id === "outcome")).toMatchObject({ state: "attention", summary: "Verification did not pass." });
    expect(trace.routing).toMatchObject({ state: "not_supplied", selectedTarget: null, fallbackReason: null, policyReason: null });
    expect(trace.activity[0]?.summary).not.toContain("complete");
  });

  it("keeps event metadata available without exposing raw payload JSON", () => {
    const trace = buildWorkTrace({
      ...projection,
      activity: [event(5, "worker.completed", { role: "planner", label: "Prepare evidence plan", status: "completed" })],
    }, null);

    const item = trace.activity[0];
    expect(item).toMatchObject({
      eventId: "event-5",
      occurredAt: "2026-09-07T00:00:05Z",
      actor: "orchestrator",
      clearance: "restricted",
      payloadHash: "hash-5",
      ledgerEventRef: "ledger-5",
    });
    expect(item).not.toHaveProperty("payload");
  });

  it("orders a valid Node event batch by sequence before presenting the trace", () => {
    const trace = buildWorkTrace({
      ...projection,
      activity: [
        event(7, "tool.completed", { role: "file_intake", label: "Inspect report", status: "completed" }),
        event(5, "worker.started", { role: "planner", label: "Prepare evidence plan", status: "running" }),
      ],
    }, null);

    expect(trace.activity.map((item) => item.sequence)).toEqual([5, 7]);
    expect(trace.latestActivity?.eventId).toBe("event-7");
  });

  it("projects artifact lifecycle state from Node events without inventing review status", () => {
    const trace = buildWorkTrace({
      ...projection,
      artifactRefs: [],
      activity: [
        event(13, "artifact.ready", { artifactId: "artifact-ready" }),
        event(14, "artifact.superseded", { artifactId: "artifact-old" }),
      ],
    }, null);

    expect(trace.artifacts.records).toMatchObject([
      { artifactId: "artifact-ready", state: "ready", latestEvent: { sequence: 13 } },
      { artifactId: "artifact-old", state: "superseded", latestEvent: { sequence: 14 } },
    ]);
    expect(trace.artifacts.records[0]).not.toHaveProperty("approval");
    expect(trace.artifacts.records[0]).not.toHaveProperty("verification");
  });
});
