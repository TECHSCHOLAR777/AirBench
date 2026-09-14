import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "./nodeBridge";
import type { ApprovedNodeProfile, ApprovedNodeProfileReference } from "./nodeConnection";

export interface DomainPackSectionHash {
  name: string;
  sha256: string;
}

export interface DomainPackStatus {
  configured: boolean;
  status: string;
  pack_id: string | null;
  pack_version: string | null;
  compatibility_id: string | null;
  signature_status: "signed" | "unsigned" | null;
  signature_verified: boolean | null;
  active_sections: string[];
  counts: Record<string, number>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function optionalString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new Error("The Node returned an invalid domain pack field.");
  return value;
}

function requireSectionNames(value: unknown): string[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 64) {
    throw new Error("The Node returned an invalid domain pack section list.");
  }
  return value.map((section) => {
    if (typeof section !== "string" || !section.trim() || section.length > 64 || !/^[A-Za-z0-9_.]+$/.test(section)) {
      throw new Error("The Node returned an invalid domain pack section name.");
    }
    return section;
  });
}

function requireCounts(value: unknown): Record<string, number> {
  if (!isRecord(value)) throw new Error("The Node returned invalid domain pack counts.");
  const counts: Record<string, number> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (typeof raw !== "number" || !Number.isSafeInteger(raw) || raw < 0) {
      throw new Error("The Node returned an invalid domain pack count.");
    }
    counts[key] = raw;
  }
  return counts;
}

export function validateDomainPackStatus(value: unknown): DomainPackStatus {
  if (!isRecord(value)) throw new Error("The Node returned an invalid domain pack status.");
  if (typeof value.configured !== "boolean") throw new Error("The Node returned an invalid domain pack status.");
  if (!value.configured) {
    return {
      configured: false, status: optionalString(value.status) ?? "disabled",
      pack_id: null, pack_version: null, compatibility_id: null,
      signature_status: null, signature_verified: null, active_sections: [], counts: {},
    };
  }
  const packId = optionalString(value.pack_id);
  const version = optionalString(value.pack_version);
  if (!packId || !version) throw new Error("The Node returned an incomplete domain pack status.");
  const signatureStatus = value.signature_status;
  if (signatureStatus !== "signed" && signatureStatus !== "unsigned") {
    throw new Error("The Node returned an invalid domain pack signature status.");
  }
  return {
    configured: true,
    status: optionalString(value.status) ?? "ready",
    pack_id: packId,
    pack_version: version,
    compatibility_id: optionalString(value.compatibility_id),
    signature_status: signatureStatus,
    signature_verified: typeof value.signature_verified === "boolean" ? value.signature_verified : signatureStatus === "signed",
    active_sections: requireSectionNames(value.active_sections),
    counts: requireCounts(value.counts ?? {}),
  };
}

export function fetchDomainPack(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
): Promise<DomainPackStatus> {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) {
    throw new Error("The approved Node profile is incomplete or not approved by policy.");
  }
  const approved = toNativeNodeProfileReference(profile);
  return invoke<unknown>("fetch_domain_pack", { profileId: approved.profile_id }).then(validateDomainPackStatus);
}

export function domainPackSignatureTone(status: DomainPackStatus): "trusted" | "attention" {
  return status.signature_status === "signed" ? "trusted" : "attention";
}
