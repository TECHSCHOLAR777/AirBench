/**
 * Model-serving bridge — fetches the Node's declared endpoint health.
 *
 * Transport goes through Rust only. The validator rejects any response that
 * does not satisfy the expected shape so a malformed Node response cannot
 * inject structured data into the settings surface.
 */
import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export interface ModelServingEndpoint {
  target_id: string;
  health: string;
  readiness: string;
  reason: string;
}

export interface ModelServingStatus {
  configured: boolean;
  status: string;
  endpoints: ModelServingEndpoint[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function validateModelServingStatus(value: unknown): ModelServingStatus {
  if (!isRecord(value) || typeof value.configured !== "boolean") {
    throw new Error("The Node returned an invalid model-serving status.");
  }
  const endpoints = Array.isArray(value.endpoints)
    ? value.endpoints.filter(isRecord).map((endpoint) => ({
        target_id: optionalString(endpoint.target_id),
        health: optionalString(endpoint.health),
        readiness: optionalString(endpoint.readiness),
        reason: optionalString(endpoint.reason),
      }))
    : [];
  return {
    configured: value.configured,
    status: optionalString(value.status),
    endpoints,
  };
}

export function fetchModelServing(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
): Promise<ModelServingStatus> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) {
    throw new Error("The approved Node profile is incomplete or not approved by policy.");
  }
  const approved = toNativeNodeProfileReference(profile);
  return invoke<unknown>("fetch_node_model_serving", { profileId: approved.profile_id }).then(
    validateModelServingStatus,
  );
}
