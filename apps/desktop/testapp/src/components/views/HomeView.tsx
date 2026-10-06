import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ChatMessage, PageView, ConversationSession, DeliverableFormat, AttachedFileMeta } from '../../types';
import { 
  Paperclip, 
  FileText, 
  Zap, 
  ChevronDown, 
  ArrowRight, 
  Check, 
  ShieldCheck, 
  Cpu, 
  FileCode, 
  Download, 
  X, 
  MessageSquare, 
  Trash2, 
  Plus, 
  Search, 
  Presentation, 
  Table, 
  FileSpreadsheet, 
  GripVertical, 
  File, 
  Clock, 
  Sparkles,
  ChevronRight,
  RefreshCw,
  Loader2
} from 'lucide-react';
import { ModelHoverTooltip, MODEL_REGISTRY, resolveModelKey } from '../ModelHoverTooltip';
import { DeliverableArtifactViewer } from '../DeliverableArtifactViewer';
import { ChatMarkdown } from '../ChatMarkdown';

export const SOVEREIGN_ROUTE_GROUPS = [
  {
    category: 'Agentic Tool-Use & Planning',
    items: [
      { label: 'Auto Dispatch (Enclave Router)', key: 'auto', role: 'Dynamic task-aware routing' },
      { label: 'Gemma 4 31B (Agentic Tool-Use / Planning)', key: 'gemma-4-31b', role: 'Dense 31B · Multi-step tool planning' },
      { label: 'Gemma 4 26B-A4B (Fast-Lane / Quick Queries)', key: 'gemma-4-26b-a4b', role: 'Active 4B MoE · Sub-50ms latency' },
      { label: 'Closed Frontier Models (Long Multi-Step Chains)', key: 'closed-frontier', role: 'Frontier Orchestrator · Multi-step reasoning' }
    ]
  },
  {
    category: 'Vision, Documents & OCR',
    items: [
      { label: 'Gemma 4 31B+26B-A4B Pipeline (Scanned Doc/VLM)', key: 'gemma-4-vlm-pipeline', role: 'Scanned document & drawing reading VLM' },
      { label: 'PaddleOCRVL (Printed Text OCR / Coords)', key: 'paddle-ocr-vl', role: 'Bounding box coordinates & confidence' },
      { label: 'TrOCR-Large + Gemma 4 (Handwriting Recognition)', key: 'trocr-large-gemma4', role: 'Field markups & redline transcription' }
    ]
  },
  {
    category: 'P&ID Digitization & Topology',
    items: [
      { label: 'YOLOv8 / YOLO11 (P&ID Symbol Detection)', key: 'yolo-pid', role: 'Fine-tuned ISA-5.1 symbol detector' },
      { label: 'Relationformer (Connectivity & Topology)', key: 'relationformer', role: 'Topology reconstruction & GraphML' }
    ]
  },
  {
    category: 'Retrieval & Reranking (RAG)',
    items: [
      { label: 'BGE-M3 (Embedding / Retrieval RAG)', key: 'bge-m3', role: '1024d Dense + Sparse vector retrieval' },
      { label: 'bge-reranker-v2-m3 (Reranking Retrieved Chunks)', key: 'bge-reranker-v2-m3', role: 'Cross-encoder relevance scoring' }
    ]
  },
  {
    category: 'Numerical Solvers',
    items: [
      { label: 'Qwen 2.5 Coder 7B (Numerical & Physics Solvers)', key: 'qwen2.5-coder-7b', role: 'Colebrook-White friction solvers' }
    ]
  }
];

