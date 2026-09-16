import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { AppIcon, type AppIconName } from "../components/AppIcon";
import type { AirBenchPresentationState, Screen } from "../contracts";
import { initialPresentationState } from "../contracts";
import { NodeConnectionController, type NodeConnectionView } from "../platform/node/nodeConnectionController";
import type { ApprovedNodeProfileReference } from "../platform/node/nodeConnection";
import { listApprovedNodeProfiles } from "../platform/node/profileBridge";
import { loadPresentationPreferences, savePresentationPreferences, type PresentationPreferences } from "../features/shell/presentationPreferences";
import { buildShellCommands, shellShortcut, type ShellCommandId } from "../features/shell/commandPalette";
import { WorkspaceCommandDialog } from "../components/WorkspaceCommandDialog";
import { NodeReadinessPanel } from "../components/NodeReadinessPanel";
import { HardwareCard } from "../components/HardwareCard";
import { ModelRoster } from "../components/ModelRoster";
import { clearNodeOperationalProjection, fetchNodeOperationalProjection, type NodeOperationalProjection } from "../platform/node/nodeOperationalProjection";
import { KnowledgeView } from "../features/knowledge/KnowledgeView";
import { HomeView } from "../features/home/HomeView";
import { ReviewView } from "../features/review/ReviewView";
import { ChatView } from "../features/chat/ChatView";
import { SandboxView } from "../features/sandbox/SandboxView";
import { PidView } from "../features/pid/PidView";

const primaryNav: Array<{ id: Screen; label: string; icon: AppIconName }> = [
  { id: "home", label: "Home", icon: "home" },
  { id: "pid", label: "P&ID", icon: "route" },
  { id: "chat", label: "Chat", icon: "chat" },
  { id: "sandbox", label: "Sandbox", icon: "cpu" },
];

