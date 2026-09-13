/**
 * Qualification bridge — fetch model roster status.
 */
import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export interface ModelQualificationStatus {
  target_id: string;
  status: "qualified" | "unqualified" | "unknown";
  routing_tier: string | null;
  measurement_pending: boolean;
  reason: string | null;
}

export function validateQualificationStatus(value: unknown): ModelQualificationStatus {
  if (typeof value !== "object" || value === null || Array.isArray(value))
    throw new Error("Invalid qualification status");
  const v = value as Record<string, unknown>;
  const statusStr = typeof v.status === "string" ? v.status : "unknown";
  return {
    target_id: typeof v.target_id === "string" ? v.target_id : "unknown",
    status: (statusStr === "qualified" || statusStr === "unqualified") ? statusStr : "unknown",
    routing_tier: typeof v.routing_tier === "string" ? v.routing_tier : null,
    measurement_pending: typeof v.measurement_pending === "boolean" ? v.measurement_pending : false,
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
