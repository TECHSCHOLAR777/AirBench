import { useMemo, useState } from "react";
import type { AirBenchPresentationState, Screen } from "./contracts";
import { initialPresentationState } from "./contracts";

const primaryNav: Array<{ id: Screen; label: string; icon: string }> = [
  { id: "home", label: "Home", icon: "⌂" },
  { id: "tasks", label: "Tasks", icon: "□" },
  { id: "review", label: "Review", icon: "✓" },
];

const recordNav: Array<{ id: Screen; label: string; icon: string }> = [
  { id: "artifacts", label: "Artifacts", icon: "▤" },
  { id: "history", label: "History", icon: "↺" },
  { id: "audit", label: "Audit", icon: "◌" },
];

function App() {
  const [state, setState] = useState<AirBenchPresentationState>(initialPresentationState);
  const [showConnectionHelp, setShowConnectionHelp] = useState(false);
  const [taskText, setTaskText] = useState("");

  const screenTitle = useMemo(() => {
    const titles: Record<Screen, string> = {
      home: "Home",
      tasks: "Tasks",
      review: "Review",
      artifacts: "Artifacts",
      history: "History",
      audit: "Audit",
      node: "Node and settings",
    };
    return titles[state.screen];
  }, [state.screen]);

  const selectScreen = (screen: Screen) => setState((current) => ({ ...current, screen }));

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="AirBench navigation">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">A</div>
          <div>
            <div className="brand-name">AirBench</div>
            <div className="brand-subtitle">Sovereign workbench</div>
          </div>
        </div>

        <button className="new-task-button" onClick={() => selectScreen("home")}>
          <span aria-hidden="true">+</span>
          <span>New task</span>
          <kbd>Ctrl N</kbd>
        </button>

        <nav className="nav-groups">
          <NavGroup title="Work" items={primaryNav} active={state.screen} onSelect={selectScreen} />
          <NavGroup title="Records" items={recordNav} active={state.screen} onSelect={selectScreen} />
        </nav>

        <div className="sidebar-spacer" />
        <button className="node-chip" onClick={() => selectScreen("node")} aria-label="Open Node and settings">
          <span className="status-dot" aria-hidden="true" />
          <span>
            <strong>Node not connected</strong>
            <small>Choose an approved Node</small>
          </span>
          <span className="chevron" aria-hidden="true">›</span>
        </button>
        <div className="user-row">
          <div className="avatar">RG</div>
          <div>
            <strong>Local operator</strong>
            <small>Clearance not resolved</small>
          </div>
          <span className="more-icon" aria-hidden="true">•••</span>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb"><span>AirBench</span><span className="breadcrumb-slash">/</span><strong>{screenTitle}</strong></div>
          <div className="topbar-actions">
            <div className="quiet-status"><span className="status-dot" aria-hidden="true" /> Node not connected</div>
            <button className="icon-button" aria-label="Open command menu">⌘</button>
            <button className="icon-button" aria-label="Open notifications">♢</button>
          </div>
        </header>

        <div className="content-wrap">
          {state.screen === "home" && (
            <HomeView taskText={taskText} setTaskText={setTaskText} onHelp={() => setShowConnectionHelp(true)} />
          )}
          {state.screen !== "home" && <PlaceholderView screen={screenTitle} onHome={() => selectScreen("home")} />}
        </div>
      </main>

      {showConnectionHelp && <ConnectionHelp onClose={() => setShowConnectionHelp(false)} onOpenNode={() => { setShowConnectionHelp(false); selectScreen("node"); }} />}
    </div>
  );
}

function NavGroup({ title, items, active, onSelect }: { title: string; items: Array<{ id: Screen; label: string; icon: string }>; active: Screen; onSelect: (screen: Screen) => void }) {
  return (
    <div className="nav-group">
      <div className="nav-group-title">{title}</div>
      {items.map((item) => (
        <button key={item.id} className={`nav-item ${active === item.id ? "active" : ""}`} onClick={() => onSelect(item.id)}>
          <span className="nav-icon" aria-hidden="true">{item.icon}</span>
          <span>{item.label}</span>
          {item.id === "review" && <span className="nav-count">0</span>}
        </button>
      ))}
    </div>
  );
}

function HomeView({ taskText, setTaskText, onHelp }: { taskText: string; setTaskText: (value: string) => void; onHelp: () => void }) {
  return (
    <div className="home-view">
      <section className="welcome-block">
        <p className="eyebrow">PRIVATE BY DESIGN</p>
        <h1>What should AirBench complete?</h1>
        <p className="lead">Describe the outcome. Add files if they are part of the work.</p>
      </section>

      <section className="composer-card" aria-label="New task composer">
        <textarea
          value={taskText}
          onChange={(event) => setTaskText(event.target.value)}
          placeholder="For example: Review the scanned inspection report and draft an approval note with the key findings and required actions."
          rows={4}
        />
        <div className="composer-footer">
          <div className="composer-tools">
            <button className="secondary-button"><span aria-hidden="true">+</span> Attach files</button>
            <button className="secondary-button">Choose project <span aria-hidden="true">⌄</span></button>
          </div>
          <button className="primary-button" disabled={!taskText.trim()}>Start task <kbd>Enter</kbd></button>
        </div>
      </section>

      <div className="trust-line" role="status">
        <span className="trust-item"><span className="trust-check" aria-hidden="true">✓</span> Files stay on your node</span>
        <span className="trust-item"><span className="trust-check" aria-hidden="true">✓</span> External network denied</span>
        <button className="text-button" onClick={onHelp}>How this works</button>
      </div>

      <section className="continue-section">
        <div className="section-heading"><div><h2>Continue work</h2><p>Your recent tasks will appear here.</p></div><button className="text-button">View history <span aria-hidden="true">→</span></button></div>
        <div className="empty-state"><div className="empty-icon" aria-hidden="true">□</div><p>No tasks yet</p><small>When you start work, you can return to it here.</small></div>
      </section>
    </div>
  );
}

function PlaceholderView({ screen, onHome }: { screen: string; onHome: () => void }) {
  return <section className="placeholder-view"><p className="eyebrow">AIRBENCH WORKBENCH</p><h1>{screen}</h1><p className="lead">This workspace will be connected to the AirBench Node in the next implementation slice.</p><button className="secondary-button" onClick={onHome}>Return home</button></section>;
}

function ConnectionHelp({ onClose, onOpenNode }: { onClose: () => void; onOpenNode: () => void }) {
  return <div className="modal-backdrop" role="presentation"><section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="connection-help-title"><button className="modal-close" aria-label="Close" onClick={onClose}>×</button><p className="eyebrow">TRUSTED EXECUTION</p><h2 id="connection-help-title">AirBench works on an approved Node</h2><p>Your files, task state, model calls, tools, and audit record stay inside the organization. Select a trusted Node before starting work.</p><div className="modal-note"><span className="status-dot" aria-hidden="true" /><span><strong>No Node is connected</strong><small>Nothing has been submitted or sent anywhere.</small></span></div><div className="modal-actions"><button className="secondary-button" onClick={onClose}>Close</button><button className="primary-button" onClick={onOpenNode}>Open Node settings</button></div></section></div>;
}

export default App;
