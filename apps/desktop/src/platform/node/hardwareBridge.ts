/**
 * Hardware bridge — fetches the Node hardware profile status.
 *
 * All transport goes through Rust. No external URLs are called from this layer.
 * The validator rejects any response that does not satisfy the expected shape
 * so that malformed Node responses cannot inject structured data into the UI.
 */
import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export interface HardwareStatus {
  configured: boolean;
  profile_id: string | null;
  gpu_model: string | null;
  gpu_count: number | null;
  vram_bytes: number | null;
  cpu_model: string | null;
  cpu_cores: number | null;
  ram_bytes: number | null;
  safe_parallel_slots: number | null;
  egress_policy: string | null;
  sandbox_runtime: string | null;
  measurement_pending: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") return null;
  return value || null;
}

function optionalInt(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.trunc(value);
}

export function validateHardwareStatus(value: unknown): HardwareStatus {
  if (!isRecord(value)) throw new Error("The Node returned an invalid hardware status.");
  if (typeof value.configured !== "boolean")
    throw new Error("The Node returned an invalid hardware status.");
  if (!value.configured) {
    return {
      configured: false,
      profile_id: null, gpu_model: null, gpu_count: null, vram_bytes: null,
      cpu_model: null, cpu_cores: null, ram_bytes: null,
      safe_parallel_slots: null, egress_policy: null, sandbox_runtime: null, measurement_pending: false,
    };
  }
  return {
    configured: true,
    profile_id: optionalString(value.profile_id),
    gpu_model: optionalString(value.gpu_model),
    gpu_count: optionalInt(value.gpu_count),
    vram_bytes: optionalInt(value.vram_bytes),
    cpu_model: optionalString(value.cpu_model),
    cpu_cores: optionalInt(value.cpu_cores),
    ram_bytes: optionalInt(value.ram_bytes),
    safe_parallel_slots: optionalInt(value.safe_parallel_slots),
    egress_policy: optionalString(value.egress_policy),
    sandbox_runtime: optionalString(value.sandbox_runtime),
    measurement_pending: typeof value.measurement_pending === "boolean"
      ? value.measurement_pending
      : false,
  };
}

export function fetchNodeHardware(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
): Promise<HardwareStatus> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) {
    throw new Error("The approved Node profile is incomplete or not approved by policy.");
  }
  const approved = toNativeNodeProfileReference(profile);
  return invoke<unknown>("fetch_node_hardware", { profileId: approved.profile_id }).then(
    validateHardwareStatus,
  );
}
