import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfile } from "./nodeBridge";
import { assertApprovedNodeProfile, type ApprovedNodeProfile } from "./nodeConnection";

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

function approvedProfilePayload(profile: ApprovedNodeProfile) {
  return toNativeNodeProfile(assertApprovedNodeProfile(profile));
}

/**
 * Sends only a native selection token and an approved profile to Rust. The
 * webview never receives or parses the selected file bytes.
 */
export function uploadSelectedQueryFile(
  profile: ApprovedNodeProfile,
  selectionId: string,
): Promise<IntakeManifest> {
  return invoke<IntakeManifest>("upload_selected_query_file", {
    profile: approvedProfilePayload(profile),
    selection_id: selectionId,
  });
}

/**
 * Requests a safe, Node-generated preview. Arbitrary HTML and document bytes
 * are intentionally not part of this frontend contract.
 */
export function fetchSafePreview(
  profile: ApprovedNodeProfile,
  previewRef: string,
): Promise<SafePreview> {
  return invoke<SafePreview>("fetch_safe_preview", {
    profile: approvedProfilePayload(profile),
    preview_ref: previewRef,
  });
}

/**
 * Requests a native save dialog and a Node-authorized artifact download.
 */
export function downloadArtifact(
  profile: ApprovedNodeProfile,
  artifactId: string,
  suggestedName: string,
): Promise<DownloadReceipt> {
  return invoke<DownloadReceipt>("download_artifact", {
    profile: approvedProfilePayload(profile),
    artifact_id: artifactId,
    suggested_name: suggestedName,
  });
}
