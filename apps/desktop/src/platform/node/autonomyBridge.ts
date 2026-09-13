/**
 * Autonomy bridge — fetch decisions and record operator authorizations.
 *
 * All transport goes through Rust IPC. The validator rejects any response
 * shape that does not match the Node autonomy contract so that escalation
 * state cannot be spoofed by a malformed Node response.
 */
import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export type AutonomyOutcome = "allow" | "escalate";

export interface AutonomyDecision {
  action_id: string;
  action_kind: string;
  outcome: AutonomyOutcome;
  required_authority: string;
  required_checks: string[];
  reason: string;
  ledger_event_ref: string;
}

export interface AutonomyStatus {
  task_id: string;
  is_blocked: boolean;
  decisions: AutonomyDecision[];
}

export interface AutonomyAuthorization {
  task_id: string;
  authorized: boolean;
  action_id: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim())
    throw new Error(`The Node returned an invalid autonomy ${label}.`);
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

function requireOutcome(value: unknown): AutonomyOutcome {
  if (value === "allow" || value === "escalate") return value;
  return "escalate"; // fail closed: unknown outcome is treated as an escalation
}

function requireDecision(value: unknown): AutonomyDecision {
  if (!isRecord(value)) throw new Error("The Node returned an invalid autonomy decision.");
  return {
    action_id: requireString(value.action_id, "action_id"),
    action_kind: requireString(value.action_kind, "action_kind"),
    outcome: requireOutcome(value.outcome),
    required_authority: typeof value.required_authority === "string" ? value.required_authority : "human",
    required_checks: requireStringList(value.required_checks),
    reason: typeof value.reason === "string" ? value.reason : "",
    ledger_event_ref: typeof value.ledger_event_ref === "string" ? value.ledger_event_ref : "",
  };
}

export function validateAutonomyStatus(value: unknown): AutonomyStatus {
  if (!isRecord(value)) throw new Error("The Node returned an invalid autonomy status.");
  const taskId = requireString(value.task_id, "task_id");
  const isBlocked = typeof value.is_blocked === "boolean" ? value.is_blocked : false;
  const decisions = Array.isArray(value.decisions)
    ? value.decisions.map(requireDecision)
    : [];
  return { task_id: taskId, is_blocked: isBlocked, decisions };
}

export function validateAutonomyAuthorization(value: unknown): AutonomyAuthorization {
  if (!isRecord(value)) throw new Error("The Node returned an invalid autonomy authorization.");
  return {
    task_id: requireString(value.task_id, "task_id"),
    authorized: typeof value.authorized === "boolean" ? value.authorized : false,
    action_id: optionalString(value.action_id),
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

/** Fetch autonomy decisions and block status for a task (read-only). */
export function fetchTaskAutonomy(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  taskId: string,
): Promise<AutonomyStatus> {
  const approved = resolveProfile(profile);
  return invoke<unknown>("fetch_task_autonomy", {
    profileId: approved.profile_id,
    taskId,
  }).then(validateAutonomyStatus);
}

/**
 * Record an operator authorization to unblock an autonomy escalation.
 * Requires an operator identity and the action being authorized.
 */
export function authorizeAutonomyEscalation(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  taskId: string,
  operatorId: string,
  actionId: string,
): Promise<AutonomyAuthorization> {
  if (!operatorId.trim()) throw new Error("An operator identity is required to authorize.");
  const approved = resolveProfile(profile);
  return invoke<unknown>("post_autonomy_authorize", {
    profileId: approved.profile_id,
    taskId,
    body: { operator_id: operatorId.trim(), action_id: actionId },
  }).then(validateAutonomyAuthorization);
}
