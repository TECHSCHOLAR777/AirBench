import { AppIcon } from "./AppIcon";
import { operatorQuestionPresentation } from "./operatorQuestion";
import type { TaskStatus } from "./protocol";

interface OperatorQuestionCardProps {
  questions: string[];
  taskStatus: TaskStatus;
  phase: string;
  synchronized: boolean;
  ledgerEventRef: string;
}

export function OperatorQuestionCard({
  questions,
  taskStatus,
  phase,
  synchronized,
  ledgerEventRef,
}: OperatorQuestionCardProps) {
  const presentation = operatorQuestionPresentation(taskStatus, phase, synchronized);

  return <section className="operator-question-card" data-testid="operator-question-card" role="status" aria-live="polite" aria-label="Node question awaiting response">
    <div className="operator-question-icon"><AppIcon name="review" size={18} /></div>
    <div className="operator-question-content">
      <p className="eyebrow">{presentation.eyebrow}</p>
      <h2>{presentation.title}</h2>
      <p className="operator-question-state">{presentation.state}</p>
      <ol className="operator-question-list">{questions.map((question, index) => <li key={`${question}-${index}`}>{question}</li>)}</ol>
      <dl className="operator-question-context">
        <div><dt>Continuation</dt><dd>{presentation.continuation}</dd></div>
        <div><dt>Ledger</dt><dd>{ledgerEventRef}</dd></div>
      </dl>
      <p className="operator-question-action"><AppIcon name="shield" size={14} /><span>{presentation.action}</span></p>
    </div>
  </section>;
}
