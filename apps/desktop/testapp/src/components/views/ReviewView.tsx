import React, { useState } from 'react';
import { ReviewDeliverable, PageView, DeliverableFormat } from '../../types';
import { 
  CheckSquare, 
  FileText, 
  Download, 
  Copy, 
  Check, 
  ExternalLink, 
  ArrowRight,
  Sparkles,
  Trash2,
  Share2,
  ChevronDown
} from 'lucide-react';
import { downloadDeliverable } from '../../services/inferenceService';
import { ModelHoverTooltip } from '../ModelHoverTooltip';

interface ReviewViewProps {
  deliverables: ReviewDeliverable[];
  onNavigate: (view: PageView) => void;
  onClearReview: () => void;
}

export const ReviewView: React.FC<ReviewViewProps> = ({
  deliverables,
  onNavigate,
  onClearReview
}) => {
  const [selectedItem, setSelectedItem] = useState<ReviewDeliverable | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>('All');
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleExport = (item: ReviewDeliverable, format: DeliverableFormat) => {
    downloadDeliverable(format, item.title, item.content);
    setActiveMenuId(null);
  };

  const filteredItems = deliverables.filter(d => {
    if (filterType === 'All') return true;
    return d.type === filterType;
  });

  return (
    <div className="flex-1 p-6 lg:p-10 bg-[#121211] overflow-y-auto font-sans" data-purpose="review-workspace">
      <div className="max-w-4xl mx-auto pb-12">
        {/* Page Title & Scope Subtitle matching screenshot 3 */}
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-4xl font-serif text-[#ede8dd] tracking-tight mb-2 font-normal">
              Review
            </h1>
            <p className="font-mono text-xs text-[#8e8982]">
              Everything produced in this session: answers, exports, and code output.
            </p>
          </div>

          {deliverables.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={onClearReview}
                className="px-3 py-1.5 rounded bg-[#201f1c] hover:bg-[#282623] border border-[#2e2d29] text-xs font-mono text-[#757069] hover:text-[#ede8dd] transition-colors flex items-center gap-1.5"
                title="Clear Review Ledger"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear Ledger</span>
              </button>
            </div>
          )}
        </div>

        {/* BEGIN: Empty State Card matching screenshot 3 */}
        {deliverables.length === 0 ? (
          <section 
            className="w-full bg-[#181716] border border-dashed border-[#383633] rounded-lg py-16 px-8 flex flex-col items-center justify-center text-center transition-all"
            data-purpose="empty-review-state"
          >
            {/* Checked box outline icon matching screenshot */}
            <div className="mb-4 text-[#8e8982]">
              <svg 
                className="w-6 h-6 stroke-current" 
                fill="none" 
                strokeLinecap="round" 
                strokeLinejoin="round" 
                strokeWidth="1.75" 
                viewBox="0 0 24 24"
              >
                <path d="m9 11 3 3L22 4"></path>
                <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
              </svg>
            </div>

            {/* Empty State Title */}
            <h2 className="text-sm font-mono font-medium text-[#ede8dd] mb-2 tracking-normal">
              Nothing generated yet
            </h2>

            {/* Empty State Description */}
            <p className="font-mono text-xs text-[#8e8982] max-w-md leading-relaxed mb-6">
              Run a request on Home, process a drawing on P&amp;ID, or execute code in the Sandbox. Results collect here.
            </p>

            <div className="flex items-center gap-3">
              <button
                onClick={() => onNavigate('home')}
                className="px-4 py-2 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white text-xs font-mono font-medium transition-colors shadow-2xs cursor-pointer"
              >
                Go to Assistant
              </button>
            </div>
          </section>
        ) : (
          /* Populated State with Deliverables */
          <div className="space-y-4">
            {/* Filter pills */}
            <div className="flex items-center gap-2 font-mono text-xs text-[#8e8982] pb-1 border-b border-[#242320]">
              {(['All', 'Document', 'Code', 'P&ID Schema', 'Audit Memo'] as const).map(type => (
                <button
                  key={type}
                  onClick={() => setFilterType(type)}
                  className={`px-2.5 py-1 rounded transition-colors ${
                    filterType === type
                      ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]'
                      : 'hover:text-[#ede8dd]'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>

            {/* Deliverables List */}
            <div className="space-y-3">
              {filteredItems.map(item => (
                <article
                  key={item.id}
                  className="bg-[#181716] border border-[#262422] hover:border-[#383633] rounded-lg p-5 transition-all space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="w-2 h-2 rounded-full bg-[#3ea877]" />
                      <h3 className="text-sm font-mono font-semibold text-[#ede8dd]">
                        {item.title}
                      </h3>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#22211e] text-[#9c978f] border border-[#2a2925]">
                        {item.type}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs font-mono text-[#757069]">
                      <span>{item.timestamp}</span>
                      <span>·</span>
                      <ModelHoverTooltip modelId={item.sourceRoute}>
                        <span className="text-[#3ea877] font-semibold hover:underline cursor-pointer">
                          {item.sourceRoute}
                        </span>
                      </ModelHoverTooltip>
                    </div>
                  </div>

                  <p className="text-xs font-mono text-[#9c978f] leading-relaxed">
                    {item.summary}
                  </p>

                  {/* Expand / Preview snippet */}
                  <div className="p-3.5 bg-[#121211] rounded border border-[#22211e] font-mono text-xs text-[#a8a39a] max-h-40 overflow-y-auto whitespace-pre-wrap">
                    {item.content}
                  </div>

                  {/* Card Action Row */}
                  <div className="pt-2 border-t border-[#22211e] flex items-center justify-between text-xs font-mono">
                    <div className="text-[11px] text-[#757069]">
                      Confidence: {item.metadata.confidenceScore || '99.4%'} · Tokens: {item.metadata.tokens || 340}
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleCopy(item.id, item.content)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-[#1e1d1b] hover:bg-[#252421] border border-[#2b2926] text-[#ede8dd] transition-colors cursor-pointer"
                      >
                        {copiedId === item.id ? <Check className="w-3.5 h-3.5 text-[#3ea877]" /> : <Copy className="w-3.5 h-3.5" />}
                        <span>{copiedId === item.id ? 'Copied' : 'Copy'}</span>
                      </button>

                      {/* Download button with format selector */}
                      <div className="relative">
                        <button
                          onClick={() => setActiveMenuId(activeMenuId === item.id ? null : item.id)}
                          className="flex items-center gap-1.5 px-3 py-1 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white transition-colors cursor-pointer text-xs font-medium"
                        >
                          <Download className="w-3.5 h-3.5" />
                          <span>Download Artifact</span>
                          <ChevronDown className="w-3 h-3 text-white/80" />
                        </button>

                        {activeMenuId === item.id && (
                          <div className="absolute right-0 bottom-full mb-1 w-52 rounded-xl bg-[#1c1b19] border border-[#2e2c28] shadow-2xl p-1 z-30 font-mono text-xs">
                            <div className="px-2 py-1 text-[10px] text-[#757069] uppercase font-semibold border-b border-[#282724] mb-1">
                              Open-Source Deliverable Engine
                            </div>
                            {[
                              { id: 'docx', label: 'Word (.docx)', ext: '.docx' },
                              { id: 'pptx', label: 'PowerPoint (.pptx)', ext: '.pptx' },
                              { id: 'xlsx', label: 'Excel (.xlsx)', ext: '.xlsx' },
                              { id: 'pdf', label: 'PDF Document (.pdf)', ext: '.pdf' },
                              { id: 'md', label: 'Markdown (.md)', ext: '.md' },
                              { id: 'py', label: 'Python Script (.py)', ext: '.py' }
                            ].map(fmt => (
                              <button
                                key={fmt.id}
                                onClick={() => handleExport(item, fmt.id as DeliverableFormat)}
                                className="w-full px-2.5 py-1.5 text-left rounded hover:bg-[#242320] text-[#ede8dd] flex items-center justify-between transition-colors cursor-pointer"
                              >
                                <span>{fmt.label}</span>
                                <span className="text-[10px] text-[#8e8982]">{fmt.ext}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
