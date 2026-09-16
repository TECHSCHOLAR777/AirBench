import type { ProcessPhase, ProcessTheaterState } from "../lib/processTheater";

/**
 * Terminal-style progress panel for `runProcessTheater`: shows the current
 * phase name against the full phase list, and the log lines revealed so far.
 * Purely presentational — all timing/log content comes from the caller.
 */
export function ProcessLogPanel({ phases, state, title }: { phases: ProcessPhase[]; state: ProcessTheaterState; title: string }) {
  return <section className="panel-cli process-log-panel" role="status" aria-live="polite" aria-atomic="true">
    <div className="panel-cli-head"><span>{title}</span><span className="process-log-phase-count">{Math.min(state.phaseIndex + 1, phases.length)}/{phases.length}</span></div>
    <ol className="process-log-phases">
      {phases.map((phase, index) => <li key={phase.id} className={index < state.phaseIndex || state.done ? "is-complete" : index === state.phaseIndex ? "is-active" : "is-pending"}>
        <span aria-hidden="true">{index < state.phaseIndex || state.done ? "✓" : index + 1}</span>
        <strong>{phase.label}</strong>
      </li>)}
    </ol>
    <pre className="process-log-lines" aria-label="Process log">
      {state.lines.map((line, index) => <div key={index} className="process-log-line">{`> ${line}`}</div>)}
      {!state.done && <div className="process-log-cursor" aria-hidden="true">{"> _"}</div>}
    </pre>
  </section>;
}