const libraryNav: Array<{ id: Screen; label: string; icon: AppIconName }> = [
  { id: "knowledge", label: "Knowledge", icon: "search" },
  { id: "review", label: "Review", icon: "review" },
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
  const [nodeOperationalProjection, setNodeOperationalProjection] = useState<NodeOperationalProjection>({ hardware: null, modelServing: null, qualification: null });
  const outcomeInputRef = useRef<HTMLTextAreaElement | null>(null);
  const commandMenuReturnFocusRef = useRef<HTMLElement | null>(null);
  const commandMenuTriggerRef = useRef<HTMLButtonElement | null>(null);
  const connectionHelpReturnFocusRef = useRef<HTMLElement | null>(null);

  const controller = useMemo(() => new NodeConnectionController(), []);
  const nodeConnected = connection.state === "connected" && controller.canSendConsequential();
  const connectedProfile = useMemo(() => profiles.find((profile) => profile.profileId === connection.profileId) ?? null, [profiles, connection.profileId]);
  const nodeLabel = connectedProfile?.displayName ?? state.node.displayName;
  const nodeDetail = nodeConnected ? "Verified for this session" : "Not connected";
  const sovereigntyLabel = nodeConnected ? "Verified" : "Unverified";
  const shellCommands = useMemo(() => buildShellCommands(false), []);

  const screenTitle = useMemo(() => {
    const titles: Record<Screen, string> = { home: "Home", pid: "P&ID", chat: "Chat", sandbox: "Sandbox", knowledge: "Knowledge", review: "Review", node: "Node and settings" };
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

  useEffect(() => {
    let active = true;
    if (connection.state !== "connected" || !connectedProfile) {
      setNodeOperationalProjection({ hardware: null, modelServing: null, qualification: null });
      return;
    }
    fetchNodeOperationalProjection(connectedProfile).then((projection) => {
      if (active) setNodeOperationalProjection(projection);
    });
    return () => { active = false; };
  }, [connection.state, connectedProfile]);

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
    clearNodeOperationalProjection(profile.profileId);
    setNodeOperationalProjection({ hardware: null, modelServing: null, qualification: null });
    applyConnection(next);
    setConnectingProfileId(null);
  };

  const reconnect = async () => {
    setConnectingProfileId(connection.profileId);
    const next = await controller.reconnect();
    if (connection.profileId) clearNodeOperationalProjection(connection.profileId);
    setNodeOperationalProjection({ hardware: null, modelServing: null, qualification: null });
    applyConnection(next);
    setConnectingProfileId(null);
  };

  const runShellCommand = (commandId: ShellCommandId) => {
    closeCommandPalette();
    if (commandId === "new_task" || commandId === "current_task") {
      openNewTask();
      return;
    }
    if (commandId === "node_settings") {
      selectScreen("node");
      return;
    }
    if (commandId === "display_preferences") {
      setShowAppearanceMenu(true);
    }
  };

  return (
    <div className="app-shell" data-theme={presentation.theme} data-density={presentation.density} data-contrast={presentation.highContrast ? "high" : "standard"}>
      <aside className="sidebar" aria-label="AirBench navigation">
        <div className="brand-lockup"><div className="brand-mark"><AppIcon name="airbench" size={19} /></div><div><div className="brand-name">AirBench</div><div className="brand-subtitle">Sovereign task command</div></div></div>
        <button type="button" className="new-task-button" onClick={openNewTask}><AppIcon name="plus" size={17} /><span>New query</span><kbd>Ctrl N</kbd></button>
        <nav className="nav-groups"><NavGroup title="Work" items={primaryNav} active={state.screen} onSelect={selectScreen} /><NavGroup title="Library" items={libraryNav} active={state.screen} onSelect={selectScreen} /></nav>
        <div className="sidebar-spacer" />
        <button type="button" className="node-chip" data-testid="node-chip" onClick={() => selectScreen("node")} aria-label="Open Node and settings"><span className={`status-dot ${nodeConnected ? "status-dot-connected" : ""}`} aria-hidden="true" /><span className="node-chip-copy"><strong>{nodeLabel}</strong><small>{nodeDetail}</small></span><AppIcon name="chevron-down" size={15} /></button>
        <div className="user-row"><div className="avatar">RG</div><div><strong>Local operator</strong><small>{connection.clearanceContext ? `${connection.clearanceContext} clearance` : "Local session"}</small></div></div>
        <small className="build-info" data-testid="app-version">AirBench {__AIRBENCH_VERSION__}</small>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>AirBench</span><span className="breadcrumb-slash">/</span><strong>{screenTitle}</strong></div>
          <div className="topbar-actions">
            <button ref={commandMenuTriggerRef} className="command-menu-button" type="button" onClick={(event) => openCommandPalette(event.currentTarget)} aria-haspopup="dialog" aria-expanded={showCommandPalette} aria-controls="workspace-command-palette"><AppIcon name="search" size={16} /><span>Command</span><kbd>Ctrl K</kbd></button>
            <button type="button" className={`sovereignty-status ${nodeConnected ? "is-verified" : ""}`} onClick={() => selectScreen("node")} aria-label="Open Node and settings"><AppIcon name={nodeConnected ? "shield" : "node"} size={16} /><span><small>Node path</small><strong>{sovereigntyLabel}</strong></span></button>
            <div className="appearance-control"><button className="appearance-button" type="button" onClick={() => setShowAppearanceMenu((open) => !open)} aria-expanded={showAppearanceMenu} aria-controls="appearance-preferences"><AppIcon name="display" size={16} /><span>Display</span><AppIcon name="chevron-down" size={14} /></button>{showAppearanceMenu && <AppearanceMenu preferences={presentation} onChange={setPresentation} onClose={() => setShowAppearanceMenu(false)} />}</div>
          </div>
        </header>
        <div className="content-wrap">
          {state.screen === "home" && <HomeView outcomeInputRef={outcomeInputRef} />}
          {state.screen === "pid" && <PidView />}
          {state.screen === "chat" && <ChatView />}
          {state.screen === "sandbox" && <SandboxView />}
          {state.screen === "knowledge" && <KnowledgeView />}
          {state.screen === "review" && <ReviewView />}
          {state.screen === "node" && <NodeSettingsView profiles={profiles} profilesState={profilesState} profileError={profileError} connection={connection} connectingProfileId={connectingProfileId} onConnect={connectProfile} onReconnect={reconnect} onReload={() => { setProfilesReloadToken((token) => token + 1); }} onHome={() => selectScreen("home")} onHelp={openConnectionHelp} operationalProjection={nodeOperationalProjection} />}
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

function NodeIdentityCard({ connection }: { connection: NodeConnectionView }) {
  return <section className="node-identity-card panel-cli" aria-label="Node identity">
    <div className="node-identity-head"><AppIcon name="shield" size={17} /><div><strong>Verified Node Identity</strong><span>All fields come from the Node handshake response.</span></div></div>
    <dl className="node-identity-grid">
      <div><dt>Node identity</dt><dd>{connection.nodeIdentity ?? "Not supplied"}</dd></div>
      <div><dt>Protocol version</dt><dd>{connection.protocolVersion ?? "Not supplied"}</dd></div>
      <div><dt>Clearance context</dt><dd>{connection.clearanceContext ?? "Not supplied"}</dd></div>
      <div><dt>Authenticated subject</dt><dd>{connection.authenticatedSubject ?? "Not supplied"}</dd></div>
      <div><dt>Domain-pack ref</dt><dd>{connection.domainPackRef ?? "Not supplied"}</dd></div>
      <div><dt>Sovereignty status</dt><dd>{connection.sovereignty ?? "unknown"}</dd></div>
    </dl>
  </section>;
}

function NodeSettingsView({ profiles, profilesState, profileError, connection, connectingProfileId, onConnect, onReconnect, onReload, onHome, onHelp, operationalProjection }: { profiles: ApprovedNodeProfileReference[]; profilesState: "idle" | "loading" | "ready" | "failed"; profileError: string | null; connection: NodeConnectionView; connectingProfileId: string | null; onConnect: (profile: ApprovedNodeProfileReference) => void; onReconnect: () => void; onReload: () => void; onHome: () => void; onHelp: () => void; operationalProjection: NodeOperationalProjection }) {
  const connectedProfile = profiles.find((profile) => profile.profileId === connection.profileId);
  return <section className="settings-view"><p className="eyebrow">TRUSTED EXECUTION</p><h1>Node and settings</h1><p className="lead">Choose an organization-approved Node. AirBench does not accept arbitrary model-server addresses or credentials in the desktop app. <button type="button" className="text-button" onClick={onHelp}>How this works</button></p>
    <NodeReadinessPanel connection={connection} profile={connectedProfile ?? null} projection={operationalProjection} />
    <HardwareCard profile={connectedProfile ?? null} connected={connection.state === "connected"} hardware={operationalProjection.hardware} />
    <ModelRoster profile={connectedProfile ?? null} connected={connection.state === "connected"} qualification={operationalProjection.qualification} />
    {connection.state === "connected" && <NodeIdentityCard connection={connection} />}
    {connection.state === "connected" && <div className="settings-actions"><button type="button" className="secondary-button bordered-button" onClick={onReconnect} disabled={connectingProfileId !== null}>Recheck Node</button><span className="settings-action-note">Recheck preserves the approved profile and creates a fresh trust result.</span></div>}
    {connection.state !== "connected" && <div className="profile-section"><div className="section-heading"><div><h2>Approved Nodes</h2><p>These profiles were installed by your organization administrator.</p></div><button type="button" className="text-button" onClick={onReload} disabled={profilesState === "loading"}>Reload</button></div>{profilesState === "loading" && <div className="profile-empty">Loading the local approved profile catalog...</div>}{profilesState === "failed" && <div className="profile-empty profile-error" role="alert">{profileError}<button type="button" className="text-button" onClick={onReload}>Try again</button></div>}{profilesState === "ready" && profiles.length === 0 && <div className="profile-empty">No approved Node profile is installed on this workstation. Ask your AirBench administrator to provision one.</div>}{profiles.length > 0 && <div className="profile-list">{profiles.map((profile) => <ProfileCard key={profile.profileId} profile={profile} busy={connectingProfileId === profile.profileId} onConnect={() => onConnect(profile)} />)}</div>}</div>}
    <button type="button" className="secondary-button bordered-button" onClick={onHome}>Return home</button></section>;
}

function ProfileCard({ profile, busy, onConnect }: { profile: ApprovedNodeProfileReference; busy: boolean; onConnect: () => void }) {
  return <article className="profile-card"><div><div className="profile-name">{profile.displayName}</div><div className="profile-meta">{profile.transport === "loopback" ? "Local workstation" : "Internal network"} <span aria-hidden="true">•</span> {profile.clearanceContext} clearance</div><div className="profile-trust">Pinned identity: {profile.nodeIdentity}</div></div><button type="button" className="primary-button" onClick={onConnect} disabled={busy}>{busy ? "Checking..." : "Connect"}</button></article>;
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

  return <div className="modal-backdrop" role="presentation"><section ref={dialogRef} className="modal-card" role="dialog" aria-modal="true" aria-labelledby="connection-help-title" aria-describedby="connection-help-copy" onKeyDown={handleKeyDown}><button type="button" className="modal-close" aria-label="Close" onClick={onClose}>X</button><p className="eyebrow">TRUSTED EXECUTION</p><h2 id="connection-help-title">AirBench works on an approved Node</h2><p id="connection-help-copy">AirBench accepts work only after you select a trusted Node. The Node owns the files, task state, model calls, and tools for that work.</p><div className="modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Close</button><button type="button" className="primary-button" onClick={onOpenNode}>Open Node settings</button></div></section></div>;
}

export default App;
