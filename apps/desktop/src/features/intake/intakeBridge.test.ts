import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { downloadArtifact, downloadVerifiedArtifact, fetchArtifactPreview, fetchSafePreview, uploadSelectedQueryFile, validateArtifactPreview, validateDownloadReceipt, validateIntakeManifest, validateSafePreview } from "./intakeBridge";
import type { ApprovedNodeProfile } from "../../platform/node/nodeConnection";
import type { ArtifactPreview, DownloadReceipt, IntakeManifest, SafePreview } from "./intakeBridge";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1",
  displayName: "Plant Node",
  endpoint: "http://127.0.0.1:9443",
  transport: "loopback",
  nodeIdentity: "node-1",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  certificatePinSha256: null,
  trustedCaPem: null,
  credentialRef: "fixture-user",
  approvedByPolicy: true,
};

const receipt: DownloadReceipt = {
  artifact_id: "artifact-1",
  destination: "C:/Users/operator/approval-note.pdf",
  content_hash: `sha256:${"a".repeat(64)}`,
  ledger_event_ref: "ledger-download-1",
  byte_size: 128,
};

const manifest: IntakeManifest = {
  intake_id: "intake-1",
  file_name: "inspection-report.pdf",
  byte_size: 2048,
  source_hash: `sha256:${"a".repeat(64)}`,
  revision_id: "revision-1",
  media_type: "application/pdf",
  page_count: 2,
  ocr_status: "completed",
  vision_status: "not_applicable",
  clearance: "restricted",
  taint: "untrusted",
  preview_ref: "preview-1",
  artifact_ref: "artifact-1",
  ledger_event_ref: "ledger-intake-1",
};

const safePreview: SafePreview = {
  preview_ref: "preview-1",
  preview_kind: "pdf_page",
  text: "Inspection report preview",
  source_hash: manifest.source_hash,
  source_region: "page:1",
  confidence: 0.98,
  clearance: "restricted",
  taint: "untrusted",
  ledger_event_ref: "ledger-preview-1",
};

const artifactPreview: ArtifactPreview = {
  artifact_id: "artifact-1",
  preview_kind: "structured_document",
  title: "Approval note",
  blocks: [{ kind: "paragraph", text: "Approval note preview" }],
  clearance: "restricted",
  taint: "untrusted",
  ledger_event_ref: "ledger-artifact-preview-1",
};

