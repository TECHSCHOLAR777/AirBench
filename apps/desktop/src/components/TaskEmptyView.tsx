import { AppIcon } from "./AppIcon";

interface TaskEmptyViewProps {
  nodeConnected: boolean;
  onNewTask: () => void;
  onOpenNode: () => void;
}

export function TaskEmptyView({ nodeConnected, onNewTask, onOpenNode }: TaskEmptyViewProps) {
  return <section className="task-empty-view" data-testid="task-empty-view" aria-label="No active task">
    <div className="task-empty-icon"><AppIcon name="tasks" size={23} /></div>
    <p className="eyebrow">TASK WORKSPACE</p>
    <h1>No active task is open</h1>
    <p className="lead">The live workspace appears after an approved Node accepts a task and returns its authoritative snapshot. AirBench does not create task state in the desktop app.</p>
    <div className="task-empty-actions"><button type="button" className="primary-button" onClick={onNewTask}>Start a task</button>{!nodeConnected && <button type="button" className="secondary-button bordered-button" onClick={onOpenNode}>Connect an approved Node</button>}</div>
    <p className="task-empty-note">Opening a task requires a Node-issued task ID, ordered event cursor, and ledger reference.</p>
  </section>;
}
