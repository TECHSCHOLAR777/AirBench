import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface ChatMarkdownProps {
  content: string;
}

export const ChatMarkdown: React.FC<ChatMarkdownProps> = ({ content }) => {
  // Strip EMIT_REPORT directive if present
  const cleanText = content.replace(/\[EMIT_REPORT:\s*[a-zA-Z0-9_\-\.]+\s*\]/g, '').trim();

  // Split content by code blocks
  const parts = cleanText.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-3 font-sans text-xs sm:text-sm leading-relaxed text-[#ede8dd]">
      {parts.map((part, idx) => {
        if (!part) return null;

        // If fenced code block
        if (part.startsWith('```')) {
          const match = part.match(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/);
          const lang = match ? match[1] || 'code' : 'code';
          const code = match ? match[2] : part.slice(3, -3).trim();

          return <CodeBlock key={idx} language={lang} code={code} />;
        }

        // Normal markdown text: process paragraphs, headers, lists, tables
        return <FormattedText key={idx} rawText={part} />;
      })}
    </div>
  );
};

const CodeBlock: React.FC<{ language: string; code: string }> = ({ language, code }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3 rounded-xl overflow-hidden border border-[#2e2c28] bg-[#11100f] font-mono text-xs shadow-md">
      <div className="px-3.5 py-1.5 bg-[#171615] border-b border-[#282622] flex items-center justify-between text-[11px] text-[#8e8982]">
        <span className="uppercase tracking-wider font-semibold text-[#bd5b38]">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-0.5 rounded hover:bg-[#22211e] text-[#a8a39a] hover:text-[#ede8dd] transition-colors cursor-pointer"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-[#3ea877]" />
              <span className="text-[#3ea877]">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span>Copy code</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3.5 overflow-x-auto text-[#e0ded8] leading-relaxed select-text">
        <code>{code}</code>
      </pre>
    </div>
  );
};

const FormattedText: React.FC<{ rawText: string }> = ({ rawText }) => {
  const lines = rawText.split('\n');
  const elements: React.ReactNode[] = [];
  let currentList: { type: 'ul' | 'ol'; items: string[] } | null = null;
  let tableLines: string[] = [];

  const flushList = () => {
    if (currentList) {
      if (currentList.type === 'ul') {
        elements.push(
          <ul key={`ul-${elements.length}`} className="my-2 space-y-1.5 pl-4 list-disc marker:text-[#bd5b38]">
            {currentList.items.map((it, i) => (
              <li key={i} className="leading-relaxed">
                <InlineFormatter text={it} />
              </li>
            ))}
          </ul>
        );
      } else {
        elements.push(
          <ol key={`ol-${elements.length}`} className="my-2 space-y-1.5 pl-5 list-decimal marker:text-[#8e8982] marker:font-mono">
            {currentList.items.map((it, i) => (
              <li key={i} className="leading-relaxed">
                <InlineFormatter text={it} />
              </li>
            ))}
          </ol>
        );
      }
      currentList = null;
    }
  };

  const flushTable = () => {
    if (tableLines.length >= 2) {
      const parsedRows = tableLines.map(line =>
        line.split('|').map(c => c.trim()).filter((_, i, arr) => i > 0 && i < arr.length - 1)
      ).filter(r => r.length > 0);

      if (parsedRows.length >= 2) {
        const header = parsedRows[0];
        // skip separator row if exists
        const isSep = (r: string[]) => r.every(cell => /^[-:\s]+$/.test(cell));
        const bodyRows = parsedRows.slice(1).filter(r => !isSep(r));

        elements.push(
          <div key={`table-${elements.length}`} className="my-3 overflow-x-auto rounded-lg border border-[#2e2c28]">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#191816] border-b border-[#2e2c28]">
                  {header.map((col, cIdx) => (
                    <th key={cIdx} className="px-3 py-2 font-semibold text-[#ede8dd] font-sans">
                      <InlineFormatter text={col} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#242220]">
                {bodyRows.map((row, rIdx) => (
                  <tr key={rIdx} className="hover:bg-[#1c1b19] transition-colors">
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} className="px-3 py-2 text-[#d4cfc5] font-sans">
                        <InlineFormatter text={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      tableLines = [];
    } else {
      tableLines.forEach(tl => {
        elements.push(<p key={`tl-${elements.length}`} className="my-1.5"><InlineFormatter text={tl} /></p>);
      });
      tableLines = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Table detection
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushList();
      tableLines.push(trimmed);
      continue;
    } else if (tableLines.length > 0) {
      flushTable();
    }

    if (!trimmed) {
      flushList();
      continue;
    }

    // Headers
    if (trimmed.startsWith('#### ')) {
      flushList();
      elements.push(
        <h4 key={`h4-${i}`} className="text-xs font-semibold text-[#c8c4bc] mt-2.5 mb-1 font-sans">
          <InlineFormatter text={trimmed.replace(/^####\s+/, '')} />
        </h4>
      );
    } else if (trimmed.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={`h3-${i}`} className="text-sm font-semibold text-[#ede8dd] mt-3.5 mb-1.5 font-sans border-b border-[#282725] pb-1">
          <InlineFormatter text={trimmed.replace(/^###\s+/, '')} />
        </h3>
      );
    } else if (trimmed.startsWith('## ')) {
      flushList();
      elements.push(
        <h2 key={`h2-${i}`} className="text-base font-bold text-[#ede8dd] mt-4 mb-2 font-sans border-b border-[#2e2c28] pb-1.5">
          <InlineFormatter text={trimmed.replace(/^##\s+/, '')} />
        </h2>
      );
    } else if (trimmed.startsWith('# ')) {
      flushList();
      elements.push(
        <h1 key={`h1-${i}`} className="text-lg font-bold text-[#ede8dd] mt-4 mb-2 font-sans">
          <InlineFormatter text={trimmed.replace(/^#\s+/, '')} />
        </h1>
      );
    } else if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
      const itemText = trimmed.replace(/^[*\-]\s+/, '');
      if (!currentList || currentList.type !== 'ul') {
        flushList();
        currentList = { type: 'ul', items: [itemText] };
      } else {
        currentList.items.push(itemText);
      }
    } else if (/^\d+\.\s+/.test(trimmed)) {
      const itemText = trimmed.replace(/^\d+\.\s+/, '');
      if (!currentList || currentList.type !== 'ol') {
        flushList();
        currentList = { type: 'ol', items: [itemText] };
      } else {
        currentList.items.push(itemText);
      }
    } else if (trimmed.startsWith('> ')) {
      flushList();
      elements.push(
        <blockquote key={`bq-${i}`} className="my-2 border-l-2 border-[#bd5b38] pl-3 italic text-[#b5b0a6] text-xs">
          <InlineFormatter text={trimmed.replace(/^>\s*/, '')} />
        </blockquote>
      );
    } else {
      flushList();
      elements.push(
        <p key={`p-${i}`} className="my-2 leading-relaxed">
          <InlineFormatter text={trimmed} />
        </p>
      );
    }
  }

  flushList();
  flushTable();

  return <>{elements}</>;
};

const InlineFormatter: React.FC<{ text: string }> = ({ text }) => {
  // Parse inline code `code`, bold **text**, italics *text*
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g);

  return (
    <>
      {parts.map((chunk, idx) => {
        if (!chunk) return null;
        if (chunk.startsWith('`') && chunk.endsWith('`')) {
          return (
            <code key={idx} className="px-1.5 py-0.5 mx-0.5 rounded bg-[#201f1d] text-[#e0a187] font-mono text-[11px] border border-[#2d2b27]">
              {chunk.slice(1, -1)}
            </code>
          );
        }
        if (chunk.startsWith('**') && chunk.endsWith('**')) {
          return (
            <strong key={idx} className="font-semibold text-[#ede8dd]">
              {chunk.slice(2, -2)}
            </strong>
          );
        }
        if (chunk.startsWith('*') && chunk.endsWith('*')) {
          return (
            <em key={idx} className="italic text-[#d4cfc5]">
              {chunk.slice(1, -1)}
            </em>
          );
        }
        return <span key={idx}>{chunk}</span>;
      })}
    </>
  );
};
