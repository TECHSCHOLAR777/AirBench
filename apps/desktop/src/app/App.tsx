import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from "react";
import { invoke } from "@airbench/tauri-invoke";
import { AppIcon, type AppIconName } from "../components/AppIcon";
import type { AirBenchPresentationState, Screen } from "../contracts";
import { initialPresentationState } from "../contracts";
import { NodeConnectionController, type NodeConnectionView } from "../platform/node/nodeConnectionController";
import type { ApprovedNodeProfileReference } from "../platform/node/nodeConnection";
import { listApprovedNodeProfiles } from "../platform/node/profileBridge";
import { downloadVerifiedArtifact, fetchArtifactPreview, fetchIntakeStatus, fetchSafePreview, uploadSelectedQueryFile, type ArtifactPreview, type DownloadReceipt, type IntakeManifest, type IntakeStatus, type SafePreview } from "../features/intake/intakeBridge";
import { approveArtifact, createTask, fetchTaskArtifactReview, fetchTaskPlan, fetchTaskRouteTrace, fetchTaskSnapshot, returnArtifactForRevision, sendTaskCommand, type CreateTaskResponse } from "../platform/node/nodeCommands";
import type { NodeArtifactReview, NodeCommandResult, NodeRouteTrace, TaskPlanReview } from "../generated/core_contracts";
import { buildApprovePlanCommand, buildAuthorizeTaskCommand, buildCancelTaskCommand, buildCreateTaskCommand, canApprovePlan, canCancelTask } from "../features/tasks/taskComposer";
import { planRecoveryGuidance } from "../features/tasks/planRecovery";
import { commandOutcomeGuidance, shouldRefreshTaskAfterCommand } from "../features/tasks/commandOutcome";
import { fetchTaskEventBatch } from "../platform/events/eventTransport";
import { maySendConsequentialCommand, TaskEventSynchronizer, type EventSyncResult, type EventSyncState } from "../platform/events/eventStore";
import { TaskEventLoop } from "../features/tasks/taskEventLoop";
import { taskSyncRecovery } from "../features/tasks/syncRecovery";
import { loadPresentationPreferences, savePresentationPreferences, type PresentationPreferences } from "../features/shell/presentationPreferences";
import { mayLaunchFromShortcut, sourceStatus, unavailableRoutingPreference } from "../features/shell/launchpadPolicy";
import { buildWorkTrace, formatTraceTime, type WorkTrace, type WorkTraceActivity, type WorkTraceStage } from "../features/work_trace/workTrace";
import { activityWindow, DEFAULT_ACTIVITY_WINDOW } from "../features/work_trace/activityWindow";
import { buildHomeWorkSummary, type HomeWorkSummary } from "../features/work_trace/homeWorkSummary";
import { buildRecordGateway, type RecordGatewayDestination } from "../features/provenance/recordGateway";
import { buildShellCommands, shellShortcut, type ShellCommandId } from "../features/shell/commandPalette";
import { WorkspaceCommandDialog } from "../components/WorkspaceCommandDialog";
import { OperatorQuestionCard } from "../components/OperatorQuestionCard";
import { ProofInspectorPanel, type ArtifactLifecycleState, type ArtifactPreviewState } from "../components/ProofInspectorPanel";
import { TaskHistoryView } from "../features/tasks/TaskHistoryView";
import { TaskEmptyView } from "../components/TaskEmptyView";
import { NodeReadinessPanel } from "../components/NodeReadinessPanel";
import { formatFactValue, formatProvenanceLocation, reconcileProofSelection, type ProofSelection } from "../features/provenance/proofInspector";
import type { TaskProjection, TaskStatus } from "../platform/events/protocol";
import { AutonomyPanel } from "../components/AutonomyPanel";
import { ConsistencyPanel } from "../components/ConsistencyPanel";
import { HardwareCard } from "../components/HardwareCard";
import { ModelRoster } from "../components/ModelRoster";
import { clearNodeOperationalProjection, type NodeOperationalProjection } from "../platform/node/nodeOperationalProjection";
import { classifyIntakeFailure, intakeConfidenceCopy, intakeStateFromManifest, intakeStatusCopy, isIntakeConfidenceBand, type IntakeUiState } from "../features/intake/intakeState";

type SelectedFile = { selection_id: string; file_name: string; byte_size: number };
type RecoveryGuidance = { preserved: string; retry: string; nextAction: string };

function boundaryErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string" && error.message.trim()) {
    return error.message.trim();
  }
  return "The approved Node returned an unrecognized intake error.";
}

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
    protocolCompatibilityId: null, clearanceContext: null, authenticatedSubject: null, domainPackRef: null, sovereignty: "unknown", ledgerEventRef: null, failure: null,
  });
  const [profiles, setProfiles] = useState<ApprovedNodeProfileReference[]>([]);
  const [profilesState, setProfilesState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [profilesReloadToken, setProfilesReloadToken] = useState(0);
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
  const [intakeState, setIntakeState] = useState<IntakeUiState>("idle");
  const [intakeManifest, setIntakeManifest] = useState<IntakeManifest | null>(null);
  const [intakeStatus, setIntakeStatus] = useState<IntakeStatus | null>(null);
  const [safePreview, setSafePreview] = useState<SafePreview | null>(null);
  const [artifactPreview, setArtifactPreview] = useState<ArtifactPreview | null>(null);
  const [downloadState, setDownloadState] = useState<"idle" | "downloading" | "downloaded" | "failed">("idle");
  const [downloadReceipt, setDownloadReceipt] = useState<DownloadReceipt | null>(null);
  const [taskResult, setTaskResult] = useState<CreateTaskResponse | null>(null);
  const [taskRouteTrace, setTaskRouteTrace] = useState<NodeRouteTrace | null>(null);
  const [planReview, setPlanReview] = useState<TaskPlanReview | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planApprovalResult, setPlanApprovalResult] = useState<NodeCommandResult | null>(null);
  const [approvingPlan, setApprovingPlan] = useState(false);
  const [taskProjection, setTaskProjection] = useState<TaskProjection | null>(null);
  const [eventSyncState, setEventSyncState] = useState<EventSyncState | null>(null);
  const [taskControlResult, setTaskControlResult] = useState<NodeCommandResult | null>(null);
  const [controllingTask, setControllingTask] = useState(false);
  const [taskArtifactPreview, setTaskArtifactPreview] = useState<ArtifactPreview | null>(null);
  const [taskArtifactReview, setTaskArtifactReview] = useState<NodeArtifactReview | null>(null);
  const [taskArtifactPreviewState, setTaskArtifactPreviewState] = useState<ArtifactPreviewState>("idle");
  const [taskArtifactPreviewError, setTaskArtifactPreviewError] = useState<string | null>(null);
  const [taskArtifactDownloadState, setTaskArtifactDownloadState] = useState<"idle" | "downloading" | "downloaded" | "failed">("idle");
  const [taskArtifactDownloadReceipt, setTaskArtifactDownloadReceipt] = useState<DownloadReceipt | null>(null);
  const [artifactCommandPending, setArtifactCommandPending] = useState(false);
  const synchronizerRef = useRef<TaskEventSynchronizer | null>(null);
  const taskEventLoopRef = useRef<TaskEventLoop | null>(null);
  const synchronizationRef = useRef<Promise<EventSyncResult> | null>(null);
  const synchronizationTokenRef = useRef<symbol | null>(null);
  const outcomeInputRef = useRef<HTMLTextAreaElement | null>(null);
  const commandMenuReturnFocusRef = useRef<HTMLElement | null>(null);
  const commandMenuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const connectionHelpReturnFocusRef = useRef<HTMLElement | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [nodeOperationalProjection, setNodeOperationalProjection] = useState<NodeOperationalProjection>({ hardware: null, modelServing: null, qualification: null });
  const [taskHistory, setTaskHistory] = useState<HomeWorkSummary[]>(() => {
    try {
      const stored = window.localStorage.getItem("airbench.task-history.v1");
      return stored ? JSON.parse(stored) as HomeWorkSummary[] : [];
    } catch { return []; }
  });
  const controller = useMemo(() => new NodeConnectionController(), []);
  const nodeConnected = connection.state === "connected" && controller.canSendConsequential();
  const taskCommandReady = taskProjection !== null && maySendConsequentialCommand(taskProjection, eventSyncState?.status ?? "idle");

  const screenTitle = useMemo(() => {
    const titles: Record<Screen, string> = { home: "Home", tasks: "Tasks", review: "Review", artifacts: "Artifacts", history: "History", audit: "Audit", node: "Node and settings" };
    return titles[state.screen];
  }, [state.screen]);

  const selectScreen = (screen: Screen) => setState((current) => ({ ...current, screen }));

  const focusOutcomeInput = useCallback(() => window.requestAnimationFrame(() => outcomeInputRef.current?.focus()), []);

  const clearActiveTaskView = useCallback(() => {
    taskEventLoopRef.current?.stop();
    taskEventLoopRef.current = null;
    synchronizationRef.current = null;
    synchronizationTokenRef.current = null;
    synchronizerRef.current = null;
    setTaskResult(null);
    setTaskRouteTrace(null);
    setPlanReview(null);
    setPlanLoading(false);
    setPlanApprovalResult(null);
    setApprovingPlan(false);
    setTaskProjection(null);
    setEventSyncState(null);
    setTaskControlResult(null);
    setControllingTask(false);
    setTaskArtifactPreview(null);
    setTaskArtifactReview(null);
    setTaskArtifactPreviewState("idle");
    setTaskArtifactPreviewError(null);
    setTaskArtifactDownloadState("idle");
    setTaskArtifactDownloadReceipt(null);
  }, []);

  const resetComposer = useCallback(() => {
    setTaskText("");
    setTaskTitle("");
    setProjectRef("");
    setSelectedFile(null);
    setIntakeState("idle");
    setIntakeManifest(null);
    setIntakeStatus(null);
    setSafePreview(null);
    setArtifactPreview(null);
    setDownloadState("idle");
    setDownloadReceipt(null);
    setNotice(null);
  }, []);

  const archiveActiveTask = useCallback(() => {
    if (!taskProjection) return;
    const summary = buildHomeWorkSummary(taskProjection);
    setTaskHistory((current) => current.some((entry) => entry.taskId === summary.taskId) ? current : [...current, summary]);
  }, [taskProjection]);

  const openNewTask = useCallback(() => {
    setShowCommandPalette(false);
    setShowAppearanceMenu(false);
    archiveActiveTask();
    clearActiveTaskView();
    resetComposer();
    setState((current) => ({ ...current, screen: "home" }));
    focusOutcomeInput();
  }, [archiveActiveTask, clearActiveTaskView, resetComposer, focusOutcomeInput]);

  const dismissCurrentTask = useCallback(() => {
    archiveActiveTask();
    clearActiveTaskView();
    setNotice("Task removed from this desktop view. The Node record and its ledger entries are unchanged.");
  }, [archiveActiveTask, clearActiveTaskView]);

  const removeHistoryTask = useCallback((taskId: string) => {
    setTaskHistory((current) => current.filter((entry) => entry.taskId !== taskId));
  }, []);

  const openCommandPalette = useCallback((returnFocus: EventTarget | null) => {
    commandMenuReturnFocusRef.current = returnFocus instanceof HTMLElement ? returnFocus : commandMenuTriggerRef.current;
    setShowAppearanceMenu(false);
    setShowCommandPalette(true);
  }, []);

  const closeCommandPalette = useCallback(() => {
    setShowCommandPalette(false);
    window.requestAnimationFrame(() => commandMenuReturnFocusRef.current?.focus());
  }, []);

  const openConnectionHelp = useCallback(() => {
    connectionHelpReturnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setShowConnectionHelp(true);
  }, []);

  const closeConnectionHelp = useCallback(() => {
    setShowConnectionHelp(false);
    window.requestAnimationFrame(() => connectionHelpReturnFocusRef.current?.focus());
  }, []);

  useEffect(() => {
    savePresentationPreferences(presentation);
  }, [presentation]);

  useEffect(() => {
    try { window.localStorage.setItem("airbench.task-history.v1", JSON.stringify(taskHistory)); } catch { /* presentation persistence is best effort */ }
  }, [taskHistory]);

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
    if (state.screen !== "node") return;
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
  }, [state.screen, profilesReloadToken]);

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

  const markNodeTransportUncertain = () => {
    applyConnection(controller.markDisconnected());
  };

  const applyTaskSyncResult = (result: EventSyncResult) => {
    setTaskProjection(result.projection);
    setEventSyncState(result.state);
    if (result.projection.status === "completed" || result.projection.status === "failed" || result.projection.status === "stopped") {
      setTaskHistory((current) => {
        const exists = current.some((t) => t.taskId === result.projection.taskId);
        if (exists) return current;
        return [...current, buildHomeWorkSummary(result.projection)];
      });
    }
    if (result.kind === "reconnecting") markNodeTransportUncertain();
    return result;
  };

  const refreshTaskRouteTrace = async (profile: ApprovedNodeProfileReference, taskId: string) => {
    try {
      setTaskRouteTrace(await fetchTaskRouteTrace(profile, taskId));
    } catch {
      // A transient route-read failure is non-authoritative. Keep the last
      // valid projection visible rather than replacing proven Node data with
      // an empty desktop guess.
    }
  };

  const connectProfile = async (profile: ApprovedNodeProfileReference) => {
    setConnectingProfileId(profile.profileId);
    setConnection({ ...controller.snapshot(), state: "connecting", profileId: profile.profileId });
    const next = await controller.connect(profile);
    clearNodeOperationalProjection(profile.profileId);
    setNodeOperationalProjection({ hardware: null, modelServing: null, qualification: null });
    applyConnection(next);
    setConnectingProfileId(null);
    setNotice(next.state === "connected" ? `${profile.displayName} is verified and ready.` : next.failure?.message ?? "The Node connection was blocked.");
  };

  const reconnect = async () => {
    setConnectingProfileId(connection.profileId);
    const next = await controller.reconnect();
    if (connection.profileId) clearNodeOperationalProjection(connection.profileId);
    setNodeOperationalProjection({ hardware: null, modelServing: null, qualification: null });
    applyConnection(next);
    setConnectingProfileId(null);
  };

  const attachFile = async () => {
    setNotice(null);
    try {
      const selection = await invoke<SelectedFile | null>("pick_query_file");
      if (selection) {
        setSelectedFile(selection);
        setIntakeState("idle");
        setIntakeManifest(null);
        setSafePreview(null);
        setArtifactPreview(null);
        setDownloadState("idle");
        setDownloadReceipt(null);
        setNotice("File selected. It will enter AirBench through the File Intake Layer when a Node is connected.");
      } else {
        setNotice("No file selected.");
      }
    } catch {
      setNotice("The native file picker is available in the desktop application. Connect an approved Node before submitting work.");
    }
  };

  const uploadFileForTask = async (profile: ApprovedNodeProfileReference, selectionId: string, taskId: string): Promise<IntakeManifest | null> => {
    setIntakeState("uploading");
    setIntakeManifest(null);
    setIntakeStatus(null);
    setSafePreview(null);
    setArtifactPreview(null);
    setDownloadState("idle");
    setDownloadReceipt(null);
    setNotice(null);
    try {
      const manifest = await uploadSelectedQueryFile(profile, selectionId, taskId);
      setIntakeManifest(manifest);
      const manifestState = intakeStateFromManifest(manifest);
      setIntakeState(manifestState);
      try {
        setIntakeStatus(await fetchIntakeStatus(profile, manifest.intake_id));
      } catch {
        setIntakeStatus(null);
      }
      if (manifestState !== "ready") {
        setNotice(manifestState === "processing"
          ? "File Intake accepted the source, but OCR or vision is still processing. The Node will keep the task gated until a completed preview exists."
          : "File Intake accepted the source, but the configured OCR or vision path is unavailable. The task remains gated until the Node supplies a complete result.");
        return null;
      }
      try {
        const preview = await fetchSafePreview(profile, manifest.preview_ref, manifest.source_hash);
        setSafePreview(preview);
      } catch (error) {
        const state = classifyIntakeFailure(error, true);
        setIntakeState(state);
        setNotice(intakeStatusCopy(state).detail);
        return null;
      }
      try {
        const artifact = await fetchArtifactPreview(profile, manifest.artifact_ref);
        setArtifactPreview(artifact);
      } catch {
        setArtifactPreview(null);
        setNotice("Source accepted by File Intake. A source-artifact preview is not available yet; task execution remains governed by the Node.");
        return null;
      }
      setNotice("AirBench accepted the file through the File Intake Layer. Previews are Node-generated and remain untrusted data.");
      return manifest;
    } catch (error) {
      const boundaryError = boundaryErrorMessage(error);
      console.error("[AirBench] File Intake upload failed", boundaryError);
      const state = classifyIntakeFailure(error);
      setIntakeState(state);
      setIntakeManifest(null);
      setIntakeStatus(null);
      setSafePreview(null);
      setArtifactPreview(null);
      setNotice(`${intakeStatusCopy(state).detail} ${boundaryError}`);
      throw error;
    }
  };

  const uploadSelectedFile = async () => {
    if (!selectedFile) return;
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected) {
      setNotice("Connect a verified Node before sending a file to the File Intake Layer.");
      return;
    }
    if (!taskResult) {
      setNotice("Launch the task first so the Node can bind this source to its task ledger. File Intake will run immediately after task creation.");
      return;
    }
    try {
      await uploadFileForTask(profile, selectedFile.selection_id, taskResult.task.task_id);
    } catch {
      // The helper has already exposed the bounded recovery state.
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
    setDownloadReceipt(null);
    setNotice(null);
    try {
      const receipt = await downloadVerifiedArtifact(profile, artifactPreview.artifact_id, "approval-note.pdf");
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
    setTaskArtifactReview(null);
    setTaskArtifactPreviewError(null);
    setTaskArtifactDownloadState("idle");
    setTaskArtifactDownloadReceipt(null);
    if (!profile || !nodeConnected) {
      setTaskArtifactPreviewState("failed");
      setTaskArtifactPreviewError("Connect a verified Node before requesting an artifact preview.");
      return;
    }
    setTaskArtifactPreviewState("loading");
    const [previewResult, reviewResult] = await Promise.allSettled([
      fetchArtifactPreview(profile, artifactId),
      taskProjection ? fetchTaskArtifactReview(profile, taskProjection.taskId) : Promise.reject(new Error("The current task is not available.")),
    ]);
    if (previewResult.status === "fulfilled") {
      setTaskArtifactPreview(previewResult.value);
      setTaskArtifactPreviewState("ready");
    } else {
      setTaskArtifactPreviewState("failed");
      setTaskArtifactPreviewError("The approved Node did not return a safe preview for this artifact.");
    }
    if (reviewResult.status === "fulfilled" && reviewResult.value.artifactId === artifactId) {
      setTaskArtifactReview(reviewResult.value);
    } else {
      setTaskArtifactReview(null);
    }
  };

  const downloadTaskArtifact = async (artifactId: string) => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !taskCommandReady) {
      setTaskArtifactDownloadState("failed");
      setNotice("The task view is not current with the Node. Reconnect and resynchronize before downloading an artifact.");
      return;
    }
    setTaskArtifactDownloadState("downloading");
    setTaskArtifactDownloadReceipt(null);
    try {
      const extension = taskArtifactReview?.artifactId === artifactId ? taskArtifactReview.fileFormat : "bin";
      const receipt = await downloadVerifiedArtifact(profile, artifactId, `airbench-artifact-${artifactId}.${extension}`);
      setTaskArtifactDownloadReceipt(receipt);
      setTaskArtifactDownloadState("downloaded");
    } catch {
      setTaskArtifactDownloadState("failed");
    }
  };

  const approveTaskArtifact = async (artifactId: string, reason: string) => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !taskCommandReady || !taskProjection) {
      setNotice("The task view is not current with the Node. Reconnect and resynchronize before approving an artifact.");
      return;
    }
    setArtifactCommandPending(true);
    setNotice(null);
    try {
      await approveArtifact(profile, taskProjection.taskId, artifactId, reason, taskProjection.lastAppliedSequence, connection.authenticatedSubject!);
      setNotice("Artifact approved. The Node recorded the sign-off.");
      await refreshTask();
    } catch (error) {
      const message = error instanceof Error ? error.message : "The Node did not accept the artifact approval.";
      setNotice(message);
    } finally {
      setArtifactCommandPending(false);
    }
  };

  const returnTaskArtifact = async (artifactId: string, reason: string) => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !taskCommandReady || !taskProjection) {
      setNotice("The task view is not current with the Node. Reconnect and resynchronize before returning an artifact.");
      return;
    }
    setArtifactCommandPending(true);
    setNotice(null);
    try {
      await returnArtifactForRevision(profile, taskProjection.taskId, artifactId, reason, taskProjection.lastAppliedSequence, connection.authenticatedSubject!);
      setNotice("Artifact returned for revision. The Node recorded a new review request.");
      await refreshTask();
    } catch (error) {
      const message = error instanceof Error ? error.message : "The Node did not accept the artifact return.";
      setNotice(message);
    } finally {
      setArtifactCommandPending(false);
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
    const applied = applyTaskSyncResult(result);
    await refreshTaskRouteTrace(profile, applied.projection.taskId);
    return applied;
  };

  const refreshTask = async () => {
    const synchronizer = synchronizerRef.current;
    if (!synchronizer) return;
    const taskId = taskProjection?.taskId;
    const result = await synchronize(synchronizer);
    applyTaskSyncResult(result);
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (profile && taskId) await refreshTaskRouteTrace(profile, taskId);
  };

  const openHistoryTask = async (taskId: string) => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected) { setNotice("Reconnect the approved Node before reopening a task."); return; }
    try {
      const snapshot = await fetchTaskSnapshot(profile, taskId);
      await syncTask(profile, snapshot);
      setState((current) => ({ ...current, screen: "tasks" }));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The Node could not reopen that task projection.");
    }
  };

  useEffect(() => {
    const taskId = taskProjection?.taskId;
    const synchronizer = synchronizerRef.current;
    if (!taskId || !synchronizer || !nodeConnected) return;

    const loop = new TaskEventLoop(
      () => synchronize(synchronizer),
      (result) => {
        const applied = applyTaskSyncResult(result);
        const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
        if (profile) void refreshTaskRouteTrace(profile, applied.projection.taskId);
      },
      {
        onTransportUncertain: markNodeTransportUncertain,
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
  }, [nodeConnected, synchronize, taskProjection?.taskId, profiles, connection.profileId]);

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
    setTaskRouteTrace(null);
    setPlanReview(null);
    setPlanApprovalResult(null);
    setTaskArtifactPreview(null);
    setTaskArtifactReview(null);
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
        inputManifestRefs: [],
        inputKind: selectedFile ? "file" : "text",
      }, commandId, `idempotency.${commandId}`);
      const result = await createTask(profile, command);
      setTaskResult(result);
      let intakeManifestForTask: IntakeManifest | null = null;
      let intakeFailureMessage: string | null = null;
      if (selectedFile) {
        try {
          intakeManifestForTask = await uploadFileForTask(profile, selectedFile.selection_id, result.task.task_id);
        } catch (error) {
          // Keep the bounded boundary diagnostic visible. The task remains a
          // real Node task, but execution stays gated until File Intake is
          // committed. Do not replace a useful IPC or Node error with a
          // generic message that invites blind retries.
          intakeFailureMessage = boundaryErrorMessage(error);
        }
      }
      let synchronizedSnapshot = result.snapshot;
      try {
        synchronizedSnapshot = await fetchTaskSnapshot(profile, result.task.task_id);
      } catch {
        // The create snapshot remains the last authoritative projection.
      }
      const taskResultWithIntake = { ...result, snapshot: synchronizedSnapshot };
      setTaskResult(taskResultWithIntake);
      if (selectedFile && !intakeManifestForTask) {
        setNotice(`The Node accepted the task, but File Intake did not return a committed manifest. Authorization is paused. ${intakeFailureMessage ?? "The approved Node returned no intake result."}`);
        return;
      }
      const authorizationCommandId = `command.authorize.${crypto.randomUUID()}`;
      const authorizationCommand = buildAuthorizeTaskCommand(
        connection.authenticatedSubject,
        result.task.task_id,
        synchronizedSnapshot.asOfSequence,
        "operator.authorized.local-task",
        authorizationCommandId,
        `idempotency.${authorizationCommandId}`,
      );
      try {
        await sendTaskCommand(profile, authorizationCommand);
        synchronizedSnapshot = await fetchTaskSnapshot(profile, result.task.task_id);
        setTaskResult({ ...result, snapshot: synchronizedSnapshot });
      } catch {
        setNotice("The Node accepted the task, but did not authorize it. No plan or execution was started.");
        return;
      }
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
      await syncTask(profile, synchronizedSnapshot);
      selectScreen("tasks");
    } catch {
      setNotice("The Node did not accept this task. No local task state was created.");
    } finally {
      setCreatingTask(false);
    }
  };

  const approvePlan = async () => {
    const profile = profiles.find((candidate) => candidate.profileId === connection.profileId);
    if (!profile || !nodeConnected || !taskCommandReady || !connection.authenticatedSubject || !taskResult || !planReview) {
      setNotice("Connect a verified Node and wait for an approvable plan before continuing.");
      return;
    }
    if (planReview.plan_state !== "ready" || planReview.required_authority !== "operator_approval") {
      setNotice("This plan is not ready for operator approval. The Node must resolve its policy or hardware state first.");
      return;
    }
    if (planReview.task_sequence !== taskProjection.lastAppliedSequence) {
      setNotice("This plan is based on an older Node sequence. Refresh the task projection before approving it.");
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
      setNotice(commandOutcomeGuidance("Plan approval", result).detail);
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
      const guidance = commandOutcomeGuidance("Stop request", result);
      setNotice(guidance.detail);
      if (shouldRefreshTaskAfterCommand(result)) await refreshTask();
    } catch {
      setNotice("The Node did not accept the stop command. No local task state was changed.");
    } finally {
      setControllingTask(false);
    }
  };

  const canStart = nodeConnected && taskText.trim().length > 0
    && (intakeState === "ready" || (!taskResult && intakeState === "idle"))
    && !creatingTask;
  const nodeLabel = nodeConnected ? (profiles.find((profile) => profile.profileId === connection.profileId)?.displayName ?? "Node connected") : connection.state === "connecting" ? "Connecting to Node" : connection.state === "reconnecting" ? "Reconnecting to Node" : "Node not connected";
  const nodeDetail = nodeConnected ? "Verified and ready" : connection.state === "failed" || connection.state === "blocked" ? "Connection blocked" : connection.state === "reconnecting" ? "Reconnect to continue" : "Choose an approved Node";
  const sovereigntyLabel = nodeConnected && connection.sovereignty === "verified" ? "Verified internal path" : "No verified Node path";
  const shellCommands = useMemo(() => buildShellCommands(taskProjection !== null), [taskProjection]);

  const runShellCommand = (commandId: ShellCommandId) => {
    closeCommandPalette();
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
        <button type="button" className="new-task-button" onClick={openNewTask}><AppIcon name="plus" size={17} /><span>New task</span><kbd>Ctrl N</kbd></button>
        <nav className="nav-groups"><NavGroup title="Work" items={primaryNav} active={state.screen} onSelect={selectScreen} /><NavGroup title="Records" items={recordNav} active={state.screen} onSelect={selectScreen} /></nav>
        <div className="sidebar-spacer" />
        <button type="button" className="node-chip" data-testid="node-chip" onClick={() => selectScreen("node")} aria-label="Open Node and settings"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" /><span className="node-chip-copy"><strong>{nodeLabel}</strong><small>{nodeDetail}</small></span><AppIcon name="chevron-down" size={15} /></button>
        <div className="user-row"><div className="avatar">RG</div><div><strong>Local operator</strong><small>{connection.clearanceContext ? `${connection.clearanceContext} clearance` : "Clearance not resolved"}</small></div><span className="operator-session">Local session</span></div>
        <small className="build-info" data-testid="app-version">AirBench {__AIRBENCH_VERSION__} / offline shell</small>
      </aside>

      <main className="main-area">
        <header className="topbar"><div className="breadcrumb"><span>AirBench</span><span className="breadcrumb-slash">/</span><strong>{screenTitle}</strong></div><div className="topbar-actions"><button ref={commandMenuTriggerRef} className="command-menu-button" type="button" onClick={(event) => openCommandPalette(event.currentTarget)} aria-haspopup="dialog" aria-expanded={showCommandPalette} aria-controls="workspace-command-palette"><AppIcon name="search" size={16} /><span>Command</span><kbd>Ctrl K</kbd></button><button type="button" className={`sovereignty-status ${nodeConnected ? "is-verified" : ""}`} onClick={() => selectScreen("node")} aria-label="Open Node and settings"><AppIcon name={nodeConnected ? "shield" : "node"} size={16} /><span><small>Node path</small><strong>{sovereigntyLabel}</strong></span></button><div className="appearance-control"><button className="appearance-button" type="button" onClick={() => setShowAppearanceMenu((open) => !open)} aria-expanded={showAppearanceMenu} aria-controls="appearance-preferences"><AppIcon name="display" size={16} /><span>Display</span><AppIcon name="chevron-down" size={14} /></button>{showAppearanceMenu && <AppearanceMenu preferences={presentation} onChange={setPresentation} onClose={() => setShowAppearanceMenu(false)} />}</div></div></header>
        <div className="content-wrap">
          {state.screen === "home" && <HomeView outcomeInputRef={outcomeInputRef} currentTask={taskProjection} taskText={taskText} setTaskText={setTaskText} taskTitle={taskTitle} setTaskTitle={setTaskTitle} projectRef={projectRef} setProjectRef={setProjectRef} outputContract={outputContract} setOutputContract={setOutputContract} priority={priority} setPriority={setPriority} deadline={deadline} setDeadline={setDeadline} selectedFile={selectedFile} intakeState={intakeState} intakeManifest={intakeManifest} intakeStatus={intakeStatus} safePreview={safePreview} artifactPreview={artifactPreview} downloadState={downloadState} downloadReceipt={downloadReceipt} taskResult={taskResult} planReview={planReview} planLoading={planLoading} planApprovalResult={planApprovalResult} approvingPlan={approvingPlan} planSynchronized={taskCommandReady} notice={notice} canStart={canStart} creatingTask={creatingTask} nodeConnected={nodeConnected} nodeLabel={nodeLabel} onAttach={attachFile} onUpload={uploadSelectedFile} onDownload={downloadApprovedArtifact} onStart={startTask} onApprovePlan={approvePlan} onCancelTask={stopTask} onRemoveFile={() => { setSelectedFile(null); setIntakeState("idle"); setIntakeManifest(null); setIntakeStatus(null); setSafePreview(null); setArtifactPreview(null); setDownloadState("idle"); setDownloadReceipt(null); }} onHelp={openConnectionHelp} onOpenNode={() => selectScreen("node")} onOpenCurrentTask={() => selectScreen("tasks")} onDismissCurrent={dismissCurrentTask} onNewQuery={openNewTask} />}
          {state.screen === "node" && <NodeSettingsView profiles={profiles} profilesState={profilesState} profileError={profileError} connection={connection} connectingProfileId={connectingProfileId} onConnect={connectProfile} onReconnect={reconnect} onReload={() => { setProfilesReloadToken((token) => token + 1); }} onHome={() => selectScreen("home")} operationalProjection={nodeOperationalProjection} onOperationalProjection={setNodeOperationalProjection} />}
          {state.screen === "tasks" && (taskProjection ? <TaskWorkspaceView projection={taskProjection} syncState={eventSyncState} plan={planReview} routeTrace={taskRouteTrace} approval={planApprovalResult} approving={approvingPlan} controlResult={taskControlResult} controlling={controllingTask} sourcePreview={intakeManifest?.intake_id === taskProjection.inputManifestRef ? safePreview : null} artifactReview={taskArtifactReview} artifactPreview={taskArtifactPreview} artifactPreviewState={taskArtifactPreviewState} artifactPreviewError={taskArtifactPreviewError} artifactDownloadState={taskArtifactDownloadState} artifactDownloadReceipt={taskArtifactDownloadReceipt} onStop={stopTask} onRefresh={refreshTask} onApprovePlan={approvePlan} onInspectArtifact={inspectTaskArtifact} onDownloadArtifact={downloadTaskArtifact} onHome={openNewTask} onOpenNode={() => selectScreen("node")} onApproveArtifact={approveTaskArtifact} onReturnArtifact={returnTaskArtifact} isArtifactCommandPending={artifactCommandPending} profile={profiles.find((p) => p.profileId === connection.profileId) ?? null} operatorId={connection.authenticatedSubject} /> : <TaskEmptyView nodeConnected={nodeConnected} onNewTask={openNewTask} onOpenNode={() => selectScreen("node")} />)}
          {isRecordGatewayDestination(state.screen) && <RecordGatewayView destination={state.screen} nodeConnected={nodeConnected} currentTask={taskProjection} onHome={() => selectScreen("home")} onOpenNode={() => selectScreen("node")} onOpenCurrentTask={() => selectScreen("tasks")} taskHistory={taskHistory} onOpenTask={openHistoryTask} onRemoveTask={removeHistoryTask} onNewTask={openNewTask} />}
        </div>
      </main>
      {showConnectionHelp && <ConnectionHelp onClose={closeConnectionHelp} onOpenNode={() => { closeConnectionHelp(); selectScreen("node"); }} />}
      {showCommandPalette && <WorkspaceCommandDialog commands={shellCommands} onClose={closeCommandPalette} onSelect={runShellCommand} />}
    </div>
  );
}