interface HomeViewProps {
  sessions: ConversationSession[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
  onClearAllSessions?: () => void;
  onSendMessage: (
    text: string, 
    deliverableType: DeliverableFormat, 
    route: string, 
    attachedFiles?: AttachedFileMeta[]
  ) => void;
  onNavigate: (view: PageView) => void;
}

export const HomeView: React.FC<HomeViewProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onClearAllSessions,
  onSendMessage,
  onNavigate
}) => {
  // Input composer state
  const [prompt, setPrompt] = useState('');
  const [selectedRoute, setSelectedRoute] = useState('Auto Dispatch (Enclave Router)');
  const [selectedDeliverable, setSelectedDeliverable] = useState<DeliverableFormat>('auto');
  const [routeDropdownOpen, setRouteDropdownOpen] = useState(false);
  const [bottomRouteDropdownOpen, setBottomRouteDropdownOpen] = useState(false);
  const [deliverableDropdownOpen, setDeliverableDropdownOpen] = useState(false);
  const [bottomDeliverableDropdownOpen, setBottomDeliverableDropdownOpen] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFileMeta[]>([]);
  const [searchHistoryQuery, setSearchHistoryQuery] = useState('');
  const [keyPoolStatus, setKeyPoolStatus] = useState<{ totalKeys: number; currentIndex: number } | null>(null);

  // Poll or fetch round-robin status on mount
  useEffect(() => {
    fetch('/api/keys/status')
      .then(res => res.json())
      .then(data => {
        if (data && typeof data.totalKeys === 'number') {
          setKeyPoolStatus(data);
        }
      })
      .catch(() => {});
  }, []);

  // Right sidebar draggable width state (default 360px, min 260px, max 640px)
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => {
    const saved = localStorage.getItem('airbench_conv_sidebar_width');
    return saved ? Math.min(640, Math.max(260, parseInt(saved, 10))) : 380;
  });
  const [isDragging, setIsDragging] = useState(false);

  // References
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const routeDropdownRef = useRef<HTMLDivElement>(null);
  const deliverableDropdownRef = useRef<HTMLDivElement>(null);

  // Active session object
  const activeSession = sessions.find(s => s.id === activeSessionId) || null;
  const messages = activeSession ? activeSession.messages : [];

  // Auto-scroll when messages change
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
    }
  }, [messages.length, activeSessionId]);

  // Click outside to close dropdowns
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (routeDropdownRef.current && !routeDropdownRef.current.contains(e.target as Node)) {
        setRouteDropdownOpen(false);
      }
      if (deliverableDropdownRef.current && !deliverableDropdownRef.current.contains(e.target as Node)) {
        setDeliverableDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Draggable sidebar resizing logic
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      // Sidebar is on the right, so width is (window.innerWidth - e.clientX)
      const newWidth = Math.min(640, Math.max(260, window.innerWidth - e.clientX));
      setSidebarWidth(newWidth);
      localStorage.setItem('airbench_conv_sidebar_width', newWidth.toString());
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  // Handle native file selection (.doc, .docx, .ppt, .pptx, .xls, .xlsx, .pdf, .md, .txt, etc.)
  const handleFilesSelected = (files: FileList | null) => {
    if (!files || files.length === 0) return;

    Array.from(files).forEach(file => {
      const ext = '.' + (file.name.split('.').pop() || '').toLowerCase();
      let type: AttachedFileMeta['type'] = 'other';

      if (['.doc', '.docx'].includes(ext)) type = 'doc';
      else if (['.ppt', '.pptx'].includes(ext)) type = 'ppt';
      else if (['.xls', '.xlsx', '.csv'].includes(ext)) type = 'excel';
      else if (['.pdf'].includes(ext)) type = 'pdf';
      else if (['.md', '.markdown'].includes(ext)) type = 'md';
      else if (['.py', '.js', '.ts', '.cpp', '.c', '.graphml', '.xml', '.json'].includes(ext)) type = 'code';

      const fileId = `att-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
      const reader = new FileReader();

      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        const newAttachment: AttachedFileMeta = {
          id: fileId,
          name: file.name,
          size: file.size,
          type,
          extension: ext,
          dataUrl
        };
        setAttachedFiles(prev => [...prev, newAttachment]);
      };

      reader.onerror = () => {
        const newAttachment: AttachedFileMeta = {
          id: fileId,
          name: file.name,
          size: file.size,
          type,
          extension: ext
        };
        setAttachedFiles(prev => [...prev, newAttachment]);
      };

      reader.readAsDataURL(file);
    });
  };

  const handleRemoveAttachment = (id: string) => {
    setAttachedFiles(prev => prev.filter(f => f.id !== id));
  };

  const handleSend = () => {
    const textToSend = prompt.trim() || (attachedFiles.length > 0 ? `Process and convert attached file: ${attachedFiles.map(f => f.name).join(', ')}` : '');
    if (!textToSend) return;
    onSendMessage(textToSend, selectedDeliverable, selectedRoute, attachedFiles.length > 0 ? attachedFiles : undefined);
    setPrompt('');
    setAttachedFiles([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleStarterClick = (starterText: string, deliverableType: DeliverableFormat) => {
    setPrompt(starterText);
    setSelectedDeliverable(deliverableType);
  };

  // Helper for file type icons & colors
  const getFileIcon = (type: AttachedFileMeta['type']) => {
    switch (type) {
      case 'doc': return <FileText className="w-3.5 h-3.5 text-[#3b82f6]" />;
      case 'ppt': return <Presentation className="w-3.5 h-3.5 text-[#ea580c]" />;
      case 'excel': return <FileSpreadsheet className="w-3.5 h-3.5 text-[#16a34a]" />;
      case 'pdf': return <FileText className="w-3.5 h-3.5 text-[#ef4444]" />;
      case 'md': return <FileCode className="w-3.5 h-3.5 text-[#a855f7]" />;
      case 'code': return <FileCode className="w-3.5 h-3.5 text-[#06b6d4]" />;
      default: return <File className="w-3.5 h-3.5 text-[#8e8982]" />;
    }
  };

  const deliverableOptions: { id: DeliverableFormat; label: string; ext: string; color: string }[] = [
    { id: 'auto', label: 'Standard Response', ext: 'Auto', color: '#3ea877' },
    { id: 'docx', label: 'Word Document', ext: '.docx', color: '#3b82f6' },
    { id: 'pptx', label: 'PowerPoint Deck', ext: '.pptx', color: '#ea580c' },
    { id: 'xlsx', label: 'Excel Spreadsheet', ext: '.xlsx', color: '#16a34a' },
    { id: 'pdf', label: 'PDF Document', ext: '.pdf', color: '#ef4444' },
    { id: 'md', label: 'Markdown Report', ext: '.md', color: '#a855f7' },
    { id: 'py', label: 'Python Code', ext: '.py', color: '#06b6d4' }
  ];

  // Filter history
  const filteredSessions = sessions.filter(s => {
    if (!searchHistoryQuery.trim()) return true;
    const q = searchHistoryQuery.toLowerCase();
    return s.title.toLowerCase().includes(q) || 
           s.lastQuerySnippet.toLowerCase().includes(q) || 
           s.deliverableType.toLowerCase().includes(q);
  });

  return (
    <div className="flex-1 flex overflow-hidden bg-[#121211] font-sans h-full">
      {/* Hidden native file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={(e) => handleFilesSelected(e.target.files)}
        multiple
        accept=".doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.pdf,.md,.txt,.py,.json,.graphml,.xml,.jpg,.jpeg,.png"
        className="hidden"
      />

      {/* CENTER / MAIN CONVERSATION WORKSPACE */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-[#121211]">
        {/* Top Sovereign Status Bar */}
        <header className="px-6 py-2.5 bg-[#141312] border-b border-[#242220] flex items-center justify-between text-xs font-mono text-[#8e8982] shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-[#3ea877] font-medium">
              <span className="w-2 h-2 rounded-full bg-[#3ea877] shadow-[0_0_8px_rgba(62,168,119,0.5)]" />
              <span>Sovereign Enclave Active</span>
            </div>
            <span className="text-[#363430]">|</span>
            <div className="flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-[#3ea877]" />
              <span className="text-[#ede8dd] font-semibold">Loopback 127.0.0.1:8000</span>
              <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#3ea877]/15 border border-[#3ea877]/30 text-[#3ea877]">
                Enclave Cluster: Online
              </span>
            </div>
            <span className="text-[#363430]">|</span>
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[#8e8982]" />
              <span className="text-[#a8a39a]">Strict Zero-Egress</span>
            </div>
            {activeSession && (
              <>
                <span className="text-[#363430]">|</span>
                <span className="text-[#ede8dd] truncate max-w-xs font-medium">
                  {activeSession.title}
                </span>
              </>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onNewSession}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1e1d1a] hover:bg-[#252420] text-[#ede8dd] border border-[#2e2c28] transition-colors cursor-pointer text-xs"
              title="Start a new conversation"
            >
              <Plus className="w-3.5 h-3.5 text-[#bd5b38]" />
              <span>New Query</span>
            </button>
          </div>
        </header>

        {/* Center Content Viewport */}
        {messages.length === 0 ? (
          /* STATE A: Initial Query Composer & Quick Launch (No active messages yet) */
          <div className="flex-1 overflow-y-auto p-6 lg:p-10 flex flex-col justify-center">
            <div className="max-w-3xl w-full mx-auto space-y-6">
              {/* Sovereign Hero Header */}
              <section className="space-y-1.5 text-center sm:text-left">
                <div className="font-mono text-[10.5px] uppercase tracking-widest text-[#8e8982] font-semibold flex items-center justify-center sm:justify-start gap-1.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-[#3ea877]" />
                  <span>Sovereign Task Command</span>
                </div>
                <h1 className="font-serif text-3xl sm:text-4xl font-normal text-[#ede8dd] tracking-tight">
                  AirBench Assistant
                </h1>
                <p className="text-xs sm:text-sm text-[#9c978f] leading-relaxed max-w-2xl font-sans">
                  Describe your engineering task. The system automatically routes queries to specialized local models, accepts multi-format files, and delivers validated Word, PowerPoint, Excel, PDF, and code artifacts.
                </p>
              </section>

              {/* Main Query Console Card */}
              <div className="bg-[#181716] border border-[#2b2925] rounded-xl shadow-xl overflow-hidden flex flex-col">
                <div className="p-3.5 bg-[#141312] border-b border-[#242320] flex items-center justify-between text-xs font-mono text-[#8e8982]">
                  <span className="font-semibold text-[#ede8dd]">New Engineering Query</span>
                  <span className="text-[11px] text-[#757069]">Press Enter to Run · Shift+Enter for newline</span>
                </div>

                <div className="p-4 space-y-3">
                  {/* Attached File Chips List */}
                  {attachedFiles.length > 0 && (
                    <div className="flex flex-wrap gap-2 pb-1">
                      {attachedFiles.map(file => (
                        <div 
                          key={file.id}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#201f1c] border border-[#33312c] text-xs font-mono text-[#ede8dd]"
                        >
                          {getFileIcon(file.type)}
                          <span className="truncate max-w-[180px]">{file.name}</span>
                          <span className="text-[10px] text-[#757069]">
                            ({(file.size / 1024).toFixed(0)} KB)
                          </span>
                          <button
                            type="button"
                            onClick={() => handleRemoveAttachment(file.id)}
                            className="text-[#757069] hover:text-[#ede8dd] ml-1 cursor-pointer"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Textarea */}
                  <textarea
                    value={prompt}
                    onChange={e => setPrompt(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Ask an engineering question, attach any document (.doc, .ppt, .excel, .pdf, .md), or select an output format..."
                    rows={4}
                    className="w-full bg-transparent text-[#ede8dd] placeholder-[#5c5852] font-sans text-sm resize-none focus:outline-none leading-relaxed"
                  />

                  {/* Prompt Controls Toolbar */}
                  <div className="pt-3 border-t border-[#262421] flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
                      {/* Attach Button (Files: doc, ppt, excel, pdf, md) */}
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#2e2c28] bg-[#1d1c1a] hover:bg-[#242320] text-[#ede8dd] transition-colors cursor-pointer"
                        title="Attach any document, presentation, spreadsheet, PDF, or markdown file"
                      >
                        <Paperclip className="w-3.5 h-3.5 text-[#bd5b38]" />
                        <span>Attach File</span>
                      </button>

                      {/* Deliverable Format Selector */}
                      <div className="relative" ref={deliverableDropdownRef}>
                        <button
                          type="button"
                          onClick={() => setDeliverableDropdownOpen(prev => !prev)}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#2e2c28] bg-[#1d1c1a] hover:bg-[#242320] text-[#ede8dd] transition-colors cursor-pointer"
                        >
                          <span 
                            className="w-2 h-2 rounded-full" 
                            style={{ backgroundColor: deliverableOptions.find(d => d.id === selectedDeliverable)?.color }}
                          />
                          <span>Output: {deliverableOptions.find(d => d.id === selectedDeliverable)?.label}</span>
                          <ChevronDown className="w-3 h-3 text-[#757069]" />
                        </button>

                        {deliverableDropdownOpen && (
                          <div className="absolute left-0 bottom-full mb-1 w-52 rounded-xl bg-[#1c1b19] border border-[#2e2c28] shadow-2xl p-1 z-40 font-mono text-xs">
                            <div className="px-2.5 py-1 text-[10px] text-[#757069] uppercase font-semibold border-b border-[#282724] mb-1">
                              Generated Deliverable Type
                            </div>
                            {deliverableOptions.map(opt => (
                              <button
                                key={opt.id}
                                type="button"
                                onClick={() => { setSelectedDeliverable(opt.id); setDeliverableDropdownOpen(false); }}
                                className={`w-full px-2.5 py-1.5 text-left rounded hover:bg-[#242320] transition-colors flex items-center justify-between cursor-pointer ${
                                  selectedDeliverable === opt.id ? 'text-[#ede8dd] bg-[#22201d]' : 'text-[#8e8982]'
                                }`}
                              >
                                <span className="flex items-center gap-2">
                                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: opt.color }} />
                                  <span>{opt.label}</span>
                                </span>
                                <span className="text-[10px] text-[#757069]">{opt.ext}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Role-Based Model Selector with Hover Tooltip */}
                      <div className="relative" ref={routeDropdownRef}>
                        <ModelHoverTooltip modelId={selectedRoute}>
                          <button
                            type="button"
                            onClick={() => setRouteDropdownOpen(prev => !prev)}
                            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-[#2e2c28] bg-[#1d1c1a] hover:bg-[#242320] text-[#ede8dd] transition-colors cursor-pointer"
                          >
                            <Zap className="w-3.5 h-3.5 text-[#3ea877]" />
                            <span className="truncate max-w-[150px]">{selectedRoute}</span>
                            <ChevronDown className="w-3 h-3 text-[#757069]" />
                          </button>
                        </ModelHoverTooltip>

                        {routeDropdownOpen && (
                          <div className="absolute left-0 bottom-full mb-1 w-80 max-h-[380px] overflow-y-auto rounded-xl bg-[#1c1b19] border border-[#2e2c28] shadow-2xl p-1 z-40 font-mono text-xs">
                            {SOVEREIGN_ROUTE_GROUPS.map((group, gIdx) => (
                              <div key={gIdx} className="mb-1.5 last:mb-0">
                                <div className="px-2.5 py-1 text-[9.5px] text-[#757069] uppercase font-semibold tracking-wider border-b border-[#282724] mb-0.5">
                                  {group.category}
                                </div>
                                {group.items.map(item => (
                                  <ModelHoverTooltip key={item.key} modelId={item.key} position="right">
                                    <button
                                      type="button"
                                      onClick={() => { setSelectedRoute(item.label); setRouteDropdownOpen(false); }}
                                      className={`w-full px-2.5 py-1.5 text-left rounded hover:bg-[#242320] transition-colors flex items-center justify-between cursor-pointer group ${
                                        selectedRoute === item.label ? 'text-[#bd5b38] bg-[#22201d]' : 'text-[#ede8dd]'
                                      }`}
                                    >
                                      <div className="truncate flex-1 pr-2">
                                        <div className="truncate font-medium">{item.label}</div>
                                        <div className="text-[10px] text-[#757069] truncate group-hover:text-[#a8a39a]">{item.role}</div>
                                      </div>
                                      {selectedRoute === item.label && <Check className="w-3.5 h-3.5 shrink-0 text-[#bd5b38]" />}
                                    </button>
                                  </ModelHoverTooltip>
                                ))}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Run CTA */}
                    <button
                      onClick={handleSend}
                      disabled={!prompt.trim()}
                      className="bg-[#bd5b38] hover:bg-[#a74f30] disabled:opacity-40 text-white text-xs font-mono font-medium px-4 py-2 rounded-lg flex items-center gap-2 shadow-sm transition-colors cursor-pointer"
                    >
                      <span>Run</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Quick Launch Scenarios Grid */}
              <div className="space-y-2">
                <span className="text-[11px] font-mono uppercase tracking-wider text-[#757069] block">
                  Quick Launch Scenarios
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 font-mono">
                  <button
                    onClick={() => handleStarterClick('Explain the thermodynamic differences between Otto and Diesel cycles with pressure-volume efficiency equations', 'auto')}
                    className="flex items-center gap-2.5 p-3 rounded-lg border border-[#2e2c28] bg-[#181716] hover:bg-[#201f1c] hover:border-[#bd5b38]/60 text-xs text-[#ede8dd] transition-all group cursor-pointer text-left"
                  >
                    <Cpu className="w-4 h-4 text-[#bd5b38] shrink-0" />
                    <span className="truncate">Thermodynamic cycle comparison</span>
                  </button>

                  <button
                    onClick={() => handleStarterClick('Prepare an executive technical briefing on industrial battery energy storage system (BESS) thermal runaway mitigation', 'pptx')}
                    className="flex items-center gap-2.5 p-3 rounded-lg border border-[#2e2c28] bg-[#181716] hover:bg-[#201f1c] hover:border-[#bd5b38]/60 text-xs text-[#ede8dd] transition-all group cursor-pointer text-left"
                  >
                    <Presentation className="w-4 h-4 text-[#ea580c] shrink-0" />
                    <span className="truncate">BESS thermal runaway slides</span>
                  </button>

                  <button
                    onClick={() => handleStarterClick('Synthesize a fluid dynamics friction comparison between Darcy-Weisbach and Hazen-Williams formulas', 'auto')}
                    className="flex items-center gap-2.5 p-3 rounded-lg border border-[#2e2c28] bg-[#181716] hover:bg-[#201f1c] hover:border-[#bd5b38]/60 text-xs text-[#ede8dd] transition-all group cursor-pointer text-left"
                  >
                    <Table className="w-4 h-4 text-[#16a34a] shrink-0" />
                    <span className="truncate">Fluid friction loss comparison</span>
                  </button>

                  <button
                    onClick={() => handleStarterClick('Draft a formal technical investigation report on mechanical seal degradation in centrifugal slurry pumps', 'docx')}
                    className="flex items-center gap-2.5 p-3 rounded-lg border border-[#2e2c28] bg-[#181716] hover:bg-[#201f1c] hover:border-[#bd5b38]/60 text-xs text-[#ede8dd] transition-all group cursor-pointer text-left"
                  >
                    <FileText className="w-4 h-4 text-[#3b82f6] shrink-0" />
                    <span className="truncate">Seal degradation report</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* STATE B: Active Conversation Stream In Center (After user puts query or selects past conversation) */
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
            {/* Conversation Messages Container */}
            <div 
              ref={scrollContainerRef}
              className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 space-y-6 max-w-4xl w-full mx-auto"
            >
              {messages.map((msg) => (
                <div 
                  key={msg.id}
                  className={`flex flex-col space-y-2 ${
                    msg.role === 'user' ? 'items-end' : 'items-start'
                  }`}
                >
                  {/* Meta details header with Model Hover Tooltip */}
                  <div className="flex items-center gap-2 text-[10.5px] font-mono text-[#757069] px-1">
                    <span>{msg.role === 'user' ? 'User Operator' : 'AirBench Sovereign Kernel'}</span>
                    <span>·</span>
                    <span>{msg.timestamp}</span>
                    {msg.role === 'assistant' && (msg.route || msg.deliverable?.sourceRoute) && (
                      <>
                        <span>·</span>
                        <ModelHoverTooltip modelId={msg.deliverable?.sourceRoute || msg.route}>
                          <span className="text-[#3ea877] font-semibold hover:underline cursor-pointer">
                            {msg.deliverable?.sourceRoute || msg.route}
                          </span>
                        </ModelHoverTooltip>
                      </>
                    )}
                  </div>

                  {/* Message Bubble */}
                  <div 
                    className={`rounded-xl p-4 text-xs sm:text-sm leading-relaxed max-w-full ${
                      msg.role === 'user'
                        ? 'bg-[#201f1c] text-[#ede8dd] border border-[#2e2c28] shadow-sm ml-8'
                        : 'bg-[#181716] text-[#e6e3dd] border border-[#2a2926] shadow-md w-full'
                    }`}
                  >
                    {/* Render user attached files if present */}
                    {msg.attachedFiles && msg.attachedFiles.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-3 pb-2 border-b border-[#2d2b27]">
                        {msg.attachedFiles.map(att => (
                          <div 
                            key={att.id}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#161514] border border-[#2e2c28] text-xs font-mono text-[#ede8dd]"
                          >
                            {getFileIcon(att.type)}
                            <span className="truncate max-w-[200px]">{att.name}</span>
                            <span className="text-[10px] text-[#757069]">({(att.size / 1024).toFixed(0)} KB)</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Generating indicator with clean chatbot feedback */}
                    {msg.isGenerating ? (
                      <div className="space-y-2 py-2">
                        <div className="flex items-center gap-3">
                          <Loader2 className="w-4 h-4 text-[#bd5b38] animate-spin shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-sans font-medium text-[#ede8dd]">
                              {msg.generatingPhase || 'Generating response...'}
                            </div>
                          </div>
                        </div>
                        {/* Animated progress bar */}
                        <div className="w-full bg-[#201f1c] rounded-full h-1 overflow-hidden border border-[#2e2c28]">
                          <div className="h-full bg-gradient-to-r from-[#bd5b38] to-[#ea580c] rounded-full animate-pulse transition-all duration-700 w-4/5" />
                        </div>
                      </div>
                    ) : (
                      <>
                        {/* Normal chatbot message body with rich markdown */}
                        <ChatMarkdown content={msg.text} />

                        {/* Deliverable Artifact Card - only downloads when user clicks download */}
                        {msg.deliverable && (
                          <DeliverableArtifactViewer deliverable={msg.deliverable} />
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Bottom Docked Conversation Composer Bar */}
            <div className="p-4 bg-[#141312] border-t border-[#242220] shrink-0">
              <div className="max-w-4xl mx-auto space-y-2.5">
                {/* Attached files preview */}
                {attachedFiles.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {attachedFiles.map(file => (
                      <div 
                        key={file.id}
                        className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-[#1e1d1b] border border-[#302e29] text-[11px] font-mono text-[#ede8dd]"
                      >
                        {getFileIcon(file.type)}
                        <span className="truncate max-w-[160px]">{file.name}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveAttachment(file.id)}
                          className="text-[#757069] hover:text-[#ede8dd] ml-1 cursor-pointer"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Input row */}
                <div className="flex items-center gap-2">
                  <div className="flex-1 bg-[#1a1917] border border-[#2e2c28] rounded-xl flex items-center px-3 py-1.5 focus-within:border-[#bd5b38] transition-colors">
                    <textarea
                      value={prompt}
                      onChange={e => setPrompt(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Ask a follow-up query, attach files, or specify calculations..."
                      rows={1}
                      className="flex-1 bg-transparent text-[#ede8dd] placeholder-[#5c5852] font-sans text-xs focus:outline-none resize-none py-1"
                    />

                    {/* Quick toolbar inside input */}
                    <div className="flex items-center gap-1.5 pl-2 font-mono text-xs">
                      {/* Attach File */}
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="p-1.5 text-[#8e8982] hover:text-[#ede8dd] hover:bg-[#252420] rounded transition-colors cursor-pointer"
                        title="Attach file (.doc, .ppt, .excel, .pdf, .md)"
                      >
                        <Paperclip className="w-3.5 h-3.5" />
                      </button>

                      {/* Deliverable dropdown */}
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setBottomDeliverableDropdownOpen(prev => !prev)}
                          className="px-2 py-1 rounded bg-[#22211e] hover:bg-[#292723] text-[#ede8dd] border border-[#2e2c28] text-[10.5px] flex items-center gap-1 cursor-pointer"
                          title="Select output format"
                        >
                          <span>{selectedDeliverable.toUpperCase()}</span>
                          <ChevronDown className="w-3 h-3 text-[#757069]" />
                        </button>

                        {bottomDeliverableDropdownOpen && (
                          <div className="absolute right-0 bottom-full mb-2 w-48 rounded-xl bg-[#1c1b19] border border-[#2e2c28] shadow-2xl p-1 z-50 font-mono text-xs">
                            {deliverableOptions.map(opt => (
                              <button
                                key={opt.id}
                                type="button"
                                onClick={() => { setSelectedDeliverable(opt.id); setBottomDeliverableDropdownOpen(false); }}
                                className={`w-full px-2 py-1.5 text-left rounded hover:bg-[#242320] flex items-center justify-between cursor-pointer ${
                                  selectedDeliverable === opt.id ? 'text-[#ede8dd] bg-[#22201d]' : 'text-[#8e8982]'
                                }`}
                              >
                                <span>{opt.label}</span>
                                <span className="text-[10px] text-[#757069]">{opt.ext}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Model Selector with Hover Tooltip */}
                      <div className="relative">
                        <ModelHoverTooltip modelId={selectedRoute}>
                          <button
                            type="button"
                            onClick={() => setBottomRouteDropdownOpen(prev => !prev)}
                            className="px-2 py-1 rounded bg-[#22211e] hover:bg-[#292723] text-[#ede8dd] border border-[#2e2c28] text-[10.5px] flex items-center gap-1 cursor-pointer truncate max-w-[130px]"
                          >
                            <Zap className="w-3 h-3 text-[#3ea877] shrink-0" />
                            <span className="truncate">
                              {selectedRoute.includes('31B') ? 'Gemma 4 31B' : 
                               selectedRoute.includes('26B') ? 'Gemma 4 26B' : 
                               selectedRoute.includes('Frontier') ? 'Frontier' : 
                               selectedRoute.includes('VLM') ? 'Gemma VLM' : 
                               selectedRoute.includes('Paddle') ? 'PaddleOCR' : 
                               selectedRoute.includes('TrOCR') ? 'TrOCR' : 
                               selectedRoute.includes('YOLO') ? 'YOLO11' : 
                               selectedRoute.includes('Relationformer') ? 'Relationformer' : 
                               selectedRoute.includes('BGE-M3') ? 'BGE-M3' : 
                               selectedRoute.includes('reranker') ? 'bge-rerank' : 
                               selectedRoute.split(' ')[0]}
                            </span>
                          </button>
                        </ModelHoverTooltip>

                        {bottomRouteDropdownOpen && (
                          <div className="absolute right-0 bottom-full mb-2 w-80 max-h-[360px] overflow-y-auto rounded-xl bg-[#1c1b19] border border-[#2e2c28] shadow-2xl p-1 z-50 font-mono text-xs">
                            {SOVEREIGN_ROUTE_GROUPS.map((group, gIdx) => (
                              <div key={gIdx} className="mb-1.5 last:mb-0">
                                <div className="px-2.5 py-1 text-[9.5px] text-[#757069] uppercase font-semibold tracking-wider border-b border-[#282724] mb-0.5">
                                  {group.category}
                                </div>
                                {group.items.map(item => (
                                  <ModelHoverTooltip key={item.key} modelId={item.key} position="left">
                                    <button
                                      type="button"
                                      onClick={() => { setSelectedRoute(item.label); setBottomRouteDropdownOpen(false); }}
                                      className={`w-full px-2.5 py-1.5 text-left rounded hover:bg-[#242320] transition-colors flex items-center justify-between cursor-pointer group ${
                                        selectedRoute === item.label ? 'text-[#bd5b38] bg-[#22201d]' : 'text-[#ede8dd]'
                                      }`}
                                    >
                                      <div className="truncate flex-1 pr-2">
                                        <div className="truncate font-medium">{item.label}</div>
                                        <div className="text-[10px] text-[#757069] truncate group-hover:text-[#a8a39a]">{item.role}</div>
                                      </div>
                                      {selectedRoute === item.label && <Check className="w-3.5 h-3.5 shrink-0 text-[#bd5b38]" />}
                                    </button>
                                  </ModelHoverTooltip>
                                ))}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Send Button */}
                  <button
                    onClick={handleSend}
                    disabled={!prompt.trim()}
                    className="p-2.5 rounded-xl bg-[#bd5b38] hover:bg-[#a74f30] disabled:opacity-40 text-white transition-colors cursor-pointer shrink-0 shadow-sm"
                  >
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* DRAGGABLE RESIZE DIVIDER (User can drag to increase/decrease right sidebar width) */}
      <div
        onMouseDown={handleMouseDown}
        className={`w-1.5 hover:w-2 transition-all bg-[#1a1917] hover:bg-[#bd5b38] cursor-col-resize shrink-0 flex items-center justify-center relative select-none z-20 ${
          isDragging ? 'bg-[#bd5b38] w-2' : ''
        }`}
        title="Drag to resize Conversation Log sidebar"
      >
        <div className="h-8 w-0.5 bg-[#3a3833] rounded-full pointer-events-none" />
      </div>

      {/* RIGHT SIDEBAR: "CONVERSATION LOG" - PAST CONVERSATION HISTORY LIST ONLY */}
      <div 
        style={{ width: `${sidebarWidth}px` }}
        className="bg-[#161514] border-l border-[#262422] flex flex-col h-full overflow-hidden shrink-0 select-none"
      >
        {/* Right Sidebar Header */}
        <div className="p-3.5 border-b border-[#262422] bg-[#141312] flex items-center justify-between text-xs font-mono shrink-0">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-3.5 h-3.5 text-[#bd5b38]" />
            <span className="font-semibold text-[#ede8dd]">Conversation log</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onNewSession}
              className="flex items-center gap-1 px-2 py-1 rounded bg-[#201f1c] hover:bg-[#262522] text-[#ede8dd] border border-[#2e2c28] transition-colors cursor-pointer text-[11px]"
              title="Start a new conversation"
            >
              <Plus className="w-3 h-3 text-[#bd5b38]" />
              <span>New</span>
            </button>

            {sessions.length > 0 && onClearAllSessions && (
              <button
                onClick={onClearAllSessions}
                className="text-[#757069] hover:text-[#ede8dd] p-1 rounded transition-colors"
                title="Clear all conversation history"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* History Search Bar */}
        <div className="p-2.5 bg-[#141312] border-b border-[#22211e]">
          <div className="flex items-center gap-2 px-2.5 py-1.5 bg-[#1a1918] border border-[#2b2926] rounded-lg text-xs font-mono text-[#8e8982]">
            <Search className="w-3.5 h-3.5 text-[#757069]" />
            <input
              type="text"
              value={searchHistoryQuery}
              onChange={e => setSearchHistoryQuery(e.target.value)}
              placeholder="Filter past conversations..."
              className="bg-transparent text-[#ede8dd] placeholder-[#5c5852] focus:outline-none w-full text-xs"
            />
            {searchHistoryQuery && (
              <button onClick={() => setSearchHistoryQuery('')} className="text-[#757069] hover:text-[#ede8dd]">
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Past Conversation History List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2 select-text font-sans">
          {filteredSessions.length === 0 ? (
            <div className="py-12 text-center text-xs font-mono text-[#757069] space-y-2">
              <Clock className="w-6 h-6 mx-auto text-[#44413c]" />
              <p>No past conversations found</p>
              <button
                onClick={onNewSession}
                className="text-[#bd5b38] hover:underline text-[11px] block mx-auto cursor-pointer"
              >
                Create a new query
              </button>
            </div>
          ) : (
            filteredSessions.map((session) => {
              const isSelected = session.id === activeSessionId;
              const modelKey = resolveModelKey(session.model);
              const modelInfo = MODEL_REGISTRY[modelKey];

              return (
                <div
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={`p-3 rounded-xl border text-left transition-all cursor-pointer group relative ${
                    isSelected
                      ? 'bg-[#22201d] border-[#bd5b38]/70 shadow-sm'
                      : 'bg-[#181716] border-[#282623] hover:bg-[#1e1d1b] hover:border-[#383530]'
                  }`}
                >
                  {/* Top row: Deliverable tag & Timestamp */}
                  <div className="flex items-center justify-between text-[10px] font-mono text-[#757069] pb-1">
                    <span className="px-1.5 py-0.5 rounded bg-[#201f1c] border border-[#2e2c28] text-[#ede8dd]">
                      {session.deliverableType}
                    </span>
                    <span>{session.createdAt}</span>
                  </div>

                  {/* Conversation Title */}
                  <h4 className="font-serif text-sm font-normal text-[#ede8dd] line-clamp-1 group-hover:text-white transition-colors">
                    {session.title}
                  </h4>

                  {/* Query snippet */}
                  <p className="text-[11px] text-[#8e8982] line-clamp-2 mt-1 font-sans leading-relaxed">
                    {session.lastQuerySnippet}
                  </p>

                  {/* Bottom row: Model badge with ModelHoverTooltip & Actions */}
                  <div className="mt-2.5 pt-2 border-t border-[#242220] flex items-center justify-between text-[10px] font-mono">
                    <ModelHoverTooltip modelId={session.model} position="left">
                      <span 
                        className="inline-flex items-center gap-1 font-semibold hover:underline cursor-pointer"
                        style={{ color: modelInfo?.badgeColor || '#3ea877' }}
                      >
                        <Cpu className="w-3 h-3" />
                        <span>{modelInfo?.shortName || session.model}</span>
                      </span>
                    </ModelHoverTooltip>

                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(session.id);
                        }}
                        className="p-1 text-[#757069] hover:text-[#ef4444] transition-colors rounded cursor-pointer"
                        title="Delete conversation"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                      <ChevronRight className="w-3.5 h-3.5 text-[#757069]" />
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Sub-footer Status */}
        <div className="px-3.5 py-2 bg-[#141312] border-t border-[#22211e] flex items-center justify-between text-[10.5px] font-mono text-[#757069] shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877]" />
            <span>{sessions.length} recorded {sessions.length === 1 ? 'session' : 'sessions'}</span>
          </div>
          <span className="text-[10px]">Drag edge to resize</span>
        </div>
      </div>
    </div>
  );
};
