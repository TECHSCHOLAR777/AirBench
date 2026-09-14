import { AppIcon } from "../../components/AppIcon";
import type { HomeWorkSummary } from "../work_trace/homeWorkSummary";

interface TaskHistoryViewProps {
  tasks: HomeWorkSummary[];
  onOpen: (taskId: string) => void;
  onRemove: (taskId: string) => void;
  onNewTask: () => void;
}

export function TaskHistoryView({ tasks, onOpen, onRemove, onNewTask }: TaskHistoryViewProps) {
  return <section className="task-history-view" data-testid="task-history-view" aria-label="Task history">
    <header className="task-history-head">
      <div>
        <p className="eyebrow">HISTORY</p>
        <h1>Task History</h1>
        <p className="lead">Completed tasks from the approved Node projection. Removing one clears it from this desktop list only; the Node record and its ledger entries are unchanged.</p>
      </div>
      <div className="task-history-head-actions">
        <button type="button" className="secondary-button bordered-button compact-button" onClick={onNewTask}>New query</button>
        <AppIcon name="history" size={19} />
      </div>
    </header>
    {tasks.length === 0 ? (
      <div className="task-history-empty">
        <AppIcon name="archive" size={19} />
        <strong>No task history available.</strong>
        <p>History comes from the Node. Completed tasks will appear here after they are recorded in the ledger.</p>
        <button type="button" className="primary-button compact-button" onClick={onNewTask}>Start a new query</button>
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
            <div className="task-history-item-actions">
              <button type="button" className="secondary-button compact-button" onClick={() => onOpen(task.taskId)}>Open task</button>
              <button type="button" className="text-button" onClick={() => onRemove(task.taskId)} aria-label={`Remove ${task.title} from this desktop list`}>Remove</button>
            </div>
          </li>
        ))}
      </ul>
    )}
  </section>;
}
