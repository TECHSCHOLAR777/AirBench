import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { invoke } from "@airbench/tauri-invoke";
import { AppIcon, type AppIconName } from "./AppIcon";
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
import { maySendConsequentialCommand, TaskEventSynchronizer, type EventSyncResult, type EventSyncState } from "./eventStore";
import { TaskEventLoop } from "./taskEventLoop";
import { loadPresentationPreferences, savePresentationPreferences, type PresentationPreferences } from "./presentationPreferences";
import { mayLaunchFromShortcut, sourceStatus, unavailableRoutingPreference } from "./launchpadPolicy";
import { buildWorkTrace, formatTraceTime, type WorkTraceActivity, type WorkTraceStage } from "./workTrace";
import { buildHomeWorkSummary } from "./homeWorkSummary";
import { buildRecordGateway, type RecordGatewayDestination } from "./recordGateway";
import { buildShellCommands, shellShortcut, type ShellCommandId } from "./commandPalette";
import { WorkspaceCommandDialog } from "./WorkspaceCommandDialog";
import { OperatorQuestionCard } from "./OperatorQuestionCard";
import { ProofInspectorPanel, type ArtifactPreviewState } from "./ProofInspectorPanel";
import { TaskEmptyView } from "./TaskEmptyView";
import { NodeReadinessPanel } from "./NodeReadinessPanel";
import { formatProvenanceLocation, type ProofSelection } from "./proofInspector";
import type { TaskProjection } from "./protocol";

type SelectedFile = { selection_id: string; file_name: string; byte_size: number };

const primaryNav: Array<{ id: Screen; label: string; icon: AppIconName }> = [
  { id: "home", label: "Home", icon: "home" },
  { id: "tasks", label: "Tasks", icon: "tasks" },
  { id: "review", label: "Review", icon: "review" },
];

const recordNav: Array<{ id: Screen; label: string; icon: AppIconName }> = [
  { id: "artifacts", label: "Artifacts", icon: "archive" },
  { id: "history", label: "History", icon: "history" },
  { id: "audit", label: "Audit", icon: "audit" },
];

