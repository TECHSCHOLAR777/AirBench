/**
 * Consistency bridge — fetch, evaluate, and justify task consistency reports.
 *
 * All transport goes through Rust IPC. No external URLs are called from
 * this layer. The validator rejects shapes that do not match the Node contract
 * so that malformed responses cannot reach App state.
 */
import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export interface ConsistencyMaterialDifference {
  feature: string;
  previous_value: string;
  current_value: string;
}

export interface ConsistencyReport {
  task_id: string;
  status: "not_evaluated" | "evaluated";
  decision_id: string | null;
  decision_type: string | null;
  object_id: string | null;
  comparable_ids: string[];
  superseded_ids: string[];
  material_differences: ConsistencyMaterialDifference[];
  deviation: boolean;
  reason: string | null;
  justified: boolean;
  justification: string | null;
  ledger_event_id: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim())
    throw new Error(`The Node returned an invalid consistency ${label}.`);
  return value;
}

function optionalString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return null;
  return value || null;
}

function requireStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function requireDifferences(value: unknown): ConsistencyMaterialDifference[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!Array.isArray(item) || item.length < 3) return [];
    const [feature, previous_value, current_value] = item;
    if (typeof feature !== "string" || typeof previous_value !== "string" || typeof current_value !== "string")
      return [];
    return [{ feature, previous_value, current_value }];
  });
}

export function validateConsistencyReport(value: unknown): ConsistencyReport {
  if (!isRecord(value)) throw new Error("The Node returned an invalid consistency report.");
  const taskId = requireString(value.task_id, "task_id");
  const status = value.status === "evaluated" ? "evaluated" : "not_evaluated";
  return {
    task_id: taskId,
    status,
    decision_id: optionalString(value.decision_id),
    decision_type: optionalString(value.decision_type),
    object_id: optionalString(value.object_id),
    comparable_ids: requireStringList(value.comparable_ids),
    superseded_ids: requireStringList(value.superseded_ids),
    material_differences: requireDifferences(value.material_differences),
    deviation: typeof value.deviation === "boolean" ? value.deviation : false,
    reason: optionalString(value.reason),
    justified: typeof value.justified === "boolean" ? value.justified : false,
    justification: optionalString(value.justification),
    ledger_event_id: optionalString(value.ledger_event_id),
  };
}

function resolveProfile(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
) {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) {
    throw new Error("The approved Node profile is incomplete or not approved by policy.");
  }
  return toNativeNodeProfileReference(profile);
}

/** Fetch the latest consistency report for a task (read-only). */
export function fetchTaskConsistency(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  taskId: string,
): Promise<ConsistencyReport> {
  const approved = resolveProfile(profile);
  return invoke<unknown>("fetch_task_consistency", {
    profileId: approved.profile_id,
    taskId,
  }).then(validateConsistencyReport);
}

/** Trigger a server-side consistency evaluation for a forming plan decision. */
export function evaluateTaskConsistency(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  taskId: string,
  body: {
    decision_id: string;
    decision_type: string;
    object_id: string;
    features: Record<string, string>;
    decision: string;
    rule_ref: string;
    authority: string;
  },
): Promise<ConsistencyReport> {
  const approved = resolveProfile(profile);
  return invoke<unknown>("post_consistency_evaluate", {
    profileId: approved.profile_id,
    taskId,
    body,
  }).then(validateConsistencyReport);
}

/** Record an operator justification for a flagged consistency deviation. */
export function justifyConsistencyDeviation(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  taskId: string,
  operatorId: string,
  justification: string,
): Promise<ConsistencyReport> {
  if (!justification.trim()) throw new Error("A justification is required.");
  if (justification.length > 4000) throw new Error("The justification exceeds 4 000 characters.");
  const approved = resolveProfile(profile);
  return invoke<unknown>("post_consistency_justify", {
    profileId: approved.profile_id,
    taskId,
    body: { operator_id: operatorId, justification: justification.trim() },
  }).then(validateConsistencyReport);
}
