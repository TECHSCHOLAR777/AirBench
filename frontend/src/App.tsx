import { useMemo, useState } from "react";
import { invoke } from "@airbench/tauri-invoke";
import type { AirBenchPresentationState, Screen } from "./contracts";
import { initialPresentationState } from "./contracts";

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
  const [showConnectionHelp, setShowConnectionHelp] = useState(false);
  const [taskText, setTaskText] = useState("");
  const [selectedFile, setSelectedFile] = useState<SelectedFile | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const screenTitle = useMemo(() => {
    const titles: Record<Screen, string> = { home: "Home", tasks: "Tasks", review: "Review", artifacts: "Artifacts", history: "History", audit: "Audit", node: "Node and settings" };
    return titles[state.screen];
  }, [state.screen]);

  const selectScreen = (screen: Screen) => setState((current) => ({ ...current, screen }));

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

  const canStart = Boolean(taskText.trim()) && state.node.state === "connected";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="AirBench navigation">
        <div className="brand-lockup"><div className="brand-mark" aria-hidden="true">A</div><div><div className="brand-name">AirBench</div><div className="brand-subtitle">Sovereign workbench</div></div></div>
        <button className="new-task-button" onClick={() => selectScreen("home")}><span aria-hidden="true">+</span><span>New task</span><kbd>Ctrl N</kbd></button>
        <nav className="nav-groups"><NavGroup title="Work" items={primaryNav} active={state.screen} onSelect={selectScreen} /><NavGroup title="Records" items={recordNav} active={state.screen} onSelect={selectScreen} /></nav>
        <div className="sidebar-spacer" />
        <button className="node-chip" data-testid="node-chip" onClick={() => selectScreen("node")} aria-label="Open Node and settings"><span className="status-dot" aria-hidden="true" /><span><strong>Node not connected</strong><small>Choose an approved Node</small></span><span className="chevron" aria-hidden="true">&gt;</span></button>
        <div className="user-row"><div className="avatar">RG</div><div><strong>Local operator</strong><small>Clearance not resolved</small></div><span className="more-icon" aria-hidden="true">...</span></div>
      </aside>

      <main className="main-area">
        <header className="topbar"><div className="breadcrumb"><span>AirBench</span><span className="breadcrumb-slash">/</span><strong>{screenTitle}</strong></div><div className="topbar-actions"><div className="quiet-status"><span className="status-dot" aria-hidden="true" /> Node not connected</div><button className="quiet-action" aria-label="Open command menu">Command</button><button className="quiet-action" aria-label="Open notifications">Alerts</button></div></header>
        <div className="content-wrap">
          {state.screen === "home" && <HomeView taskText={taskText} setTaskText={setTaskText} selectedFile={selectedFile} notice={notice} canStart={canStart} onAttach={attachFile} onRemoveFile={() => setSelectedFile(null)} onHelp={() => setShowConnectionHelp(true)} onOpenNode={() => selectScreen("node")} />}
          {state.screen === "node" && <NodeSettingsView onHome={() => selectScreen("home")} />}
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

function HomeView({ taskText, setTaskText, selectedFile, notice, canStart, onAttach, onRemoveFile, onHelp, onOpenNode }: { taskText: string; setTaskText: (value: string) => void; selectedFile: SelectedFile | null; notice: string | null; canStart: boolean; onAttach: () => void; onRemoveFile: () => void; onHelp: () => void; onOpenNode: () => void }) {
  return <div className="home-view">
    <section className="welcome-block"><p className="eyebrow">PRIVATE BY DESIGN</p><h1>What should AirBench complete?</h1><p className="lead">Describe the outcome. Add files if they are part of the work.</p></section>
    <section className="composer-card" data-testid="task-composer" aria-label="New task composer">
      <textarea value={taskText} onChange={(event) => setTaskText(event.target.value)} placeholder="For example: Review the scanned inspection report and draft an approval note with the key findings and required actions." rows={4} />
      {selectedFile && <div className="selected-file"><span className="file-badge">FILE</span><span><strong>{selectedFile.file_name}</strong><small>{formatBytes(selectedFile.byte_size)} / ready for File Intake</small></span><button className="remove-file" onClick={onRemoveFile} aria-label="Remove selected file">Remove</button></div>}
      <div className="composer-footer"><div className="composer-tools"><button className="secondary-button" data-testid="attach-files" onClick={onAttach}><span aria-hidden="true">+</span> Attach files</button><button className="secondary-button" disabled>Choose project</button></div><button className="primary-button" data-testid="start-task" disabled={!canStart} title={canStart ? "Start task" : "Connect an approved Node before starting work"}>Start task <kbd>Enter</kbd></button></div>
    </section>
    {notice && <div className="inline-notice" role="status">{notice}</div>}
    <div className="trust-line" role="status"><span className="trust-item"><span className="trust-check" aria-hidden="true">OK</span> Files stay on your node</span><span className="trust-item"><span className="trust-check" aria-hidden="true">OK</span> External network denied</span><button className="text-button" onClick={onHelp}>How this works</button></div>
    <section className="continue-section"><div className="section-heading"><div><h2>Continue work</h2><p>Your recent tasks will appear here.</p></div><button className="text-button" disabled>View history <span aria-hidden="true">-&gt;</span></button></div><div className="empty-state"><div className="empty-icon" aria-hidden="true">T</div><p>No tasks yet</p><small>When you start work, you can return to it here.</small></div></section>
    <section className="readiness-card"><div><p className="eyebrow">READY WHEN YOU ARE</p><h2>Connect a trusted Node to begin</h2><p>Your organization controls the models, tools, files, and audit record on that Node.</p></div><button className="secondary-button bordered-button" data-testid="open-node-settings" onClick={onOpenNode}>Open Node settings</button></section>
  </div>;
}

function NodeSettingsView({ onHome }: { onHome: () => void }) {
  return <section className="settings-view"><p className="eyebrow">TRUSTED EXECUTION</p><h1>Node and settings</h1><p className="lead">AirBench connects to an organization-approved Node. The desktop app does not accept arbitrary model-server addresses.</p><div className="settings-card"><div className="settings-status"><span className="status-dot" aria-hidden="true" /><div><strong>No Node connected</strong><small>Nothing has been submitted or sent anywhere.</small></div></div><div className="settings-row"><span>Connection</span><strong>Awaiting approved profile</strong></div><div className="settings-row"><span>Network</span><strong>Webview external access denied</strong></div><div className="settings-row"><span>Identity</span><strong>Not resolved</strong></div></div><div className="settings-note"><strong>How connection is established</strong><p>Your administrator provisions an approved local or internal Node profile and its credential in the operating system. AirBench verifies the Node identity, protocol, clearance, and trust before allowing work.</p></div><button className="secondary-button bordered-button" onClick={onHome}>Return home</button></section>;
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