function App() {
  const [state, setState] = useState<AirBenchPresentationState>(initialPresentationState);
  const [presentation, setPresentation] = useState<PresentationPreferences>(() => loadPresentationPreferences());
  const [showAppearanceMenu, setShowAppearanceMenu] = useState(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
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
  const [taskArtifactPreview, setTaskArtifactPreview] = useState<ArtifactPreview | null>(null);
  const [taskArtifactPreviewState, setTaskArtifactPreviewState] = useState<ArtifactPreviewState>("idle");
  const [taskArtifactPreviewError, setTaskArtifactPreviewError] = useState<string | null>(null);
  const [taskArtifactDownloadState, setTaskArtifactDownloadState] = useState<"idle" | "downloading" | "downloaded" | "failed">("idle");
  const [taskArtifactDownloadReceipt, setTaskArtifactDownloadReceipt] = useState<DownloadReceipt | null>(null);
  const synchronizerRef = useRef<TaskEventSynchronizer | null>(null);
  const taskEventLoopRef = useRef<TaskEventLoop | null>(null);
  const synchronizationRef = useRef<Promise<EventSyncResult> | null>(null);
  const synchronizationTokenRef = useRef<symbol | null>(null);
  const outcomeInputRef = useRef<HTMLTextAreaElement | null>(null);
  const commandMenuReturnFocusRef = useRef<HTMLElement | null>(null);
  const commandMenuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const controller = useMemo(() => new NodeConnectionController(), []);
  const nodeConnected = connection.state === "connected" && controller.canSendConsequential();

  const screenTitle = useMemo(() => {
    const titles: Record<Screen, string> = { home: "Home", tasks: "Tasks", review: "Review", artifacts: "Artifacts", history: "History", audit: "Audit", node: "Node and settings" };
    return titles[state.screen];
  }, [state.screen]);

  const selectScreen = (screen: Screen) => setState((current) => ({ ...current, screen }));

  const focusOutcomeInput = useCallback(() => window.requestAnimationFrame(() => outcomeInputRef.current?.focus()), []);

  const openNewTask = useCallback(() => {
    setShowCommandPalette(false);
    setShowAppearanceMenu(false);
    setState((current) => ({ ...current, screen: "home" }));
    focusOutcomeInput();
  }, [focusOutcomeInput]);

  const openCommandPalette = useCallback((returnFocus: EventTarget | null) => {
    commandMenuReturnFocusRef.current = returnFocus instanceof HTMLElement ? returnFocus : commandMenuTriggerRef.current;
    setShowAppearanceMenu(false);
    setShowCommandPalette(true);
  }, []);

  const closeCommandPalette = useCallback(() => {
    setShowCommandPalette(false);
    window.requestAnimationFrame(() => commandMenuReturnFocusRef.current?.focus());
  }, []);

  useEffect(() => {
    savePresentationPreferences(presentation);
  }, [presentation]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      const shortcut = shellShortcut(event);
      if (shortcut === "open_command_palette") {
        event.preventDefault();
        if (showCommandPalette) closeCommandPalette();
        else openCommandPalette(event.target);
        return;
      }
      if (shortcut === "new_task") {
        event.preventDefault();
        openNewTask();
        return;
      }
      if (event.key === "Escape" && showAppearanceMenu) {
        event.preventDefault();
        setShowAppearanceMenu(false);
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, [closeCommandPalette, openCommandPalette, openNewTask, showAppearanceMenu, showCommandPalette]);

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

  const inspectTaskArtifact = async (artifactId: string) => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    setTaskArtifactPreview(null);
    setTaskArtifactPreviewError(null);
    setTaskArtifactDownloadState("idle");
    setTaskArtifactDownloadReceipt(null);
    if (!profile || !nodeConnected) {
      setTaskArtifactPreviewState("failed");
      setTaskArtifactPreviewError("Connect a verified Node before requesting an artifact preview.");
      return;
    }
    setTaskArtifactPreviewState("loading");
    try {
      const preview = await fetchArtifactPreview(profile, artifactId);
      setTaskArtifactPreview(preview);
      setTaskArtifactPreviewState("ready");
    } catch {
      setTaskArtifactPreviewState("failed");
      setTaskArtifactPreviewError("The approved Node did not return a safe preview for this artifact.");
    }
  };

  const downloadTaskArtifact = async (artifactId: string) => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected) {
      setTaskArtifactDownloadState("failed");
      return;
    }
    setTaskArtifactDownloadState("downloading");
    setTaskArtifactDownloadReceipt(null);
    try {
      const receipt = await downloadArtifact(profile, artifactId, `airbench-artifact-${artifactId}.bin`);
      setTaskArtifactDownloadReceipt(receipt);
      setTaskArtifactDownloadState("downloaded");
    } catch {
      setTaskArtifactDownloadState("failed");
    }
  };

  const synchronize = useCallback((synchronizer: TaskEventSynchronizer): Promise<EventSyncResult> => {
    if (synchronizationRef.current) return synchronizationRef.current;
    const token = Symbol("task-synchronization");
    synchronizationTokenRef.current = token;
    const operation = (async () => {
      try {
        return await synchronizer.synchronizeWithRetry({ maxAttempts: 3 });
      } finally {
        if (synchronizationTokenRef.current === token) {
          synchronizationRef.current = null;
          synchronizationTokenRef.current = null;
        }
      }
    })();
    synchronizationRef.current = operation;
    return operation;
  }, []);

  const syncTask = async (profile: ApprovedNodeProfileReference, snapshot: CreateTaskResponse["snapshot"]) => {
    const synchronizer = new TaskEventSynchronizer(
      (taskId, afterSequence) => fetchTaskEventBatch(profile, taskId, afterSequence),
      (taskId) => fetchTaskSnapshot(profile, taskId),
    );
    synchronizerRef.current = synchronizer;
    setTaskProjection(synchronizer.loadSnapshot(snapshot));
    setEventSyncState(synchronizer.state());
    const result = await synchronize(synchronizer);
    setTaskProjection(result.projection);
    setEventSyncState(result.state);
    return result;
  };

  const refreshTask = async () => {
    const synchronizer = synchronizerRef.current;
    if (!synchronizer) return;
    const result = await synchronize(synchronizer);
    setTaskProjection(result.projection);
    setEventSyncState(result.state);
  };

  useEffect(() => {
    const taskId = taskProjection?.taskId;
    const synchronizer = synchronizerRef.current;
    if (!taskId || !synchronizer || !nodeConnected) return;

    const loop = new TaskEventLoop(
      () => synchronize(synchronizer),
      (result) => {
        setTaskProjection(result.projection);
        setEventSyncState(result.state);
      },
      {
        onError: () => setEventSyncState((current) => current ? {
          ...current,
          status: "reconnecting",
          error: { code: "event_sync_failed", message: "Live task updates are temporarily unavailable. The Node may continue working while this desktop reconnects." },
        } : current),
      },
    );
    taskEventLoopRef.current = loop;
    loop.start();
    return () => {
      loop.stop();
      if (taskEventLoopRef.current === loop) taskEventLoopRef.current = null;
    };
  }, [nodeConnected, synchronize, taskProjection?.taskId]);

  const startTask = async () => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !connection.authenticatedSubject || !connection.clearanceContext || !connection.domainPackRef) {
      setNotice("Connect a verified Node before submitting a task.");
      return;
    }
    setCreatingTask(true);
    taskEventLoopRef.current?.stop();
    synchronizationRef.current = null;
    synchronizationTokenRef.current = null;
    setTaskResult(null);
    setPlanReview(null);
    setPlanApprovalResult(null);
    setTaskArtifactPreview(null);
    setTaskArtifactPreviewState("idle");
    setTaskArtifactPreviewError(null);
    setTaskArtifactDownloadState("idle");
    setTaskArtifactDownloadReceipt(null);
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

  const canStart = nodeConnected && taskText.trim().length > 0 && (!selectedFile || intakeState === "ready") && !creatingTask;
  const nodeLabel = nodeConnected ? (profiles.find((profile) => profile.profileId === connection.profileId)?.displayName ?? "Node connected") : connection.state === "connecting" ? "Connecting to Node" : "Node not connected";
  const nodeDetail = nodeConnected ? "Verified and ready" : connection.state === "failed" ? "Connection blocked" : "Choose an approved Node";
  const sovereigntyLabel = nodeConnected && connection.sovereignty === "verified" ? "Verified internal path" : "No verified Node path";
  const shellCommands = useMemo(() => buildShellCommands(taskProjection !== null), [taskProjection]);

  const runShellCommand = (commandId: ShellCommandId) => {
    setShowCommandPalette(false);
    if (commandId === "new_task") {
      openNewTask();
      return;
    }
    if (commandId === "current_task") {
      if (taskProjection) selectScreen("tasks");
      return;
    }
    if (commandId === "node_settings") {
      selectScreen("node");
      return;
    }
    setShowAppearanceMenu(true);
  };

  return (
    <div className="app-shell" data-theme={presentation.theme} data-density={presentation.density} data-contrast={presentation.highContrast ? "high" : "standard"}>
      <aside className="sidebar" aria-label="AirBench navigation">
        <div className="brand-lockup"><div className="brand-mark"><AppIcon name="airbench" size={19} /></div><div><div className="brand-name">AirBench</div><div className="brand-subtitle">Sovereign task command</div></div></div>
        <button className="new-task-button" onClick={openNewTask}><AppIcon name="plus" size={17} /><span>New task</span><kbd>Ctrl N</kbd></button>
        <nav className="nav-groups"><NavGroup title="Work" items={primaryNav} active={state.screen} onSelect={selectScreen} /><NavGroup title="Records" items={recordNav} active={state.screen} onSelect={selectScreen} /></nav>
        <div className="sidebar-spacer" />
        <button className="node-chip" data-testid="node-chip" onClick={() => selectScreen("node")} aria-label="Open Node and settings"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" /><span className="node-chip-copy"><strong>{nodeLabel}</strong><small>{nodeDetail}</small></span><AppIcon name="chevron-down" size={15} /></button>
        <div className="user-row"><div className="avatar">RG</div><div><strong>Local operator</strong><small>{connection.clearanceContext ? `${connection.clearanceContext} clearance` : "Clearance not resolved"}</small></div><span className="operator-session">Local session</span></div>
        <small className="build-info" data-testid="app-version">AirBench {__AIRBENCH_VERSION__} / offline shell</small>
      </aside>

      <main className="main-area">
        <header className="topbar"><div className="breadcrumb"><span>AirBench</span><span className="breadcrumb-slash">/</span><strong>{screenTitle}</strong></div><div className="topbar-actions"><button ref={commandMenuTriggerRef} className="command-menu-button" type="button" onClick={(event) => openCommandPalette(event.currentTarget)} aria-haspopup="dialog" aria-expanded={showCommandPalette} aria-controls="workspace-command-palette"><AppIcon name="search" size={16} /><span>Command</span><kbd>Ctrl K</kbd></button><button className={`sovereignty-status ${nodeConnected ? "is-verified" : ""}`} onClick={() => selectScreen("node")} aria-label="Open Node and settings"><AppIcon name={nodeConnected ? "shield" : "node"} size={16} /><span><small>Node path</small><strong>{sovereigntyLabel}</strong></span></button><div className="appearance-control"><button className="appearance-button" type="button" onClick={() => setShowAppearanceMenu((open) => !open)} aria-expanded={showAppearanceMenu} aria-controls="appearance-preferences"><AppIcon name="display" size={16} /><span>Display</span><AppIcon name="chevron-down" size={14} /></button>{showAppearanceMenu && <AppearanceMenu preferences={presentation} onChange={setPresentation} onClose={() => setShowAppearanceMenu(false)} />}</div></div></header>
        <div className="content-wrap">
          {state.screen === "home" && <HomeView outcomeInputRef={outcomeInputRef} currentTask={taskProjection} taskText={taskText} setTaskText={setTaskText} taskTitle={taskTitle} setTaskTitle={setTaskTitle} projectRef={projectRef} setProjectRef={setProjectRef} outputContract={outputContract} setOutputContract={setOutputContract} priority={priority} setPriority={setPriority} deadline={deadline} setDeadline={setDeadline} selectedFile={selectedFile} intakeState={intakeState} intakeManifest={intakeManifest} safePreview={safePreview} artifactPreview={artifactPreview} downloadState={downloadState} downloadReceipt={downloadReceipt} taskResult={taskResult} planReview={planReview} planLoading={planLoading} planApprovalResult={planApprovalResult} approvingPlan={approvingPlan} notice={notice} canStart={canStart} creatingTask={creatingTask} nodeConnected={nodeConnected} nodeLabel={nodeLabel} onAttach={attachFile} onUpload={uploadSelectedFile} onDownload={downloadApprovedArtifact} onStart={startTask} onApprovePlan={approvePlan} onRemoveFile={() => { setSelectedFile(null); setIntakeState("idle"); setIntakeManifest(null); setSafePreview(null); setArtifactPreview(null); setDownloadState("idle"); setDownloadReceipt(null); }} onHelp={() => setShowConnectionHelp(true)} onOpenNode={() => selectScreen("node")} onOpenCurrentTask={() => selectScreen("tasks")} />}
          {state.screen === "node" && <NodeSettingsView profiles={profiles} profilesState={profilesState} profileError={profileError} connection={connection} connectingProfileId={connectingProfileId} onConnect={connectProfile} onReconnect={reconnect} onReload={() => { setProfilesState("idle"); }} onHome={() => selectScreen("home")} />}
          {state.screen === "tasks" && (taskProjection ? <TaskWorkspaceView projection={taskProjection} syncState={eventSyncState} plan={planReview} approval={planApprovalResult} approving={approvingPlan} controlResult={taskControlResult} controlling={controllingTask} sourcePreview={intakeManifest?.intake_id === taskProjection.inputManifestRef ? safePreview : null} artifactPreview={taskArtifactPreview} artifactPreviewState={taskArtifactPreviewState} artifactPreviewError={taskArtifactPreviewError} artifactDownloadState={taskArtifactDownloadState} artifactDownloadReceipt={taskArtifactDownloadReceipt} onStop={stopTask} onRefresh={refreshTask} onApprovePlan={approvePlan} onInspectArtifact={inspectTaskArtifact} onDownloadArtifact={downloadTaskArtifact} onHome={openNewTask} /> : <TaskEmptyView nodeConnected={nodeConnected} onNewTask={openNewTask} onOpenNode={() => selectScreen("node")} />)}
          {isRecordGatewayDestination(state.screen) && <RecordGatewayView destination={state.screen} nodeConnected={nodeConnected} currentTask={taskProjection} onHome={() => selectScreen("home")} onOpenNode={() => selectScreen("node")} onOpenCurrentTask={() => selectScreen("tasks")} />}
        </div>
      </main>
      {showConnectionHelp && <ConnectionHelp onClose={() => setShowConnectionHelp(false)} onOpenNode={() => { setShowConnectionHelp(false); selectScreen("node"); }} />}
      {showCommandPalette && <WorkspaceCommandDialog commands={shellCommands} onClose={closeCommandPalette} onSelect={runShellCommand} />}
    </div>
  );
}

