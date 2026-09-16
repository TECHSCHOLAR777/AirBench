import { useEffect, useMemo, useRef, useState } from "react";
import { downloadDeliverable, recordDeliverable, type Deliverable } from "../deliverables/deliverableStore";
import { runPythonSandbox } from "./sandboxBridge";
import { runProcessTheater } from "../../lib/processTheater";
import { createBootPhases, createContainerIdentity, createIdleLines } from "./sandboxContainer";

const DEFAULT_CODE = "print('Hello from the sandbox!')\n";

interface TerminalLine {
  id: number;
  text: string;
  kind: "boot" | "command" | "stdout" | "stderr" | "meta";
}

/** Terminal-styled front end for the real local Python sandbox, framed as a container session for the demo. */
export function SandboxView() {
  const identity = useMemo(() => createContainerIdentity(), []);
  const [code, setCode] = useState(DEFAULT_CODE);
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<TerminalLine[]>(() =>
    createIdleLines(identity).map((text, index) => ({ id: index, text, kind: "boot" as const })),
  );
  const [lastScript, setLastScript] = useState<Deliverable | null>(null);
  const nextId = useRef(lines.length);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [lines]);

  const append = (text: string, kind: TerminalLine["kind"]) => {
    const id = nextId.current++;
    setLines((current) => [...current, { id, text, kind }]);
  };

  const clear = () => {
    const idle = createIdleLines(identity).map((text, index) => ({ id: index, text, kind: "boot" as const }));
    nextId.current = idle.length;
    setLines(idle);
  };

  const run = async () => {
    setRunning(true);
    append("$ airbench sandbox run script.py", "command");
    try {
      const call = runPythonSandbox(code);
      let revealed = 0;
      await runProcessTheater(createBootPhases(identity), (state) => {
        for (; revealed < state.lines.length; revealed += 1) append(state.lines[revealed], "meta");
      }, { waitFor: call });
      const outcome = await call;
      if (outcome.timedOut) append("[ENCLAVE] Execution killed: exceeded 15s budget.", "meta");
      else append(`[DAEMON] Process exited with code ${outcome.exitCode}.`, "meta");
      if (outcome.stdout) outcome.stdout.split("\n").forEach((line) => append(line, "stdout"));
      if (outcome.stderr) outcome.stderr.split("\n").forEach((line) => append(line, "stderr"));
      if (!outcome.stdout && !outcome.stderr) append("(no output)", "stdout");

      const script = recordDeliverable({
        title: `Sandbox script · exit ${outcome.exitCode}`,
        kind: "code",
        source: "Sandbox",
        content: code,
        fileName: `sandbox-script-${Date.now()}.py`,
      });
      setLastScript(script);
    } catch (thrown) {
      append(thrown instanceof Error ? `[ENCLAVE] ${thrown.message}` : "[ENCLAVE] The sandbox could not run this code.", "stderr");
    } finally {
      setRunning(false);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !running) {
      event.preventDefault();
      void run();
    }
    if (event.key.toLowerCase() === "l" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      clear();
    }
  };

  return <section className="workspace-page sandbox-page" aria-label="Python sandbox">
    <div className="sandbox-cli">
      <div className="sandbox-cli-titlebar">
        <span className="sandbox-cli-dots" aria-hidden="true"><i /><i /><i /></span>
        <button type="button" className="text-button sandbox-cli-clear" onClick={clear}>Clear</button>
      </div>

      <div className="sandbox-cli-body" ref={bodyRef} role="log" aria-live="polite">
        {lines.map((line) => (
          <div key={line.id} className={`sandbox-cli-line sandbox-cli-line-${line.kind}`}>{line.text || " "}</div>
        ))}
        {running && <div className="sandbox-cli-line sandbox-cli-line-meta">Awaiting node input cursor signal<span className="sandbox-cli-cursor" aria-hidden="true">▌</span></div>}
      </div>

      <div className="sandbox-cli-input-row">
        <span className="sandbox-cli-prompt">~ $</span>
        <textarea
          className="sandbox-cli-input"
          spellCheck={false}
          value={code}
          onChange={(event) => setCode(event.target.value)}
          onKeyDown={onKeyDown}
          rows={5}
          aria-label="Python source"
          disabled={running}
        />
        <button type="button" className="primary-button sandbox-cli-run" disabled={running} onClick={() => void run()}>
          {running ? "Running…" : "Run"}
        </button>
        {lastScript && (
          <button type="button" className="secondary-button sandbox-cli-download" onClick={() => downloadDeliverable(lastScript)}>
            Download .py
          </button>
        )}
      </div>

      <div className="sandbox-cli-footer">
        <span><kbd>Ctrl</kbd>+<kbd>L</kbd> Clear · <kbd>Ctrl</kbd>+<kbd>C</kbd> Interrupt · <kbd>Ctrl</kbd>+<kbd>Enter</kbd> Run</span>
        <span className="sandbox-cli-footer-right">
          TTY: /dev/pts/3 &nbsp;·&nbsp;
          <span className={`sandbox-cli-sync-dot${running ? " is-busy" : ""}`} aria-hidden="true" />
          {running ? "RUNNING" : "BUFFER: SYNCED"}
        </span>
      </div>
    </div>
  </section>;
}
