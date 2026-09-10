import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "../../platform/node/nodeBridge";
import { type ApprovedNodeProfile, type ApprovedNodeProfileReference } from "../../platform/node/nodeConnection";

export interface IntakeManifest {
  intake_id: string;
  file_name: string;
  byte_size: number;
  source_hash: string;
  revision_id: string;
  media_type: string;
  page_count: number;
  ocr_status: string;
  vision_status: string;
  clearance: string;
  taint: string;
  preview_ref: string;
  artifact_ref: string;
  ledger_event_ref: string;
}

export interface SafePreview {
  preview_ref: string;
  preview_kind: string;
  text: string;
  source_hash: string;
  source_region: string;
  confidence: number;
  clearance: string;
  taint: string;
  ledger_event_ref: string;
}

export interface DownloadReceipt {
  artifact_id: string;
  destination: string;
  content_hash: string;
  ledger_event_ref: string;
  byte_size: number;
}

const MAX_QUERY_UPLOAD_BYTES = 100 * 1024 * 1024;
const MAX_NODE_REFERENCE_LENGTH = 256;
const MAX_PREVIEW_TEXT_BYTES = 10 * 1024 * 1024;
type Clearance = "public" | "internal" | "restricted" | "secret";
type Taint = "clean" | "untrusted" | "contaminated";
type IntakeStatus = "pending" | "running" | "completed" | "failed" | "not_applicable" | "unavailable";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`The Node returned an invalid ${label}.`);
  return value;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string") throw new Error(`The Node returned an invalid ${label}.`);
  return value;
}

function requireNonEmptyString(value: unknown, label: string): string {
  const result = requireString(value, label);
  if (!result.trim() || result.includes("\0")) throw new Error(`The Node returned an invalid ${label}.`);
  return result;
}

function requireNodeReference(value: unknown, label: string): string {
  const result = requireString(value, label);
  if (result.length === 0 || result.length > MAX_NODE_REFERENCE_LENGTH || result.includes("..") || !/^[A-Za-z0-9._:-]+$/.test(result)) {
    throw new Error(`The Node returned an invalid ${label} reference.`);
  }
  return result;
}

function requireSha256(value: unknown, label: string): string {
  const result = requireString(value, label);
  if (!/^sha256:[0-9a-f]{64}$/i.test(result)) throw new Error(`The Node returned an invalid ${label}.`);
  return result;
}

function isClearance(value: unknown): value is Clearance {
  return value === "public" || value === "internal" || value === "restricted" || value === "secret";
}

function clearanceRank(value: Clearance): number {
  return { public: 0, internal: 1, restricted: 2, secret: 3 }[value];
}

function requireClearance(value: unknown, approvedContext: Clearance, label: string): Clearance {
  if (!isClearance(value) || clearanceRank(value) > clearanceRank(approvedContext)) {
    throw new Error(`The Node returned an invalid or over-cleared ${label}.`);
  }
  return value;
}

function requireTaint(value: unknown, label: string): Taint {
  if (value !== "clean" && value !== "untrusted" && value !== "contaminated") {
    throw new Error(`The Node returned an invalid ${label}.`);
  }
  return value;
}

function requireStatus(value: unknown, label: string): IntakeStatus {
  if (value !== "pending" && value !== "running" && value !== "completed" && value !== "failed" && value !== "not_applicable" && value !== "unavailable") {
    throw new Error(`The Node returned an invalid ${label} status.`);
  }
  return value;
}

function requireSafeInteger(value: unknown, label: string, minimum: number, maximum?: number): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum || (maximum !== undefined && value > maximum)) {
    throw new Error(`The Node returned an invalid ${label}.`);
  }
  return value;
}

function requirePreviewText(value: unknown, label: string): string {
  const result = requireString(value, label);
  if (result.includes("\0") || new TextEncoder().encode(result).byteLength > MAX_PREVIEW_TEXT_BYTES) {
    throw new Error(`The Node returned an invalid ${label}.`);
  }
  return result;
}

function requireFileName(value: unknown): string {
  const result = requireString(value, "intake file name");
  if (!result || result.length > 255 || result.includes("/") || result.includes("\\") || result.includes("\0")) {
    throw new Error("The Node returned an invalid intake file name.");
  }
  return result;
}

function validateClearanceContext(profile: ApprovedNodeProfileReference | ApprovedNodeProfile): Clearance {
  if (!isClearance(profile.clearanceContext)) throw new Error("The approved Node profile has an invalid clearance context.");
  return profile.clearanceContext;
}

