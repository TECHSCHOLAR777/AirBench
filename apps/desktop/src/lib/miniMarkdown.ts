/**
 * A small, hand-rolled, XSS-safe markdown-ish renderer.
 *
 * This intentionally avoids pulling in a new dependency for a narrow need:
 * rendering chat/report/fixture text (which may originate from a Node,
 * a hardcoded fixture, or operator-entered text) as readable HTML without
 * ever interpreting it as live markup. Every text run is escaped before
 * insertion; the only structure this produces is a fixed allow-list of
 * elements built up here in code, never via string concatenation of
 * untrusted content into HTML.
 *
 * Supported: fenced code blocks, headings (# .. ######), unordered/ordered
 * lists, blockquotes, bold/italic/inline-code spans, links (rendered as
 * text + safe href), and paragraphs.
 */

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function safeHref(href: string): string {
  const trimmed = href.trim();
  if (/^(https?:|mailto:)/i.test(trimmed)) return escapeHtml(trimmed);
  return "#";
}

function renderInline(text: string): string {
  let escaped = escapeHtml(text);
  // Inline code first so its contents are not further transformed.
  escaped = escaped.replace(/`([^`]+)`/g, (_match, code: string) => `<code>${code}</code>`);
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, (_match, bold: string) => `<strong>${bold}</strong>`);
  escaped = escaped.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, (_match, italic: string) => `<em>${italic}</em>`);
  escaped = escaped.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_match, label: string, href: string) => `<a href="${safeHref(href)}" target="_blank" rel="noreferrer noopener">${label}</a>`);
  return escaped;
}

export function renderMarkdownToHtml(source: string): string {
  const lines = (source ?? "").replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  let index = 0;
  let listBuffer: { ordered: boolean; items: string[] } | null = null;

  const flushList = () => {
    if (!listBuffer) return;
    const tag = listBuffer.ordered ? "ol" : "ul";
    out.push(`<${tag}>${listBuffer.items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</${tag}>`);
    listBuffer = null;
  };

  while (index < lines.length) {
    const line = lines[index];

    if (/^```/.test(line.trim())) {
      const lang = line.trim().slice(3).trim();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) {
        codeLines.push(lines[index]);
        index += 1;
      }
      index += 1; // skip closing fence
      flushList();
      const langClass = lang ? ` class="lang-${escapeHtml(lang)}"` : "";
      out.push(`<pre class="chat-code-block"><code${langClass}>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      flushList();
      const level = heading[1].length;
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    const bullet = /^\s*[-*]\s+(.*)$/.exec(line);
    const ordered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || ordered) {
      const isOrdered = Boolean(ordered);
      const content = (bullet ?? ordered)![1];
      if (!listBuffer || listBuffer.ordered !== isOrdered) {
        flushList();
        listBuffer = { ordered: isOrdered, items: [] };
      }
      listBuffer.items.push(content);
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flushList();
      const quoteLines: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      out.push(`<blockquote>${quoteLines.map((quoteLine) => `<p>${renderInline(quoteLine)}</p>`).join("")}</blockquote>`);
      continue;
    }

    if (line.trim() === "") {
      flushList();
      index += 1;
      continue;
    }

    flushList();
    const paragraphLines: string[] = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() !== "" && !/^```/.test(lines[index].trim()) && !/^(#{1,6})\s+/.test(lines[index]) && !/^\s*[-*]\s+/.test(lines[index]) && !/^\s*\d+[.)]\s+/.test(lines[index]) && !/^\s*>\s?/.test(lines[index])) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    out.push(`<p>${paragraphLines.map(renderInline).join("<br />")}</p>`);
  }

  flushList();
  return out.join("\n");
}
