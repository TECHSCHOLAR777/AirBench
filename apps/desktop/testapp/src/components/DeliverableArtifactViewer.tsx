import React, { useState } from 'react';
import { ReviewDeliverable, DeliverableFormat } from '../types';
import { 
  FileText, 
  Download, 
  Copy, 
  Check, 
  Table, 
  Presentation, 
  FileCode, 
  File, 
  Loader2
} from 'lucide-react';
import { downloadDeliverable } from '../services/inferenceService';

interface DeliverableArtifactViewerProps {
  deliverable: ReviewDeliverable;
  onCopy?: (text: string) => void;
}

export const DeliverableArtifactViewer: React.FC<DeliverableArtifactViewerProps> = ({
  deliverable,
  onCopy
}) => {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // Format is locked to the user pre-send selection — no post-send changing
  const format: DeliverableFormat = (deliverable.format && deliverable.format !== 'auto')
    ? deliverable.format
    : 'docx';

  const handleCopy = () => {
    navigator.clipboard.writeText(deliverable.content);
    setCopied(true);
    if (onCopy) onCopy(deliverable.content);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadDeliverable(format, deliverable.title, deliverable.content, deliverable.sourceFile);
    } catch (err: any) {
      setDownloadError(err?.message || 'Download failed. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  const formatMeta: Record<DeliverableFormat, {
    label: string; ext: string; color: string; bgColor: string; borderColor: string; icon: React.ReactNode;
  }> = {
    docx: {
      label: 'Word Document', ext: '.docx', color: '#3b82f6',
      bgColor: 'rgba(59,130,246,0.08)', borderColor: 'rgba(59,130,246,0.22)',
      icon: <FileText className="w-5 h-5" style={{ color: '#3b82f6' }} />
    },
    pdf: {
      label: 'PDF Document', ext: '.pdf', color: '#ef4444',
      bgColor: 'rgba(239,68,68,0.08)', borderColor: 'rgba(239,68,68,0.22)',
      icon: <FileText className="w-5 h-5" style={{ color: '#ef4444' }} />
    },
    pptx: {
      label: 'PowerPoint Deck', ext: '.pptx', color: '#ea580c',
      bgColor: 'rgba(234,88,12,0.08)', borderColor: 'rgba(234,88,12,0.22)',
      icon: <Presentation className="w-5 h-5" style={{ color: '#ea580c' }} />
    },
    xlsx: {
      label: 'Excel Spreadsheet', ext: '.xlsx', color: '#16a34a',
      bgColor: 'rgba(22,163,74,0.08)', borderColor: 'rgba(22,163,74,0.22)',
      icon: <Table className="w-5 h-5" style={{ color: '#16a34a' }} />
    },
    md: {
      label: 'Markdown Report', ext: '.md', color: '#a855f7',
      bgColor: 'rgba(168,85,247,0.08)', borderColor: 'rgba(168,85,247,0.22)',
      icon: <File className="w-5 h-5" style={{ color: '#a855f7' }} />
    },
    py: {
      label: 'Python Script', ext: '.py', color: '#06b6d4',
      bgColor: 'rgba(6,182,212,0.08)', borderColor: 'rgba(6,182,212,0.22)',
      icon: <FileCode className="w-5 h-5" style={{ color: '#06b6d4' }} />
    },
    auto: {
      label: 'Word Document', ext: '.docx', color: '#3b82f6',
      bgColor: 'rgba(59,130,246,0.08)', borderColor: 'rgba(59,130,246,0.22)',
      icon: <FileText className="w-5 h-5" style={{ color: '#3b82f6' }} />
    }
  };

  const meta = formatMeta[format] || formatMeta.docx;
  const safeFilename = deliverable.title
    .replace(/[^a-zA-Z0-9_\-\s]/g, '')
    .trim()
    .replace(/\s+/g, '_') || 'deliverable';

  return (
    <div className="mt-4 pt-3 border-t border-[#262422]">
      <div
        className="rounded-xl p-3 sm:p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-all"
        style={{ background: meta.bgColor, border: `1px solid ${meta.borderColor}` }}
      >
        {/* Left: icon + file info */}
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0 border"
            style={{ background: 'rgba(0,0,0,0.25)', borderColor: meta.borderColor }}
          >
            {meta.icon}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-semibold text-[#ede8dd] truncate">
                {safeFilename}{meta.ext}
              </span>
              <span
                className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded uppercase shrink-0"
                style={{ color: meta.color, background: 'rgba(0,0,0,0.3)', border: `1px solid ${meta.borderColor}` }}
              >
                {format.toUpperCase()}
              </span>
            </div>
            <div className="text-[11px] text-[#9c978f] flex items-center gap-2 mt-0.5 font-sans">
              <span>{deliverable.sourceFile ? `From ${deliverable.sourceFile.name}` : meta.label}</span>
              <span>·</span>
              <span>{deliverable.metadata?.tokens || Math.round(deliverable.content.length / 4)} tokens</span>
              <span>·</span>
              <span style={{ color: '#3ea877' }} className="font-medium">{deliverable.sourceFile ? 'Converted' : 'Ready'}</span>
            </div>
          </div>
        </div>

        {/* Right: Copy + Download */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={handleCopy}
            className="p-1.5 rounded-lg border border-[#2e2c28] bg-[#1a1917] hover:bg-[#22211e] text-[#8e8982] hover:text-[#ede8dd] transition-colors cursor-pointer"
            title="Copy text content"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-[#3ea877]" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-white text-xs font-mono font-medium shadow-sm transition-all cursor-pointer disabled:opacity-50 hover:brightness-110 active:scale-95"
            style={{ background: meta.color }}
            title={`Download as ${meta.label}`}
          >
            {downloading
              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
              : <Download className="w-3.5 h-3.5" />
            }
            <span>{downloading ? 'Generating...' : `Download ${meta.ext}`}</span>
          </button>
        </div>
      </div>

      {downloadError && (
        <div className="mt-2 px-3 py-2 rounded-lg bg-[#2a1515] border border-[#ef4444]/30 text-xs text-[#ef8f8f] font-mono">
          ⚠ {downloadError}
        </div>
      )}
    </div>
  );
};