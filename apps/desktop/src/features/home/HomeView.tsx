import { useState, type RefObject } from "react";
import { AppIcon } from "../../components/AppIcon";
import { ChatMessage } from "../../components/ChatMessage";
import { ProcessLogPanel } from "../../components/ProcessLogPanel";
import { runProcessTheater, type ProcessTheaterState } from "../../lib/processTheater";
import { buildAnswerPhases, resolveAnswer, routeFor, type ResolvedAnswer } from "../assistant/answerEngine";
import {
  generateDocument,
  parseGenerateDocumentReply,
  pickChatAttachment,
  type ChatAttachment,
  type GeneratedDocumentRequest,
} from "../chat/geminiBridge";
import { recordDeliverable, slugify } from "../deliverables/deliverableStore";

const MAX_CHARS = 65536;

const TEMPLATES = [
  { label: "findings --review", prompt: "List the findings that need management review" },
  { label: "procedure --governing", prompt: "Which procedure governs the evidence required?" },
  { label: "route --downstream", prompt: "What is downstream of P-101?" },
  { label: "note --draft", prompt: "Draft the approval note" },
];

const EXPORTS = ["Document", "Summary", "Spreadsheet", "Presentation"] as const;

const EXPORT_FORMAT: Record<(typeof EXPORTS)[number], GeneratedDocumentRequest["format"]> = {
  Document: "docx",
  Summary: "pdf",
  Spreadsheet: "xlsx",
  Presentation: "pptx",
};

