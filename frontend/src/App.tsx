import { useEffect, useMemo, useState } from "react";
import { invoke } from "@airbench/tauri-invoke";
import type { AirBenchPresentationState, Screen } from "./contracts";
import { initialPresentationState } from "./contracts";
import { NodeConnectionController, type NodeConnectionView } from "./nodeConnectionController";
import type { ApprovedNodeProfileReference } from "./nodeConnection";
import { listApprovedNodeProfiles } from "./profileBridge";
import { downloadArtifact, fetchArtifactPreview, fetchSafePreview, uploadSelectedQueryFile, type ArtifactPreview, type DownloadReceipt, type IntakeManifest, type SafePreview } from "./intakeBridge";

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
    clearanceContext: null, authenticatedSubject: null, sovereignty: "unknown", ledgerEventRef: null, failure: null,
  });
  const [profiles, setProfiles] = useState<ApprovedNodeProfileReference[]>([]);
  const [profilesState, setProfilesState] = useState<"idle" | "loading" | "ready" | "failed">("idle");
  const [profileError, setProfileError] = useState<string | null>(null);
  const [connectingProfileId, setConnectingProfileId] = useState<string | null>(null);
  const [showConnectionHelp, setShowConnectionHelp] = useState(false);
  const [taskText, setTaskText] = useState("");
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [intakeState, setIntakeState] = useState<"idle" | "uploading" | "ready" | "failed">("idle");
  const [intakeManifest, setIntakeManifest] = useState<IntakeManifest | null>(null);
  const [safePreview, setSafePreview] = useState<SafePreview | null>(null);
  const [artifactPreview, setArtifactPreview] = useState<ArtifactPreview | null>(null);
  const [downloadState, setDownloadState] = useState<"idle" | "downloading" | "downloaded" | "failed">("idle");
  const [downloadReceipt, setDownloadReceipt] = useState<DownloadReceipt | null>(null);
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
      const preview = await fetchSafePreview(profile, manifest.preview_ref);
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

  const nodeConnected = connection.state === "connected" && controller.canSendConsequential();
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
          {state.screen === "home" && <HomeView taskText={taskText} setTaskText={setTaskText} selectedFile={selectedFile} intakeState={intakeState} intakeManifest={intakeManifest} safePreview={safePreview} artifactPreview={artifactPreview} downloadState={downloadState} downloadReceipt={downloadReceipt} notice={notice} canStart={false} onAttach={attachFile} onUpload={uploadSelectedFile} onDownload={downloadApprovedArtifact} onRemoveFile={() => { setSelectedFile(null); setIntakeState("idle"); setIntakeManifest(null); setSafePreview(null); setArtifactPreview(null); setDownloadState("idle"); setDownloadReceipt(null); }} onHelp={() => setShowConnectionHelp(true)} onOpenNode={() => selectScreen("node")} />}
          {state.screen === "node" && <NodeSettingsView profiles={profiles} profilesState={profilesState} profileError={profileError} connection={connection} connectingProfileId={connectingProfileId} onConnect={connectProfile} onReconnect={reconnect} onReload={() => { setProfilesState("idle"); }} onHome={() => selectScreen("home")} />}
          {state.screen !== "home" && state.screen !== "node" && <RecordView screen={screenTitle} onHome={() => selectScreen("home")} />}
        </div>
      </main>
      {showConnectionHelp && <ConnectionHelp onClose={() => setShowConnectionHelp(false)} onOpenNode={() => { setShowConnectionHelp(false); selectScreen("node"); }} />}
    </div>
  );
}