function NavGroup({ title, items, active, onSelect }: { title: string; items: Array<{ id: Screen; label: string; icon: AppIconName }>; active: Screen; onSelect: (screen: Screen) => void }) {
  return <div className="nav-group">
    <div className="nav-group-title">{title}</div>
    {items.map((item) => <button key={item.id} className={`nav-item ${active === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}>
      <span className="nav-icon"><AppIcon name={item.icon} size={16} /></span>
      <span>{item.label}</span>
    </button>)}
  </div>;
}

function AppearanceMenu({ preferences, onChange, onClose }: { preferences: PresentationPreferences; onChange: (next: PresentationPreferences) => void; onClose: () => void }) {
  return <section className="appearance-menu" id="appearance-preferences" aria-label="Display preferences">
    <div className="appearance-menu-header">
      <div><span>Display</span><small>Stored only on this desktop profile</small></div>
      <button type="button" className="text-button" onClick={onClose}>Close</button>
    </div>
    <fieldset className="appearance-fieldset">
      <legend>Theme</legend>
      <div className="appearance-options">
        <button type="button" className={`appearance-choice ${preferences.theme === "obsidian" ? "selected" : ""}`} aria-pressed={preferences.theme === "obsidian"} onClick={() => onChange({ ...preferences, theme: "obsidian" })}>
          <span className="theme-preview theme-preview-obsidian" aria-hidden="true" />
          <span><strong>Obsidian Signal</strong><small>Dark, focused workspace</small></span>
        </button>
        <button type="button" className={`appearance-choice ${preferences.theme === "ledger" ? "selected" : ""}`} aria-pressed={preferences.theme === "ledger"} onClick={() => onChange({ ...preferences, theme: "ledger" })}>
          <span className="theme-preview theme-preview-ledger" aria-hidden="true" />
          <span><strong>Ledger Paper</strong><small>Warm document review</small></span>
        </button>
      </div>
    </fieldset>
    <fieldset className="appearance-fieldset appearance-split">
      <legend>Density</legend>
      <div className="segmented-control">
        <button type="button" className={preferences.density === "comfortable" ? "selected" : ""} aria-pressed={preferences.density === "comfortable"} onClick={() => onChange({ ...preferences, density: "comfortable" })}>Comfortable</button>
        <button type="button" className={preferences.density === "compact" ? "selected" : ""} aria-pressed={preferences.density === "compact"} onClick={() => onChange({ ...preferences, density: "compact" })}>Compact</button>
      </div>
    </fieldset>
    <label className="contrast-toggle">
      <span><strong>High contrast</strong><small>Increase borders and focus visibility</small></span>
      <input type="checkbox" checked={preferences.highContrast} onChange={(event) => onChange({ ...preferences, highContrast: event.target.checked })} />
    </label>
  </section>;
}

type LaunchpadPanel = "sources" | "deliverable" | "details" | "routing" | "review";

const outputContractOptions = [
  { value: "document", label: "Document", detail: "A reviewable written deliverable" },
  { value: "summary", label: "Summary", detail: "A concise evidence-based brief" },
  { value: "spreadsheet", label: "Spreadsheet", detail: "A structured workbook or calculation output" },
  { value: "presentation", label: "Presentation", detail: "A decision-ready presentation" },
  { value: "code", label: "Code", detail: "A working, verifiable code artifact" },
] as const;

function HomeView({ outcomeInputRef, currentTask, taskText, setTaskText, taskTitle, setTaskTitle, projectRef, setProjectRef, outputContract, setOutputContract, priority, setPriority, deadline, setDeadline, selectedFile, intakeState, intakeManifest, safePreview, artifactPreview, downloadState, downloadReceipt, taskResult, planReview, planLoading, planApprovalResult, approvingPlan, notice, canStart, creatingTask, nodeConnected, nodeLabel, onAttach, onUpload, onDownload, onStart, onApprovePlan, onRemoveFile, onHelp, onOpenNode, onOpenCurrentTask }: { outcomeInputRef: RefObject<HTMLTextAreaElement | null>; currentTask: TaskProjection | null; taskText: string; setTaskText: (value: string) => void; taskTitle: string; setTaskTitle: (value: string) => void; projectRef: string; setProjectRef: (value: string) => void; outputContract: string; setOutputContract: (value: string) => void; priority: string; setPriority: (value: string) => void; deadline: string; setDeadline: (value: string) => void; selectedFile: SelectedFile | null; intakeState: "idle" | "uploading" | "ready" | "failed"; intakeManifest: IntakeManifest | null; safePreview: SafePreview | null; artifactPreview: ArtifactPreview | null; downloadState: "idle" | "downloading" | "downloaded" | "failed"; downloadReceipt: DownloadReceipt | null; taskResult: CreateTaskResponse | null; planReview: TaskPlanReview | null; planLoading: boolean; planApprovalResult: NodeCommandResult | null; approvingPlan: boolean; notice: string | null; canStart: boolean; creatingTask: boolean; nodeConnected: boolean; nodeLabel: string; onAttach: () => void; onUpload: () => void; onDownload: () => void; onStart: () => void; onApprovePlan: () => void; onRemoveFile: () => void; onHelp: () => void; onOpenNode: () => void; onOpenCurrentTask: () => void }) {
  const [openPanel, setOpenPanel] = useState<LaunchpadPanel | null>(null);
  const outputLabel = outputContractOptions.find((option) => option.value === outputContract)?.label ?? "Deliverable";
  const selectedSourceStatus = sourceStatus(Boolean(selectedFile), intakeState);
  const routingPreference = unavailableRoutingPreference(nodeConnected);
  const currentWork = currentTask ? buildHomeWorkSummary(currentTask) : null;
  const launchTitle = canStart ? "Launch task" : "Connect an approved Node, describe the outcome, and finish file intake before launching";
  const togglePanel = (panel: LaunchpadPanel) => setOpenPanel((current) => current === panel ? null : panel);
  const openSourcePicker = () => { setOpenPanel("sources"); onAttach(); };

  return <div className="home-view launchpad-view">
    <section className="welcome-block launchpad-intro"><p className="eyebrow">NEW TASK</p><h1>What do you want AirBench to complete?</h1><p className="lead">Describe the finished result. Add sources and only the context that matters.</p></section>
    <section className="composer-card launchpad-card" data-testid="task-composer" aria-label="Task launchpad">
      <div className="launchpad-prompt">
        <textarea ref={outcomeInputRef} value={taskText} onChange={(event) => setTaskText(event.target.value)} onKeyDown={(event) => { if (mayLaunchFromShortcut(event, canStart)) { event.preventDefault(); onStart(); } }} placeholder="For example: Review the scanned inspection report and draft an approval note with the key findings and required actions." rows={3} aria-label="Task outcome" aria-describedby="launchpad-prompt-hint" />
        <p id="launchpad-prompt-hint">Describe the outcome, relevant constraints, and what a complete result should contain. Longer briefs scroll inside this field.</p>
      </div>
      <div className="launchpad-context-bar" aria-label="Task context">
        <button type="button" className={`launchpad-context-trigger ${openPanel === "sources" ? "is-open" : ""}`} aria-expanded={openPanel === "sources"} aria-controls="launchpad-sources" onClick={() => togglePanel("sources")}><AppIcon name="attachment" size={16} /><span><strong>Sources</strong><small>{selectedSourceStatus}</small></span></button>
        <button type="button" className={`launchpad-context-trigger ${openPanel === "deliverable" ? "is-open" : ""}`} aria-expanded={openPanel === "deliverable"} aria-controls="launchpad-deliverable" onClick={() => togglePanel("deliverable")}><AppIcon name="document" size={16} /><span><strong>Deliverable</strong><small>{outputLabel}</small></span></button>
        <button type="button" className={`launchpad-context-trigger ${openPanel === "routing" ? "is-open" : ""}`} aria-expanded={openPanel === "routing"} aria-controls="launchpad-routing" onClick={() => togglePanel("routing")}><AppIcon name="route" size={16} /><span><strong>Auto route</strong><small>Node controlled</small></span></button>
        <button type="button" className={`launchpad-context-trigger ${openPanel === "details" ? "is-open" : ""}`} aria-expanded={openPanel === "details"} aria-controls="launchpad-details" onClick={() => togglePanel("details")}><AppIcon name="sliders" size={16} /><span><strong>Task details</strong><small>Optional context</small></span></button>
        <button type="button" className={`launchpad-context-trigger ${openPanel === "review" ? "is-open" : ""}`} aria-expanded={openPanel === "review"} aria-controls="launchpad-review" onClick={() => togglePanel("review")}><AppIcon name="review" size={16} /><span><strong>Review</strong><small>Policy controlled</small></span></button>
      </div>
      {openPanel === "sources" && <section className="launchpad-panel" id="launchpad-sources" aria-label="Sources">
        <div className="launchpad-panel-heading"><div><p className="eyebrow">SOURCES</p><h2>Bring in the material that matters</h2></div><button type="button" className="text-button" onClick={() => setOpenPanel(null)}>Done</button></div>
        {!selectedFile && <div className="launchpad-source-empty"><AppIcon name="attachment" size={19} /><div><strong>No source selected</strong><p>Every file is sent to the Node through File Intake before it can be used.</p></div><button type="button" className="secondary-button" onClick={openSourcePicker}>Choose file</button></div>}
        {selectedFile && <div className="selected-file"><span className="file-badge">FILE</span><span><strong>{selectedFile.file_name}</strong><small>{formatBytes(selectedFile.byte_size)} / {intakeState === "ready" ? "accepted by File Intake" : intakeState === "uploading" ? "being sent to File Intake" : "ready for File Intake"}</small></span><div className="selected-file-actions">{intakeState !== "ready" && <button className="secondary-button compact-button" onClick={onUpload} disabled={intakeState === "uploading"}>{intakeState === "uploading" ? "Sending..." : "Send to Node"}</button>}<button className="remove-file" onClick={onRemoveFile} aria-label="Remove selected file">Remove</button></div></div>}
        <div className="launchpad-policy-note"><AppIcon name="shield" size={15} /><span>Uploaded material is untrusted data. The desktop app does not parse it or treat it as instructions.</span></div>
      </section>}
      {openPanel === "deliverable" && <section className="launchpad-panel" id="launchpad-deliverable" aria-label="Deliverable intent">
        <div className="launchpad-panel-heading"><div><p className="eyebrow">DELIVERABLE</p><h2>Choose the result format</h2></div><button type="button" className="text-button" onClick={() => setOpenPanel(null)}>Done</button></div>
        <div className="output-intent-grid">{outputContractOptions.map((option) => <button type="button" className={`output-intent-choice ${outputContract === option.value ? "selected" : ""}`} aria-pressed={outputContract === option.value} key={option.value} onClick={() => setOutputContract(option.value)}><strong>{option.label}</strong><small>{option.detail}</small></button>)}</div>
        <p className="launchpad-panel-footnote">This expresses the intended artifact type. The Node verifies any final deliverable and computes authoritative values.</p>
      </section>}
      {openPanel === "details" && <section className="launchpad-panel" id="launchpad-details" aria-label="Task details">
        <div className="launchpad-panel-heading"><div><p className="eyebrow">TASK DETAILS</p><h2>Add only useful operating context</h2></div><button type="button" className="text-button" onClick={() => setOpenPanel(null)}>Done</button></div>
        <div className="launchpad-details-grid">
          <label><span>Title</span><input value={taskTitle} onChange={(event) => setTaskTitle(event.target.value)} placeholder="A short name for this work" maxLength={256} /></label>
          <label><span>Project</span><input value={projectRef} onChange={(event) => setProjectRef(event.target.value)} placeholder="Optional project reference" maxLength={256} /></label>
          <label><span>Priority</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="normal">Normal</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
          <label><span>Deadline</span><input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label>
        </div>
      </section>}
      {openPanel === "routing" && <section className="launchpad-panel" id="launchpad-routing" aria-label="Model routing">
        <div className="launchpad-panel-heading"><div><p className="eyebrow">MODEL ROUTING</p><h2>Auto route is always in control</h2></div><button type="button" className="text-button" onClick={() => setOpenPanel(null)}>Done</button></div>
        <div className="route-overview"><div className="route-state"><AppIcon name="route" size={19} /><div><strong>Auto route</strong><p>The Node selects a qualified capability for each validated step. Models do not control the task loop.</p></div><span>Required</span></div><div className="route-facts"><div><strong>Qualification</strong><span>Node policy checks clearance, capability, and availability.</span></div><div><strong>Fallback</strong><span>Only the Node can approve a fallback or queue work for hardware.</span></div><div><strong>Visibility</strong><span>Route evidence appears only when the Node supplies it to the task trace.</span></div></div></div>
        <details className="route-advanced"><summary>Advanced qualified preference</summary><div><p>A manual preference is not available until the trusted Node supplies a clearance-filtered, qualified capability catalog. This release will not send a model name, endpoint, or server address from the desktop app.</p><label><span>Qualified preference</span><select disabled aria-describedby="route-preference-status"><option>{routingPreference.status}</option></select></label><small id="route-preference-status">{routingPreference.explanation}</small></div></details>
        <div className="launchpad-policy-list"><div><AppIcon name="archive" size={15} /><span><strong>Knowledge scope</strong>Collection selection needs a Node-provided catalog and is not exposed as free text.</span></div><div><AppIcon name="sliders" size={15} /><span><strong>Tools</strong>Permitted tools are determined by the Node, not selected by the desktop client.</span></div></div>
      </section>}
      {openPanel === "review" && <section className="launchpad-panel" id="launchpad-review" aria-label="Review posture">
        <div className="launchpad-panel-heading"><div><p className="eyebrow">REVIEW POSTURE</p><h2>Approval is decided after validation</h2></div><button type="button" className="text-button" onClick={() => setOpenPanel(null)}>Done</button></div>
        <div className="review-policy-card"><AppIcon name="review" size={19} /><div><strong>The Node determines review requirements.</strong><p>It evaluates task risk, file intake state, permitted authority, verification needs, and the available execution plan before any consequential work begins.</p></div></div>
        <p className="launchpad-panel-footnote">If a decision or answer is needed during work, it will appear as a task card with the Node's recorded context. The current launch protocol does not let the desktop app invent an approval path.</p>
      </section>}
      <div className="composer-footer launchpad-footer"><div className="composer-tools"><button className="secondary-button launchpad-attach-button" data-testid="attach-files" onClick={openSourcePicker}><AppIcon name="attachment" size={15} /> Attach files</button><span className="launchpad-footer-status"><AppIcon name="route" size={15} /><span><strong>Auto route</strong> Node validates the task before choosing qualified workers.</span></span></div><button className="primary-button" data-testid="start-task" onClick={onStart} disabled={!canStart} title={launchTitle}>{creatingTask ? "Launching..." : "Launch"} <kbd>Ctrl Enter</kbd></button></div>
    </section>
    {intakeManifest && safePreview && <section className="intake-result" data-testid="intake-result" aria-label="File Intake result"><div className="intake-result-head"><div><p className="eyebrow">FILE INTAKE COMPLETE</p><h2>{intakeManifest.file_name}</h2></div><span className="intake-badge">{intakeManifest.ocr_status} OCR</span></div><div className="intake-meta-grid"><div><span>Source hash</span><strong>{intakeManifest.source_hash}</strong></div><div><span>Pages</span><strong>{intakeManifest.page_count}</strong></div><div><span>Clearance</span><strong>{intakeManifest.clearance}</strong></div><div><span>Taint</span><strong>{intakeManifest.taint}</strong></div></div><div className="safe-preview"><div className="safe-preview-label">Node-generated safe preview <span>Page region: {safePreview.source_region}</span></div><p>{safePreview.text}</p><small>Confidence {Math.round(safePreview.confidence * 100)}% / ledger {safePreview.ledger_event_ref}</small></div></section>}
    {artifactPreview && <section className="artifact-preview" data-testid="artifact-preview" aria-label="Artifact preview"><div className="intake-result-head"><div><p className="eyebrow">NODE ARTIFACT PREVIEW</p><h2>{artifactPreview.title}</h2></div><span className="intake-badge">{artifactPreview.preview_kind}</span></div><div className="artifact-preview-meta"><span>{artifactPreview.clearance} clearance</span><span>{artifactPreview.taint} data</span><span>Ledger {artifactPreview.ledger_event_ref}</span></div><div className="artifact-blocks">{artifactPreview.blocks.map((block, index) => <div className="artifact-block" key={`${block.kind}-${index}`}><span className="artifact-block-kind">{block.kind}</span><p>{block.text}</p></div>)}</div><div className="artifact-actions"><button className="primary-button" data-testid="download-artifact" onClick={onDownload} disabled={downloadState === "downloading"}>{downloadState === "downloading" ? "Verifying..." : downloadState === "downloaded" ? "Download again" : "Download artifact"}</button>{downloadReceipt && <small data-testid="download-receipt">Saved {downloadReceipt.byte_size} bytes / {downloadReceipt.content_hash} / ledger {downloadReceipt.ledger_event_ref}</small>}</div></section>}
    {taskResult && <section className="task-confirmation" data-testid="task-confirmation" aria-label="Task submission result"><p className="eyebrow">TASK ACCEPTED BY NODE</p><strong>{taskResult.task.task_id}</strong><span>State: {taskResult.command.state ?? taskResult.task.state ?? "created"}</span><small>Ledger {taskResult.command.ledger_event_ref ?? taskResult.ledger_event_ref} / sequence {taskResult.command.sequence ?? taskResult.snapshot.asOfSequence}</small></section>}
    {taskResult && <PlanReviewCard plan={planReview} loading={planLoading} approval={planApprovalResult} approving={approvingPlan} onApprove={onApprovePlan} />}
    {notice && <div className="inline-notice" role="status">{notice}</div>}
    <div className="trust-line" role="status"><span className="trust-item"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" />{nodeConnected ? `${nodeLabel} is verified for this session.` : "No Node path is verified. Nothing has been submitted."}</span><button className="text-button" onClick={onHelp}>How this works</button></div>
    <section className="continue-section" aria-label="Continue work"><div className="section-heading"><div><h2>Continue work</h2><p>{currentWork ? "One task is available from the approved Node projection." : "The current Node has not supplied a task projection to this desktop."}</p></div>{currentWork && <span className={`home-work-health home-work-health-${currentWork.health}`}>{currentWork.healthLabel}</span>}</div>{currentWork ? <article className="current-work-card" data-testid="current-task-card"><div className="current-work-card-head"><div><p className="eyebrow">NODE TASK</p><h3>{currentWork.title}</h3><p>{currentWork.requestSummary}</p></div><span className={`home-work-status home-work-status-${currentWork.status}`}>{currentWork.statusLabel}</span></div><dl className="current-work-meta"><div><dt>Current phase</dt><dd>{currentWork.phase}</dd></div><div><dt>Node cursor</dt><dd>{currentWork.lastAppliedSequence}</dd></div><div><dt>Ledger head</dt><dd>{currentWork.ledgerHeadRef}</dd></div><div><dt>Latest record</dt><dd>{currentWork.latestActivity?.label ?? "No activity event in this cursor"}</dd></div></dl>{currentWork.latestActivity && <div className="current-work-latest"><span>Latest Node record</span><strong>{currentWork.latestActivity.summary}</strong><small>{formatTraceTime(currentWork.latestActivity.occurredAt)} / sequence {currentWork.latestActivity.sequence} / ledger {currentWork.latestActivity.ledgerEventRef}</small></div>}<div className="current-work-footer"><p>{currentWork.health === "current" ? "This card reflects the latest accepted Node snapshot." : "This snapshot remains readable, but consequential task actions stay gated until the event stream is current."}</p><button type="button" className="secondary-button bordered-button" onClick={onOpenCurrentTask}>Open task</button></div></article> : <div className="home-empty-state"><div className="empty-icon" aria-hidden="true"><AppIcon name="tasks" size={17} /></div><p>{nodeConnected ? "No current task in this desktop session" : "Connect an approved Node to view current work"}</p><small>{nodeConnected ? "When the Node returns a task snapshot, its recorded state will appear here." : "AirBench does not reconstruct task history locally."}</small></div>}</section>
    <section className="readiness-card"><div><p className="eyebrow">{nodeConnected ? "NODE READY" : "READY WHEN YOU ARE"}</p><h2>{nodeConnected ? "Ready to receive a task" : "Connect a trusted Node to begin"}</h2><p>{nodeConnected ? `${nodeLabel} will validate task policy, sources, capacity, and qualified capabilities before any work starts.` : "Your organization controls the models, tools, files, and audit record on that Node."}</p></div><button className="secondary-button bordered-button" data-testid="open-node-settings" onClick={onOpenNode}>{nodeConnected ? "Node settings" : "Connect Node"}</button></section>
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
    <NodeReadinessPanel connection={connection} profile={connectedProfile ?? null} />
    {connection.state === "connected" && <div className="settings-actions"><button className="secondary-button bordered-button" onClick={onReconnect} disabled={connectingProfileId !== null}>Recheck Node</button><span className="settings-action-note">Recheck preserves the approved profile and creates a fresh trust result.</span></div>}
    {connection.state !== "connected" && <><div className="profile-section"><div className="section-heading"><div><h2>Approved Nodes</h2><p>These profiles were installed by your organization administrator.</p></div><button className="text-button" onClick={onReload} disabled={profilesState === "loading"}>Reload</button></div>{profilesState === "loading" && <div className="profile-empty">Loading the local approved profile catalog...</div>}{profilesState === "failed" && <div className="profile-empty profile-error" role="alert">{profileError}<button className="text-button" onClick={onReload}>Try again</button></div>}{profilesState === "ready" && profiles.length === 0 && <div className="profile-empty">No approved Node profile is installed on this workstation. Ask your AirBench administrator to provision one.</div>}{profiles.length > 0 && <div className="profile-list">{profiles.map((profile) => <ProfileCard key={profile.profileId} profile={profile} busy={connectingProfileId === profile.profileId} onConnect={() => onConnect(profile)} />)}</div>}</div></>}
    <div className="settings-note"><strong>What AirBench verifies</strong><p>The native transport checks the approved profile, Node identity, protocol version, clearance context, certificate policy, and authenticated subject before the UI treats the Node as ready. Secrets stay in operating-system credential storage.</p></div><button className="secondary-button bordered-button" onClick={onHome}>Return home</button></section>;
}

function ProfileCard({ profile, busy, onConnect }: { profile: ApprovedNodeProfileReference; busy: boolean; onConnect: () => void }) {
  return <article className="profile-card"><div><div className="profile-name">{profile.displayName}</div><div className="profile-meta">{profile.transport === "loopback" ? "Local workstation" : "Internal network"} <span aria-hidden="true">•</span> {profile.clearanceContext} clearance</div><div className="profile-trust">Pinned identity: {profile.nodeIdentity}</div></div><button className="primary-button" onClick={onConnect} disabled={busy}>{busy ? "Checking..." : "Connect"}</button></article>;
}

function TaskWorkspaceView({ projection, syncState, plan, approval, approving, controlResult, controlling, sourcePreview, artifactPreview, artifactPreviewState, artifactPreviewError, artifactDownloadState, artifactDownloadReceipt, onStop, onRefresh, onApprovePlan, onInspectArtifact, onDownloadArtifact, onHome }: { projection: TaskProjection; syncState: EventSyncState | null; plan: TaskPlanReview | null; approval: NodeCommandResult | null; approving: boolean; controlResult: NodeCommandResult | null; controlling: boolean; sourcePreview: SafePreview | null; artifactPreview: ArtifactPreview | null; artifactPreviewState: ArtifactPreviewState; artifactPreviewError: string | null; artifactDownloadState: "idle" | "downloading" | "downloaded" | "failed"; artifactDownloadReceipt: DownloadReceipt | null; onStop: () => Promise<void>; onRefresh: () => Promise<void>; onApprovePlan: () => Promise<void>; onInspectArtifact: (artifactId: string) => Promise<void>; onDownloadArtifact: (artifactId: string) => Promise<void>; onHome: () => void }) {
  const syncLabel: Record<string, string> = { idle: "Not synchronized", syncing: "Checking Node", connected: "Connected and current", reconnecting: "Reconnecting", replaying: "Replaying events", blocked: "Blocked by protocol or policy" };
  const statusLabel: Record<string, string> = { accepted: "Accepted", planning: "Planning", running: "Running", needs_review: "Needs review", completed: "Completed", blocked: "Blocked", failed: "Failed", stopped: "Stopped" };
  const syncStatus = syncState?.status ?? "idle";
  const canStop = maySendConsequentialCommand(projection, syncStatus) && !["completed", "failed", "stopped"].includes(projection.status) && !controlling;
  const trace = buildWorkTrace(projection, plan);
  const [proofSelection, setProofSelection] = useState<ProofSelection | null>(null);
  useEffect(() => { setProofSelection(null); }, [projection.taskId]);
  const inspectArtifact = (artifactId: string) => {
    setProofSelection({ kind: "artifact", artifactId });
    void onInspectArtifact(artifactId);
  };
  return <section className="workspace-view" data-testid="task-workspace" aria-label="Live task workspace">
    <div className="workspace-head"><div><p className="eyebrow">LIVE TASK</p><h1>{projection.title}</h1><p className="lead">{projection.requestSummary}</p></div><span className={`workspace-status workspace-status-${projection.status}`}>{statusLabel[projection.status] ?? projection.status}</span></div>
    <div className={`workspace-sync workspace-sync-${syncStatus}`} role="status" aria-live="polite"><span className="status-dot" aria-hidden="true" /><strong>{syncLabel[syncStatus] ?? syncStatus}</strong><span>{syncState?.error?.message ?? (syncStatus === "reconnecting" ? "The Node may continue work while this desktop reconnects." : "Task state comes from the approved Node event stream.")}</span><button className="text-button" onClick={onRefresh} disabled={syncStatus === "syncing" || syncStatus === "replaying"}>Refresh</button></div>
    <div className="workspace-actions"><button className="secondary-button bordered-button" onClick={onHome}>Back to Home</button><button className="secondary-button" onClick={onStop} disabled={!canStop} title={canStop ? "Send a Node-authorized stop command" : "Stopping is disabled until the Node is current"}>{controlling ? "Stopping..." : "Stop task"}</button><span className="workspace-command-note">Pause, resume, and question responses appear only when the Node supplies their typed command contracts.</span></div>
    {trace.review.questions.length > 0 && <OperatorQuestionCard questions={trace.review.questions} taskStatus={projection.status} phase={projection.phase} synchronized={syncStatus === "connected"} ledgerEventRef={projection.ledgerHeadRef} />}
    <section className="workspace-now" aria-label="Current Node state"><div><p className="eyebrow">CURRENT NODE STATE</p><h2>{statusLabel[projection.status] ?? projection.status} in {projection.phase}</h2><p>The task state and phase come from the latest approved Node snapshot.</p></div><div className="workspace-now-record">{trace.latestActivity ? <><span>Latest recorded activity</span><strong>{trace.latestActivity.label}</strong><p>{trace.latestActivity.summary}</p><small>{formatTraceTime(trace.latestActivity.occurredAt)} / ledger {trace.latestActivity.ledgerEventRef}</small></> : <><span>Latest recorded activity</span><strong>No activity event yet</strong><p>The Node has supplied the task snapshot but no newer event in this cursor.</p></>}</div></section>
    <section className="worktrace-board" aria-label="Node-backed work trace"><div className="worktrace-board-head"><div><p className="eyebrow">WORK TRACE</p><h2>What AirBench has recorded</h2><p>Each stage is derived from a Node snapshot, plan, or ordered event. Private model reasoning is not shown.</p></div><span className="workspace-count">{trace.activity.length} event{trace.activity.length === 1 ? "" : "s"}</span></div><ol className="worktrace-stage-list">{trace.stages.map((stage) => <TraceStageCard key={stage.id} stage={stage} />)}</ol></section>
    <div className="workspace-proof-layout">
    <div className="worktrace-detail-grid">
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Workers and tools</h2><p>Recorded execution activity, not inferred progress.</p></div><span>{trace.execution.workers.length + trace.execution.tools.length} records</span></div><TraceActivityGroup label="Workers" items={trace.execution.workers} empty="No worker event has been supplied by the Node yet." /><TraceActivityGroup label="Tools and retrieval" items={trace.execution.tools} empty="No tool or retrieval event has been supplied by the current protocol." /></section>
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Evidence and verification</h2><p>Source metadata remains attached to Node evidence.</p></div><span>{trace.evidence.records.length} evidence</span></div>{projection.evidence.length === 0 ? <div className="worktrace-empty">No evidence record has been supplied by the Node yet.</div> : <ul className="worktrace-evidence-list">{projection.evidence.map((item) => <li key={item.evidenceId}><button className="proof-record-button" type="button" onClick={() => setProofSelection({ kind: "evidence", evidence: item })}><strong>{item.source.sourceDocumentId}</strong><span>{formatProvenanceLocation(item.source.location)} / {Math.round(item.confidence * 100)}% confidence</span><small>{item.clearance} clearance / {item.taint} data / ledger {item.source.ledgerEventRef}</small></button></li>)}</ul>}{projection.facts.length > 0 && <div className="worktrace-facts"><span>Findings</span><ul>{projection.facts.map((fact) => <li key={fact.factId}><button className="proof-record-button" type="button" onClick={() => setProofSelection({ kind: "fact", fact })}><strong>{fact.factId}</strong><small>{fact.clearance} clearance / {fact.taint} data / ledger {fact.source.ledgerEventRef}</small></button></li>)}</ul></div>}{sourcePreview && <button className="proof-input-preview-button" type="button" onClick={() => setProofSelection({ kind: "source_preview", preview: sourcePreview })}><AppIcon name="document" size={15} /> Inspect query-upload preview</button>}{trace.verification.latest ? <div className={`worktrace-verification tone-${trace.verification.latest.tone}`}><strong>{trace.verification.latest.label}</strong><p>{trace.verification.latest.summary}</p><small>Ledger {trace.verification.latest.ledgerEventRef}</small></div> : <div className="worktrace-empty">No verification result has been supplied by the Node yet.</div>}</section>
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Waiting for you</h2><p>Only Node-reported questions appear here.</p></div><span>{trace.review.questions.length} waiting</span></div>{trace.review.questions.length === 0 ? <div className="worktrace-empty">The Node has not reported a question requiring your response.</div> : <ul className="worktrace-question-list">{trace.review.questions.map((question, index) => <li key={`${question}-${index}`}><AppIcon name="review" size={16} /><span>{question}</span></li>)}</ul>}<p className="worktrace-contract-note">A response control will appear only after the Node provides a sequence-aware answer command and ledger transition.</p></section>
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Artifacts</h2><p>References returned by the Node, not locally generated files.</p></div><span>{trace.artifacts.ids.length} artifacts</span></div>{trace.artifacts.ids.length === 0 ? <div className="worktrace-empty">No artifact reference has been supplied by the Node yet.</div> : <ul className="worktrace-artifact-list">{trace.artifacts.ids.map((artifactId) => <li key={artifactId}><button className="proof-record-button" type="button" onClick={() => inspectArtifact(artifactId)}><AppIcon name="document" size={16} /><span>{artifactId}</span><small>Inspect Node preview</small></button></li>)}</ul>}<p className="worktrace-contract-note">Open and approval actions remain in the artifact review path after the Node supplies the permitted preview and state.</p></section>
    </div>
    <ProofInspectorPanel selection={proofSelection} artifactPreview={artifactPreview} artifactPreviewState={artifactPreviewState} artifactPreviewError={artifactPreviewError} downloadState={artifactDownloadState} downloadReceipt={artifactDownloadReceipt} onDownloadArtifact={(artifactId: string) => { void onDownloadArtifact(artifactId); }} />
    </div>
    {plan && <PlanReviewCard plan={plan} loading={false} approval={approval} approving={approving} onApprove={onApprovePlan} />}
    {controlResult && <div className="workspace-receipt" role="status">Stop command accepted by Node. Ledger {controlResult.ledger_event_ref ?? "pending"}; waiting for the authoritative event.</div>}
    <section className="workspace-activity"><div className="section-heading"><div><h2>Activity</h2><p>Chronological Node records. Model reasoning traces are not exposed.</p></div><span className="workspace-count">{trace.activity.length} events</span></div>{trace.activity.length === 0 ? <div className="workspace-empty">The Node has not returned a new activity event yet.</div> : <ol className="activity-list">{trace.activity.map((event) => <TraceActivityRow key={`${event.eventId}-${event.sequence}`} item={event} />)}</ol>}</section>
    {projection.diagnostics.length > 0 && <section className="workspace-warning" role="alert"><strong>Task view needs attention</strong>{projection.diagnostics.map((diagnostic) => <span key={`${diagnostic.code}-${diagnostic.sequence}`}>{diagnostic.code}: {diagnostic.detail}</span>)}</section>}
    <details className="workspace-technical"><summary>Technical trace</summary><div className="technical-trace-content"><section><h2>Routing and hardware</h2><p>{trace.routing.state === "not_supplied" ? "No Node routing record is available. The desktop cannot infer a selected target, fallback, or policy reason." : "The Node supplied plan-level capability and hardware context. Exact routing records are not present in the current task event contract."}</p><dl className="technical-trace-grid"><div><dt>Execution mode</dt><dd>{trace.routing.executionMode ?? "Not supplied"}</dd></div><div><dt>Hardware profile</dt><dd>{trace.routing.hardwareProfileRef ?? "Not supplied"}</dd></div><div><dt>Hardware reason</dt><dd>{trace.routing.hardwareReason ?? "Not supplied"}</dd></div><div><dt>Selected target</dt><dd>{trace.routing.selectedTarget ?? "Not supplied"}</dd></div><div><dt>Fallback record</dt><dd>{trace.routing.fallbackReason ?? "Not supplied"}</dd></div><div><dt>Routing policy reason</dt><dd>{trace.routing.policyReason ?? "Not supplied"}</dd></div><div><dt>Plan ledger</dt><dd>{trace.routing.planLedgerEventRef ?? "Not supplied"}</dd></div><div><dt>Plan hash</dt><dd>{trace.routing.planVersionHash ?? "Not supplied"}</dd></div><div><dt>Policy hash</dt><dd>{trace.routing.policyVersionHash ?? "Not supplied"}</dd></div></dl><div className="technical-capability-lanes"><span>Capability lanes</span>{Object.keys(trace.routing.capabilityLanes).length === 0 ? <small>None supplied by the Node.</small> : Object.entries(trace.routing.capabilityLanes).map(([worker, capability]) => <span key={worker}>{worker}: {capability}</span>)}</div></section><section><h2>Event metadata</h2>{trace.activity.length === 0 ? <p>No ordered event metadata is available in this cursor.</p> : <ol className="technical-event-list">{trace.activity.map((event) => <li key={`technical-${event.eventId}`}><strong>{event.label}</strong><dl><div><dt>Event</dt><dd>{event.eventType}</dd></div><div><dt>Sequence</dt><dd>{event.sequence}</dd></div><div><dt>Node time</dt><dd>{event.occurredAt}</dd></div><div><dt>Actor</dt><dd>{event.actor}</dd></div><div><dt>Clearance</dt><dd>{event.clearance}</dd></div><div><dt>Payload hash</dt><dd>{event.payloadHash}</dd></div><div><dt>Ledger</dt><dd>{event.ledgerEventRef}</dd></div></dl></li>)}</ol>}</section></div></details>
  </section>;
}

function TraceStageCard({ stage }: { stage: WorkTraceStage }) {
  return <li className={`worktrace-stage state-${stage.state}`}><span className="worktrace-stage-icon"><AppIcon name={traceStageIcon(stage.id)} size={16} /></span><div><strong>{stage.label}</strong><p>{stage.summary}</p></div><span className="worktrace-stage-status">{traceStateLabel(stage.state)}</span><small>{stage.events.length} record{stage.events.length === 1 ? "" : "s"}</small></li>;
}

function TraceActivityGroup({ label, items, empty }: { label: string; items: WorkTraceActivity[]; empty: string }) {
  return <div className="worktrace-activity-group"><span>{label}</span>{items.length === 0 ? <p>{empty}</p> : <ol>{items.map((item) => <li key={`${label}-${item.eventId}`} className={`tone-${item.tone}`}><strong>{item.label}</strong><small>{item.summary}</small><em>{formatTraceTime(item.occurredAt)} / ledger {item.ledgerEventRef}</em></li>)}</ol>}</div>;
}

function TraceActivityRow({ item }: { item: WorkTraceActivity }) {
  return <li className={`activity-row tone-${item.tone}`}><span className="activity-sequence">{item.sequence}</span><div><strong>{item.label}</strong><p>{item.summary}</p><small>{formatTraceTime(item.occurredAt)} / {item.eventType} / ledger {item.ledgerEventRef}</small></div></li>;
}

function traceStageIcon(stage: WorkTraceStage["id"]): AppIconName {
  const icons: Record<WorkTraceStage["id"], AppIconName> = { plan: "tasks", execution: "airbench", evidence: "archive", verification: "review", review: "shield", artifacts: "document", outcome: "tasks" };
  return icons[stage];
}

function traceStateLabel(state: WorkTraceStage["state"]): string {
  const labels: Record<WorkTraceStage["state"], string> = { waiting: "Waiting", active: "Active", recorded: "Recorded", attention: "Needs attention" };
  return labels[state];
}

function isRecordGatewayDestination(screen: Screen): screen is RecordGatewayDestination {
  return screen === "review" || screen === "artifacts" || screen === "history" || screen === "audit";
}

function RecordGatewayView({ destination, nodeConnected, currentTask, onHome, onOpenNode, onOpenCurrentTask }: { destination: RecordGatewayDestination; nodeConnected: boolean; currentTask: TaskProjection | null; onHome: () => void; onOpenNode: () => void; onOpenCurrentTask: () => void }) {
  const gateway = buildRecordGateway(destination, nodeConnected, currentTask);
  const destinationLabel: Record<RecordGatewayDestination, string> = { review: "Review", artifacts: "Artifacts", history: "History", audit: "Audit ledger" };
  return <section className="record-gateway" data-testid={`record-gateway-${destination}`} aria-label={`${destinationLabel[destination]} record availability`}><header><p className="eyebrow">{gateway.eyebrow}</p><h1>{gateway.title}</h1><p className="lead">{gateway.description}</p></header><section className={`record-gateway-state record-gateway-state-${gateway.state}`} role="status"><span className="record-gateway-icon" aria-hidden="true"><AppIcon name={gateway.state === "node_unavailable" ? "node" : "archive"} size={19} /></span><div><strong>{gateway.stateLabel}</strong><p>{gateway.stateDescription}</p></div></section><section className="record-gateway-requirement"><p className="eyebrow">WHAT IS NEEDED</p><p>{gateway.requiredProjection}</p></section>{gateway.currentTask && <section className="record-gateway-context" aria-label="Current task context"><div><p className="eyebrow">CURRENT TASK CONTEXT</p><h2>{gateway.currentTask.title}</h2><p>This is an existing Node task projection, not a substitute for the requested record query.</p></div><dl><div><dt>Task ID</dt><dd>{gateway.currentTask.taskId}</dd></div><div><dt>State</dt><dd>{gateway.currentTask.status} / {gateway.currentTask.phase}</dd></div><div><dt>Ledger head</dt><dd>{gateway.currentTask.ledgerHeadRef}</dd></div></dl></section>}<footer className="record-gateway-actions">{gateway.state === "node_unavailable" && <button type="button" className="primary-button" onClick={onOpenNode}>Connect approved Node</button>}{gateway.currentTask && <button type="button" className="secondary-button bordered-button" onClick={onOpenCurrentTask}>Open current task</button>}<button type="button" className="text-button" onClick={onHome}>Return home</button></footer></section>;
}

function ConnectionHelp({ onClose, onOpenNode }: { onClose: () => void; onOpenNode: () => void }) {
  return <div className="modal-backdrop" role="presentation"><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="connection-help-title"><button className="modal-close" aria-label="Close" onClick={onClose}>X</button><p className="eyebrow">TRUSTED EXECUTION</p><h2 id="connection-help-title">AirBench works on an approved Node</h2><p>AirBench accepts work only after you select a trusted Node. The Node owns the files, task state, model calls, tools, and audit record for that work.</p><div className="modal-note"><span className="status-dot" aria-hidden="true" /><span><strong>No Node is connected</strong><small>Nothing has been submitted or sent anywhere.</small></span></div><div className="modal-actions"><button className="secondary-button" onClick={onClose}>Close</button><button className="primary-button" onClick={onOpenNode}>Open Node settings</button></div></section></div>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default App;
