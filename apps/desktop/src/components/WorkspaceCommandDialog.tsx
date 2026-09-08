import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { AppIcon } from "./AppIcon";
import { filterShellCommands, type ShellCommand } from "../features/shell/commandPalette";

interface WorkspaceCommandDialogProps {
  commands: ShellCommand[];
  onClose: () => void;
  onSelect: (commandId: ShellCommand["id"]) => void;
}

export function WorkspaceCommandDialog({ commands, onClose, onSelect }: WorkspaceCommandDialogProps) {
  const [query, setQuery] = useState("");
  const dialogRef = useRef<HTMLElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const filtered = useMemo(() => filterShellCommands(commands, query), [commands, query]);

  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  const closeFromBackdrop = (target: EventTarget, currentTarget: EventTarget) => {
    if (target === currentTarget) onClose();
  };

  const handleDialogKeyDown = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const results = Array.from(dialogRef.current?.querySelectorAll<HTMLButtonElement>(".command-palette-result:not(:disabled)") ?? []);
      if (results.length > 0) {
        const currentIndex = results.indexOf(document.activeElement as HTMLButtonElement);
        const nextIndex = currentIndex === -1
          ? (event.key === "ArrowDown" ? 0 : results.length - 1)
          : Math.max(0, Math.min(results.length - 1, currentIndex + (event.key === "ArrowDown" ? 1 : -1)));
        event.preventDefault();
        results[nextIndex]?.focus();
      }
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>("button:not([disabled]), input:not([disabled])") ?? []);
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

  return <div className="command-palette-overlay" role="presentation" onMouseDown={(event) => closeFromBackdrop(event.target, event.currentTarget)}>
    <section ref={dialogRef} id="workspace-command-palette" className="command-palette" role="dialog" aria-modal="true" aria-labelledby="command-palette-title" onKeyDown={handleDialogKeyDown}>
      <header className="command-palette-header">
        <div><p className="eyebrow">WORKSPACE COMMANDS</p><h2 id="command-palette-title">Go to</h2></div>
        <button type="button" className="text-button" onClick={onClose}>Close <kbd>Esc</kbd></button>
      </header>
      <label className="command-palette-search">
        <AppIcon name="search" size={18} />
        <span className="sr-only">Search workspace commands</span>
        <input ref={searchRef} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search workspace" type="search" />
      </label>
      <div className="command-palette-results" aria-label="Available workspace commands">
        {filtered.length === 0 && <p className="command-palette-empty">No local workspace command matches that search.</p>}
        {filtered.map((command) => <button key={command.id} className="command-palette-result" type="button" disabled={command.disabled} onClick={() => onSelect(command.id)}>
          <span className="command-palette-icon"><AppIcon name={command.icon} size={16} /></span>
          <span><strong>{command.title}</strong><small>{command.description}</small></span>
          {command.shortcut && <kbd>{command.shortcut}</kbd>}
          {command.disabled && <em>Unavailable</em>}
        </button>)}
      </div>
      <footer className="command-palette-footer"><span><kbd>Arrow keys</kbd> browse</span><span><kbd>Tab</kbd> move</span><span><kbd>Esc</kbd> close</span></footer>
    </section>
  </div>;
}
