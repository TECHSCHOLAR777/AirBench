import { useState } from "react";
import { AppIcon } from "../../components/AppIcon";
import { ChatMessage } from "../../components/ChatMessage";
import { ProcessLogPanel } from "../../components/ProcessLogPanel";
import { runProcessTheater, type ProcessTheaterState } from "../../lib/processTheater";
import { buildAnswerPhases, resolveAnswer, routeFor, type ResolvedAnswer } from "../assistant/answerEngine";
import { recordDeliverable, slugify } from "../deliverables/deliverableStore";

interface KnowledgeDocument {
  id: string;
  title: string;
  revision: string;
  pages: number;
  passages: number;
  category: string;
}

const LIBRARY: KnowledgeDocument[] = [
  { id: "SOP-MNT-022", title: "Unit 4 maintenance review procedure", revision: "Rev 7", pages: 26, passages: 212, category: "Maintenance" },
  { id: "SOP-QAL-017", title: "Deviation and findings management", revision: "Rev 8", pages: 16, passages: 141, category: "Quality" },
  { id: "SOP-SAF-003", title: "Line breaking and positive isolation", revision: "Rev 5", pages: 12, passages: 98, category: "Safety" },
  { id: "SOP-PRC-014", title: "Pump changeover and isolation", revision: "Rev 4", pages: 18, passages: 154, category: "Process" },
  { id: "SOP-INS-031", title: "Relief valve inspection intervals", revision: "Rev 6", pages: 21, passages: 176, category: "Inspection" },
  { id: "STD-PID-001", title: "P&ID drafting and symbol standard", revision: "Rev 9", pages: 44, passages: 318, category: "Engineering" },
  { id: "SOP-OPS-009", title: "Crude feed rate adjustment", revision: "Rev 2", pages: 9, passages: 74, category: "Operations" },
  { id: "SOP-ENV-005", title: "Flare gas recovery monitoring", revision: "Rev 3", pages: 14, passages: 111, category: "Environmental" },
];

const TOTAL_PASSAGES = LIBRARY.reduce((total, document) => total + document.passages, 0);
const TOTAL_PAGES = LIBRARY.reduce((total, document) => total + document.pages, 0);

export function KnowledgeView() {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [routedModel, setRoutedModel] = useState<string | null>(null);
  const [stage, setStage] = useState<ProcessTheaterState | null>(null);
  const [answer, setAnswer] = useState<ResolvedAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    const request = query.trim();
    if (!request || busy) return;
    const model = routeFor(request, null);
    setBusy(true);
    setError(null);
    setAnswer(null);
    setStage(null);
    setRoutedModel(model);
    try {
      const work = resolveAnswer(request, {});
      await runProcessTheater(buildAnswerPhases(model), (state) => setStage(state), { waitFor: work });
      const resolved = await work;
      setAnswer(resolved);
      if (resolved.text.trim()) {
        recordDeliverable({
          title: resolved.title,
          kind: "markdown",
          source: "Knowledge",
          content: resolved.text,
          fileName: `${slugify(resolved.title)}.md`,
          routedModel: resolved.routedModel,
        });
      }
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : "That question could not be answered.");
    } finally {
      setBusy(false);
    }
  };

  return <section className="workspace-page knowledge-page" aria-label="Knowledge base">
    <header className="workspace-header">
      <h1>Knowledge base</h1>
      <p>Standard operating procedures indexed on the connected node.</p>
    </header>

    <div className="knowledge-stats">
      <Stat label="Documents" value={String(LIBRARY.length)} />
      <Stat label="Pages" value={String(TOTAL_PAGES)} />
      <Stat label="Indexed passages" value={TOTAL_PASSAGES.toLocaleString()} />
      <Stat label="Index status" value="Synced" tone="ready" />
    </div>

    <div className="knowledge-ask">
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void ask(); } }}
        placeholder="Ask about a procedure…"
        aria-label="Ask the knowledge base"
      />
      <button type="button" className="primary-button" onClick={() => void ask()} disabled={busy || !query.trim()}>
        {busy ? "Searching…" : "Search"}
      </button>
    </div>

    {error && <div className="workspace-notice" role="alert">{error}</div>}
    {stage && routedModel && <ProcessLogPanel phases={buildAnswerPhases(routedModel)} state={stage} title="Searching" />}
    {answer && <ChatMessage role="assistant" text={answer.text} routedModel={answer.routedModel} deliverableTitle={answer.title} showDownload />}

    <section className="workspace-panel">
      <div className="workspace-panel-head"><span>Indexed documents</span><span className="workspace-panel-meta">{LIBRARY.length} sources</span></div>
      <ul className="knowledge-list">
        {LIBRARY.map((document) => <li key={document.id} className="knowledge-item">
          <span className="knowledge-item-icon" aria-hidden="true"><AppIcon name="document" size={17} /></span>
          <span className="knowledge-item-body">
            <strong>{document.title}</strong>
            <small>{document.id} · {document.revision} · {document.pages} pages</small>
          </span>
          <span className="knowledge-item-category">{document.category}</span>
          <span className="knowledge-item-state">Indexed</span>
        </li>)}
      </ul>
    </section>
  </section>;
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "ready" }) {
  return <div className={`knowledge-stat ${tone === "ready" ? "is-ready" : ""}`}>
    <strong>{value}</strong>
    <small>{label}</small>
  </div>;
}
