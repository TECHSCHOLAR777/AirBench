import React, { useState } from 'react';
import { SopDocument } from '../types';
import { X, Upload, FileText, CheckCircle2, Loader2 } from 'lucide-react';

interface IngestDocModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngest: (doc: SopDocument) => void;
}

export const IngestDocModal: React.FC<IngestDocModalProps> = ({
  isOpen,
  onClose,
  onIngest
}) => {
  const [title, setTitle] = useState('');
  const [code, setCode] = useState('');
  const [rev, setRev] = useState('Rev 1');
  const [category, setCategory] = useState<SopDocument['category']>('Process');
  const [pages, setPages] = useState(12);
  const [sectionText, setSectionText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !code.trim()) return;

    setIsProcessing(true);
    setTimeout(() => {
      const newDoc: SopDocument = {
        id: `doc-${Date.now()}`,
        title: title.trim(),
        code: code.trim().toUpperCase(),
        rev: rev.trim(),
        pages: Number(pages) || 10,
        category,
        status: 'Indexed',
        passagesCount: (Number(pages) || 10) * 8,
        lastUpdated: new Date().toISOString().split('T')[0],
        sections: [
          {
            heading: '1.0 Enclave Ingested Standard Directive',
            text: sectionText.trim() || 'All isolation boundaries, interlock overrides, and pressure envelopes must be signed with cryptographic proof on the local worker node before physical line intervention.'
          },
          {
            heading: '2.0 Quality Assurance Compliance',
            text: 'Independent witness inspection required at 50% disassembly stage. Calibration records must be verified against ISO 9001 quality catalog.'
          }
        ]
      };

      onIngest(newDoc);
      setIsProcessing(false);
      onClose();
      // Reset
      setTitle('');
      setCode('');
      setSectionText('');
    }, 900);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div 
        className="w-full max-w-lg bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#282725] bg-[#1a1918]">
          <div className="flex items-center gap-2">
            <Upload className="w-4 h-4 text-[#bd5b38]" />
            <span className="font-semibold text-sm text-[#ede8dd]">
              Ingest Standard Operating Procedure
            </span>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className="text-[10px] uppercase text-[#757069] tracking-wider block mb-1">
              Document Title *
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="e.g. Steam methane reformer catalyst swap"
              className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-2 text-[#ede8dd] placeholder-[#63605a] focus:outline-none focus:border-[#bd5b38]"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-[10px] uppercase text-[#757069] tracking-wider block mb-1">
                SOP Code *
              </label>
              <input
                type="text"
                required
                value={code}
                onChange={e => setCode(e.target.value)}
                placeholder="SOP-PRC-042"
                className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-2 text-[#ede8dd] placeholder-[#63605a] focus:outline-none focus:border-[#bd5b38]"
              />
            </div>
            <div>
              <label className="text-[10px] uppercase text-[#757069] tracking-wider block mb-1">
                Revision
              </label>
              <input
                type="text"
                value={rev}
                onChange={e => setRev(e.target.value)}
                placeholder="Rev 1"
                className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-2 text-[#ede8dd] placeholder-[#63605a] focus:outline-none focus:border-[#bd5b38]"
              />
            </div>
            <div>
              <label className="text-[10px] uppercase text-[#757069] tracking-wider block mb-1">
                Page Count
              </label>
              <input
                type="number"
                min={1}
                value={pages}
                onChange={e => setPages(Number(e.target.value))}
                className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-2 text-[#ede8dd] focus:outline-none focus:border-[#bd5b38]"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] uppercase text-[#757069] tracking-wider block mb-1">
              Engineering Domain Discipline
            </label>
            <select
              value={category}
              onChange={e => setCategory(e.target.value as any)}
              className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-2 text-[#ede8dd] focus:outline-none focus:border-[#bd5b38]"
            >
              <option value="Process">Process</option>
              <option value="Maintenance">Maintenance</option>
              <option value="Safety">Safety</option>
              <option value="Quality">Quality</option>
              <option value="Inspection">Inspection</option>
              <option value="Engineering">Engineering</option>
              <option value="Operations">Operations</option>
              <option value="Environmental">Environmental</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] uppercase text-[#757069] tracking-wider block mb-1">
              Initial Clause / Isolation Text
            </label>
            <textarea
              rows={3}
              value={sectionText}
              onChange={e => setSectionText(e.target.value)}
              placeholder="Paste clause or boundary specification for vector passage indexing..."
              className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-2 text-[#ede8dd] placeholder-[#63605a] focus:outline-none focus:border-[#bd5b38] resize-none"
            />
          </div>

          <div className="p-3 bg-[#141312] rounded border border-[#262422] text-[11px] text-[#757069]">
            Passages are vectorized locally via <code className="text-[#ede8dd]">nomic-embed-text</code> loopback. Zero cloud egress guaranteed.
          </div>

          {/* Footer actions */}
          <div className="pt-2 flex items-center justify-end gap-2 border-t border-[#262422]">
            <button
              type="button"
              onClick={onClose}
              disabled={isProcessing}
              className="px-3.5 py-2 rounded bg-[#201f1c] hover:bg-[#282623] text-[#ede8dd] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isProcessing}
              className="px-4 py-2 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white font-medium flex items-center gap-1.5 transition-colors"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Indexing Passages...</span>
                </>
              ) : (
                <span>Ingest &amp; Index Document</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
