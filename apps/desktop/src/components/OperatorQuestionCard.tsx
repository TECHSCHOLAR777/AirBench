import { AppIcon } from "./AppIcon";
import { operatorQuestionAnnouncement, operatorQuestionPresentation } from "../features/operator_questions/operatorQuestion";
import type { TaskStatus } from "../platform/events/protocol";

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

  return <section className="operator-question-card" data-testid="operator-question-card" role="region" aria-labelledby="operator-question-title" aria-describedby="operator-question-state">
    <span className="sr-only" data-testid="operator-question-announcement" role="status" aria-live="polite" aria-atomic="true">{operatorQuestionAnnouncement(presentation)}</span>
    <div className="operator-question-icon"><AppIcon name="review" size={18} /></div>
    <div className="operator-question-content">
      <p className="eyebrow">{presentation.eyebrow}</p>
      <h2 id="operator-question-title">{presentation.title}</h2>
      <p id="operator-question-state" className="operator-question-state">{presentation.state}</p>
      <ol className="operator-question-list" aria-label="Questions from the Node">{questions.map((question, index) => <li key={`${question}-${index}`}>{question}</li>)}</ol>
      <dl className="operator-question-context">
        <div><dt>Continuation</dt><dd>{presentation.continuation}</dd></div>
        <div><dt>Ledger</dt><dd>{ledgerEventRef}</dd></div>
      </dl>
      <p className="operator-question-action"><AppIcon name="shield" size={14} /><span>{presentation.action}</span></p>
    </div>
  </section>;
}
