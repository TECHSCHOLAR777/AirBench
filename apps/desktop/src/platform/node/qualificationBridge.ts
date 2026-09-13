/**
 * Qualification bridge — fetch model roster status.
 */
import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export type QualificationState = "qualified" | "unqualified" | "pending" | "not_listed" | "unavailable" | "unknown";

export interface ModelQualificationStatus {
  target_id: string;
  status: QualificationState;
  routing_tier: string | null;
  measurement_pending: boolean;
  reason: string | null;
}

const QUALIFICATION_STATES: readonly QualificationState[] = [
  "qualified", "unqualified", "pending", "not_listed", "unavailable", "unknown",
];

export function validateQualificationStatus(value: unknown): ModelQualificationStatus {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("Invalid qualification status");
  const v = value as Record<string, unknown>;
  const statusStr = typeof v.status === "string" ? v.status : "unknown";
  const status = (QUALIFICATION_STATES as readonly string[]).includes(statusStr)
    ? (statusStr as QualificationState)
    : "unknown";
  return {
    target_id: typeof v.target_id === "string" ? v.target_id : "unknown",
    status,
    routing_tier: typeof v.routing_tier === "string" ? v.routing_tier : null,
    measurement_pending: typeof v.measurement_pending === "boolean" ? v.measurement_pending : status === "pending",
    reason: typeof v.reason === "string" ? v.reason : null,
  };
}

export function fetchModelQualification(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  targetId: string,
): Promise<ModelQualificationStatus> {
  const approved = toNativeNodeProfileReference(profile);
  return invoke<unknown>("fetch_model_qualification", { profileId: approved.profile_id, targetId }).then(validateQualificationStatus);
}

export interface QualificationRoster {
  configured: boolean;
  count: number;
  targets: ModelQualificationStatus[];
}

export function validateQualificationRoster(value: unknown): QualificationRoster {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("Invalid qualification roster");
  const v = value as Record<string, unknown>;
  const targets = Array.isArray(v.targets) ? v.targets.map(validateQualificationStatus) : [];
  return { configured: v.configured === true, count: targets.length, targets };
}

/** Fetch the whole Node-authoritative model roster in one call. */
export function fetchQualificationRoster(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
): Promise<QualificationRoster> {
  const approved = toNativeNodeProfileReference(profile);
  return invoke<unknown>("fetch_qualification_roster", { profileId: approved.profile_id }).then(validateQualificationRoster);
}
