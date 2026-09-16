import { useEffect, useRef, useState } from "react";
import { AppIcon } from "../../components/AppIcon";
import { ChatMessage } from "../../components/ChatMessage";
import { ProcessLogPanel } from "../../components/ProcessLogPanel";
import { runProcessTheater, type ProcessTheaterState } from "../../lib/processTheater";
import { buildAnswerPhases, resolveAnswer, routeFor } from "../assistant/answerEngine";
import { recordDeliverable, slugify } from "../deliverables/deliverableStore";
import {
  generateDocument,
  parseGenerateDocumentReply,
  pickChatAttachment,
  type ChatAttachment,
  type ChatTurn,
  type GeneratedDocumentRequest,
} from "./geminiBridge";

interface ChatEntry {
  id: string;
  role: "user" | "assistant";
  text: string;
  imageUrl?: string;
  title?: string;
  attachmentName?: string;
  routedModel?: string;
  documentRequest?: GeneratedDocumentRequest;
}

export function ChatView() {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [attachment, setAttachment] = useState<ChatAttachment | null>(null);
  const [busy, setBusy] = useState(false);
  const [routedModel, setRoutedModel] = useState<string | null>(null);
  const [stage, setStage] = useState<ProcessTheaterState | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [entries, stage]);

  const attach = async () => {
    setNotice(null);
    try {
      const picked = await pickChatAttachment();
      if (picked) setAttachment(picked);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The file picker is only available in the desktop application.");
    }
  };

  const send = async () => {
    const message = draft.trim();
    if (!message || busy) return;
    const currentAttachment = attachment;
    const model = routeFor(message, currentAttachment);
    const history: ChatTurn[] = entries.map((entry) => ({ role: entry.role, text: entry.text }));

    setNotice(null);
    setBusy(true);
    setDraft("");
    setAttachment(null);
    setRoutedModel(model);
    setStage(null);
    setEntries((current) => [...current, {
      id: crypto.randomUUID(),
      role: "user",
      text: message,
      attachmentName: currentAttachment?.fileName,
    }]);

    try {
      const work = resolveAnswer(message, { attachment: currentAttachment, history });
      await runProcessTheater(buildAnswerPhases(model), (state) => setStage(state), { waitFor: work });
      const resolved = await work;
      const documentRequest = parseGenerateDocumentReply(resolved.text);
      setEntries((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: documentRequest ? `Ready to export as ${documentRequest.format.toUpperCase()}.` : resolved.text,
        imageUrl: resolved.imageUrl,
        title: resolved.title,
        routedModel: resolved.routedModel,
        documentRequest: documentRequest ?? undefined,
      }]);
      if (!documentRequest && resolved.text.trim()) {
        recordDeliverable({
          title: resolved.title,
          kind: "markdown",
          source: "Chat",
          content: resolved.text,
          fileName: `${slugify(resolved.title)}.md`,
          routedModel: resolved.routedModel,
        });
      }
    } catch (error) {
      setEntries((current) => [...current, {
        id: crypto.randomUUID(),
        role: "assistant",
        text: error instanceof Error ? error.message : "That message could not be answered.",
      }]);
    } finally {
      setStage(null);
      setBusy(false);
    }
  };

  const saveDocument = async (entryId: string, request: GeneratedDocumentRequest) => {
    setSavingId(entryId);
    setNotice(null);
    try {
      const result = await generateDocument(request);
      setNotice(result.cancelled ? "Save cancelled." : `Saved to ${result.filePath}`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The document could not be generated.");
    } finally {
      setSavingId(null);
    }
  };

  return <section className="workspace-page chat-page" aria-label="Chat">
    <header className="workspace-header">
      <h1>Chat</h1>
      <p>Ask follow-up questions, attach a document, or request a Word, Excel, PowerPoint, or PDF export.</p>
    </header>

    <div className="chat-scroll" ref={scrollRef}>
      {entries.length === 0 && !stage && <div className="workspace-empty">
        <AppIcon name="chat" size={24} />
        <strong>No messages yet</strong>
        <p>Start a conversation, or attach a file and ask about it.</p>
      </div>}
      {entries.map((entry) => <div key={entry.id} className="chat-entry">
        {entry.attachmentName && <div className="chat-entry-attachment"><AppIcon name="attachment" size={13} /> {entry.attachmentName}</div>}
        <ChatMessage
          role={entry.role}
          text={entry.text}
          imageUrl={entry.imageUrl}
          imageAlt={entry.title}
          routedModel={entry.routedModel}
          deliverableTitle={entry.title}
          showDownload={entry.role === "assistant" && !entry.documentRequest}
        />
        {entry.documentRequest && <button
          type="button"
          className="primary-button compact-button"
          disabled={savingId === entry.id}
          onClick={() => void saveDocument(entry.id, entry.documentRequest!)}
        >
          {savingId === entry.id ? "Generating…" : `Export ${entry.documentRequest.format.toUpperCase()}`}
        </button>}
      </div>)}
      {stage && routedModel && <ProcessLogPanel phases={buildAnswerPhases(routedModel)} state={stage} title="Working" />}
    </div>

    {notice && <div className="workspace-notice" role="status">{notice}</div>}

    <div className="chat-composer">
      {attachment && <div className="home-attachment">
        <AppIcon name="attachment" size={15} />
        <span>{attachment.fileName}</span>
        <button type="button" onClick={() => setAttachment(null)} aria-label="Remove attachment">×</button>
      </div>}
      <div className="chat-composer-row">
        <button type="button" className="chat-attach-button" onClick={() => void attach()} aria-label="Attach a file" disabled={busy}>
          <AppIcon name="attachment" size={17} />
        </button>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          placeholder="Send a message…"
          rows={2}
          aria-label="Message"
        />
        <button type="button" className="primary-button" onClick={() => void send()} disabled={busy || !draft.trim()}>
          {busy ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  </section>;
}
