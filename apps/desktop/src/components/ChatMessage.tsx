import { useMemo } from "react";
import { AppIcon } from "./AppIcon";
import { renderMarkdownToHtml } from "../lib/miniMarkdown";

export interface DeliverableMeta {
  title: string;
  routedModel?: string;
  generatedAt?: string;
}

function triggerMarkdownDownload(meta: DeliverableMeta, content: string) {
  const header = [
    `# ${meta.title}`,
    "",
    `Generated: ${meta.generatedAt ?? new Date().toISOString()}`,
    meta.routedModel ? `Routed model: ${meta.routedModel}` : null,
    "",
    "---",
    "",
  ].filter((line): line is string => line !== null).join("\n");
  const blob = new Blob([header + content], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${meta.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "deliverable"}.md`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/**
 * Renders a finished answer (markdown text and/or an image result) as a
 * chat-style bubble, with an optional "Download deliverable" action that
 * writes a plain .md file client-side. This is purely a presentation
 * component: it never calls a backend and never fabricates a download of
 * anything other than the text actually passed in.
 */
export function ChatMessage({
  role,
  text,
  imageUrl,
  imageAlt,
  routedModel,
  deliverableTitle,
  showDownload,
}: {
  role: "user" | "assistant";
  text?: string;
  imageUrl?: string;
  imageAlt?: string;
  routedModel?: string;
  deliverableTitle?: string;
  showDownload?: boolean;
}) {
  const html = useMemo(() => (text ? renderMarkdownToHtml(text) : ""), [text]);

  return <div className={`chat-message chat-message-${role}`}>
    <div className="chat-message-avatar" aria-hidden="true">{role === "assistant" ? <AppIcon name="airbench" size={15} /> : "You"}</div>
    <div className="chat-message-body">
      {imageUrl && <img className="chat-message-image" src={imageUrl} alt={imageAlt ?? "Result"} />}
      {text && <div className="chat-message-markdown" dangerouslySetInnerHTML={{ __html: html }} />}
      {role === "assistant" && (routedModel || (showDownload && text)) && (
        <div className="chat-message-footer">
          {routedModel && <span className="chat-message-route"><AppIcon name="route" size={12} /> Routed to {routedModel}</span>}
          {showDownload && text && (
            <button
              type="button"
              className="text-button chat-download-button"
              onClick={() => triggerMarkdownDownload({ title: deliverableTitle ?? "AirBench deliverable", routedModel }, text)}
            >
              Download deliverable (.md)
            </button>
          )}
        </div>
      )}
    </div>
  </div>;
}
