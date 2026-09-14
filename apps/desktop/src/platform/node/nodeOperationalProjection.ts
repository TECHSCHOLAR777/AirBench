import { fetchNodeHardware, type HardwareStatus } from "./hardwareBridge";
import { fetchModelServing, type ModelServingStatus } from "./modelServingBridge";
import { fetchQualificationRoster, type QualificationRoster } from "./qualificationBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export interface NodeOperationalProjection {
  hardware: HardwareStatus | null;
  modelServing: ModelServingStatus | null;
  qualification: QualificationRoster | null;
}

const cache = new Map<string, Promise<NodeOperationalProjection>>();

export function fetchNodeOperationalProjection(profile: ApprovedNodeProfileReference | ApprovedNodeProfile): Promise<NodeOperationalProjection> {
  const existing = cache.get(profile.profileId);
  if (existing) return existing;
  const request = Promise.allSettled([fetchNodeHardware(profile), fetchModelServing(profile), fetchQualificationRoster(profile)]).then(([hardware, modelServing, qualification]) => ({
    hardware: hardware.status === "fulfilled" ? hardware.value : null,
    modelServing: modelServing.status === "fulfilled" ? modelServing.value : { configured: true, status: "degraded", endpoints: [] },
    qualification: qualification.status === "fulfilled" ? qualification.value : null,
  }));
  cache.set(profile.profileId, request);
  return request;
}

export function clearNodeOperationalProjection(profileId?: string): void {
  if (profileId) cache.delete(profileId);
  else cache.clear();
}
