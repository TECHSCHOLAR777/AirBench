import { useState, useSyncExternalStore } from "react";
import { AppIcon } from "../../components/AppIcon";
import { ChatMessage } from "../../components/ChatMessage";
import { clearDeliverables, downloadDeliverable, listDeliverables, subscribeToDeliverables, type Deliverable, type DeliverableKind } from "../deliverables/deliverableStore";

const KIND_LABEL: Record<DeliverableKind, string> = {
  markdown: "Document",
  json: "JSON",
  graphml: "GraphML",
  code: "Code",
  text: "Text",
};

export function ReviewView() {
  const deliverables = useSyncExternalStore(subscribeToDeliverables, listDeliverables);
  const [openId, setOpenId] = useState<string | null>(null);
  const open = deliverables.find((entry) => entry.id === openId) ?? deliverables[0] ?? null;

  return <section className="workspace-page review-page" aria-label="Review">
    <header className="workspace-header">
      <h1>Review</h1>
      <p>Everything produced in this session — answers, exports, and code output.</p>
      {deliverables.length > 0 && <button type="button" className="text-button" onClick={clearDeliverables}>Clear all</button>}
    </header>

    {deliverables.length === 0 && <div className="workspace-empty">
      <AppIcon name="review" size={24} />
      <strong>Nothing generated yet</strong>
      <p>Run a request on Home, process a drawing on P&amp;ID, or execute code in the Sandbox. Results collect here.</p>
    </div>}

    {deliverables.length > 0 && <div className="review-layout">
      <ul className="review-list">
        {deliverables.map((entry) => <li key={entry.id}>
          <button type="button" className={`review-item ${open?.id === entry.id ? "is-active" : ""}`} onClick={() => setOpenId(entry.id)}>
            <span className={`review-kind review-kind-${entry.kind}`}>{KIND_LABEL[entry.kind]}</span>
            <strong>{entry.title}</strong>
            <small>{entry.source} · {formatTime(entry.createdAt)}</small>
          </button>
        </li>)}
      </ul>
      {open && <DeliverablePanel deliverable={open} />}
    </div>}
  </section>;
}

function DeliverablePanel({ deliverable }: { deliverable: Deliverable }) {
  return <section className="workspace-panel review-detail">
    <div className="workspace-panel-head">
      <span>{deliverable.title}</span>
      <button type="button" className="primary-button compact-button" onClick={() => downloadDeliverable(deliverable)}>Download</button>
    </div>
    {deliverable.kind === "markdown"
      ? <ChatMessage role="assistant" text={deliverable.content} routedModel={deliverable.routedModel} />
      : <pre className="review-raw">{deliverable.content.slice(0, 6000)}{deliverable.content.length > 6000 ? "\n…" : ""}</pre>}
  </section>;
}

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
