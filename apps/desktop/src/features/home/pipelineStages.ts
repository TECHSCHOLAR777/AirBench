/**
 * Maps the REAL launch state machine in App.tsx (creating -> intake ->
 * authorizing -> planning -> syncing) onto the five themed stage labels the
 * old showcase-assistant screen used (intake -> qualification -> routing ->
 * verification -> delivery), so Home visually resembles that pipeline theater
 * while only ever reflecting real progress. Nothing here is a timer or a
 * canned delay — the active stage always comes from the actual launch phase
 * passed in by the caller.
 */

export type LaunchPhase = "idle" | "creating" | "intake" | "authorizing" | "planning" | "syncing" | "failed";
export type PipelineStageId = "intake" | "qualification" | "routing" | "verification" | "delivery";

export interface PipelineStage {
  id: PipelineStageId;
  label: string;
  detail: string;
}

const STAGES: PipelineStage[] = [
  { id: "intake", label: "Intake", detail: "Task registered and sources validated by the Node." },
  { id: "qualification", label: "Qualification", detail: "Clearance and capability catalog checked against policy." },
  { id: "routing", label: "Routing", detail: "Node authorizes the task and a qualified worker is selected." },
  { id: "verification", label: "Verification", detail: "The Node prepares an execution plan and checks it against policy." },
  { id: "delivery", label: "Delivery", detail: "The live work trace opens with ordered Node events." },
];

const PHASE_TO_STAGE_INDEX: Record<Exclude<LaunchPhase, "idle" | "failed">, number> = {
  creating: 0,
  intake: 0,
  authorizing: 1,
  planning: 2,
  syncing: 4,
};

export function activeStageIndex(phase: LaunchPhase): number {
  if (phase === "idle" || phase === "failed") return -1;
  return PHASE_TO_STAGE_INDEX[phase];
}

export function pipelineStages(): PipelineStage[] {
  return STAGES;
}
