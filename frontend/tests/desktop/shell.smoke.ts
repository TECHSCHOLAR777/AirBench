import { browser, expect } from "@wdio/globals";

describe("AirBench desktop shell", () => {
  it("renders the private-by-design task surface", async () => {
    await expect(browser.$("h1")).toHaveText("What should AirBench complete?");
    await expect(browser.$('[data-testid="task-composer"]')).toBeDisplayed();
    await expect(browser.$('[data-testid="start-task"]')).toBeDisabled();
    await expect(browser.$('[data-testid="app-version"]')).toHaveText(expect.stringContaining("AirBench 0.1.0"));
  });

  it("uses IPC mocking for native file selection", async () => {
    const pickFile = await browser.tauri.mock("pick_query_file");
    await pickFile.mockReturnValue({
      selection_id: "webdriver-selection",
      file_name: "inspection-report.pdf",
      byte_size: 4096
    });

    await browser.$('[data-testid="attach-files"]').click();
    await expect(browser.$(".selected-file")).toHaveText(expect.stringContaining("inspection-report.pdf"));
    await expect(browser.$('[role="status"]')).toHaveText(expect.stringContaining("File selected"));
  });

  it("navigates to trusted Node settings without exposing an endpoint editor", async () => {
    await browser.$('[data-testid="open-node-settings"]').click();
    await expect(browser.$("h1")).toHaveText("Node and settings");
    await expect(browser.$("body")).not.toHaveText(expect.stringContaining("http://"));
    await expect(browser.$("body")).not.toHaveText(expect.stringContaining("https://"));
  });

  it("executes a Tauri-side assertion and emits a frontend log marker", async () => {
    const location = await browser.tauri.execute(() => window.location.href);
    expect(location).toBeTruthy();
    await browser.tauri.execute(() => console.info("[AIRBENCH_WDIO] frontend log capture marker"));
  });

  it("connects through the approved profile and renders a safe intake preview", async () => {
    const profiles = await browser.tauri.mock("list_approved_node_profiles");
    await profiles.mockReturnValue([{
      profile_id: "fixture-profile",
      display_name: "Fixture Node",
      transport: "loopback",
      node_identity: "fixture-node-01",
      protocol_version: "0.1",
      clearance_context: "restricted",
      approved_by_policy: true
    }]);
    const connect = await browser.tauri.mock("connect_node");
    await connect.mockReturnValue({
      state: "connected",
      profile_id: "fixture-profile",
      node_identity: "fixture-node-01",
      protocol_version: "0.1",
      clearance_context: "restricted",
      authenticated_subject: "fixture-user",
      sovereignty: "verified",
      ledger_event_ref: "fixture-ledger-connection-001"
    });
    const pickFile = await browser.tauri.mock("pick_query_file");
    await pickFile.mockReturnValue({ selection_id: "fixture-selection", file_name: "inspection-report.pdf", byte_size: 110 });
    const upload = await browser.tauri.mock("upload_selected_query_file");
    await upload.mockReturnValue({ intake_id: "intake-1", file_name: "inspection-report.pdf", byte_size: 110, source_hash: "sha256:source", revision_id: "revision-1", media_type: "application/pdf", page_count: 1, ocr_status: "completed", vision_status: "completed", clearance: "restricted", taint: "untrusted", preview_ref: "preview-1", artifact_ref: "artifact-1", ledger_event_ref: "ledger-intake-1" });
    const preview = await browser.tauri.mock("fetch_safe_preview");
    await preview.mockReturnValue({ preview_ref: "preview-1", preview_kind: "text", text: "Node-generated safe preview. The source remains untrusted data.", source_hash: "sha256:source", source_region: "page:1", confidence: 0.98, clearance: "restricted", taint: "untrusted", ledger_event_ref: "ledger-preview-1" });
    const artifactPreview = await browser.tauri.mock("fetch_artifact_preview");
    await artifactPreview.mockReturnValue({ artifact_id: "artifact-1", preview_kind: "structured_document", title: "Inspection approval note", blocks: [{ kind: "heading", text: "Approval note" }, { kind: "paragraph", text: "Node-generated artifact data." }], clearance: "restricted", taint: "untrusted", ledger_event_ref: "ledger-artifact-preview-1" });
    const artifactDownload = await browser.tauri.mock("download_artifact");
    await artifactDownload.mockReturnValue({ artifact_id: "artifact-1", destination: "approval-note.pdf", content_hash: "sha256:artifact", ledger_event_ref: "ledger-download-1", byte_size: 128 });

    await browser.$('[data-testid="node-chip"]').click();
    await browser.$("button*=Reload").click();
    await expect(browser.$(".profile-card")).toBeDisplayed();
    await browser.$(".profile-card button").click();
    await expect(browser.$(".settings-status")).toHaveText(expect.stringContaining("Fixture Node is connected"));
    await browser.$(".new-task-button").click();
    await browser.$('[data-testid="attach-files"]').click();
    await browser.$(".compact-button").click();
    await expect(browser.$('[data-testid="intake-result"]')).toHaveText(expect.stringContaining("Node-generated safe preview"));
    await expect(browser.$('[data-testid="intake-result"]')).toHaveText(expect.stringContaining("untrusted"));
    await expect(browser.$('[data-testid="artifact-preview"]')).toHaveText(expect.stringContaining("Inspection approval note"));
    await browser.$('[data-testid="download-artifact"]').click();
    await expect(browser.$('[data-testid="download-receipt"]')).toHaveText(expect.stringContaining("ledger-download-1"));
  });
});
