import { useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@airbench/tauri-invoke";
import type { AirBenchPresentationState, Screen } from "./contracts";
import { initialPresentationState } from "./contracts";
import { NodeConnectionController, type NodeConnectionView } from "./nodeConnectionController";
import type { ApprovedNodeProfileReference } from "./nodeConnection";
import { listApprovedNodeProfiles } from "./profileBridge";
import { downloadArtifact, fetchArtifactPreview, fetchSafePreview, uploadSelectedQueryFile, type ArtifactPreview, type DownloadReceipt, type IntakeManifest, type SafePreview } from "./intakeBridge";
import { createTask, fetchTaskPlan, fetchTaskSnapshot, sendTaskCommand, type CreateTaskResponse } from "./nodeCommands";
import type { NodeCommandResult, TaskPlanReview } from "./generated/core_contracts";
import { buildApprovePlanCommand, buildCancelTaskCommand, buildCreateTaskCommand } from "./taskComposer";
import { fetchTaskEventBatch } from "./eventTransport";
import { maySendConsequentialCommand, TaskEventSynchronizer, type EventSyncState } from "./eventStore";
import type { TaskEvent, TaskProjection } from "./protocol";

type SelectedFile = { selection_id: string; file_name: string; byte_size: number };

const primaryNav: Array<{ id: Screen; label: string; icon: string }> = [
  { id: "home", label: "Home", icon: "H" },
  { id: "tasks", label: "Tasks", icon: "T" },
  { id: "review", label: "Review", icon: "R" },
];

const recordNav: Array<{ id: Screen; label: string; icon: string }> = [
  { id: "artifacts", label: "Artifacts", icon: "A" },
  { id: "history", label: "History", icon: "H" },
  { id: "audit", label: "Audit", icon: "L" },
];

function App() {
  const [state, setState] = useState<AirBenchPresentationState>(initialPresentationState);
  const [connection, setConnection] = useState<NodeConnectionView>({
    state: "not_connected", profileId: null, nodeIdentity: null, protocolVersion: null,
    clearanceContext: null, authenticatedSubject: null, domainPackRef: null, sovereignty: "unknown", ledgerEventRef: null, failure: null,
  });
  const [profiles, setProfiles] = useState<ApprovedNodeProfileReference[]>([]);
  const [profilesState, setProfilesState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [connectingProfileId, setConnectingProfileId] = useState<string | null>(null);
  const [showConnectionHelp, setShowConnectionHelp] = useState(false);
  const [taskText, setTaskText] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [projectRef, setProjectRef] = useState("");
  const [outputContract, setOutputContract] = useState("document");
  const [priority, setPriority] = useState("normal");
  const [deadline, setDeadline] = useState("");
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [intakeState, setIntakeState] = useState<"idle" | "uploading" | "ready" | "failed">("idle");
  const [intakeManifest, setIntakeManifest] = useState<IntakeManifest | null>(null);
  const [safePreview, setSafePreview] = useState<SafePreview | null>(null);
  const [artifactPreview, setArtifactPreview] = useState<ArtifactPreview | null>(null);
  const [downloadState, setDownloadState] = useState<"idle" | "downloading" | "downloaded" | "failed">("idle");
  const [downloadReceipt, setDownloadReceipt] = useState<DownloadReceipt | null>(null);
  const [taskResult, setTaskResult] = useState<CreateTaskResponse | null>(null);
  const [planReview, setPlanReview] = useState<TaskPlanReview | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planApprovalResult, setPlanApprovalResult] = useState<NodeCommandResult | null>(null);
  const [approvingPlan, setApprovingPlan] = useState(false);
  const [taskProjection, setTaskProjection] = useState<TaskProjection | null>(null);
  const [eventSyncState, setEventSyncState] = useState<EventSyncState | null>(null);
  const [taskControlResult, setTaskControlResult] = useState<NodeCommandResult | null>(null);
  const [controllingTask, setControllingTask] = useState(false);
  const synchronizerRef = useRef<TaskEventSynchronizer | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const controller = useMemo(() => new NodeConnectionController(), []);

  const screenTitle = useMemo(() => {
    const titles: Record<Screen, string> = { home: "Home", tasks: "Tasks", review: "Review", artifacts: "Artifacts", history: "History", audit: "Audit", node: "Node and settings" };
    return titles[state.screen];
  }, [state.screen]);

  const selectScreen = (screen: Screen) => setState((current) => ({ ...current, screen }));

  useEffect(() => {
    if (state.screen !== "node" || profilesState !== "idle") return;
    let active = true;
    setProfilesState("loading");
    setProfileError(null);
    listApprovedNodeProfiles().then((loadedProfiles) => {
      if (!active) return;
      setProfiles(loadedProfiles);
      setProfilesState("ready");
    }).catch(() => {
      if (!active) return;
      setProfilesState("failed");
      setProfileError("The approved Node catalog could not be read. No connection is permitted.");
    });
    return () => { active = false; };
  }, [profilesState, state.screen]);

  const applyConnection = (next: NodeConnectionView) => {
    setConnection(next);
    setState((current) => ({
      ...current,
      node: {
        ...current.node,
        state: next.state === "connected" ? "connected" : "not_connected",
        displayName: profiles.find((profile) => profile.profileId === next.profileId)?.displayName ?? current.node.displayName,
        lastCheckedAt: next.state === "connected" ? new Date().toISOString() : current.node.lastCheckedAt,
        sovereignty: next.sovereignty === "verified" ? "verified" : "unknown",
      },
    }));
  };

  const connectProfile = async (profile: ApprovedNodeProfileReference) => {
    setConnectingProfileId(profile.profileId);
    setConnection({ ...controller.snapshot(), state: "connecting", profileId: profile.profileId });
    const next = await controller.connect(profile);
    applyConnection(next);
    setConnectingProfileId(null);
    setNotice(next.state === "connected" ? `${profile.displayName} is verified and ready.` : next.failure?.message ?? "The Node connection was blocked.");
  };

  const reconnect = async () => {
    setConnectingProfileId(connection.profileId);
    const next = await controller.reconnect();
    applyConnection(next);
    setConnectingProfileId(null);
  };

  const attachFile = async () => {
    setNotice(null);
    try {
      const selection = await invoke<SelectedFile | null>("pick_query_file");
      if (selection) {
        setSelectedFile(selection);
        setNotice("File selected. It will enter AirBench through the File Intake Layer when a Node is connected.");
      } else {
        setNotice("No file selected.");
      }
    } catch {
      setNotice("The native file picker is available in the desktop application. Connect an approved Node before submitting work.");
    }
  };

  const uploadSelectedFile = async () => {
    if (!selectedFile) return;
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected) {
      setNotice("Connect a verified Node before sending a file to the File Intake Layer.");
      return;
    }
    setIntakeState("uploading");
    setIntakeManifest(null);
    setSafePreview(null);
    setArtifactPreview(null);
    setDownloadState("idle");
    setDownloadReceipt(null);
    setNotice(null);
    try {
      const manifest = await uploadSelectedQueryFile(profile, selectedFile.selection_id);
      const preview = await fetchSafePreview(profile, manifest.preview_ref, manifest.source_hash);
      const artifact = await fetchArtifactPreview(profile, manifest.artifact_ref);
      setIntakeManifest(manifest);
      setSafePreview(preview);
      setArtifactPreview(artifact);
      setIntakeState("ready");
      setNotice("AirBench accepted the file through the File Intake Layer. Both previews are Node-generated and remain untrusted data.");
    } catch {
      setIntakeState("failed");
      setNotice("The Node could not complete intake. The original file was not parsed by the desktop app.");
    }
  };

  const downloadApprovedArtifact = async () => {
    if (!artifactPreview) return;
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected) {
      setDownloadState("failed");
      setNotice("Connect a verified Node before downloading an artifact.");
      return;
    }
    setDownloadState("downloading");
    setNotice(null);
    try {
      const receipt = await downloadArtifact(profile, artifactPreview.artifact_id, "approval-note.pdf");
      setDownloadReceipt(receipt);
      setDownloadState("downloaded");
      setNotice("The Node-authorized artifact was saved after its hash and ledger receipt were verified.");
    } catch {
      setDownloadState("failed");
      setNotice("The Node did not authorize or complete the artifact download. No unverified file was saved.");
    }
  };

  const syncTask = async (profile: ApprovedNodeProfileReference, snapshot: CreateTaskResponse["snapshot"]) => {
    const synchronizer = new TaskEventSynchronizer(
      (taskId, afterSequence) => fetchTaskEventBatch(profile, taskId, afterSequence),
      (taskId) => fetchTaskSnapshot(profile, taskId),
    );
    synchronizerRef.current = synchronizer;
    setTaskProjection(synchronizer.loadSnapshot(snapshot));
    setEventSyncState(synchronizer.state());
    const result = await synchronizer.synchronizeWithRetry({ maxAttempts: 3 });
    setTaskProjection(result.projection);
    setEventSyncState(result.state);
    return result;
  };

  const refreshTask = async () => {
    const synchronizer = synchronizerRef.current;
    if (!synchronizer) return;
    const result = await synchronizer.synchronizeWithRetry({ maxAttempts: 3 });
    setTaskProjection(result.projection);
    setEventSyncState(result.state);
  };

  const startTask = async () => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !connection.authenticatedSubject || !connection.clearanceContext || !connection.domainPackRef) {
      setNotice("Connect a verified Node before submitting a task.");
      return;
    }
    setCreatingTask(true);
    setTaskResult(null);
    setPlanReview(null);
    setPlanApprovalResult(null);
    setNotice(null);
    try {
      const commandId = `command.create.${crypto.randomUUID()}`;
      const command = buildCreateTaskCommand({
        actor: connection.authenticatedSubject,
        clearance: connection.clearanceContext,
        domainPackRef: connection.domainPackRef,
        request: taskText,
        title: taskTitle,
        projectRef: projectRef || null,
        outputContract,
        priority,
        deadline: deadline || null,
        inputManifestRefs: intakeManifest ? [intakeManifest.intake_id] : [],
      }, commandId, `idempotency.${commandId}`);
      const result = await createTask(profile, command);
      setTaskResult(result);
      setPlanLoading(true);
      try {
        const plan = await fetchTaskPlan(profile, result.task.task_id);
        setPlanReview(plan);
        setNotice(`Task accepted by ${profile.displayName}. The Node owns the task state and has returned the current plan review.`);
      } catch {
        setNotice(`Task accepted by ${profile.displayName}. The Node plan review is not available yet.`);
      } finally {
        setPlanLoading(false);
      }
      await syncTask(profile, result.snapshot);
      selectScreen("tasks");
    } catch {
      setNotice("The Node did not accept this task. No local task state was created.");
    } finally {
      setCreatingTask(false);
    }
  };

  const approvePlan = async () => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !connection.authenticatedSubject || !taskResult || !planReview) {
      setNotice("Connect a verified Node and wait for an approvable plan before continuing.");
      return;
    }
    if (planReview.plan_state !== "ready" || planReview.required_authority !== "operator_approval") {
      setNotice("This plan is not ready for operator approval. The Node must resolve its policy or hardware state first.");
      return;
    }
    setApprovingPlan(true);
    setPlanApprovalResult(null);
    setNotice(null);
    try {
      const commandId = `command.approve.${crypto.randomUUID()}`;
      const command = buildApprovePlanCommand(
        connection.authenticatedSubject,
        taskResult.task.task_id,
        planReview.task_sequence,
        "operator.confirmed.plan-review",
        commandId,
        `idempotency.${commandId}`,
      );
      const result = await sendTaskCommand(profile, command);
      setPlanApprovalResult(result);
      setNotice("Plan approval was accepted by the Node. Execution state will change only after the authoritative event arrives.");
    } catch {
      setNotice("The Node did not accept this plan approval. No local execution state was changed.");
    } finally {
      setApprovingPlan(false);
    }
  };

  const stopTask = async () => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !connection.authenticatedSubject || !taskProjection || !eventSyncState || !maySendConsequentialCommand(taskProjection, eventSyncState.status)) {
      setNotice("The task is not current on the approved Node. Reconnect and resynchronize before stopping it.");
      return;
    }
    setControllingTask(true);
    setTaskControlResult(null);
    try {
      const commandId = `command.stop.${crypto.randomUUID()}`;
      const command = buildCancelTaskCommand(
        connection.authenticatedSubject,
        taskProjection.taskId,
        taskProjection.lastAppliedSequence,
        "Operator requested stop from the live task workspace.",
        commandId,
        `idempotency.${commandId}`,
      );
      const result = await sendTaskCommand(profile, command);
      setTaskControlResult(result);
      setNotice("The stop command was accepted by the Node. The task view will change only after the stopped event is received.");
      await refreshTask();
    } catch {
      setNotice("The Node did not accept the stop command. No local task state was changed.");
    } finally {
      setControllingTask(false);
    }
  };

  const nodeConnected = connection.state === "connected" && controller.canSendConsequential();
  const canStart = nodeConnected && taskText.trim().length > 0 && (!selectedFile || intakeState === "ready") && !creatingTask;
  const nodeLabel = nodeConnected ? (profiles.find((profile) => profile.profileId === connection.profileId)?.displayName ?? "Node connected") : connection.state === "connecting" ? "Connecting to Node" : "Node not connected";
  const nodeDetail = nodeConnected ? "Verified and ready" : connection.state === "failed" ? "Connection blocked" : "Choose an approved Node";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="AirBench navigation">
        <div className="brand-lockup"><div className="brand-mark" aria-hidden="true">A</div><div><div className="brand-name">AirBench</div><div className="brand-subtitle">Sovereign workbench</div></div></div>
        <button className="new-task-button" onClick={() => selectScreen("home")}><span aria-hidden="true">+</span><span>New task</span><kbd>Ctrl N</kbd></button>
        <nav className="nav-groups"><NavGroup title="Work" items={primaryNav} active={state.screen} onSelect={selectScreen} /><NavGroup title="Records" items={recordNav} active={state.screen} onSelect={selectScreen} /></nav>
        <div className="sidebar-spacer" />
        <button className="node-chip" data-testid="node-chip" onClick={() => selectScreen("node")} aria-label="Open Node and settings"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" /><span><strong>{nodeLabel}</strong><small>{nodeDetail}</small></span><span className="chevron" aria-hidden="true">&gt;</span></button>
        <div className="user-row"><div className="avatar">RG</div><div><strong>Local operator</strong><small>{connection.clearanceContext ? `${connection.clearanceContext} clearance` : "Clearance not resolved"}</small></div><span className="more-icon" aria-hidden="true">...</span></div>
        <small className="build-info" data-testid="app-version">AirBench {__AIRBENCH_VERSION__} / offline shell</small>
      </aside>

      <main className="main-area">
        <header className="topbar"><div className="breadcrumb"><span>AirBench</span><span className="breadcrumb-slash">/</span><strong>{screenTitle}</strong></div><div className="topbar-actions"><div className="quiet-status"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" /> {nodeLabel}</div><button className="quiet-action" aria-label="Open command menu">Command</button><button className="quiet-action" aria-label="Open notifications">Alerts</button></div></header>
        <div className="content-wrap">
          {state.screen === "home" && <HomeView taskText={taskText} setTaskText={setTaskText} taskTitle={taskTitle} setTaskTitle={setTaskTitle} projectRef={projectRef} setProjectRef={setProjectRef} outputContract={outputContract} setOutputContract={setOutputContract} priority={priority} setPriority={setPriority} deadline={deadline} setDeadline={setDeadline} selectedFile={selectedFile} intakeState={intakeState} intakeManifest={intakeManifest} safePreview={safePreview} artifactPreview={artifactPreview} downloadState={downloadState} downloadReceipt={downloadReceipt} taskResult={taskResult} planReview={planReview} planLoading={planLoading} planApprovalResult={planApprovalResult} approvingPlan={approvingPlan} notice={notice} canStart={canStart} creatingTask={creatingTask} onAttach={attachFile} onUpload={uploadSelectedFile} onDownload={downloadApprovedArtifact} onStart={startTask} onApprovePlan={approvePlan} onRemoveFile={() => { setSelectedFile(null); setIntakeState("idle"); setIntakeManifest(null); setSafePreview(null); setArtifactPreview(null); setDownloadState("idle"); setDownloadReceipt(null); }} onHelp={() => setShowConnectionHelp(true)} onOpenNode={() => selectScreen("node")} />}
          {state.screen === "node" && <NodeSettingsView profiles={profiles} profilesState={profilesState} profileError={profileError} connection={connection} connectingProfileId={connectingProfileId} onConnect={connectProfile} onReconnect={reconnect} onReload={() => { setProfilesState("idle"); }} onHome={() => selectScreen("home")} />}
          {state.screen === "tasks" && taskProjection && <TaskWorkspaceView projection={taskProjection} syncState={eventSyncState} plan={planReview} approval={planApprovalResult} approving={approvingPlan} controlResult={taskControlResult} controlling={controllingTask} onStop={stopTask} onRefresh={refreshTask} onApprovePlan={approvePlan} onHome={() => selectScreen("home")} />}
          {state.screen !== "home" && state.screen !== "node" && state.screen !== "tasks" && <RecordView screen={screenTitle} onHome={() => selectScreen("home")} />}
        </div>
      </main>
      {showConnectionHelp && <ConnectionHelp onClose={() => setShowConnectionHelp(false)} onOpenNode={() => { setShowConnectionHelp(false); selectScreen("node"); }} />}
    </div>
  );
}