/**
 * Re-validates the Rust response at the webview boundary. The native layer
 * remains authoritative; this guard prevents an unexpected IPC payload from
 * becoming trusted React state if the native command or Node contract drifts.
 */
export function validateIntakeManifest(value: unknown, approvedContext: Clearance): IntakeManifest {
  const source = requireRecord(value, "intake manifest");
  return {
    intake_id: requireNodeReference(source.intake_id, "intake"),
    file_name: requireFileName(source.file_name),
    byte_size: requireSafeInteger(source.byte_size, "intake byte size", 1, MAX_QUERY_UPLOAD_BYTES),
    source_hash: requireSha256(source.source_hash, "source hash"),
    revision_id: requireNodeReference(source.revision_id, "revision"),
    media_type: requireNonEmptyString(source.media_type, "intake media type"),
    page_count: requireSafeInteger(source.page_count, "intake page count", 1),
    ocr_status: requireStatus(source.ocr_status, "OCR"),
    vision_status: requireStatus(source.vision_status, "vision"),
    clearance: requireClearance(source.clearance, approvedContext, "intake clearance"),
    taint: requireTaint(source.taint, "intake taint"),
    preview_ref: requireNodeReference(source.preview_ref, "preview"),
    artifact_ref: requireNodeReference(source.artifact_ref, "artifact"),
    ledger_event_ref: requireNodeReference(source.ledger_event_ref, "ledger event"),
  };
}

export function validateSafePreview(value: unknown, requestedRef: string, expectedSourceHash: string, approvedContext: Clearance): SafePreview {
  const source = requireRecord(value, "safe preview");
  const previewRef = requireNodeReference(source.preview_ref, "preview");
  if (previewRef !== requestedRef) throw new Error("The Node preview reference does not match the requested preview.");
  const sourceHash = requireSha256(source.source_hash, "preview source hash");
  if (sourceHash !== expectedSourceHash) throw new Error("The Node preview source hash does not match the intake manifest.");
  const previewKind = requireString(source.preview_kind, "preview kind");
  if (previewKind !== "text" && previewKind !== "image" && previewKind !== "pdf_page" && previewKind !== "table") {
    throw new Error("The Node returned an unsupported safe preview kind.");
  }
  const sourceRegion = requireNonEmptyString(source.source_region, "preview source region");
  const confidence = source.confidence;
  if (typeof confidence !== "number" || !Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    throw new Error("The Node returned an invalid preview confidence.");
  }
  return {
    preview_ref: previewRef,
    preview_kind: previewKind,
    text: requirePreviewText(source.text, "preview text"),
    source_hash: sourceHash,
    source_region: sourceRegion,
    confidence,
    clearance: requireClearance(source.clearance, approvedContext, "preview clearance"),
    taint: requireTaint(source.taint, "preview taint"),
    ledger_event_ref: requireNodeReference(source.ledger_event_ref, "ledger event"),
  };
}

export function validateArtifactPreview(value: unknown, requestedArtifactId: string, approvedContext: Clearance): ArtifactPreview {
  const source = requireRecord(value, "artifact preview");
  const artifactId = requireNodeReference(source.artifact_id, "artifact");
  if (artifactId !== requestedArtifactId) throw new Error("The Node artifact preview does not match the requested artifact.");
  const previewKind = requireString(source.preview_kind, "artifact preview kind");
  if (previewKind !== "structured_document" && previewKind !== "pdf" && previewKind !== "text") {
    throw new Error("The Node returned an unsupported artifact preview kind.");
  }
  const title = requireString(source.title, "artifact preview title");
  if (!title.trim() || title.length > 255 || title.includes("\0")) throw new Error("The Node returned an invalid artifact preview.");
  if (!Array.isArray(source.blocks) || source.blocks.length === 0 || source.blocks.length > 1024) {
    throw new Error("The Node returned an invalid artifact preview.");
  }
  const blocks = source.blocks.map((value) => {
    const block = requireRecord(value, "artifact preview block");
    const kind = requireString(block.kind, "artifact preview block kind");
    if (!kind.trim() || kind.length > 64 || kind.includes("\0")) throw new Error("The Node returned an unsafe artifact preview block.");
    return { kind, text: requirePreviewText(block.text, "artifact preview block text") };
  });
  return {
    artifact_id: artifactId,
    preview_kind: previewKind,
    title,
    blocks,
    clearance: requireClearance(source.clearance, approvedContext, "artifact preview clearance"),
    taint: requireTaint(source.taint, "artifact preview taint"),
    ledger_event_ref: requireNodeReference(source.ledger_event_ref, "ledger event"),
  };
}