function NavGroup({ title, items, active, onSelect }: { title: string; items: Array<{ id: Screen; label: string; icon: string }>; active: Screen; onSelect: (screen: Screen) => void }) {
  return <div className="nav-group"><div className="nav-group-title">{title}</div>{items.map((item) => <button key={item.id} className={`nav-item ${active === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}><span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>{item.id === "review" && <span className="nav-count">0</span>}</button>)}</div>;
}

function HomeView({ taskText, setTaskText, selectedFile, intakeState, intakeManifest, safePreview, artifactPreview, downloadState, downloadReceipt, notice, canStart, onAttach, onUpload, onDownload, onRemoveFile, onHelp, onOpenNode }: { taskText: string; setTaskText: (value: string) => void; selectedFile: SelectedFile | null; intakeState: "idle" | "uploading" | "ready" | "failed"; intakeManifest: IntakeManifest | null; safePreview: SafePreview | null; artifactPreview: ArtifactPreview | null; downloadState: "idle" | "downloading" | "downloaded" | "failed"; downloadReceipt: DownloadReceipt | null; notice: string | null; canStart: boolean; onAttach: () => void; onUpload: () => void; onDownload: () => void; onRemoveFile: () => void; onHelp: () => void; onOpenNode: () => void }) {
  return <div className="home-view">
    <section className="welcome-block"><p className="eyebrow">PRIVATE BY DESIGN</p><h1>What should AirBench complete?</h1><p className="lead">Describe the outcome. Add files if they are part of the work.</p></section>
    <section className="composer-card" data-testid="task-composer" aria-label="New task composer">
      <textarea value={taskText} onChange={(event) => setTaskText(event.target.value)} placeholder="For example: Review the scanned inspection report and draft an approval note with the key findings and required actions." rows={4} />
      {selectedFile && <div className="selected-file"><span className="file-badge">FILE</span><span><strong>{selectedFile.file_name}</strong><small>{formatBytes(selectedFile.byte_size)} / {intakeState === "ready" ? "accepted by File Intake" : "ready for File Intake"}</small></span><div className="selected-file-actions">{intakeState !== "ready" && <button className="secondary-button compact-button" onClick={onUpload} disabled={intakeState === "uploading"}>{intakeState === "uploading" ? "Sending..." : "Send to Node"}</button>}<button className="remove-file" onClick={onRemoveFile} aria-label="Remove selected file">Remove</button></div></div>}
      <div className="composer-footer"><div className="composer-tools"><button className="secondary-button" data-testid="attach-files" onClick={onAttach}><span aria-hidden="true">+</span> Attach files</button><button className="secondary-button" disabled>Choose project</button></div><button className="primary-button" data-testid="start-task" disabled={!canStart} title={canStart ? "Start task" : "Connect an approved Node and wait for task intake to be available"}>Start task <kbd>Enter</kbd></button></div>
    </section>
    {intakeManifest && safePreview && <section className="intake-result" data-testid="intake-result" aria-label="File Intake result"><div className="intake-result-head"><div><p className="eyebrow">FILE INTAKE COMPLETE</p><h2>{intakeManifest.file_name}</h2></div><span className="intake-badge">{intakeManifest.ocr_status} OCR</span></div><div className="intake-meta-grid"><div><span>Source hash</span><strong>{intakeManifest.source_hash}</strong></div><div><span>Pages</span><strong>{intakeManifest.page_count}</strong></div><div><span>Clearance</span><strong>{intakeManifest.clearance}</strong></div><div><span>Taint</span><strong>{intakeManifest.taint}</strong></div></div><div className="safe-preview"><div className="safe-preview-label">Node-generated safe preview <span>Page region: {safePreview.source_region}</span></div><p>{safePreview.text}</p><small>Confidence {Math.round(safePreview.confidence * 100)}% / ledger {safePreview.ledger_event_ref}</small></div></section>}
    {artifactPreview && <section className="artifact-preview" data-testid="artifact-preview" aria-label="Artifact preview"><div className="intake-result-head"><div><p className="eyebrow">NODE ARTIFACT PREVIEW</p><h2>{artifactPreview.title}</h2></div><span className="intake-badge">{artifactPreview.preview_kind}</span></div><div className="artifact-preview-meta"><span>{artifactPreview.clearance} clearance</span><span>{artifactPreview.taint} data</span><span>Ledger {artifactPreview.ledger_event_ref}</span></div><div className="artifact-blocks">{artifactPreview.blocks.map((block, index) => <div className="artifact-block" key={`${block.kind}-${index}`}><span className="artifact-block-kind">{block.kind}</span><p>{block.text}</p></div>)}</div><div className="artifact-actions"><button className="primary-button" data-testid="download-artifact" onClick={onDownload} disabled={downloadState === "downloading"}>{downloadState === "downloading" ? "Verifying..." : downloadState === "downloaded" ? "Download again" : "Download artifact"}</button>{downloadReceipt && <small data-testid="download-receipt">Saved {downloadReceipt.byte_size} bytes / {downloadReceipt.content_hash} / ledger {downloadReceipt.ledger_event_ref}</small>}</div></section>}
    {notice && <div className="inline-notice" role="status">{notice}</div>}
    <div className="trust-line" role="status"><span className="trust-item"><span className="trust-check" aria-hidden="true">OK</span> Files stay on your node</span><span className="trust-item"><span className="trust-check" aria-hidden="true">OK</span> External network denied</span><button className="text-button" onClick={onHelp}>How this works</button></div>
    <section className="continue-section"><div className="section-heading"><div><h2>Continue work</h2><p>Your recent tasks will appear here.</p></div><button className="text-button" disabled>View history <span aria-hidden="true">-&gt;</span></button></div><div className="empty-state"><div className="empty-icon" aria-hidden="true">T</div><p>No tasks yet</p><small>When you start work, you can return to it here.</small></div></section>
    <section className="readiness-card"><div><p className="eyebrow">READY WHEN YOU ARE</p><h2>Connect a trusted Node to begin</h2><p>Your organization controls the models, tools, files, and audit record on that Node.</p></div><button className="secondary-button bordered-button" data-testid="open-node-settings" onClick={onOpenNode}>Open Node settings</button></section>
  </div>;
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