function NavGroup({ title, items, active, onSelect }: { title: string; items: Array<{ id: Screen; label: string; icon: string }>; active: Screen; onSelect: (screen: Screen) => void }) {
  return <div className="nav-group"><div className="nav-group-title">{title}</div>{items.map((item) => <button key={item.id} className={`nav-item ${active === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}><span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>{item.id === "review" && <span className="nav-count">0</span>}</button>)}</div>;
}

function HomeView({ taskText, setTaskText, taskTitle, setTaskTitle, projectRef, setProjectRef, outputContract, setOutputContract, priority, setPriority, deadline, setDeadline, selectedFile, intakeState, intakeManifest, safePreview, artifactPreview, downloadState, downloadReceipt, taskResult, planReview, planLoading, planApprovalResult, approvingPlan, notice, canStart, creatingTask, onAttach, onUpload, onDownload, onStart, onApprovePlan, onRemoveFile, onHelp, onOpenNode }: { taskText: string; setTaskText: (value: string) => void; taskTitle: string; setTaskTitle: (value: string) => void; projectRef: string; setProjectRef: (value: string) => void; outputContract: string; setOutputContract: (value: string) => void; priority: string; setPriority: (value: string) => void; deadline: string; setDeadline: (value: string) => void; selectedFile: SelectedFile | null; intakeState: "idle" | "uploading" | "ready" | "failed"; intakeManifest: IntakeManifest | null; safePreview: SafePreview | null; artifactPreview: ArtifactPreview | null; downloadState: "idle" | "downloading" | "downloaded" | "failed"; downloadReceipt: DownloadReceipt | null; taskResult: CreateTaskResponse | null; planReview: TaskPlanReview | null; planLoading: boolean; planApprovalResult: NodeCommandResult | null; approvingPlan: boolean; notice: string | null; canStart: boolean; creatingTask: boolean; onAttach: () => void; onUpload: () => void; onDownload: () => void; onStart: () => void; onApprovePlan: () => void; onRemoveFile: () => void; onHelp: () => void; onOpenNode: () => void }) {
  return <div className="home-view">
    <section className="welcome-block"><p className="eyebrow">PRIVATE BY DESIGN</p><h1>What should AirBench complete?</h1><p className="lead">Describe the outcome. Add files if they are part of the work.</p></section>
    <section className="composer-card" data-testid="task-composer" aria-label="New task composer">
      <textarea value={taskText} onChange={(event) => setTaskText(event.target.value)} placeholder="For example: Review the scanned inspection report and draft an approval note with the key findings and required actions." rows={4} />
      <div className="composer-fields" aria-label="Task details">
        <label><span>Title</span><input value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="A short name for this work" maxLength={256} /></label>
        <label><span>Project</span><input value={projectRef} onChange={(event) => setProjectRef(event.target.value)} placeholder="Optional project reference" maxLength={256} /></label>
        <label><span>Deliverable</span><select value={outputContract} onChange={(event) => setOutputContract(event.target.value)}><option value="document">Document</option><option value="summary">Summary</option><option value="spreadsheet">Spreadsheet</option><option value="presentation">Presentation</option><option value="code">Code</option></select></label>
        <label><span>Priority</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
        <label><span>Deadline</span><input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label>
      </div>
      {selectedFile && <div className="selected-file"><span className="file-badge">FILE</span><span><strong>{selectedFile.file_name}</strong><small>{formatBytes(selectedFile.byte_size)} / {intakeState === "ready" ? "accepted by File Intake" : "ready for File Intake"}</small></span><div className="selected-file-actions">{intakeState !== "ready" && <button className="secondary-button compact-button" onClick={onUpload} disabled={intakeState === "uploading"}>{intakeState === "uploading" ? "Sending..." : "Send to Node"}</button>}<button className="remove-file" onClick={onRemoveFile} aria-label="Remove selected file">Remove</button></div></div>}
      <div className="composer-footer"><div className="composer-tools"><button className="secondary-button" data-testid="attach-files" onClick={onAttach}><span aria-hidden="true">+</span> Attach files</button></div><button className="primary-button" data-testid="start-task" onClick={onStart} disabled={!canStart} title={canStart ? "Start task" : "Connect an approved Node, describe the outcome, and finish file intake before starting"}>{creatingTask ? "Submitting..." : "Start task"} <kbd>Enter</kbd></button></div>
    </section>
    {intakeManifest && safePreview && <section className="intake-result" data-testid="intake-result" aria-label="File Intake result"><div className="intake-result-head"><div><p className="eyebrow">FILE INTAKE COMPLETE</p><h2>{intakeManifest.file_name}</h2></div><span className="intake-badge">{intakeManifest.ocr_status} OCR</span></div><div className="intake-meta-grid"><div><span>Source hash</span><strong>{intakeManifest.source_hash}</strong></div><div><span>Pages</span><strong>{intakeManifest.page_count}</strong></div><div><span>Clearance</span><strong>{intakeManifest.clearance}</strong></div><div><span>Taint</span><strong>{intakeManifest.taint}</strong></div></div><div className="safe-preview"><div className="safe-preview-label">Node-generated safe preview <span>Page region: {safePreview.source_region}</span></div><p>{safePreview.text}</p><small>Confidence {Math.round(safePreview.confidence * 100)}% / ledger {safePreview.ledger_event_ref}</small></div></section>}
    {artifactPreview && <section className="artifact-preview" data-testid="artifact-preview" aria-label="Artifact preview"><div className="intake-result-head"><div><p className="eyebrow">NODE ARTIFACT PREVIEW</p><h2>{artifactPreview.title}</h2></div><span className="intake-badge">{artifactPreview.preview_kind}</span></div><div className="artifact-preview-meta"><span>{artifactPreview.clearance} clearance</span><span>{artifactPreview.taint} data</span><span>Ledger {artifactPreview.ledger_event_ref}</span></div><div className="artifact-blocks">{artifactPreview.blocks.map((block, index) => <div className="artifact-block" key={`${block.kind}-${index}`}><span className="artifact-block-kind">{block.kind}</span><p>{block.text}</p></div>)}</div><div className="artifact-actions"><button className="primary-button" data-testid="download-artifact" onClick={onDownload} disabled={downloadState === "downloading"}>{downloadState === "downloading" ? "Verifying..." : downloadState === "downloaded" ? "Download again" : "Download artifact"}</button>{downloadReceipt && <small data-testid="download-receipt">Saved {downloadReceipt.byte_size} bytes / {downloadReceipt.content_hash} / ledger {downloadReceipt.ledger_event_ref}</small>}</div></section>}
    {taskResult && <section className="task-confirmation" data-testid="task-confirmation" aria-label="Task submission result"><p className="eyebrow">TASK ACCEPTED BY NODE</p><strong>{taskResult.task.task_id}</strong><span>State: {taskResult.command.state ?? taskResult.task.state ?? "created"}</span><small>Ledger {taskResult.command.ledger_event_ref ?? taskResult.ledger_event_ref} / sequence {taskResult.command.sequence ?? taskResult.snapshot.asOfSequence}</small></section>}
    {taskResult && <PlanReviewCard plan={planReview} loading={planLoading} approval={planApprovalResult} approving={approvingPlan} onApprove={onApprovePlan} />}
    {notice && <div className="inline-notice" role="status">{notice}</div>}
    <div className="trust-line" role="status"><span className="trust-item"><span className="trust-check" aria-hidden="true">OK</span> Files stay on your node</span><span className="trust-item"><span className="trust-check" aria-hidden="true">OK</span> External network denied</span><button className="text-button" onClick={onHelp}>How this works</button></div>
    <section className="continue-section"><div className="section-heading"><div><h2>Continue work</h2><p>Your recent tasks will appear here.</p></div><button className="text-button" disabled>View history <span aria-hidden="true">-&gt;</span></button></div><div className="empty-state"><div className="empty-icon" aria-hidden="true">T</div><p>No tasks yet</p><small>When you start work, you can return to it here.</small></div></section>
    <section className="readiness-card"><div><p className="eyebrow">READY WHEN YOU ARE</p><h2>Connect a trusted Node to begin</h2><p>Your organization controls the models, tools, files, and audit record on that Node.</p></div><button className="secondary-button bordered-button" data-testid="open-node-settings" onClick={onOpenNode}>Open Node settings</button></section>
  </div>;
}

function PlanReviewCard({ plan, loading, approval, approving, onApprove }: { plan: TaskPlanReview | null; loading: boolean; approval: NodeCommandResult | null; approving: boolean; onApprove: () => void }) {
  if (loading) {
    return <section className="plan-review-card" data-testid="plan-review-loading" aria-label="Task plan review"><p className="eyebrow">PLAN REVIEW</p><h2>AirBench is preparing the plan</h2><p className="plan-muted">The Node is validating the work against policy and available hardware. No execution has started.</p></section>;
  }
  if (!plan) return null;
  const modeLabel: Record<string, string> = { parallel: "Parallel team", pipelined: "Pipelined team", serial_virtual_team: "Serial virtual team", not_selected: "Not selected" };
  const stateLabel: Record<string, string> = { not_ready: "Not ready", ready: "Ready for approval", queued: "Queued for hardware", needs_review: "Needs review", blocked: "Blocked", rejected: "Rejected" };
  const canApprove = plan.plan_state === "ready" && plan.required_authority === "operator_approval" && !approval;
  return <section className="plan-review-card" data-testid="plan-review" aria-label="Task plan review">
    <div className="plan-review-head"><div><p className="eyebrow">PLAN REVIEW</p><h2>{stateLabel[plan.plan_state] ?? plan.plan_state}</h2></div><span className={`intake-badge plan-state-${plan.plan_state}`}>{modeLabel[plan.execution_mode] ?? plan.execution_mode}</span></div>
    <p className="plan-muted">{plan.authority_reason}</p>
    {plan.failure_reason && <div className="plan-warning" role="status"><strong>{plan.failure_code ?? "Plan requires attention"}</strong><span>{plan.failure_reason}</span></div>}
    <div className="plan-meta-grid"><div><span>Team</span><strong>{plan.team_id ?? "Not assigned"}</strong></div><div><span>Concurrency</span><strong>{plan.concurrency_ceiling || "Not selected"}</strong></div><div><span>Hardware</span><strong>{plan.hardware_profile_ref ?? "Admission pending"}</strong></div><div><span>Verification</span><strong>{plan.required_verification ? "Required" : "Missing"}</strong></div></div>
    <div className="plan-reason"><span>Why this mode</span><p>{plan.hardware_reason}</p></div>
    <div className="plan-workers"><span>Capability lanes</span><div>{Object.entries(plan.worker_capabilities).map(([worker, capability]) => <span className="plan-worker" key={worker}>{worker}: {capability}</span>)}</div></div>
    <div className="plan-stages"><span>Stage dependencies</span>{Object.entries(plan.dependency_graph).map(([stage, dependencies]) => <div className="plan-stage" key={stage}><strong>{stage}</strong><small>{dependencies.length ? `After ${dependencies.join(", ")}` : "Can begin first"}</small></div>)}</div>
    <div className="plan-review-footer"><small>Plan {plan.plan_version_hash ?? "pending"} / ledger {plan.ledger_event_ref ?? "pending"} / sequence {plan.task_sequence}</small>{approval ? <span className="plan-approved" role="status">Approval accepted by Node. Awaiting task event.</span> : <button className="primary-button" data-testid="approve-plan" onClick={onApprove} disabled={!canApprove || approving} title={canApprove ? "Approve this Node-validated plan" : "The Node must return a ready plan requiring operator approval"}>{approving ? "Sending..." : "Approve and run"}</button>}</div>
  </section>;
}

function NodeSettingsView({ profiles, profilesState, profileError, connection, connectingProfileId, onConnect, onReconnect, onReload, onHome }: { profiles: ApprovedNodeProfileReference[]; profilesState: "idle" | "loading" | "ready" | "failed"; profileError: string | null; connection: NodeConnectionView; connectingProfileId: string | null; onConnect: (profile: ApprovedNodeProfileReference) => void; onReconnect: () => void; onReload: () => void; onHome: () => void }) {
  const connectedProfile = profiles.find((profile) => profile.profileId === connection.profileId);
  return <section className="settings-view"><p className="eyebrow">TRUSTED EXECUTION</p><h1>Node and settings</h1><p className="lead">Choose an organization-approved Node. AirBench does not accept arbitrary model-server addresses or credentials in the desktop app.</p>
    <div className={`settings-card connection-card ${connection.state === "connected" ? "is-connected" : ""}`}>
      <div className="settings-status"><span className={`status-dot ${connection.state === "connected" ? "status-dot-connected" : ""}`} aria-hidden="true" /><div><strong>{connection.state === "connected" ? `${connectedProfile?.displayName ?? "AirBench Node"} is connected` : connection.state === "connecting" ? "Connecting to approved Node" : connection.state === "failed" ? "Node connection blocked" : "No Node connected"}</strong><small>{connection.state === "connected" ? "Identity and clearance verified. Consequential work can be enabled by the Node." : connection.failure?.message ?? "Nothing has been submitted or sent anywhere."}</small></div></div>
      {connection.state === "connected" && <><div className="settings-row"><span>Node identity</span><strong>{connection.nodeIdentity}</strong></div><div className="settings-row"><span>Clearance</span><strong>{connection.clearanceContext}</strong></div><div className="settings-row"><span>Protocol</span><strong>{connection.protocolVersion}</strong></div><div className="settings-row"><span>Ledger connection ref</span><strong>{connection.ledgerEventRef}</strong></div></>}
      {connection.state !== "connected" && <div className="settings-row"><span>Connection</span><strong>{profilesState === "loading" ? "Loading approved profiles" : profilesState === "ready" ? `${profiles.length} approved profile${profiles.length === 1 ? "" : "s"} available` : "Awaiting approved profile"}</strong></div>}
      <div className="settings-row"><span>Network policy</span><strong>Node-only transport</strong></div>
    </div>
    {connection.state === "connected" && <div className="settings-actions"><button className="secondary-button bordered-button" onClick={onReconnect} disabled={connectingProfileId !== null}>Recheck Node</button><span className="settings-action-note">Recheck preserves the approved profile and creates a fresh trust result.</span></div>}
    {connection.state !== "connected" && <><div className="profile-section"><div className="section-heading"><div><h2>Approved Nodes</h2><p>These profiles were installed by your organization administrator.</p></div><button className="text-button" onClick={onReload} disabled={profilesState === "loading"}>Reload</button></div>{profilesState === "loading" && <div className="profile-empty">Loading the local approved profile catalog...</div>}{profilesState === "failed" && <div className="profile-empty profile-error" role="alert">{profileError}<button className="text-button" onClick={onReload}>Try again</button></div>}{profilesState === "ready" && profiles.length === 0 && <div className="profile-empty">No approved Node profile is installed on this workstation. Ask your AirBench administrator to provision one.</div>}{profiles.length > 0 && <div className="profile-list">{profiles.map((profile) => <ProfileCard key={profile.profileId} profile={profile} busy={connectingProfileId === profile.profileId} onConnect={() => onConnect(profile)} />)}</div>}</div></>}
    <div className="settings-note"><strong>What AirBench verifies</strong><p>The native transport checks the approved profile, Node identity, protocol version, clearance context, certificate policy, and authenticated subject before the UI treats the Node as ready. Secrets stay in operating-system credential storage.</p></div><button className="secondary-button bordered-button" onClick={onHome}>Return home</button></section>;
}

function ProfileCard({ profile, busy, onConnect }: { profile: ApprovedNodeProfileReference; busy: boolean; onConnect: () => void }) {
  return <article className="profile-card"><div><div className="profile-name">{profile.displayName}</div><div className="profile-meta">{profile.transport === "loopback" ? "Local workstation" : "Internal network"} <span aria-hidden="true">•</span> {profile.clearanceContext} clearance</div><div className="profile-trust">Pinned identity: {profile.nodeIdentity}</div></div><button className="primary-button" onClick={onConnect} disabled={busy}>{busy ? "Checking..." : "Connect"}</button></article>;
}

function TaskWorkspaceView({ projection, syncState, plan, approval, approving, controlResult, controlling, onStop, onRefresh, onApprovePlan, onHome }: { projection: TaskProjection; syncState: EventSyncState | null; plan: TaskPlanReview | null; approval: NodeCommandResult | null; approving: boolean; controlResult: NodeCommandResult | null; controlling: boolean; onStop: () => Promise<void>; onRefresh: () => Promise<void>; onApprovePlan: () => Promise<void>; onHome: () => void }) {
  const syncLabel: Record<string, string> = { idle: "Not synchronized", syncing: "Checking Node", connected: "Connected and current", reconnecting: "Reconnecting", replaying: "Replaying events", blocked: "Blocked by protocol or policy" };
  const statusLabel: Record<string, string> = { accepted: "Accepted", planning: "Planning", running: "Running", needs_review: "Needs review", completed: "Completed", blocked: "Blocked", failed: "Failed", stopped: "Stopped" };
  const syncStatus = syncState?.status ?? "idle";
  const canStop = maySendConsequentialCommand(projection, syncStatus) && !["completed", "failed", "stopped"].includes(projection.status) && !controlling;
  return <section className="workspace-view" data-testid="task-workspace" aria-label="Live task workspace">
    <div className="workspace-head"><div><p className="eyebrow">LIVE TASK</p><h1>{projection.title}</h1><p className="lead">{projection.requestSummary}</p></div><span className={`workspace-status workspace-status-${projection.status}`}>{statusLabel[projection.status] ?? projection.status}</span></div>
    <div className={`workspace-sync workspace-sync-${syncStatus}`} role="status" aria-live="polite"><span className="status-dot" aria-hidden="true" /><strong>{syncLabel[syncStatus] ?? syncStatus}</strong><span>{syncState?.error?.message ?? (syncStatus === "reconnecting" ? "The Node may continue work while this desktop reconnects." : "Task state comes from the approved Node event stream.")}</span><button className="text-button" onClick={onRefresh} disabled={syncStatus === "syncing" || syncStatus === "replaying"}>Refresh</button></div>
    <div className="workspace-actions"><button className="secondary-button bordered-button" onClick={onHome}>Back to Home</button><button className="secondary-button" onClick={onStop} disabled={!canStop} title={canStop ? "Send a Node-authorized stop command" : "Stopping is disabled until the Node is current"}>{controlling ? "Stopping..." : "Stop task"}</button><button className="secondary-button" disabled title="Pause is not available in the current Node command contract">Pause</button><button className="secondary-button" disabled title="Resume is not available in the current Node command contract">Resume</button></div>
    <div className="workspace-metrics"><div><span>Phase</span><strong>{projection.phase}</strong></div><div><span>Applied sequence</span><strong>{projection.lastAppliedSequence}</strong></div><div><span>Node</span><strong>{projection.nodeConnectionRef}</strong></div><div><span>Ledger head</span><strong>{projection.ledgerHeadRef}</strong></div></div>
    {plan && <PlanReviewCard plan={plan} loading={false} approval={approval} approving={approving} onApprove={onApprovePlan} />}
    {controlResult && <div className="workspace-receipt" role="status">Stop command accepted by Node. Ledger {controlResult.ledger_event_ref ?? "pending"}; waiting for the authoritative event.</div>}
    <section className="workspace-activity"><div className="section-heading"><div><h2>Activity</h2><p>Only server-authoritative events are shown. Model reasoning traces are not exposed.</p></div><span className="workspace-count">{projection.activity.length} events</span></div>{projection.activity.length === 0 ? <div className="workspace-empty">The Node has not returned a new activity event yet.</div> : <ol className="activity-list">{projection.activity.map((event) => <li key={`${event.eventId}-${event.sequence}`} className="activity-row"><span className="activity-sequence">{event.sequence}</span><div><strong>{eventLabel(event)}</strong><p>{eventSummary(event)}</p><small>{event.eventType} / ledger {event.ledgerEventRef}</small></div></li>)}</ol>}</section>
    {projection.diagnostics.length > 0 && <section className="workspace-warning" role="alert"><strong>Task view needs attention</strong>{projection.diagnostics.map((diagnostic) => <span key={`${diagnostic.code}-${diagnostic.sequence}`}>{diagnostic.code}: {diagnostic.detail}</span>)}</section>}
    <details className="workspace-technical"><summary>Technical event details</summary><pre>{JSON.stringify(projection.activity, null, 2)}</pre></details>
  </section>;
}

function eventLabel(event: TaskEvent): string {
  const labels: Record<string, string> = { "task.accepted": "Task accepted", "plan.created": "Plan created", "plan.approved": "Plan approved", "worker.started": "Worker started", "worker.completed": "Worker completed", "tool.started": "Tool started", "tool.completed": "Tool completed", "evidence.added": "Evidence added", "verification.completed": "Verification completed", "verification.failed": "Verification failed", "approval.required": "Approval required", "approval.recorded": "Approval recorded", "artifact.ready": "Artifact ready", "task.completed": "Task completed", "task.failed": "Task failed", "task.stopped": "Task stopped", "ledger.written": "Ledger entry recorded" };
  return labels[event.eventType] ?? event.eventType;
}

function eventSummary(event: TaskEvent): string {
  const payload = event.payload as Record<string, unknown>;
  for (const key of ["summary", "label", "reason", "status"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "The Node recorded this event without a user-facing summary.";
}

function RecordView({ screen, onHome }: { screen: string; onHome: () => void }) {
  const descriptions: Record<string, string> = { Tasks: "Tasks will appear here after a trusted Node accepts work.", Review: "Nothing is waiting for review.", Artifacts: "Generated artifacts will appear here after Node verification.", History: "Completed and stopped work will appear here.", Audit: "Ledger references will appear here when a Node is connected." };
  return <section className="placeholder-view"><p className="eyebrow">AIRBENCH WORKBENCH</p><h1>{screen}</h1><p className="lead">{descriptions[screen] ?? "Connect a trusted Node to continue."}</p><button className="secondary-button bordered-button" onClick={onHome}>Return home</button></section>;
}

function ConnectionHelp({ onClose, onOpenNode }: { onClose: () => void; onOpenNode: () => void }) {
  return <div className="modal-backdrop" role="presentation"><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="connection-help-title"><button className="modal-close" aria-label="Close" onClick={onClose}>X</button><p className="eyebrow">TRUSTED EXECUTION</p><h2 id="connection-help-title">AirBench works on an approved Node</h2><p>Your files, task state, model calls, tools, and audit record stay inside the organization. Select a trusted Node before starting work.</p><div className="modal-note"><span className="status-dot" aria-hidden="true" /><span><strong>No Node is connected</strong><small>Nothing has been submitted or sent anywhere.</small></span></div><div className="modal-actions"><button className="secondary-button" onClick={onClose}>Close</button><button className="primary-button" onClick={onOpenNode}>Open Node settings</button></div></section></div>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default App;
