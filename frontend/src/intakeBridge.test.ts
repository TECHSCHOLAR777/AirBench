import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { downloadArtifact, fetchArtifactPreview, fetchSafePreview, uploadSelectedQueryFile } from "./intakeBridge";
import type { ApprovedNodeProfile } from "./nodeConnection";

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

describe("File Intake frontend bridge", () => {
  beforeEach(() => {
    invokeMock.mockReset();
  });

  it("submits only the selection token through the approved Rust command", async () => {
    invokeMock.mockResolvedValueOnce({ intake_id: "intake-1" });

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
    invokeMock.mockResolvedValueOnce({ preview_ref: "preview-1" });
    invokeMock.mockResolvedValueOnce({ artifact_id: "artifact-1", blocks: [] });
    invokeMock.mockResolvedValueOnce({ artifact_id: "artifact-1" });

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
