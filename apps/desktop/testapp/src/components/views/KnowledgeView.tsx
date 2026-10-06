import React, { useState } from 'react';
import { SopDocument } from '../../types';
import { Search, FileText, CheckCircle2, ChevronRight, Plus, Sparkles, Loader2, Copy, Check, MessageSquare, ArrowRight, X } from 'lucide-react';
import { askKnowledgeBase } from '../../services/inferenceService';
import { ModelHoverTooltip } from '../ModelHoverTooltip';

interface KnowledgeViewProps {
  documents: SopDocument[];
  onSelectDocument: (doc: SopDocument) => void;
  onOpenIngestModal: () => void;
}

export const KnowledgeView: React.FC<KnowledgeViewProps> = ({
  documents,
  onSelectDocument,
  onOpenIngestModal
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isAsking, setIsAsking] = useState(false);
  const [qaAnswer, setQaAnswer] = useState<{
    question: string;
    answer: string;
    modelUsed: string;
    latencyMs: number;
  } | null>(null);
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  const filteredDocs = documents.filter(doc => 
    doc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.sections.some(s => s.heading.toLowerCase().includes(searchQuery.toLowerCase()) || s.text.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const totalPages = documents.reduce((acc, d) => acc + d.pages, 0);
  const totalPassages = documents.reduce((acc, d) => acc + d.passagesCount, 0);

  const handleAskKnowledge = async (q: string) => {
    if (!q.trim()) return;
    setIsAsking(true);
    try {
      const res = await askKnowledgeBase(q.trim(), documents);
      setQaAnswer({
        question: q.trim(),
        answer: res.answer,
        modelUsed: res.modelUsed,
        latencyMs: res.latencyMs
      });
    } catch (err: any) {
      console.warn('Knowledge Q&A failed:', err);
    } finally {
      setIsAsking(false);
    }
  };

  const handleCopyAnswer = () => {
    if (!qaAnswer) return;
    navigator.clipboard.writeText(qaAnswer.answer);
    setCopiedAnswer(true);
    setTimeout(() => setCopiedAnswer(false), 2000);
  };

  const sampleQuestions = [
    'What is the Double Block & Bleed isolation protocol?',
    'What are the emergency depressurization limits?',
    'What are ISA-5.1 tagging conventions for valves?',
    'What checks are required before crude line flange unbolting?'
  ];

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto bg-[#121211] px-6 lg:px-12 py-10 font-sans" data-purpose="knowledge-main-content">
      <div className="max-w-6xl w-full mx-auto space-y-9 pb-12">
        {/* Page Header */}
        <section className="space-y-2" data-purpose="header-section">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <h1 className="font-serif text-3xl md:text-4xl text-[#ede8dd] tracking-tight font-normal">
              Knowledge base
            </h1>
            <div className="flex items-center gap-2 font-mono text-[10.5px]">
              <ModelHoverTooltip modelId="bge-m3" position="bottom">
                <span className="px-2 py-0.5 rounded bg-[#3ea877]/10 border border-[#3ea877]/30 text-[#3ea877] font-semibold cursor-pointer">
                  BGE-M3 (Dense + Sparse)
                </span>
              </ModelHoverTooltip>
              <span className="text-[#555047]">•</span>
              <ModelHoverTooltip modelId="bge-reranker-v2-m3" position="bottom">
                <span className="px-2 py-0.5 rounded bg-[#14b8a6]/10 border border-[#14b8a6]/30 text-[#2dd4bf] font-semibold cursor-pointer">
                  bge-reranker-v2-m3
                </span>
              </ModelHoverTooltip>
            </div>
          </div>
          <p className="font-mono text-xs text-[#9c978f] tracking-tight">
            Standard operating procedures indexed on the connected node. Vector retrieval powered by sovereign BGE-M3 with cross-encoder reranking.
          </p>
        </section>

        {/* Stat Cards Grid matching screenshot 1 */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" data-purpose="metrics-summary-grid">
          {/* Card 1: Documents */}
          <div className="bg-[#1a1918] border border-[#282725] rounded-lg p-5 flex flex-col justify-between shadow-sm">
            <span className="text-3xl font-mono font-medium text-[#ede8dd] leading-none mb-2">
              {documents.length}
            </span>
            <span className="font-mono text-xs text-[#9c978f]">Documents</span>
          </div>

          {/* Card 2: Pages */}
          <div className="bg-[#1a1918] border border-[#282725] rounded-lg p-5 flex flex-col justify-between shadow-sm">
            <span className="text-3xl font-mono font-medium text-[#ede8dd] leading-none mb-2">
              {totalPages}
            </span>
            <span className="font-mono text-xs text-[#9c978f]">Pages</span>
          </div>

          {/* Card 3: Indexed Passages */}
          <div className="bg-[#1a1918] border border-[#282725] rounded-lg p-5 flex flex-col justify-between shadow-sm">
            <span className="text-3xl font-mono font-medium text-[#ede8dd] leading-none mb-2">
              {totalPassages.toLocaleString()}
            </span>
            <span className="font-mono text-xs text-[#9c978f]">Indexed passages</span>
          </div>

          {/* Card 4: Index Status */}
          <div className="bg-[#1a1918] border border-[#282725] rounded-lg p-5 flex flex-col justify-between shadow-sm">
            <span className="text-3xl font-mono font-medium text-[#3ea877] leading-none mb-2">
              Synced
            </span>
            <span className="font-mono text-xs text-[#9c978f]">Index status</span>
          </div>
        </section>

        {/* Search and Action Bar with SOP Q&A */}
        <section className="space-y-3" data-purpose="search-and-action-bar">
          <form 
            onSubmit={(e) => { e.preventDefault(); handleAskKnowledge(searchQuery); }}
            className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3"
          >
            <div className="relative flex-1">
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Query indexed SOP clauses, emergency limits, or isolation procedures..."
                className="w-full bg-[#1a1918] border border-[#282725] rounded-md px-4 py-2.5 text-xs font-mono text-[#ede8dd] placeholder-[#63605a] focus:outline-none focus:border-[#bd5b38] focus:ring-1 focus:ring-[#bd5b38] transition-all shadow-inner"
              />
            </div>

            <div className="flex items-center gap-2.5">
              <button
                type="submit"
                disabled={isAsking || !searchQuery.trim()}
                className="px-5 py-2.5 bg-[#bd5b38] hover:bg-[#a74f30] disabled:opacity-40 text-white rounded-md text-xs font-mono font-medium transition-all shadow-sm cursor-pointer flex items-center gap-2"
              >
                {isAsking ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Analyzing...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Query SOPs</span>
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={onOpenIngestModal}
                className="px-4 py-2.5 bg-[#1a1918] hover:bg-[#22211e] border border-[#282725] text-[#ede8dd] rounded-md text-xs font-mono font-medium transition-all whitespace-nowrap cursor-pointer"
              >
                Ingest document
              </button>
            </div>
          </form>

          {/* Quick Suggested SOP Questions */}
          <div className="flex flex-wrap gap-2 pt-1 font-mono text-[11px]">
            <span className="text-[#757069] flex items-center gap-1 text-[10.5px]">
              <MessageSquare className="w-3 h-3 text-[#bd5b38]" />
              <span>Suggested:</span>
            </span>
            {sampleQuestions.map((sq, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  setSearchQuery(sq);
                  handleAskKnowledge(sq);
                }}
                className="px-2.5 py-1 rounded bg-[#181716] hover:bg-[#22201d] text-[#a8a39a] hover:text-[#ede8dd] border border-[#282725] transition-colors cursor-pointer text-left truncate max-w-sm"
              >
                {sq}
              </button>
            ))}
          </div>

          {/* Active Sovereign Q&A Answer Card */}
          {qaAnswer && (
            <div className="p-5 rounded-xl bg-[#181716] border border-[#bd5b38]/50 shadow-xl space-y-3 animate-in fade-in duration-200">
              <div className="flex items-center justify-between pb-2 border-b border-[#282624] text-xs font-mono text-[#8e8982]">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#3ea877] shadow-[0_0_6px_rgba(62,168,119,0.5)]" />
                  <ModelHoverTooltip modelId={qaAnswer.modelUsed} position="bottom">
                    <span className="font-semibold text-[#ede8dd] hover:underline cursor-pointer">{qaAnswer.modelUsed}</span>
                  </ModelHoverTooltip>
                  <span className="text-[10px] text-[#757069]">· {qaAnswer.latencyMs} ms</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleCopyAnswer}
                    className="flex items-center gap-1 px-2.5 py-1 rounded bg-[#201f1c] hover:bg-[#262522] text-[#ede8dd] text-[11px] transition-colors cursor-pointer border border-[#2c2a26]"
                  >
                    {copiedAnswer ? (
                      <>
                        <Check className="w-3 h-3 text-[#3ea877]" />
                        <span className="text-[#3ea877]">Copied</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3 h-3 text-[#757069]" />
                        <span>Copy</span>
                      </>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => setQaAnswer(null)}
                    className="text-[#757069] hover:text-[#ede8dd] p-1 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <div className="text-xs font-mono text-[#a8a39a]">
                <strong>Query:</strong> {qaAnswer.question}
              </div>

              <div className="text-xs text-[#ede8dd] leading-relaxed whitespace-pre-wrap font-sans bg-[#131211] p-4 rounded-lg border border-[#242320]">
                {qaAnswer.answer}
              </div>
            </div>
          )}
        </section>

        {/* Indexed Documents Section matching screenshot 1 */}
        <section className="space-y-3 pt-1" data-purpose="indexed-documents-table">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-mono font-semibold text-[#ede8dd] tracking-tight uppercase">
                Indexed documents
              </h2>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#201f1c] border border-[#2b2926] text-[#757069]">
                nomic-embed-text
              </span>
            </div>
            <span className="text-xs font-mono text-[#63605a]">
              {filteredDocs.length} {filteredDocs.length === 1 ? 'source' : 'sources'}
            </span>
          </div>

          <div className="space-y-2">
            {filteredDocs.map((doc) => (
              <article
                key={doc.id}
                onClick={() => onSelectDocument(doc)}
                className="bg-[#1a1918] border border-[#282725] hover:border-[#383633] rounded-md px-4 py-3 flex items-center justify-between transition-colors group cursor-pointer"
              >
                <div className="flex items-center gap-3.5">
                  {/* Document Icon */}
                  <div className="w-8 h-8 rounded bg-[#242321] border border-[#282725] flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-[#63605a] group-hover:text-[#9c978f] transition-colors" />
                  </div>
                  {/* Meta Info */}
                  <div className="flex flex-col">
                    <span className="text-xs font-mono font-semibold text-[#ede8dd] tracking-tight group-hover:text-[#bd5b38] transition-colors">
                      {doc.title}
                    </span>
                    <span className="text-[11px] font-mono text-[#63605a] mt-0.5">
                      {doc.code} · {doc.rev} · {doc.pages} pages
                    </span>
                  </div>
                </div>

                {/* Category Badge & Index Status */}
                <div className="flex items-center gap-6">
                  <span className="px-2.5 py-0.5 rounded-full text-[10.5px] font-mono bg-[#232220] border border-[#282725] text-[#9c978f]">
                    {doc.category}
                  </span>
                  <span className="text-[11px] font-mono text-[#3ea877] font-medium w-14 text-right">
                    {doc.status}
                  </span>
                </div>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};