function NavGroup({ title, items, active, onSelect }: { title: string; items: Array<{ id: Screen; label: string; icon: AppIconName }>; active: Screen; onSelect: (screen: Screen) => void }) {
  return <div className="nav-group">
    <div className="nav-group-title">{title}</div>
    {items.map((item) => <button type="button" key={item.id} className={`nav-item ${active === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}>
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

function HomeView({ outcomeInputRef, currentTask, taskText, setTaskText, taskTitle, setTaskTitle, projectRef, setProjectRef, outputContract, setOutputContract, priority, setPriority, deadline, setDeadline, selectedFile, intakeState, intakeManifest, intakeStatus, safePreview, artifactPreview, downloadState, downloadReceipt, taskResult, planReview, planLoading, planApprovalResult, approvingPlan, planSynchronized, notice, canStart, creatingTask, nodeConnected, nodeLabel, onAttach, onUpload, onDownload, onStart, onApprovePlan, onCancelTask, onRemoveFile, onHelp, onOpenNode, onOpenCurrentTask, onDismissCurrent, onNewQuery }: { outcomeInputRef: RefObject<HTMLTextAreaElement | null>; currentTask: TaskProjection | null; taskText: string; setTaskText: (value: string) => void; taskTitle: string; setTaskTitle: (value: string) => void; projectRef: string; setProjectRef: (value: string) => void; outputContract: string; setOutputContract: (value: string) => void; priority: string; setPriority: (value: string) => void; deadline: string; setDeadline: (value: string) => void; selectedFile: SelectedFile | null; intakeState: IntakeUiState; intakeManifest: IntakeManifest | null; intakeStatus: IntakeStatus | null; safePreview: SafePreview | null; artifactPreview: ArtifactPreview | null; downloadState: "idle" | "downloading" | "downloaded" | "failed"; downloadReceipt: DownloadReceipt | null; taskResult: CreateTaskResponse | null; planReview: TaskPlanReview | null; planLoading: boolean; planApprovalResult: NodeCommandResult | null; approvingPlan: boolean; planSynchronized: boolean; notice: string | null; canStart: boolean; creatingTask: boolean; nodeConnected: boolean; nodeLabel: string; onAttach: () => void; onUpload: () => void; onDownload: () => void; onStart: () => void; onApprovePlan: () => void; onCancelTask: () => Promise<void>; onRemoveFile: () => void; onHelp: () => void; onOpenNode: () => void; onOpenCurrentTask: () => void; onDismissCurrent: () => void; onNewQuery: () => void }) {
  const [openPanel, setOpenPanel] = useState<LaunchpadPanel | null>(null);
  const outputLabel = outputContractOptions.find((option) => option.value === outputContract)?.label ?? "Deliverable";
  const selectedSourceStatus = sourceStatus(Boolean(selectedFile), intakeState);
  const intakeCopy = intakeStatusCopy(intakeState);
  const intakeBand = intakeStatus && isIntakeConfidenceBand(intakeStatus.confidence_band) ? intakeStatus.confidence_band : null;
  const routingPreference = unavailableRoutingPreference(nodeConnected);
  const currentWork = currentTask ? buildHomeWorkSummary(currentTask) : null;
  const launchTitle = canStart ? "Launch task" : !nodeConnected ? "Connect an approved Node first" : !taskText.trim() ? "Describe the outcome first" : "Finish File Intake before launching";
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
        {!selectedFile && <div className="launchpad-source-empty"><AppIcon name="attachment" size={19} /><div><strong>Text input will be captured</strong><p>The task request enters the Node through the File Intake Layer as untrusted text. Attach a file when the task needs one.</p></div><button type="button" className="secondary-button" onClick={openSourcePicker}>Choose file</button></div>}
        {selectedFile && <div className="selected-file"><span className="file-badge">FILE</span><span><strong>{selectedFile.file_name}</strong><small>{formatBytes(selectedFile.byte_size)} / {intakeCopy.label}</small></span><div className="selected-file-actions">{intakeState === "idle" && taskResult && <button type="button" className="secondary-button compact-button" onClick={onUpload}>Send to Node</button>}{intakeState === "idle" && !taskResult && <span className="selected-file-handoff">Sent after Launch</span>}{intakeState === "uploading" && <button type="button" className="secondary-button compact-button" disabled>Sending...</button>}{intakeState !== "idle" && intakeState !== "uploading" && intakeState !== "ready" && intakeCopy.retryable && <button type="button" className="secondary-button compact-button" onClick={openSourcePicker}>Choose again</button>}<button type="button" className="remove-file" onClick={onRemoveFile} aria-label="Remove selected file">Remove</button></div></div>}
        {selectedFile && intakeState !== "idle" && intakeState !== "ready" && <div className={`intake-status intake-status-${intakeState}`} role={intakeState === "uploading" || intakeState === "processing" ? "status" : "alert"}><strong>{intakeCopy.title}</strong><span>{intakeCopy.detail}</span><IntakeRecoveryGuidance recovery={intakeCopy.recovery} /></div>}
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
      <div className="composer-footer launchpad-footer"><div className="composer-tools"><button type="button" className="secondary-button launchpad-attach-button" data-testid="attach-files" onClick={openSourcePicker}><AppIcon name="attachment" size={15} /> Attach files</button><span className="launchpad-footer-status"><AppIcon name="route" size={15} /><span><strong>Auto route</strong> Node validates the task before choosing qualified workers.</span></span></div><button type="button" className="primary-button" data-testid="start-task" onClick={onStart} disabled={!canStart} title={launchTitle}>{creatingTask ? "Launching..." : "Launch"} <kbd>Ctrl Enter</kbd></button></div>
    </section>
    {intakeManifest && <section className="source-summary" data-testid="intake-result" aria-label="Source accepted by File Intake"><AppIcon name="archive" size={15} /><strong>{intakeManifest.file_name}</strong><span>{intakeManifest.page_count} page{intakeManifest.page_count === 1 ? "" : "s"}</span><span>{intakeManifest.clearance} clearance</span><span>{intakeManifest.taint} data</span><span className={`source-summary-state source-summary-state-${intakeState}`}>{intakeCopy.label}</span>{intakeBand && <span className={`intake-badge intake-confidence-${intakeBand}`} data-testid="intake-confidence-badge">{intakeConfidenceCopy(intakeBand).label}</span>}</section>}
    {taskResult && <section className="task-confirmation" data-testid="task-confirmation" aria-label="Task submission result"><p className="eyebrow">TASK ACCEPTED BY NODE</p><strong>{taskResult.task.task_id}</strong><span>State: {taskResult.command.state ?? taskResult.task.state ?? "created"}</span><small>Ledger {taskResult.command.ledger_event_ref ?? taskResult.ledger_event_ref} / sequence {taskResult.command.sequence ?? taskResult.snapshot.asOfSequence}</small></section>}
    {taskResult && <PlanReviewCard plan={planReview} loading={planLoading} approval={planApprovalResult} approving={approvingPlan} synchronized={planSynchronized} currentTaskSequence={currentTask?.lastAppliedSequence ?? taskResult.snapshot.asOfSequence} taskStatus={currentTask?.status ?? "accepted"} onApprove={onApprovePlan} onCancel={onCancelTask} />}
    {notice && <div className="inline-notice" role="status">{notice}</div>}
    <div className="trust-line" role="status"><span className="trust-item"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" />{nodeConnected ? `${nodeLabel} is verified for this session.` : "No Node path is verified. Nothing has been submitted."}</span><button type="button" className="text-button" onClick={onHelp}>How this works</button></div>
    <section className="continue-section" aria-label="Continue work"><div className="section-heading"><div><h2>Continue work</h2><p>{currentWork ? "One task is available from the approved Node projection." : "The current Node has not supplied a task projection to this desktop."}</p></div>{currentWork && <span className={`home-work-health home-work-health-${currentWork.health}`}>{currentWork.healthLabel}</span>}<button type="button" className="text-button" onClick={onNewQuery}>New query</button></div>{currentWork ? <article className="current-work-card" data-testid="current-task-card"><div className="current-work-card-head"><div><p className="eyebrow">NODE TASK</p><h3>{currentWork.title}</h3><p>{currentWork.requestSummary}</p></div><span className={`home-work-status home-work-status-${currentWork.status}`}>{currentWork.statusLabel}</span></div><dl className="current-work-meta"><div><dt>Current phase</dt><dd>{currentWork.phase}</dd></div><div><dt>Node cursor</dt><dd>{currentWork.lastAppliedSequence}</dd></div><div><dt>Ledger head</dt><dd>{currentWork.ledgerHeadRef}</dd></div><div><dt>Latest record</dt><dd>{currentWork.latestActivity?.label ?? "No activity event in this cursor"}</dd></div></dl>{currentWork.latestActivity && <div className="current-work-latest"><span>Latest Node record</span><strong>{currentWork.latestActivity.summary}</strong><small>{formatTraceTime(currentWork.latestActivity.occurredAt)} / sequence {currentWork.latestActivity.sequence} / ledger {currentWork.latestActivity.ledgerEventRef}</small></div>}<div className="current-work-footer"><p>{currentWork.health === "current" ? "This card reflects the latest accepted Node snapshot." : "This snapshot remains readable, but consequential task actions stay gated until the event stream is current."}</p><div className="current-work-actions"><button type="button" className="text-button" onClick={onDismissCurrent}>Remove from view</button><button type="button" className="secondary-button bordered-button" onClick={onOpenCurrentTask}>Open task</button></div></div></article> : <div className="home-empty-state"><div className="empty-icon" aria-hidden="true"><AppIcon name="tasks" size={17} /></div><p>{nodeConnected ? "No current task in this desktop session" : "Connect an approved Node to view current work"}</p><small>{nodeConnected ? "When the Node returns a task snapshot, its recorded state will appear here." : "AirBench does not reconstruct task history locally."}</small></div>}</section>
    <section className="readiness-card"><div><p className="eyebrow">{nodeConnected ? "NODE READY" : "READY WHEN YOU ARE"}</p><h2>{nodeConnected ? "Ready to receive a task" : "Connect a trusted Node to begin"}</h2><p>{nodeConnected ? `${nodeLabel} will validate task policy, sources, capacity, and qualified capabilities before any work starts.` : "Your organization controls the models, tools, files, and audit record on that Node."}</p></div><button type="button" className="secondary-button bordered-button" data-testid="open-node-settings" onClick={onOpenNode}>{nodeConnected ? "Node settings" : "Connect Node"}</button></section>
  </div>;
}

function IntakeRecoveryGuidance({ recovery }: { recovery: RecoveryGuidance }) {
  return <dl className="intake-recovery-guidance" aria-label="Safe File Intake recovery guidance">
    <div><dt>Preserved</dt><dd>{recovery.preserved}</dd></div>
    <div><dt>Retry</dt><dd>{recovery.retry}</dd></div>
    <div><dt>Next</dt><dd>{recovery.nextAction}</dd></div>
  </dl>;
}

function PlanRecoveryBlock({ guidance }: { guidance: RecoveryGuidance }) {
  return <dl className="plan-recovery-guidance" aria-label="Safe plan recovery guidance">
    <div><dt>Preserved</dt><dd>{guidance.preserved}</dd></div>
    <div><dt>Retry</dt><dd>{guidance.retry}</dd></div>
    <div><dt>Next</dt><dd>{guidance.nextAction}</dd></div>
  </dl>;
}

function PlanReviewCard({ plan, loading, approval, approving, synchronized, currentTaskSequence, taskStatus, onApprove, onCancel }: { plan: TaskPlanReview | null; loading: boolean; approval: NodeCommandResult | null; approving: boolean; synchronized: boolean; currentTaskSequence: number | null; taskStatus: TaskStatus; onApprove: () => void; onCancel: () => Promise<void> }) {
  if (loading) {
    return <section className="plan-review-card" data-testid="plan-review-loading" aria-label="Task plan review"><p className="eyebrow">PLAN REVIEW</p><h2>AirBench is preparing the plan</h2><p className="plan-muted">The Node is validating the work against policy and available hardware. No execution has started.</p></section>;
  }
  if (!plan) return null;
  const modeLabel: Record<string, string> = { parallel: "Parallel team", pipelined: "Pipelined team", serial_virtual_team: "Serial virtual team", not_selected: "Not selected" };
  const stateLabel: Record<string, string> = { not_ready: "Not ready", ready: "Ready for approval", queued: "Queued for hardware", needs_review: "Needs review", blocked: "Blocked", rejected: "Rejected" };
  const canApprove = canApprovePlan(plan, synchronized, Boolean(approval), approving, currentTaskSequence);
  const canCancel = canCancelTask(taskStatus, synchronized, approving);
  const planIsStale = currentTaskSequence !== null && plan.task_sequence !== currentTaskSequence;
  const approvalHint = !synchronized ? "Approval is paused until the task view is current with the Node." : planIsStale ? "This plan is based on an older Node sequence. Refresh the task projection before approving it." : "The Node must return a ready plan requiring operator approval.";
  return <section className="plan-review-card" data-testid="plan-review" aria-label="Task plan review">
    <div className="plan-review-head"><div><p className="eyebrow">PLAN REVIEW</p><h2>{stateLabel[plan.plan_state] ?? plan.plan_state}</h2></div><span className={`intake-badge plan-state-${plan.plan_state}`}>{modeLabel[plan.execution_mode] ?? plan.execution_mode}</span></div>
    <p className="plan-muted">{plan.authority_reason}</p>
    {plan.failure_reason && <div className="plan-warning" role="status"><strong>{plan.failure_code ?? "Plan requires attention"}</strong><span>{plan.failure_reason}</span></div>}
    {!approval && (plan.plan_state !== "ready" || !synchronized) && <PlanRecoveryBlock guidance={planRecoveryGuidance(plan, synchronized, false)} />}
    <div className="plan-meta-grid"><div><span>Team</span><strong>{plan.team_id ?? "Not assigned"}</strong></div><div><span>Concurrency</span><strong>{plan.concurrency_ceiling || "Not selected"}</strong></div><div><span>Hardware</span><strong>{plan.hardware_profile_ref ?? "Admission pending"}</strong></div><div><span>Verification</span><strong>{plan.required_verification ? "Required" : "Missing"}</strong></div></div>
    <div className="plan-reason"><span>Why this mode</span><p>{plan.hardware_reason}</p></div>
    <div className="plan-workers"><span>Capability lanes</span><div>{Object.entries(plan.worker_capabilities).map(([worker, capability]) => <span className="plan-worker" key={worker}>{worker}: {capability}</span>)}</div></div>
    <div className="plan-stages"><span>Stage dependencies</span>{Object.entries(plan.dependency_graph).map(([stage, dependencies]) => <div className="plan-stage" key={stage}><strong>{stage}</strong><small>{dependencies.length ? `After ${dependencies.join(", ")}` : "Can begin first"}</small></div>)}</div>
    <div className={`plan-review-footer${approval ? " plan-review-footer-outcome" : ""}`}><small>Plan {plan.plan_version_hash ?? "pending"} / ledger {plan.ledger_event_ref ?? "pending"} / sequence {plan.task_sequence}</small>{approval ? <CommandOutcomeBlock action="Plan approval" result={approval} /> : <div className="plan-review-actions"><button type="button" className="primary-button" data-testid="approve-plan" onClick={onApprove} disabled={!canApprove} aria-describedby="plan-approval-hint" title={canApprove ? "Approve this Node-validated plan" : approvalHint}>{approving ? "Sending..." : "Approve and run"}</button><button type="button" className="secondary-button bordered-button" data-testid="cancel-task" onClick={() => { void onCancel(); }} disabled={!canCancel} title={canCancel ? "Send a Node-authorized cancel command" : "Cancel is disabled until the Node is current"}>Cancel task</button></div>}{!approval && <span id="plan-approval-hint" className="plan-action-note">{approvalHint}</span>}</div>
  </section>;
}

function CommandOutcomeBlock({ action, result }: { action: "Plan approval" | "Stop request"; result: NodeCommandResult }) {
  const guidance = commandOutcomeGuidance(action, result);
  return <section className={`command-outcome command-outcome-${guidance.tone}`} role={result.outcome === "rejected" ? "alert" : "status"} aria-label={`${action} result`}>
    <div><strong>{guidance.label}</strong><span>{guidance.detail}</span></div>
    <dl>
      <div><dt>Preserved</dt><dd>{guidance.preserved}</dd></div>
      <div><dt>Retry</dt><dd>{guidance.retry}</dd></div>
      <div><dt>Next</dt><dd>{guidance.nextAction}</dd></div>
      <div><dt>Ledger</dt><dd>{result.ledger_event_ref ?? "Not supplied by Node"}</dd></div>
    </dl>
  </section>;
}

function NodeIdentityCard({ connection }: { connection: NodeConnectionView }) {
  return <section className="node-identity-card" aria-label="Node identity">
    <div className="node-identity-head"><AppIcon name="shield" size={17} /><div><strong>Verified Node Identity</strong><span>All fields come from the Node handshake response.</span></div></div>
    <dl className="node-identity-grid">
      <div><dt>Node identity</dt><dd>{connection.nodeIdentity ?? "Not supplied"}</dd></div>
      <div><dt>Protocol version</dt><dd>{connection.protocolVersion ?? "Not supplied"}</dd></div>
      <div><dt>Protocol compatibility</dt><dd>{connection.protocolCompatibilityId ?? "Not supplied"}</dd></div>
      <div><dt>Clearance context</dt><dd>{connection.clearanceContext ?? "Not supplied"}</dd></div>
      <div><dt>Authenticated subject</dt><dd>{connection.authenticatedSubject ?? "Not supplied"}</dd></div>
      <div><dt>Domain-pack ref</dt><dd>{connection.domainPackRef ?? "Not supplied"}</dd></div>
      <div><dt>Ledger event ref</dt><dd>{connection.ledgerEventRef ?? "Not supplied"}</dd></div>
      <div><dt>Sovereignty status</dt><dd>{connection.sovereignty ?? "unknown"}</dd></div>
    </dl>
  </section>;
}

function NodeSettingsView({ profiles, profilesState, profileError, connection, connectingProfileId, onConnect, onReconnect, onReload, onHome, operationalProjection, onOperationalProjection }: { profiles: ApprovedNodeProfileReference[]; profilesState: "idle" | "loading" | "ready" | "failed"; profileError: string | null; connection: NodeConnectionView; connectingProfileId: string | null; onConnect: (profile: ApprovedNodeProfileReference) => void; onReconnect: () => void; onReload: () => void; onHome: () => void; operationalProjection: NodeOperationalProjection; onOperationalProjection: (projection: NodeOperationalProjection) => void }) {
  const connectedProfile = profiles.find((profile) => profile.profileId === connection.profileId);
  return <section className="settings-view"><p className="eyebrow">TRUSTED EXECUTION</p><h1>Node and settings</h1><p className="lead">Choose an organization-approved Node. AirBench does not accept arbitrary model-server addresses or credentials in the desktop app.</p>
    <NodeReadinessPanel connection={connection} profile={connectedProfile ?? null} onProjection={onOperationalProjection} />
    <HardwareCard profile={connectedProfile ?? null} connected={connection.state === "connected"} hardware={operationalProjection.hardware} />
    <ModelRoster profile={connectedProfile ?? null} connected={connection.state === "connected"} qualification={operationalProjection.qualification} />
    {connection.state === "connected" && <NodeIdentityCard connection={connection} />}
    {connection.state === "connected" && <div className="settings-actions"><button type="button" className="secondary-button bordered-button" onClick={onReconnect} disabled={connectingProfileId !== null}>Recheck Node</button><span className="settings-action-note">Recheck preserves the approved profile and creates a fresh trust result.</span></div>}
    {connection.state !== "connected" && <><div className="profile-section"><div className="section-heading"><div><h2>Approved Nodes</h2><p>These profiles were installed by your organization administrator.</p></div><button type="button" className="text-button" onClick={onReload} disabled={profilesState === "loading"}>Reload</button></div>{profilesState === "loading" && <div className="profile-empty">Loading the local approved profile catalog...</div>}{profilesState === "failed" && <div className="profile-empty profile-error" role="alert">{profileError}<button type="button" className="text-button" onClick={onReload}>Try again</button></div>}{profilesState === "ready" && profiles.length === 0 && <div className="profile-empty">No approved Node profile is installed on this workstation. Ask your AirBench administrator to provision one.</div>}{profiles.length > 0 && <div className="profile-list">{profiles.map((profile) => <ProfileCard key={profile.profileId} profile={profile} busy={connectingProfileId === profile.profileId} onConnect={() => onConnect(profile)} />)}</div>}</div></>}
    <div className="settings-note"><strong>What AirBench verifies</strong><p>The native transport checks the approved profile, Node identity, protocol version, clearance context, certificate policy, and authenticated subject before the UI treats the Node as ready. Secrets stay in operating-system credential storage.</p></div><button type="button" className="secondary-button bordered-button" onClick={onHome}>Return home</button></section>;
}

function ProfileCard({ profile, busy, onConnect }: { profile: ApprovedNodeProfileReference; busy: boolean; onConnect: () => void }) {
  return <article className="profile-card"><div><div className="profile-name">{profile.displayName}</div><div className="profile-meta">{profile.transport === "loopback" ? "Local workstation" : "Internal network"} <span aria-hidden="true">•</span> {profile.clearanceContext} clearance</div><div className="profile-trust">Pinned identity: {profile.nodeIdentity}</div></div><button type="button" className="primary-button" onClick={onConnect} disabled={busy}>{busy ? "Checking..." : "Connect"}</button></article>;
}

function TaskWorkspaceView({ projection, syncState, plan, routeTrace, approval, approving, controlResult, controlling, sourcePreview, artifactReview, artifactPreview, artifactPreviewState, artifactPreviewError, artifactDownloadState, artifactDownloadReceipt, onStop, onRefresh, onApprovePlan, onInspectArtifact, onDownloadArtifact, onHome, onOpenNode, onApproveArtifact, onReturnArtifact, isArtifactCommandPending, profile, operatorId }: { projection: TaskProjection; syncState: EventSyncState | null; plan: TaskPlanReview | null; routeTrace: NodeRouteTrace | null; approval: NodeCommandResult | null; approving: boolean; controlResult: NodeCommandResult | null; controlling: boolean; sourcePreview: SafePreview | null; artifactReview: NodeArtifactReview | null; artifactPreview: ArtifactPreview | null; artifactPreviewState: ArtifactPreviewState; artifactPreviewError: string | null; artifactDownloadState: "idle" | "downloading" | "downloaded" | "failed"; artifactDownloadReceipt: DownloadReceipt | null; onStop: () => Promise<void>; onRefresh: () => Promise<void>; onApprovePlan: () => Promise<void>; onInspectArtifact: (artifactId: string) => Promise<void>; onDownloadArtifact: (artifactId: string) => Promise<void>; onHome: () => void; onOpenNode: () => void; onApproveArtifact: (artifactId: string, reason: string) => void; onReturnArtifact: (artifactId: string, reason: string) => void; isArtifactCommandPending: boolean; profile: ApprovedNodeProfileReference | null; operatorId: string | null; }) {
  const syncLabel: Record<string, string> = { idle: "Not synchronized", syncing: "Checking Node", connected: "Connected and current", reconnecting: "Reconnecting", replaying: "Replaying events", blocked: "Blocked by protocol or policy" };
  const statusLabel: Record<string, string> = { accepted: "Accepted", planning: "Planning", running: "Running", needs_review: "Needs review", completed: "Completed", blocked: "Blocked", failed: "Failed", stopped: "Stopped" };
  const syncStatus = syncState?.status ?? "idle";
  const syncRecovery = taskSyncRecovery(syncStatus, projection, syncState?.error ?? null);
  const canStop = maySendConsequentialCommand(projection, syncStatus) && !["completed", "failed", "stopped"].includes(projection.status) && !controlling;
  const trace = buildWorkTrace(projection, plan, routeTrace);
  const [proofSelection, setProofSelection] = useState<ProofSelection | null>(null);
  const [activityLimit, setActivityLimit] = useState(DEFAULT_ACTIVITY_WINDOW);
  useEffect(() => { setProofSelection(null); }, [projection.taskId]);
  useEffect(() => { setActivityLimit(DEFAULT_ACTIVITY_WINDOW); }, [projection.taskId]);
  useEffect(() => {
    setProofSelection((current) => reconcileProofSelection(current, projection.evidence, projection.facts, sourcePreview));
  }, [projection.evidence, projection.facts, sourcePreview]);
  const inspectArtifact = (artifactId: string) => {
    setProofSelection({ kind: "artifact", artifactId });
    void onInspectArtifact(artifactId);
  };
  const selectedArtifactLifecycleState: ArtifactLifecycleState | null = proofSelection?.kind === "artifact"
    ? trace.artifacts.records.find((record) => record.artifactId === proofSelection.artifactId)?.state ?? null
    : null;
  const visibleActivity = activityWindow(trace.activity, activityLimit);
  const visibleWorkers = activityWindow(trace.execution.workers, activityLimit);
  const visibleTools = activityWindow(trace.execution.tools, activityLimit);
  const visibleCoordination = activityWindow(trace.execution.coordination, activityLimit);
  return <section className="workspace-view" data-testid="task-workspace" aria-label="Live task workspace">
    <div className="workspace-head"><div><p className="eyebrow">LIVE TASK</p><h1>{projection.title}</h1><p className="lead">{projection.requestSummary}</p></div><span className={`workspace-status workspace-status-${projection.status}`}>{statusLabel[projection.status] ?? projection.status}</span></div>
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">Task status: {statusLabel[projection.status] ?? projection.status}. Phase: {projection.phase}. Node cursor: {projection.lastAppliedSequence}.</div>
    <div className={`workspace-sync workspace-sync-${syncStatus}`} role="status" aria-live="polite"><span className="status-dot" aria-hidden="true" /><strong>{syncLabel[syncStatus] ?? syncStatus}</strong><span>{syncState?.error?.message ?? (syncStatus === "reconnecting" ? "The Node may continue work while this desktop reconnects." : "Task state comes from the approved Node event stream.")}</span><button type="button" className="text-button" onClick={onRefresh} disabled={syncStatus === "syncing" || syncStatus === "replaying"}>Refresh</button>{syncStatus === "reconnecting" && <button type="button" className="text-button" onClick={onOpenNode}>Reconnect Node</button>}</div>
    <section className={`workspace-sync-recovery workspace-sync-recovery-${syncRecovery.tone}`} aria-label="Task synchronization recovery guidance"><div><strong>{syncRecovery.label}</strong><span>{syncRecovery.detail}</span></div><dl><div><dt>Preserved</dt><dd>{syncRecovery.preserved}</dd></div><div><dt>Retry</dt><dd>{syncRecovery.retry}</dd></div><div><dt>Next</dt><dd>{syncRecovery.nextAction}</dd></div></dl></section>
    <div className="workspace-actions"><button type="button" className="secondary-button bordered-button" onClick={onHome}>Back to Home</button><button type="button" className="secondary-button" onClick={onStop} disabled={!canStop} title={canStop ? "Send a Node-authorized stop command" : "Stopping is disabled until the Node is current"}>{controlling ? "Stopping..." : "Stop task"}</button><span className="workspace-command-note">Pause, resume, and question responses appear only when the Node supplies their typed command contracts.</span></div>
    {trace.review.questions.length > 0 && <OperatorQuestionCard questions={trace.review.questions} taskStatus={projection.status} phase={projection.phase} synchronized={syncStatus === "connected" && projection.health === "current"} ledgerEventRef={projection.ledgerHeadRef} />}
    <section className="workspace-now" aria-label="Current Node state"><div><p className="eyebrow">CURRENT NODE STATE</p><h2>{statusLabel[projection.status] ?? projection.status} in {projection.phase}</h2><p>The task state and phase come from the latest approved Node snapshot.</p></div><div className="workspace-now-record">{trace.latestActivity ? <><span>Latest recorded activity</span><strong>{trace.latestActivity.label}</strong><p>{trace.latestActivity.summary}</p><small>{formatTraceTime(trace.latestActivity.occurredAt)} / ledger {trace.latestActivity.ledgerEventRef}</small></> : <><span>Latest recorded activity</span><strong>No activity event yet</strong><p>The Node has supplied the task snapshot but no newer event in this cursor.</p></>}</div></section>
    <section className="worktrace-board" aria-label="Node-backed work trace"><div className="worktrace-board-head"><div><p className="eyebrow">WORK TRACE</p><h2>What AirBench has recorded</h2><p>Each stage is derived from a Node snapshot, plan, or ordered event. Private model reasoning is not shown.</p></div><span className="workspace-count">{trace.activity.length} event{trace.activity.length === 1 ? "" : "s"}</span></div><ol className="worktrace-stage-list">{trace.stages.map((stage) => <TraceStageCard key={stage.id} stage={stage} />)}</ol></section>
    {profile && operatorId && <AutonomyPanel profile={profile} taskId={projection.taskId} operatorId={operatorId} taskStatus={projection.status} />}
    <div className="workspace-proof-layout">
    <div className="worktrace-detail-grid">
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Workers and tools</h2><p>Recorded execution activity, not inferred progress.</p></div><span>{trace.execution.workers.length + trace.execution.tools.length + trace.execution.coordination.length} records</span></div>{trace.team.state === "planned" && <TeamPlanSummary plan={trace.team} />}<TraceActivityGroup label="Team coordination" items={visibleCoordination.visible} empty="No team, barrier, handoff, or resource event has been supplied by the Node yet." /><TraceActivityGroup label="Workers" items={visibleWorkers.visible} empty="No worker event has been supplied by the Node yet." /><TraceActivityGroup label="Tools and retrieval" items={visibleTools.visible} empty="No tool or retrieval event has been supplied by the current protocol." /></section>
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Evidence and verification</h2><p>Source metadata remains attached to Node evidence.</p></div><span>{trace.evidence.records.length} evidence</span></div>{projection.evidence.length === 0 ? <div className="worktrace-empty">No evidence record has been supplied by the Node yet.</div> : <ul className="worktrace-evidence-list">{projection.evidence.map((item) => <li key={item.evidenceId}><button className="proof-record-button" type="button" onClick={() => setProofSelection({ kind: "evidence", evidence: item })}><strong>{item.source.sourceDocumentId}</strong><span>{formatProvenanceLocation(item.source.location)} / {item.source.sourceVersion} / {Math.round(item.confidence * 100)}% confidence</span><small>{item.clearance} clearance / {item.taint} data / hash {item.contentHash} / ledger {item.source.ledgerEventRef}</small></button></li>)}</ul>}{projection.facts.length > 0 && <div className="worktrace-facts"><span>Findings</span><ul>{projection.facts.map((fact) => <li key={fact.factId}><button className="proof-record-button" type="button" onClick={() => setProofSelection({ kind: "fact", fact })}><strong>{fact.factId}</strong><span>{formatFactValue(fact.value, fact.unit)} / {formatProvenanceLocation(fact.source.location)}</span><small>{fact.source.sourceDocumentId} / {fact.source.sourceVersion} / {fact.clearance} clearance / {fact.taint} data / ledger {fact.source.ledgerEventRef}</small></button></li>)}</ul></div>}{sourcePreview && <button className="proof-input-preview-button" type="button" onClick={() => setProofSelection({ kind: "source_preview", preview: sourcePreview })}><AppIcon name="document" size={15} /> Inspect query-upload preview</button>}{trace.verification.latest ? <div className={`worktrace-verification tone-${trace.verification.latest.tone}`}><strong>{trace.verification.latest.label}</strong><p>{trace.verification.latest.summary}</p><small>Ledger {trace.verification.latest.ledgerEventRef}</small></div> : <div className="worktrace-empty">No verification result has been supplied by the Node yet.</div>}</section>
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Waiting for you</h2><p>Only Node-reported questions appear here.</p></div><span>{trace.review.questions.length} waiting</span></div>{trace.review.questions.length === 0 ? <div className="worktrace-empty">The Node has not reported a question requiring your response.</div> : <ul className="worktrace-question-list">{trace.review.questions.map((question, index) => <li key={`${question}-${index}`}><AppIcon name="review" size={16} /><span>{question}</span></li>)}</ul>}<p className="worktrace-contract-note">A response control will appear only after the Node provides a sequence-aware answer command and ledger transition.</p></section>
      <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Artifacts</h2><p>References returned by the Node, not locally generated files.</p></div><span>{trace.artifacts.records.length} records</span></div>{trace.artifacts.records.length === 0 ? <div className="worktrace-empty">No artifact reference has been supplied by the Node yet.</div> : <ul className="worktrace-artifact-list">{trace.artifacts.records.map((artifact) => <li key={artifact.artifactId}><button className="proof-record-button" type="button" onClick={() => { if (artifact.state !== "superseded") inspectArtifact(artifact.artifactId); }} disabled={artifact.state === "superseded"} aria-label={`${artifact.artifactId}, ${artifact.state === "superseded" ? "superseded" : artifact.state === "ready" ? "ready" : "reference only"}`}><AppIcon name="document" size={16} /><span className="artifact-record-name">{artifact.artifactId}</span><span className={`artifact-record-state artifact-record-state-${artifact.state}`}>{artifact.state === "reference_only" ? "Reference only" : artifact.state === "superseded" ? "Superseded" : "Ready"}</span><small>{artifact.latestEvent ? `Node recorded ${artifact.latestEvent.label} at sequence ${artifact.latestEvent.sequence}.` : "No lifecycle event is present in this task cursor."}{artifact.state === "superseded" ? " Preview and download are unavailable for superseded records." : " Inspect Node preview"}</small></button></li>)}</ul>}<p className="worktrace-contract-note">Status is derived from ordered Node events. Approval, verification, version comparison, and clarification remain unavailable until the Node supplies those contracts.</p></section>
    </div>
    <ProofInspectorPanel selection={proofSelection} artifactReview={artifactReview} artifactPreview={artifactPreview} artifactPreviewState={artifactPreviewState} artifactPreviewError={artifactPreviewError} artifactLifecycleState={selectedArtifactLifecycleState} downloadState={artifactDownloadState} downloadReceipt={artifactDownloadReceipt} onDownloadArtifact={(artifactId: string) => { void onDownloadArtifact(artifactId); }} onApproveArtifact={onApproveArtifact} onReturnArtifact={onReturnArtifact} isArtifactCommandPending={isArtifactCommandPending} />
    </div>
    {plan && <div>
      <PlanReviewCard plan={plan} loading={false} approval={approval} approving={approving} synchronized={maySendConsequentialCommand(projection, syncStatus)} currentTaskSequence={projection.lastAppliedSequence} taskStatus={projection.status} onApprove={onApprovePlan} onCancel={onStop} />
      {profile && operatorId && <ConsistencyPanel profile={profile} taskId={projection.taskId} operatorId={operatorId} />}
    </div>}
    {controlResult && <CommandOutcomeBlock action="Stop request" result={controlResult} />}
    <section className="workspace-activity"><div className="section-heading"><div><h2>Activity</h2><p>Chronological Node records. Model reasoning traces are not exposed.</p></div><span className="workspace-count">{trace.activity.length} events</span></div>{visibleActivity.hiddenCount > 0 && <div className="workspace-activity-window" role="status"><span>Showing the latest {visibleActivity.visible.length} of {visibleActivity.totalCount} Node records. Older records remain on the Node and are not discarded.</span><button type="button" className="text-button" onClick={() => setActivityLimit((current) => current + DEFAULT_ACTIVITY_WINDOW)}>Show older recorded activity</button></div>}{trace.activity.length === 0 ? <div className="workspace-empty">The Node has not returned a new activity event yet.</div> : <ol className="activity-list">{visibleActivity.visible.map((event) => <TraceActivityRow key={`${event.eventId}-${event.sequence}`} item={event} />)}</ol>}</section>
    {projection.diagnostics.length > 0 && <section className="workspace-warning" role="alert"><strong>Task view needs attention</strong>{projection.diagnostics.map((diagnostic) => <span key={`${diagnostic.code}-${diagnostic.sequence}`}>{diagnostic.code}: {diagnostic.detail}</span>)}</section>}
    <details className="workspace-technical"><summary>Technical trace</summary><div className="technical-trace-content"><section><h2>Routing and hardware</h2><p>{trace.routing.state === "not_supplied" ? "No Node routing record is available. The desktop cannot infer a selected target, fallback, or policy reason." : trace.routing.state === "route_context" ? "The approved Node supplied the route trace below. Targets, fallback, qualification, and policy metadata are recorded facts, not desktop guesses." : "The Node supplied plan-level capability and hardware context. Exact route decisions will appear after the Node provides its route trace."}</p><dl className="technical-trace-grid"><div><dt>Execution mode</dt><dd>{trace.routing.executionMode ?? "Not supplied"}</dd></div><div><dt>Hardware profile</dt><dd>{trace.routing.hardwareProfileRef ?? "Not supplied"}</dd></div><div><dt>Hardware reason</dt><dd>{trace.routing.hardwareReason ?? "Not supplied"}</dd></div><div><dt>Selected target</dt><dd>{trace.routing.selectedTarget ?? "Not supplied"}</dd></div><div><dt>Fallback record</dt><dd>{trace.routing.fallbackReason ?? "Not supplied"}</dd></div><div><dt>Routing policy reason</dt><dd>{trace.routing.policyReason ?? "Not supplied"}</dd></div><div><dt>Plan ledger</dt><dd>{trace.routing.planLedgerEventRef ?? "Not supplied"}</dd></div><div><dt>Plan hash</dt><dd>{trace.routing.planVersionHash ?? "Not supplied"}</dd></div><div><dt>Policy hash</dt><dd>{trace.routing.policyVersionHash ?? "Not supplied"}</dd></div></dl><div className="technical-capability-lanes"><span>Capability lanes</span>{Object.keys(trace.routing.capabilityLanes).length === 0 ? <small>None supplied by the Node.</small> : Object.entries(trace.routing.capabilityLanes).map(([worker, capability]) => <span key={worker}>{worker}: {capability}</span>)}</div>{trace.routing.routeEntries.length > 0 && <><h2>Routing events</h2><ol className="technical-event-list">{trace.routing.routeEntries.map((entry) => <li key={`route-${entry.sequence}-${entry.eventType}`}><strong>{entry.eventType}</strong><dl><div><dt>Sequence</dt><dd>{entry.sequence}</dd></div><div><dt>Target</dt><dd>{entry.selectedTarget ?? "Not supplied"}</dd></div><div><dt>Fallback</dt><dd>{entry.fallbackTarget ?? "Not supplied"}</dd></div><div><dt>Decision source</dt><dd>{entry.decisionSource ?? "Not supplied"}</dd></div><div><dt>Qualification</dt><dd>{entry.qualificationCertificate ?? "Not supplied"}</dd></div><div><dt>Ledger</dt><dd>{entry.ledgerEventRef}</dd></div></dl><small className="technical-route-reason">{entry.reason ?? entry.ruleOrThreshold ?? "No additional route reason supplied."}</small></li>)}</ol></>}</section><section><h2>Event metadata</h2>{trace.activity.length === 0 ? <p>No ordered event metadata is available in this cursor.</p> : <ol className="technical-event-list">{trace.activity.map((event) => <li key={`technical-${event.eventId}`}><strong>{event.label}</strong><dl><div><dt>Event</dt><dd>{event.eventType}</dd></div><div><dt>Sequence</dt><dd>{event.sequence}</dd></div><div><dt>Node time</dt><dd>{event.occurredAt}</dd></div><div><dt>Actor</dt><dd>{event.actor}</dd></div><div><dt>Clearance</dt><dd>{event.clearance}</dd></div><div><dt>Payload hash</dt><dd>{event.payloadHash}</dd></div><div><dt>Ledger</dt><dd>{event.ledgerEventRef}</dd></div></dl></li>)}</ol>}</section></div></details>
  </section>;
}

function TraceStageCard({ stage }: { stage: WorkTraceStage }) {
  return <li className={`worktrace-stage state-${stage.state}`}><span className="worktrace-stage-icon"><AppIcon name={traceStageIcon(stage.id)} size={16} /></span><div><strong>{stage.label}</strong><p>{stage.summary}</p></div><span className="worktrace-stage-status">{traceStateLabel(stage.state)}</span><small>{stage.events.length} record{stage.events.length === 1 ? "" : "s"}</small></li>;
}

function TraceActivityGroup({ label, items, empty }: { label: string; items: WorkTraceActivity[]; empty: string }) {
  return <div className="worktrace-activity-group"><span>{label}</span>{items.length === 0 ? <p>{empty}</p> : <ol>{items.map((item) => <li key={`${label}-${item.eventId}`} className={`tone-${item.tone}`}><strong>{item.label}</strong><small>{item.summary}</small>{item.context.length > 0 && <ul className="worktrace-activity-context">{item.context.map((field) => <li key={`${field.label}-${field.value}`}><span>{field.label}</span><strong>{field.value}</strong></li>)}</ul>}<em>{formatTraceTime(item.occurredAt)} / ledger {item.ledgerEventRef}</em></li>)}</ol>}</div>;
}

function TeamPlanSummary({ plan }: { plan: WorkTrace["team"] }) {
  return <section className="worktrace-team-plan" aria-label="Node execution plan">
    <div className="worktrace-team-plan-head"><div><span className="worktrace-team-plan-label">NODE EXECUTION PLAN</span><strong>{plan.executionModeLabel}</strong><p>{plan.executionModeDetail}</p></div><span className="worktrace-team-plan-ceiling">{plan.concurrencyCeiling} lane{plan.concurrencyCeiling === 1 ? "" : "s"}</span></div>
    {plan.teamId && <small className="worktrace-team-plan-meta">Team {plan.teamId}{plan.planLedgerEventRef ? ` / ledger ${plan.planLedgerEventRef}` : ""}</small>}
    <div className="worktrace-team-plan-grid">
      <div><span>Planned assignments</span>{plan.assignments.length === 0 ? <p>No assignment list supplied.</p> : <ol>{plan.assignments.map((assignment) => <li key={assignment.assignmentId}><strong>{assignment.assignmentId}</strong><small>{assignment.dependencies.length > 0 ? `waits for ${assignment.dependencies.join(", ")}` : "no declared predecessor"}</small></li>)}</ol>}</div>
      <div><span>Capability lanes</span>{plan.capabilityLanes.length === 0 ? <p>No capability lanes supplied.</p> : <ul>{plan.capabilityLanes.map((lane) => <li key={`${lane.role}-${lane.capability}`}><strong>{lane.role}</strong><small>{lane.capability}</small></li>)}</ul>}</div>
    </div>
    <p className="worktrace-team-plan-note">This is the Node-issued plan. Runtime status appears only in the recorded coordination and worker events below.</p>
  </section>;
}

function TraceActivityRow({ item }: { item: WorkTraceActivity }) {
  return <li className={`activity-row tone-${item.tone}`}><span className="activity-sequence">{item.sequence}</span><div><strong>{item.label}</strong><p>{item.summary}</p>{item.context.length > 0 && <ul className="worktrace-activity-context">{item.context.map((field) => <li key={`${field.label}-${field.value}`}><span>{field.label}</span><strong>{field.value}</strong></li>)}</ul>}<small>{formatTraceTime(item.occurredAt)} / {item.eventType} / ledger {item.ledgerEventRef}</small></div></li>;
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

function RecordGatewayView({ destination, nodeConnected, currentTask, onHome, onOpenNode, onOpenCurrentTask, taskHistory, onOpenTask, onRemoveTask, onNewTask }: { destination: RecordGatewayDestination; nodeConnected: boolean; currentTask: TaskProjection | null; onHome: () => void; onOpenNode: () => void; onOpenCurrentTask: () => void; taskHistory: HomeWorkSummary[]; onOpenTask: (taskId: string) => void; onRemoveTask: (taskId: string) => void; onNewTask: () => void }) {
  const gateway = buildRecordGateway(destination, nodeConnected, currentTask);
  const destinationLabel: Record<RecordGatewayDestination, string> = { review: "Review", artifacts: "Artifacts", history: "History", audit: "Audit ledger" };
  if (destination === "history") {
    return <TaskHistoryView tasks={taskHistory} onOpen={onOpenTask} onRemove={onRemoveTask} onNewTask={onNewTask} />;
  }
  return <section className="record-gateway" data-testid={`record-gateway-${destination}`} aria-label={`${destinationLabel[destination]} record availability`}><header><p className="eyebrow">{gateway.eyebrow}</p><h1>{gateway.title}</h1><p className="lead">{gateway.description}</p></header><section className={`record-gateway-state record-gateway-state-${gateway.state}`} role="status"><span className="record-gateway-icon" aria-hidden="true"><AppIcon name={gateway.state === "node_unavailable" ? "node" : "archive"} size={19} /></span><div><strong>{gateway.stateLabel}</strong><p>{gateway.stateDescription}</p></div></section><section className="record-gateway-requirement"><p className="eyebrow">WHAT IS NEEDED</p><p>{gateway.requiredProjection}</p></section>{gateway.currentTask && <section className="record-gateway-context" aria-label="Current task context"><div><p className="eyebrow">CURRENT TASK CONTEXT</p><h2>{gateway.currentTask.title}</h2><p>This is an existing Node task projection, not a substitute for the requested record query.</p></div><dl><div><dt>Task ID</dt><dd>{gateway.currentTask.taskId}</dd></div><div><dt>State</dt><dd>{gateway.currentTask.status} / {gateway.currentTask.phase}</dd></div><div><dt>Ledger head</dt><dd>{gateway.currentTask.ledgerHeadRef}</dd></div></dl></section>}<footer className="record-gateway-actions">{gateway.state === "node_unavailable" && <button type="button" className="primary-button" onClick={onOpenNode}>Connect approved Node</button>}{gateway.currentTask && <button type="button" className="secondary-button bordered-button" onClick={onOpenCurrentTask}>Open current task</button>}<button type="button" className="text-button" onClick={onHome}>Return home</button></footer></section>;
}

function ConnectionHelp({ onClose, onOpenNode }: { onClose: () => void; onOpenNode: () => void }) {
  const dialogRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    dialogRef.current?.querySelector<HTMLElement>(".modal-close")?.focus();
  }, []);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("button:not([disabled])") ?? []);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first && last) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return <div className="modal-backdrop" role="presentation"><section ref={dialogRef} className="modal-card" role="dialog" aria-modal="true" aria-labelledby="connection-help-title" aria-describedby="connection-help-copy" onKeyDown={handleKeyDown}><button type="button" className="modal-close" aria-label="Close" onClick={onClose}>X</button><p className="eyebrow">TRUSTED EXECUTION</p><h2 id="connection-help-title">AirBench works on an approved Node</h2><p id="connection-help-copy">AirBench accepts work only after you select a trusted Node. The Node owns the files, task state, model calls, tools, and audit record for that work.</p><div className="modal-note"><span className="status-dot" aria-hidden="true" /><span><strong>No Node is connected</strong><small>Nothing has been submitted or sent anywhere.</small></span></div><div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Close</button><button type="button" className="primary-button" onClick={onOpenNode}>Open Node settings</button></div></section></div>;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default App;
