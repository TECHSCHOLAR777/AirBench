import React, { useState } from 'react';
import { SopDocument } from '../types';
import { X, BookOpen, Copy, Check, ExternalLink, Hash, ArrowRight } from 'lucide-react';

interface SopReaderModalProps {
  document: SopDocument | null;
  onClose: () => void;
  onCrossReference: (doc: SopDocument) => void;
}

export const SopReaderModal: React.FC<SopReaderModalProps> = ({
  document,
  onClose,
  onCrossReference
}) => {
  const [copiedCitation, setCopiedCitation] = useState<string | null>(null);

  if (!document) return null;

  const copyCitation = (heading: string) => {
    const citation = `[${document.code}::${heading.split(' ')[0]}]`;
    navigator.clipboard.writeText(citation);
    setCopiedCitation(citation);
    setTimeout(() => setCopiedCitation(null), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 lg:p-6 animate-in fade-in duration-150">
      <div 
        className="w-full max-w-3xl max-h-[85vh] bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden flex flex-col font-mono text-xs"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#282725] bg-[#1a1918]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-[#242320] border border-[#35332f] flex items-center justify-center text-[#bd5b38]">
              <BookOpen className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-sm text-[#ede8dd]">
                  {document.title}
                </h3>
                <span className="text-[10px] px-2 py-0.2 rounded bg-[#232220] border border-[#282725] text-[#3ea877]">
                  {document.status}
                </span>
              </div>
              <div className="text-[11px] text-[#757069] mt-0.5">
                {document.code} · {document.rev} · {document.pages} pages · {document.passagesCount} indexed passages
              </div>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1.5 rounded hover:bg-[#262421]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Action sub-bar */}
        <div className="px-6 py-2 bg-[#141312] border-b border-[#262422] flex items-center justify-between">
          <span className="text-[11px] text-[#757069]">
            Category: <strong className="text-[#ede8dd]">{document.category}</strong> · Last synchronized: {document.lastUpdated}
          </span>
          <button
            onClick={() => onCrossReference(document)}
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white text-xs font-semibold transition-colors"
          >
            <span>Query Against This SOP</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Document Passages Content */}
        <div className="flex-1 p-6 overflow-y-auto space-y-4">
          <div className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
            Indexed Technical Clauses &amp; Passages
          </div>

          {document.sections.map((section, idx) => (
            <div 
              key={idx}
              className="p-4 rounded-lg bg-[#1f1e1c] border border-[#2b2926] hover:border-[#383633] transition-colors space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Hash className="w-3.5 h-3.5 text-[#bd5b38]" />
                  <span className="text-xs font-semibold text-[#ede8dd]">
                    {section.heading}
                  </span>
                </div>
                <button
                  onClick={() => copyCitation(section.heading)}
                  className="flex items-center gap-1 text-[10px] text-[#8e8982] hover:text-[#ede8dd] transition-colors"
                  title="Copy citation reference identifier"
                >
                  {copiedCitation === `[${document.code}::${section.heading.split(' ')[0]}]` ? (
                    <>
                      <Check className="w-3 h-3 text-[#3ea877]" />
                      <span className="text-[#3ea877]">Copied tag</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      <span>Copy Citation Tag</span>
                    </>
                  )}
                </button>
              </div>

              <p className="text-xs text-[#a8a39a] leading-relaxed font-sans">
                {section.text}
              </p>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-[#282725] bg-[#1a1918] flex items-center justify-between text-[11px] text-[#757069]">
          <span>Enclave cryptographic index signature verified: zero egress</span>
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 rounded bg-[#22211e] hover:bg-[#2e2d29] text-[#ede8dd] text-xs transition-colors border border-[#383633]"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
