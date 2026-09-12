import { AppIcon } from "../../components/AppIcon";
import type { HomeWorkSummary } from "../work_trace/homeWorkSummary";

interface TaskHistoryViewProps {
  tasks: HomeWorkSummary[];
}

export function TaskHistoryView({ tasks }: TaskHistoryViewProps) {
  return <section className="task-history-view" data-testid="task-history-view" aria-label="Task history">
    <header className="task-history-head">
      <div>
        <p className="eyebrow">HISTORY</p>
        <h1>Task History</h1>
        <p className="lead">Completed tasks from the approved Node projection.</p>
      </div>
      <AppIcon name="history" size={19} />
    </header>
    {tasks.length === 0 ? (
      <div className="task-history-empty">
        <AppIcon name="archive" size={19} />
        <strong>No task history available.</strong>
        <p>History comes from the Node. Completed tasks will appear here after they are recorded in the ledger.</p>
      </div>
    ) : (
      <ul className="task-history-list">
        {tasks.map((task) => (
          <li key={task.taskId} className="task-history-item">
            <div className="task-history-item-main">
              <div className="task-history-item-title">
                <strong>{task.title}</strong>
                <span className={`task-history-status task-history-status-${task.status}`}>{task.statusLabel}</span>
              </div>
              <p className="task-history-item-summary">{task.requestSummary}</p>
            </div>
            <dl className="task-history-item-meta">
              <div><dt>Task ID</dt><dd>{task.taskId}</dd></div>
              <div><dt>Phase</dt><dd>{task.phase}</dd></div>
              <div><dt>Health</dt><dd>{task.healthLabel}</dd></div>
              <div><dt>Node cursor</dt><dd>{task.lastAppliedSequence}</dd></div>
              <div><dt>Ledger head</dt><dd>{task.ledgerHeadRef}</dd></div>
              {task.latestActivity && (
                <>
                  <div><dt>Latest activity</dt><dd>{task.latestActivity.label}</dd></div>
                  <div><dt>Occurred</dt><dd>{task.latestActivity.occurredAt}</dd></div>
                  <div><dt>Sequence</dt><dd>{task.latestActivity.sequence}</dd></div>
                  <div><dt>Ledger event</dt><dd>{task.latestActivity.ledgerEventRef}</dd></div>
                </>
              )}
            </dl>
          </li>
        ))}
      </ul>
    )}
  </section>;
}