export function HomeView({ outcomeInputRef }: { outcomeInputRef: RefObject<HTMLTextAreaElement | null> }) {
  const [prompt, setPrompt] = useState("");
  const [attachment, setAttachment] = useState<ChatAttachment | null>(null);
  const [exportKind, setExportKind] = useState<string>(EXPORTS[0]);
  const [busy, setBusy] = useState(false);
  const [routedModel, setRoutedModel] = useState<string | null>(null);
  const [stage, setStage] = useState<ProcessTheaterState | null>(null);
  const [answer, setAnswer] = useState<ResolvedAnswer | null>(null);
  const [documentRequest, setDocumentRequest] = useState<GeneratedDocumentRequest | null>(null);
  const [savingDoc, setSavingDoc] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const plannedModel = routeFor(prompt, attachment, exportKind.toLowerCase());

  const attach = async () => {
    setError(null);
    try {
      const picked = await pickChatAttachment();
      if (picked) setAttachment(picked);
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : "The file picker is only available in the desktop application.");
    }
  };

  const run = async () => {
    const request = prompt.trim();
    if (!request || busy) return;
    const model = plannedModel;
    const format = EXPORT_FORMAT[exportKind as (typeof EXPORTS)[number]];
    const requestWithHint = format
      ? `${request}\n\n(Deliverable requested: ${exportKind} — if generating a document, use format "${format}".)`
      : request;
    setBusy(true);
    setError(null);
    setAnswer(null);
    setDocumentRequest(null);
    setStage(null);
    setRoutedModel(model);
    try {
      const work = resolveAnswer(requestWithHint, { attachment, outputContract: exportKind.toLowerCase() });
      await runProcessTheater(buildAnswerPhases(model), (state) => setStage(state), { waitFor: work });
      const resolved = await work;
      const parsedDocument = parseGenerateDocumentReply(resolved.text);
      if (parsedDocument) {
        setDocumentRequest(parsedDocument);
        setAnswer({ ...resolved, text: `Ready to export as ${parsedDocument.format.toUpperCase()}.` });
      } else {
        setAnswer(resolved);
        if (resolved.text.trim()) {
          recordDeliverable({
            title: resolved.title,
            kind: "markdown",
            source: "Home",
            content: resolved.text,
            fileName: `${slugify(resolved.title)}.md`,
            routedModel: resolved.routedModel,
          });
        }
      }
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : "That request could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const saveDocument = async () => {
    if (!documentRequest) return;
    setSavingDoc(true);
    setError(null);
    setNotice(null);
    try {
      const result = await generateDocument(documentRequest);
      setNotice(result.cancelled ? "Save cancelled." : `Saved to ${result.filePath}`);
    } catch (thrown) {
      setError(thrown instanceof Error ? thrown.message : "The document could not be generated.");
    } finally {
      setSavingDoc(false);
    }
  };

  const reset = () => {
    setPrompt("");
    setAttachment(null);
    setAnswer(null);
    setDocumentRequest(null);
    setStage(null);
    setError(null);
    setNotice(null);
    outcomeInputRef.current?.focus();
  };

  return <section className="workspace-page home-page" aria-label="Home">
    <header className="home-hero">
      <div>
        <h1>What do you need?</h1>
        <p>Describe the outcome. Attach a source when the work needs one.</p>
      </div>
    </header>

    <section className="cli-card" aria-label="Request">
      <div className="cli-prompt">
        <span className="cli-caret" aria-hidden="true">❯</span>
        <textarea
          ref={outcomeInputRef}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value.slice(0, MAX_CHARS))}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              void run();
            }
          }}
          placeholder="describe what you need"
          rows={2}
          aria-label="Request"
        />
      </div>
      <p className="cli-hint">Press Ctrl Enter to run, or set the parameters below.</p>

      <div className="cli-status">
        <span className="cli-status-ready"><span className="cli-dot" aria-hidden="true" />Library match runs first</span>
        <span className="cli-count">{prompt.length} / {MAX_CHARS}</span>
      </div>

      <div className="cli-flags">
        <button type="button" className="cli-flag" onClick={() => void attach()} disabled={busy}>
          <AppIcon name="attachment" size={14} />
          <span className="cli-flag-key">--source:</span>
          <span className="cli-flag-value">{attachment ? attachment.fileName : "Add file"}</span>
        </button>
        <label className="cli-flag">
          <AppIcon name="document" size={14} />
          <span className="cli-flag-key">--deliverable:</span>
          <select value={exportKind} onChange={(event) => setExportKind(event.target.value)} aria-label="Deliverable type">
            {EXPORTS.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
        </label>
        <span className="cli-flag is-static">
          <AppIcon name="route" size={14} />
          <span className="cli-flag-key">--route:</span>
          <span className="cli-flag-value">{plannedModel}</span>
        </span>
        {attachment && <button type="button" className="cli-flag is-clear" onClick={() => setAttachment(null)}>
          <span className="cli-flag-value">clear source</span>
        </button>}
      </div>

      <div className="cli-footer">
        <span className="cli-footer-note">Results are saved to Review automatically.</span>
        <button type="button" className="primary-button cli-launch" onClick={() => void run()} disabled={busy || !prompt.trim()}>
          {busy ? "Running…" : "Run"} <kbd>Ctrl ⏎</kbd>
        </button>
      </div>
    </section>

    <section className="session-block" aria-label="Session">
      <div className="session-head">
        <h2>Result</h2>
        <span className="session-tag">SESSION LOG</span>
        <button type="button" className="text-button" onClick={reset}>New query</button>
      </div>

      {error && <div className="workspace-notice" role="alert">{error}</div>}
      {notice && <div className="workspace-notice" role="status">{notice}</div>}
      {stage && routedModel && <ProcessLogPanel phases={buildAnswerPhases(routedModel)} state={stage} title="Working" />}

      {answer && <ChatMessage
        role="assistant"
        text={answer.text}
        imageUrl={answer.imageUrl}
        imageAlt={answer.title}
        routedModel={answer.routedModel}
        deliverableTitle={answer.title}
        showDownload={!documentRequest}
      />}

      {documentRequest && <button
        type="button"
        className="primary-button compact-button"
        disabled={savingDoc}
        onClick={() => void saveDocument()}
      >
        {savingDoc ? "Generating…" : `Export ${documentRequest.format.toUpperCase()}`}
      </button>}

      {!answer && !stage && !error && <div className="session-empty">
        <span className="session-empty-icon" aria-hidden="true"><AppIcon name="tasks" size={20} /></span>
        <strong>Nothing run yet</strong>
        <p>Enter a request above. The answer and its deliverable appear here and in Review.</p>
        <div className="session-templates">
          <span>Quick start:</span>
          {TEMPLATES.map((template) => <button type="button" key={template.label} className="session-template" onClick={() => { setPrompt(template.prompt); outcomeInputRef.current?.focus(); }}>
            {template.label}
          </button>)}
        </div>
      </div>}
    </section>
  </section>;
}