describe("File Intake frontend bridge", () => {
  beforeEach(() => {
    invokeMock.mockReset();
  });

  it("submits only the selection token through the approved Rust command", async () => {
    invokeMock.mockResolvedValueOnce(manifest);

    await uploadSelectedQueryFile(profile, "selection-1");

    expect(invokeMock).toHaveBeenCalledWith("upload_selected_query_file", {
      profileId: "profile-1",
      selection_id: "selection-1",
    });
  });

  it("rejects an unapproved profile before IPC", async () => {
    expect(() => uploadSelectedQueryFile({ ...profile, approvedByPolicy: false }, "selection-1")).toThrowError(/approved by policy/);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("keeps preview and download as typed Node commands", async () => {
    invokeMock.mockResolvedValueOnce(safePreview);
    invokeMock.mockResolvedValueOnce(artifactPreview);
    invokeMock.mockResolvedValueOnce(receipt);

    await fetchSafePreview(profile, "preview-1", `sha256:${"a".repeat(64)}`);
    await fetchArtifactPreview(profile, "artifact-1");
    await downloadArtifact(profile, "artifact-1", "approval-note.pdf");

    expect(invokeMock.mock.calls.slice(-3)).toEqual([
      ["fetch_safe_preview", expect.objectContaining({ profileId: "profile-1", preview_ref: "preview-1", expected_source_hash: `sha256:${"a".repeat(64)}` })],
      ["fetch_artifact_preview", expect.objectContaining({ profileId: "profile-1", artifact_id: "artifact-1" })],
      ["download_artifact", expect.objectContaining({ profileId: "profile-1", artifact_id: "artifact-1", suggested_name: "approval-note.pdf" })],
    ]);
  });
});

describe("webview intake response boundary", () => {
  it("accepts complete Node responses and returns contract-shaped values", () => {
    expect(validateIntakeManifest({ ...manifest, unexpected: "ignored" }, "restricted")).toEqual(manifest);
    expect(validateSafePreview({ ...safePreview, unexpected: "ignored" }, "preview-1", manifest.source_hash, "restricted")).toEqual(safePreview);
    expect(validateArtifactPreview({ ...artifactPreview, unexpected: "ignored" }, "artifact-1", "restricted")).toEqual(artifactPreview);
  });

  it("rejects malformed manifests before they become React state", () => {
    expect(() => validateIntakeManifest({ ...manifest, source_hash: "not-a-hash" }, "restricted")).toThrow("source hash");
    expect(() => validateIntakeManifest({ ...manifest, ocr_status: "finished" }, "restricted")).toThrow("OCR status");
    expect(() => validateIntakeManifest({ ...manifest, clearance: "secret" }, "restricted")).toThrow("over-cleared");
    expect(() => validateIntakeManifest({ ...manifest, ledger_event_ref: "../ledger" }, "restricted")).toThrow("ledger event reference");
  });

  it("rejects previews that lose source identity, provenance, or safe text limits", () => {
    expect(() => validateSafePreview({ ...safePreview, source_hash: `sha256:${"b".repeat(64)}` }, "preview-1", manifest.source_hash, "restricted")).toThrow("does not match");
    expect(() => validateSafePreview({ ...safePreview, confidence: 1.1 }, "preview-1", manifest.source_hash, "restricted")).toThrow("confidence");
    expect(() => validateSafePreview({ ...safePreview, taint: "unknown" }, "preview-1", manifest.source_hash, "restricted")).toThrow("taint");
    expect(() => validateArtifactPreview({ ...artifactPreview, blocks: [{ kind: "paragraph", text: "" + "x".repeat(10 * 1024 * 1024 + 1) }] }, "artifact-1", "restricted")).toThrow("artifact preview block text");
    expect(() => validateArtifactPreview({ ...artifactPreview, artifact_id: "artifact-2" }, "artifact-1", "restricted")).toThrow("does not match");
  });
});

describe("download receipt boundary", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts a complete receipt for the requested artifact", () => {
    expect(validateDownloadReceipt(receipt, "artifact-1")).toBe(receipt);
  });

  it("rejects a receipt for a different artifact or with an invalid hash", () => {
    expect(() => validateDownloadReceipt({ ...receipt, artifact_id: "artifact-2" }, "artifact-1")).toThrow("does not match");
    expect(() => validateDownloadReceipt({ ...receipt, content_hash: "sha256:not-a-digest" }, "artifact-1")).toThrow("content hash");
  });

  it("rejects incomplete local save or ledger information", () => {
    expect(() => validateDownloadReceipt({ ...receipt, destination: "" }, "artifact-1")).toThrow("destination");
    expect(() => validateDownloadReceipt({ ...receipt, byte_size: -1 }, "artifact-1")).toThrow("byte size");
    expect(() => validateDownloadReceipt({ ...receipt, ledger_event_ref: "" }, "artifact-1")).toThrow("ledger event");
  });

  it("validates the native receipt before reporting a verified download", async () => {
    invokeMock.mockResolvedValueOnce(receipt);
    await expect(downloadVerifiedArtifact(profile, "artifact-1", "approval-note.pdf")).resolves.toEqual(receipt);

    invokeMock.mockResolvedValueOnce({ ...receipt, artifact_id: "artifact-other" });
    await expect(downloadVerifiedArtifact(profile, "artifact-1", "approval-note.pdf")).rejects.toThrow("does not match");
  });
});
