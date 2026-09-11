import { browser, expect } from "@wdio/globals";

describe("AirBench desktop shell", () => {
  it("renders the private-by-design task surface", async () => {
    await expect(browser.$("h1")).toHaveText("What do you want AirBench to complete?");
    await expect(browser.$('[data-testid="task-composer"]')).toBeDisplayed();
    await expect(browser.$('[data-testid="start-task"]')).toBeDisabled();
    await expect(browser.$('[data-testid="app-version"]')).toHaveText(expect.stringContaining("AirBench 0.1.0"));
  });

  it("keeps routing policy-controlled when no qualified capability catalog exists", async () => {
    await browser.$('[aria-controls="launchpad-routing"]').click();
    await expect(browser.$("#launchpad-routing")).toHaveText(expect.stringContaining("Auto route is always in control"));
    await expect(browser.$("#launchpad-routing select")).toBeDisabled();
    await expect(browser.$("#launchpad-routing")).toHaveText(expect.stringContaining("The Node selects a qualified capability for each validated step"));
    await expect(browser.$("#launchpad-routing")).not.toHaveText(expect.stringContaining("http://"));
    await expect(browser.$("#launchpad-routing")).not.toHaveText(expect.stringContaining("https://"));
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
    const taskId = "task-desktop-1";
    const nodeIdentity = "fixture-node-01";
    const protocolVersion = "0.1";
    const now = "2026-09-10T12:00:00Z";
    const contentHash = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const sourceHash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const initialSnapshot = {
      schemaVersion: protocolVersion,
      compatibilityId: "airbench-node-protocol",
      taskId: taskId,
      snapshotId: "snapshot-desktop-1",
      asOfSequence: 1,
      title: "Inspection approval note",
      requestSummary: "Review the scanned inspection report and draft an approval note.",
      status: "planning",
      phase: "planning",
      clearanceContext: "restricted",
      inputManifestRef: "",
      evidence: [],
      facts: [],
      artifactRefs: [],
      unresolvedQuestions: [],
      nodeConnectionRef: nodeIdentity,
      ledgerHeadRef: "ledger-task-created",
    };
    const taskSnapshot = {
      ...initialSnapshot,
      snapshotId: "snapshot-desktop-6",
      asOfSequence: 6,
      inputManifestRef: "intake-1",
      artifactRefs: [],
      ledgerHeadRef: "ledger-task-current",
    };
    const plan = {
      schema_version: "1.0",
      compatibility_id: "airbench-core-contracts",
      task_id: taskId,
      node_identity: nodeIdentity,
      protocol_version: protocolVersion,
      clearance_context: "restricted",
      plan_state: "ready",
      task_sequence: 6,
      team_id: "team-desktop-1",
      assignments: ["assignment-desktop-1"],
      dependency_graph: { "assignment-desktop-1": [] },
      concurrency_ceiling: 1,
      execution_mode: "serial_virtual_team",
      worker_capabilities: { "assignment-desktop-1": "reasoning" },
      hardware_profile_ref: "hardware-desktop-1",
      hardware_reason: "The local fixture Node admitted a bounded CPU execution lane for this shell validation.",
      required_verification: true,
      completion_criteria: ["A reviewed approval note is produced."],
      required_authority: "operator_approval",
      authority_reason: "An authorized operator must approve this plan before execution.",
      plan_version_hash: "plan-desktop-1",
      policy_version_hash: "policy-desktop-1",
      ledger_event_ref: "ledger-plan-desktop-1",
      failure_code: null,
      failure_reason: null,
    };
    const artifactReview = {
      schemaVersion: protocolVersion,
      compatibilityId: "airbench-node-protocol",
      taskId,
      artifactId: "artifact-1",
      nodeIdentity,
      protocolVersion,
      clearanceContext: "restricted",
      title: "Inspection approval note",
      mediaType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      fileFormat: "docx",
      templateId: "validation-pack.approval-note",
      templateVersion: "0.1",
      contentHash,
      byteSize: 128,
      status: "verified_draft",
      verificationStatus: "passed",
      structuralCheck: "passed",
      visualCheck: "unavailable",
      approvalState: "pending",
      approvalBlockingReasons: ["Operator review is required before release."],
      sourceRefs: ["intake-1"],
      evidenceRefs: ["evidence-inspection-1"],
      verificationRefs: ["verification-1"],
      deterministicValueRefs: ["finding_count"],
      confidence: 0.96,
      clearance: "restricted",
      taint: "untrusted",
      derivation: { finding_count: { operation: "count", input_refs: ["evidence-inspection-1"] } },
      previewRef: "artifact-1",
      downloadRef: "artifact-1",
      ledgerEventRef: "ledger-artifact-review",
      artifactSequence: 7,
      createdAt: now,
    };
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
      protocol_compatibility_id: "airbench-node-protocol",
      clearance_context: "restricted",
      authenticated_subject: "fixture-user",
      domain_pack_ref: "validation-pack.v0",
      sovereignty: "verified",
      ledger_event_ref: "fixture-ledger-connection-001"
    });
    const pickFile = await browser.tauri.mock("pick_query_file");
    await pickFile.mockReturnValue({ selection_id: "fixture-selection", file_name: "inspection-report.pdf", byte_size: 110 });
    const upload = await browser.tauri.mock("upload_selected_query_file");
    await upload.mockReturnValue({ intake_id: "intake-1", file_name: "inspection-report.pdf", byte_size: 110, source_hash: `sha256:${sourceHash}`, revision_id: "revision-1", media_type: "application/pdf", page_count: 1, ocr_status: "completed", vision_status: "completed", clearance: "restricted", taint: "untrusted", preview_ref: "preview-1", artifact_ref: "artifact-1", ledger_event_ref: "ledger-intake-1" });
    const preview = await browser.tauri.mock("fetch_safe_preview");
    await preview.mockReturnValue({ preview_ref: "preview-1", preview_kind: "text", text: "Node-generated safe preview. The source remains untrusted data.", source_hash: `sha256:${sourceHash}`, source_region: "page:1", confidence: 0.98, clearance: "restricted", taint: "untrusted", ledger_event_ref: "ledger-preview-1" });
    const artifactPreview = await browser.tauri.mock("fetch_artifact_preview");
    await artifactPreview.mockReturnValue({ artifact_id: "artifact-1", preview_kind: "structured_document", title: "Inspection approval note", blocks: [{ kind: "heading", text: "Approval note" }, { kind: "paragraph", text: "Node-generated artifact data." }], clearance: "restricted", taint: "untrusted", ledger_event_ref: "ledger-artifact-preview-1" });
    const artifactDownload = await browser.tauri.mock("download_artifact");
    await artifactDownload.mockImplementation((args: { artifact_id?: string; suggested_name?: string } | undefined) => {
      const input = args ?? {};
      return { artifact_id: input.artifact_id ?? "artifact-1", destination: input.suggested_name ?? "approval-note.docx", content_hash: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", ledger_event_ref: "ledger-download-1", byte_size: 128 };
    });
    const create = await browser.tauri.mock("create_task");
    await create.mockImplementation((args: { command?: { command_id?: string; idempotency_key?: string } } | undefined) => {
      const submitted = args?.command ?? {};
      return {
        task: {
          schema_version: "1.0",
          compatibility_id: "airbench-core-contracts",
          task_id: "task-desktop-1",
          principal_id: "fixture-user",
          clearance: "restricted",
          request: "Review the scanned inspection report and draft an approval note.",
          domain_pack_ref: "validation-pack.v0",
          risk_class: "review",
          autonomy_ceiling: "review_required",
          allowed_evidence_scope: ["task-input"],
          permitted_worker_capabilities: ["reasoning"],
          permitted_tools: [],
          output_contract: "approval_note.docx",
          verification_criteria: ["A reviewed approval note is produced."],
          resource_budget: { timeout_seconds: 300 },
          title: "Inspection approval note",
          project_ref: null,
          priority: "normal",
          deadline: null,
          input_manifest_refs: [],
          state: "accepted",
          parent_task_id: null,
          created_at: "2026-09-10T12:00:00Z",
        },
        snapshot: {
          schemaVersion: "0.1",
          compatibilityId: "airbench-node-protocol",
          taskId: "task-desktop-1",
          snapshotId: "snapshot-desktop-1",
          asOfSequence: 1,
          title: "Inspection approval note",
          requestSummary: "Review the scanned inspection report and draft an approval note.",
          status: "planning",
          phase: "planning",
          clearanceContext: "restricted",
          inputManifestRef: "",
          evidence: [],
          facts: [],
          artifactRefs: [],
          unresolvedQuestions: [],
          nodeConnectionRef: "fixture-node-01",
          ledgerHeadRef: "ledger-task-created",
        },
        ledger_event_ref: "ledger-task-created",
        command: {
          schema_version: "1.0",
          compatibility_id: "airbench-core-contracts",
          outcome: "accepted",
          command_id: submitted.command_id,
          task_id: "task-desktop-1",
          idempotency_key: submitted.idempotency_key,
          ledger_event_ref: "ledger-task-created",
          sequence: 1,
          state: "accepted",
          node_identity: "fixture-node-01",
          protocol_version: "0.1",
          clearance_context: "restricted",
          event_type: "task.created",
          code: null,
          message: null,
          reason: null,
        },
      };
    });
    const snapshot = await browser.tauri.mock("fetch_task_snapshot");
    await snapshot.mockReturnValue(taskSnapshot);
    const authorize = await browser.tauri.mock("send_task_command");
    await authorize.mockImplementation((args: { command?: { command_id?: string; command_type?: string; task_id?: string | null; idempotency_key?: string } } | undefined) => {
      const submitted = args?.command ?? {};
      const fixtureState = (globalThis as typeof globalThis & { __airbenchFixture?: { planApproved: boolean } }).__airbenchFixture ??= { planApproved: false };
      const approvingPlan = submitted.command_type === "task.approve_plan";
      if (approvingPlan) fixtureState.planApproved = true;
      return {
        schema_version: "1.0",
        compatibility_id: "airbench-core-contracts",
        outcome: "accepted",
        command_id: submitted.command_id,
        task_id: submitted.task_id,
        idempotency_key: submitted.idempotency_key,
        ledger_event_ref: approvingPlan ? "ledger-plan-approved" : "ledger-task-authorized",
        sequence: approvingPlan ? 7 : 5,
        state: "accepted",
        node_identity: "fixture-node-01",
        protocol_version: "0.1",
        clearance_context: "restricted",
        event_type: approvingPlan ? "task.plan.approved" : "task.authorized",
        code: null,
        message: null,
        reason: null,
      };
    });
    const taskPlan = await browser.tauri.mock("fetch_task_plan");
    await taskPlan.mockReturnValue(plan);
    const events = await browser.tauri.mock("fetch_task_events");
    await events.mockImplementation((args: { afterSequence?: number } | undefined) => {
      const afterSequence = Number(args?.afterSequence ?? 0);
      const fixtureState = (globalThis as typeof globalThis & { __airbenchFixture?: { planApproved: boolean } }).__airbenchFixture;
      const eventBatch = fixtureState?.planApproved && afterSequence < 7 ? [{
        eventId: "event-artifact-ready",
        taskId: "task-desktop-1",
        sequence: 7,
        schemaVersion: "0.1",
        compatibilityId: "airbench-node-protocol",
        eventType: "artifact.ready",
        occurredAt: "2026-09-10T12:00:00Z",
        actor: "fixture-node-01",
        clearanceContext: "restricted",
        payloadHash: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        ledgerEventRef: "ledger-artifact-ready",
        payload: { artifactId: "artifact-1" },
      }] : [];
      return {
        schema_version: "1.0",
        compatibility_id: "airbench-core-contracts",
        stream_id: "task-desktop-1",
        node_identity: "fixture-node-01",
        protocol_version: "0.1",
        clearance_context: "restricted",
        events: eventBatch,
        next_sequence: eventBatch.length > 0 ? 7 : 7,
        has_more: false,
        ledger_event_refs: eventBatch.length > 0 ? ["ledger-artifact-ready"] : [],
      };
    });
    const routeTrace = await browser.tauri.mock("fetch_task_route_trace");
    await routeTrace.mockReturnValue({ schemaVersion: protocolVersion, compatibilityId: "airbench-node-protocol", taskId, nodeIdentity, protocolVersion, clearanceContext: "restricted", entries: [] });
    const review = await browser.tauri.mock("fetch_task_artifact_review");
    await review.mockReturnValue(artifactReview);

    await browser.$('[data-testid="node-chip"]').click();
    await browser.$("button*=Reload").click();
    await expect(browser.$(".profile-card")).toBeDisplayed();
    await browser.$(".profile-card button").click();
    await expect(browser.$('[data-testid="node-readiness-panel"]')).toHaveText(expect.stringContaining("Approved Node connection verified"));
    await browser.$(".new-task-button").click();
    await browser.$('[aria-label="Task outcome"]').setValue("Review the scanned inspection report and draft an approval note.");
    await browser.$('[data-testid="attach-files"]').click();
    await expect(browser.$(".selected-file")).toHaveText(expect.stringContaining("inspection-report.pdf"));
    await browser.$('[data-testid="start-task"]').click();
    try {
      await browser.$('[data-testid="task-workspace"]').waitForDisplayed({ timeout: 10000 });
    } catch (error) {
      console.info("[AIRBENCH_WDIO_FAILURE_STATE]", await browser.$("body").getText());
      throw error;
    }
    await expect(browser.$('[data-testid="task-workspace"]')).toHaveText(expect.stringContaining("serial_virtual_team"));
    await expect(browser.$('[data-testid="plan-review"]')).toBeDisplayed();
    await browser.$('[data-testid="approve-plan"]').click();
    await expect(browser.$('[aria-label="Plan approval result"]')).toBeDisplayed();
    await expect(browser.$(".worktrace-artifact-list")).toBeDisplayed();
    await browser.$(".worktrace-artifact-list .proof-record-button").click();
    await expect(browser.$('[aria-label="Node-generated artifact preview"]')).toHaveText(expect.stringContaining("Inspection approval note"));
    await expect(browser.$('[aria-label="Node artifact review"]')).toHaveText(expect.stringContaining("Verified Draft"));
    await browser.$(".proof-artifact-preview .compact-button").click();
    await expect(browser.$(".proof-artifact-actions")).toHaveText(expect.stringContaining("ledger-download-1"));
  });
});