/**
 * Checks the typed receipt again at the webview boundary before success is
 * shown. Rust verifies the hash and Node permission; this guard prevents a
 * mismatched or incomplete response from being presented as this artifact's
 * download receipt.
 */
export function validateDownloadReceipt(value: unknown, expectedArtifactId: string): DownloadReceipt {
  const receipt = requireRecord(value, "download receipt");
  if (receipt.artifact_id !== expectedArtifactId) {
    throw new Error("The download receipt does not match the requested artifact.");
  }
  requireNodeReference(receipt.artifact_id, "artifact");
  requireSha256(receipt.content_hash, "download content hash");
  requireSafeInteger(receipt.byte_size, "download byte size", 0);
  requireNonEmptyString(receipt.destination, "download destination");
  requireNodeReference(receipt.ledger_event_ref, "ledger event");
  return receipt as unknown as DownloadReceipt;
}

export interface ArtifactPreviewBlock {
  kind: string;
  text: string;
}

export interface ArtifactPreview {
  artifact_id: string;
  preview_kind: string;
  title: string;
  blocks: ArtifactPreviewBlock[];
  clearance: string;
  taint: string;
  ledger_event_ref: string;
}

function approvedProfilePayload(profile: ApprovedNodeProfileReference | ApprovedNodeProfile) {
  if (!profile.approvedByPolicy || !profile.profileId.trim()) throw new Error("The approved Node profile is incomplete or not approved by policy.");
  return toNativeNodeProfileReference(profile);
}

/**
 * Sends only a native selection token and an approved profile to Rust. The
 * webview never receives or parses the selected file bytes.
 */
export function uploadSelectedQueryFile(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  selectionId: string,
  taskId: string,
): Promise<IntakeManifest> {
  const approved = approvedProfilePayload(profile);
  if (!taskId.trim() || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(taskId)) throw new Error("The task identifier is invalid for File Intake.");
  return invoke<unknown>("upload_selected_query_file", {
    profileId: approved.profile_id,
    selection_id: selectionId,
    task_id: taskId,
  }).then((value) => validateIntakeManifest(value, validateClearanceContext(profile)));
}

/**
 * Requests a safe, Node-generated preview. Arbitrary HTML and document bytes
 * are intentionally not part of this frontend contract.
 */
export function fetchSafePreview(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  previewRef: string,
  expectedSourceHash: string,
): Promise<SafePreview> {
  const approved = approvedProfilePayload(profile);
  return invoke<unknown>("fetch_safe_preview", {
    profileId: approved.profile_id,
    preview_ref: previewRef,
    expected_source_hash: expectedSourceHash,
  }).then((value) => validateSafePreview(value, previewRef, expectedSourceHash, validateClearanceContext(profile)));
}

/**
 * Requests a Node-generated structured artifact preview. The webview receives
 * typed text blocks only, never an Office package, PDF script, or HTML payload.
 */
export function fetchArtifactPreview(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  artifactId: string,
): Promise<ArtifactPreview> {
  const approved = approvedProfilePayload(profile);
  return invoke<unknown>("fetch_artifact_preview", {
    profileId: approved.profile_id,
    artifact_id: artifactId,
  }).then((value) => validateArtifactPreview(value, artifactId, validateClearanceContext(profile)));
}

/**
 * Requests a native save dialog and a Node-authorized artifact download.
 */
export function downloadArtifact(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  artifactId: string,
  suggestedName: string,
): Promise<DownloadReceipt> {
  const approved = approvedProfilePayload(profile);
  return invoke<unknown>("download_artifact", {
    profileId: approved.profile_id,
    artifact_id: artifactId,
    suggested_name: suggestedName,
  }).then((value) => validateDownloadReceipt(value, artifactId));
}

/**
 * Shared download boundary for every desktop surface. A native save result
 * is not presented as successful until its artifact identity, content hash,
 * size, destination, and ledger reference have been checked.
 */
export async function downloadVerifiedArtifact(
  profile: ApprovedNodeProfileReference | ApprovedNodeProfile,
  artifactId: string,
  suggestedName: string,
): Promise<DownloadReceipt> {
  return validateDownloadReceipt(await downloadArtifact(profile, artifactId, suggestedName), artifactId);
}
