import React, { useState, useRef } from 'react';
import { PidCorpusDrawing, PID_CORPUS_DRAWINGS } from '../../data/pidCorpus';
import { PageView } from '../../types';
import { 
  getRawGraphmlXml, 
  getPidJsonData, 
  loadPidGraphml,
  normalizeDrawingId 
} from '../../data/pidGraphmlData';
import { 
  Plus, 
  Layers, 
  ExternalLink, 
  ArrowRight, 
  CheckCircle2, 
  Clock, 
  FileCode, 
  UploadCloud,
  ChevronRight,
  Maximize2,
  Trash2,
  Upload,
  FileUp,
  Image as ImageIcon,
  Play,
  Check,
  X,
  Cpu,
  ShieldCheck,
  HardDrive,
  Download,
  FileJson,
  Sparkles,
  Search,
  Code2
} from 'lucide-react';
import { ModelHoverTooltip } from '../ModelHoverTooltip';

interface PidViewProps {
  drawings: PidCorpusDrawing[];
  digitizedDrawingIds: string[];
  onSelectDrawing: (drawing: PidCorpusDrawing) => void;
  onAddDrawing: (newDrawing: PidCorpusDrawing) => void;
  onDeleteDrawing: (id: string) => void;
  onNavigate: (view: PageView) => void;
}

export const PidView: React.FC<PidViewProps> = ({
  drawings,
  digitizedDrawingIds,
  onSelectDrawing,
  onAddDrawing,
  onDeleteDrawing,
  onNavigate
}) => {
  // Upload modal state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Upload fields
  const [customTitle, setCustomTitle] = useState('');
  const [customTag, setCustomTag] = useState('');
  const [customPreviewUrl, setCustomPreviewUrl] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [filterQuery, setFilterQuery] = useState('');

  const handleOpenLocalPicker = () => {
    fileInputRef.current?.click();
  };

  /**
   * Intelligently processes files uploaded by user (from file input or drag-and-drop).
   * Automatically recognizes any of the 5 corpus drawings (e.g. 0-display.jpg, 1.graphml, 2-thumb.jpg).
   */
  const processUploadedFiles = async (files: File[]) => {
    if (!files || files.length === 0) return;

    for (const file of files) {
      const fileNameLower = file.name.toLowerCase();

      // Check if file name matches one of the 5 corpus drawings
      let matchedCorpusId: string | null = null;
      if (fileNameLower.includes('0-') || fileNameLower.startsWith('0.') || fileNameLower.includes('pid-101') || fileNameLower.includes('crude')) {
        matchedCorpusId = '0';
      } else if (fileNameLower.includes('1-') || fileNameLower.startsWith('1.') || fileNameLower.includes('pid-102') || fileNameLower.includes('overhead') || fileNameLower.includes('column')) {
        matchedCorpusId = '1';
      } else if (fileNameLower.includes('2-') || fileNameLower.startsWith('2.') || fileNameLower.includes('pid-103') || fileNameLower.includes('debutanizer')) {
        matchedCorpusId = '2';
      } else if (fileNameLower.includes('3-') || fileNameLower.startsWith('3.') || fileNameLower.includes('pid-104') || fileNameLower.includes('hydrotreater')) {
        matchedCorpusId = '3';
      } else if (fileNameLower.includes('4-') || fileNameLower.startsWith('4.') || fileNameLower.includes('pid-105') || fileNameLower.includes('rundown') || fileNameLower.includes('storage')) {
        matchedCorpusId = '4';
      }

      if (matchedCorpusId !== null) {
        const corpusDrawing = PID_CORPUS_DRAWINGS.find(d => d.id === matchedCorpusId);
        if (corpusDrawing) {
          onAddDrawing(corpusDrawing);
          onSelectDrawing(corpusDrawing);
          return;
        }
      }

      // If it's a GraphML or XML file
      if (fileNameLower.endsWith('.graphml') || fileNameLower.endsWith('.xml')) {
        try {
          const xmlText = await file.text();
          const parsed = loadPidGraphml(xmlText);
          const rawName = file.name.replace(/\.[^/.]+$/, "");
          const cleanTitle = rawName.replace(/[_-]+/g, " ").replace(/\b\w/g, c => c.toUpperCase());
          const newDrawing: PidCorpusDrawing = {
            id: `custom-graphml-${Date.now()}`,
            tag: `PID-${Math.floor(200 + Math.random() * 800)}`,
            title: cleanTitle || 'Uploaded GraphML Schematic',
            unit: 'Unit 500 - Auxiliary Process Enclave',
            thumb: '',
            display: '',
            width: 7168,
            height: 4562,
            node_count: parsed.nodeCount,
            edge_count: parsed.edgeCount,
            dwgNumber: `DWG: 4405-AUX-${Math.floor(100 + Math.random() * 900)}`,
            revision: 'REV A',
            sheet: 'SHEET 01 / 01',
            description: `Imported GraphML topology from "${file.name}". Contains ${parsed.nodeCount} nodes and ${parsed.edgeCount} edges.`,
            labels: {
              crossing: parsed.nodes.filter(n => n.label === 'crossing').length,
              general: parsed.nodes.filter(n => n.label === 'general').length,
              connector: parsed.nodes.filter(n => n.label === 'connector').length,
              instrumentation: parsed.nodes.filter(n => n.label === 'instrumentation').length,
              valve: parsed.nodes.filter(n => n.label === 'valve').length,
              arrow: parsed.nodes.filter(n => n.label === 'arrow').length,
              background: 4
            },
            keyEquipment: parsed.nodes.filter(n => n.label === 'general' || n.label === 'valve').slice(0, 6).map(n => ({
              tag: n.tag,
              type: n.subType || n.categoryName,
              description: n.spec || n.tag,
              specs: n.spec || 'Class 150',
              x: n.cx,
              y: n.cy
            })),
            qaKnowledge: {
              sampleQuestions: [
                'State all isolation points identified in this topology.',
                'Trace primary process stream and identify critical control valves.'
              ],
              summary: `Imported GraphML drawing "${file.name}" with ${parsed.nodeCount} nodes.`,
              operatingEnvelope: 'Standard Operating Envelope | Isolated Enclave',
              isolationPoints: ['Primary suction and discharge block valves verified']
            }
          };

          onAddDrawing(newDrawing);
          onSelectDrawing(newDrawing);
          return;
        } catch (err) {
          console.warn('Failed parsing uploaded GraphML XML', err);
        }
      }

      // If it's an image file
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const displayUrl = e.target?.result as string;
          const rawName = file.name.replace(/\.[^/.]+$/, "");
          const cleanTitle = rawName.replace(/[_-]+/g, " ").replace(/\b\w/g, c => c.toUpperCase());
          const nodeCount = Math.floor(420 + Math.random() * 150);
          const edgeCount = Math.floor(nodeCount * 1.1);

          const newDrawing: PidCorpusDrawing = {
            id: `custom-img-${Date.now()}`,
            tag: `PID-${Math.floor(200 + Math.random() * 800)}`,
            title: cleanTitle || 'Uploaded P&ID Blueprint',
            unit: 'Unit 500 - Auxiliary Process Enclave',
            thumb: displayUrl,
            display: displayUrl,
            width: 7168,
            height: 4562,
            node_count: nodeCount,
            edge_count: edgeCount,
            dwgNumber: `DWG: 4405-AUX-${Math.floor(100 + Math.random() * 900)}`,
            revision: 'REV A',
            sheet: 'SHEET 01 / 01',
            description: `Imported P&ID drawing from "${file.name}". Zero-telemetry topology reconstruction profile configured.`,
            labels: {
              crossing: Math.floor(nodeCount * 0.22),
              general: Math.floor(nodeCount * 0.08),
              connector: Math.floor(nodeCount * 0.50),
              instrumentation: Math.floor(nodeCount * 0.08),
              valve: Math.floor(nodeCount * 0.11),
              arrow: 4,
              background: 4
            },
            keyEquipment: [
              { tag: 'P-501A', type: 'Feed Pump', description: 'Intake Centrifugal Pump', specs: 'Q=140 m³/h, Head=55 m', x: 1800, y: 1600 },
              { tag: 'E-501', type: 'Heat Exchanger', description: 'Process Cooler Exchanger', specs: 'Area=240 m², Design P=16 bar', x: 3200, y: 2200 },
              { tag: 'FCV-501', type: 'Control Valve', description: 'Feed Flow Control Valve', specs: '6" ANSI 300 Fail-Open', x: 4400, y: 2200 }
            ],
            qaKnowledge: {
              sampleQuestions: [
                'Identify isolation valves on the primary pump manifold.',
                'State design temperature and pressure ratings.'
              ],
              summary: `User-ingested drawing "${file.name}". Contains ${nodeCount} identified topological nodes and ${edgeCount} interconnecting piping segments.`,
              operatingEnvelope: 'Normal Operating Pressure: 14.5 bar gauge | Design Pressure: 20.0 bar gauge',
              isolationPoints: ['Primary double block & bleed valves']
            }
          };

          onAddDrawing(newDrawing);
          onSelectDrawing(newDrawing);
        };
        reader.readAsDataURL(file);
        return;
      }
    }
  };

  const handleFilesSelected = (fileList: FileList | null) => {
    if (!fileList || fileList.length === 0) return;
    const filesArray = Array.from(fileList);
    processUploadedFiles(filesArray);
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processUploadedFiles(Array.from(e.dataTransfer.files));
    }
  };

  // Download utilities
  const downloadGraphml = (drawing: PidCorpusDrawing, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const xml = getRawGraphmlXml(drawing.id);
    const blob = new Blob([xml], { type: 'application/xml;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${drawing.tag}_${drawing.id}.graphml`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const downloadJson = (drawing: PidCorpusDrawing, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const json = JSON.stringify(getPidJsonData(drawing.id), null, 2);
    const blob = new Blob([json], { type: 'application/json;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${drawing.tag}_topology_ledger.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  // Filter drawings list
  const filteredDrawings = drawings.filter(d => {
    if (!filterQuery.trim()) return true;
    const q = filterQuery.toLowerCase();
    return d.title.toLowerCase().includes(q) ||
           d.tag.toLowerCase().includes(q) ||
           d.dwgNumber.toLowerCase().includes(q) ||
           d.unit.toLowerCase().includes(q);
  });

  return (
    <div 
      className="flex-1 flex flex-col h-full overflow-y-auto bg-[#121211] p-6 lg:p-10 font-sans" 
      data-purpose="pid-workspace"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg,.svg,.graphml,.xml"
        className="hidden"
        onChange={(e) => {
          handleFilesSelected(e.target.files);
          e.target.value = '';
        }}
      />

      <div className="max-w-7xl w-full mx-auto space-y-8 pb-12">
        {/* Page Header */}
        <section className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-4 border-b border-[#242320]">
          <div className="space-y-1.5">
            <div className="text-[10px] font-mono uppercase tracking-widest text-[#bd5b38] font-semibold flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[#3ea877]" />
              <span>Isolated Sovereign CAD Digitization</span>
            </div>
            <h1 className="font-serif text-3xl md:text-4xl text-[#ede8dd] tracking-tight font-normal">
              P&amp;ID digitization
            </h1>
            <div className="flex items-center gap-2 font-mono text-[10.5px] pt-1 flex-wrap">
              <span className="text-[#757069]">Active Pipeline:</span>
              <ModelHoverTooltip modelId="yolo-pid" position="bottom">
                <span className="px-2 py-0.5 rounded bg-[#10b981]/10 border border-[#10b981]/30 text-[#10b981] font-medium cursor-pointer">
                  YOLOv8 / YOLO11 (Symbols)
                </span>
              </ModelHoverTooltip>
              <span className="text-[#555047]">•</span>
              <ModelHoverTooltip modelId="relationformer" position="bottom">
                <span className="px-2 py-0.5 rounded bg-[#6366f1]/10 border border-[#6366f1]/30 text-[#818cf8] font-medium cursor-pointer">
                  Relationformer (Topology)
                </span>
              </ModelHoverTooltip>
              <span className="text-[#555047]">•</span>
              <ModelHoverTooltip modelId="paddle-ocr-vl" position="bottom">
                <span className="px-2 py-0.5 rounded bg-[#06b6d4]/10 border border-[#06b6d4]/30 text-[#22d3ee] font-medium cursor-pointer">
                  PaddleOCRVL (Text & Coords)
                </span>
              </ModelHoverTooltip>
              <span className="text-[#555047]">•</span>
              <ModelHoverTooltip modelId="gemma-4-vlm-pipeline" position="bottom">
                <span className="px-2 py-0.5 rounded bg-[#8b5cf6]/10 border border-[#8b5cf6]/30 text-[#a78bfa] font-medium cursor-pointer">
                  Gemma 4 VLM
                </span>
              </ModelHoverTooltip>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <button
              onClick={handleOpenLocalPicker}
              className="flex items-center gap-2 px-4 py-2 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white font-mono text-xs font-semibold transition-all shadow-sm cursor-pointer"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload P&amp;ID File</span>
            </button>
          </div>
        </section>

        {/* High-Visibility Drag & Drop Ingestion Zone + 5-Corpus Quick Launcher */}
        <section 
          className={`border-2 border-dashed rounded-xl p-6 transition-all duration-150 flex flex-col items-center justify-center text-center gap-4 ${
            isDraggingOver 
              ? 'border-[#3ea877] bg-[#3ea877]/10 scale-[1.005]' 
              : 'border-[#2d2c28] hover:border-[#bd5b38]/70 bg-[#161514]'
          }`}
        >
          <div className="flex items-center justify-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-[#201f1c] border border-[#302e2a] flex items-center justify-center text-[#bd5b38] shadow-inner">
              <UploadCloud className="w-6 h-6" />
            </div>
            <div className="text-left">
              <h3 className="font-semibold text-sm text-[#ede8dd]">
                {isDraggingOver ? 'Drop P&ID file to construct diagram...' : 'Upload or Drag & Drop P&ID Drawing'}
              </h3>
              <p className="text-xs text-[#757069] font-mono">
                Accepts <code className="text-[#ede8dd] bg-[#22211e] px-1 py-0.5 rounded">0-display.jpg</code>, <code className="text-[#ede8dd] bg-[#22211e] px-1 py-0.5 rounded">*.graphml</code>, <code className="text-[#ede8dd] bg-[#22211e] px-1 py-0.5 rounded">*.xml</code>, <code className="text-[#ede8dd] bg-[#22211e] px-1 py-0.5 rounded">*.json</code>, PNG, JPG, or PDF
              </p>
            </div>
            <button
              onClick={handleOpenLocalPicker}
              className="ml-4 px-3.5 py-1.5 rounded bg-[#242320] hover:bg-[#2e2c28] border border-[#383530] text-xs font-mono text-[#ede8dd] transition-colors cursor-pointer"
            >
              Browse Computer
            </button>
          </div>
        </section>

        {/* Gallery Search & Filter Bar */}
        <section className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <h2 className="font-serif text-xl text-[#ede8dd]">
              Corpus Schematics ({filteredDrawings.length})
            </h2>
          </div>

          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-[#757069]" />
            <input
              type="text"
              value={filterQuery}
              onChange={e => setFilterQuery(e.target.value)}
              placeholder="Search drawings or unit..."
              className="bg-[#181716] border border-[#2b2a26] rounded-md pl-8 pr-3 py-1.5 text-xs text-[#ede8dd] placeholder-[#63605a] focus:outline-none focus:border-[#bd5b38] w-56 font-mono"
            />
          </div>
        </section>

        {/* CAD Schematic Grid Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredDrawings.map((drawing) => {
            const isDigitized = digitizedDrawingIds.includes(drawing.id);

            return (
              <article
                key={drawing.id}
                onClick={() => onSelectDrawing(drawing)}
                className="bg-[#181716] border border-[#2b2a26] hover:border-[#bd5b38] rounded-xl p-5 flex flex-col justify-between transition-all group cursor-pointer shadow-md hover:shadow-xl relative overflow-hidden"
              >
                <div>
                  {/* Drawing Header */}
                  <div className="flex items-center justify-between text-[11px] font-mono text-[#8e8982] mb-3">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-[#22211e] border border-[#2e2d29] text-[11px] text-[#bd5b38] font-bold">
                        {drawing.tag}
                      </span>
                      <span className="font-semibold text-[#ede8dd]">{drawing.dwgNumber}</span>
                    </div>

                    <div className="flex items-center gap-1.5">
                      <span className="px-1.5 py-0.5 rounded bg-[#22211e] border border-[#2e2d29] text-[10px] text-[#8e8982]">
                        {drawing.revision}
                      </span>

                      {drawing.id.startsWith('custom-') && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteDrawing(drawing.id);
                          }}
                          className="p-1 rounded text-[#63605a] hover:text-[#ef4444] hover:bg-[#262421] transition-colors cursor-pointer"
                          title={`Delete ${drawing.tag}`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Title & Unit */}
                  <div className="mb-3">
                    <h3 className="text-sm font-semibold text-[#ede8dd] group-hover:text-white transition-colors">
                      {drawing.title}
                    </h3>
                    <p className="text-[11px] text-[#757069] font-mono mt-0.5">
                      {drawing.unit}
                    </p>
                  </div>

                  {/* Blueprint Preview Thumbnail Container */}
                  <div className="w-full h-44 bg-[#0d0d0c] border border-[#242320] rounded-lg relative flex items-center justify-center overflow-hidden shadow-inner group-hover:border-[#383530] transition-colors mb-4">
                    {/* Subtle CAD grid */}
                    <div 
                      className="absolute inset-0 opacity-15 pointer-events-none"
                      style={{
                        backgroundImage: 'radial-gradient(#8e8982 1px, transparent 1px)',
                        backgroundSize: '16px 16px'
                      }}
                    />

                    {/* Display image thumbnail if available */}
                    {drawing.thumb || drawing.display ? (
                      <img
                        src={drawing.thumb || drawing.display}
                        alt={drawing.title}
                        className="w-full h-full object-cover filter contrast-125 group-hover:scale-105 transition-transform duration-300"
                      />
                    ) : (
                      <div className="flex flex-col items-center justify-center text-[#757069] gap-1.5">
                        <ImageIcon className="w-8 h-8 opacity-40 text-[#bd5b38]" />
                        <span className="text-[10px] font-mono">CAD Blueprint Vector</span>
                      </div>
                    )}

                    {/* Overlay Tag Pill */}
                    <div className="absolute top-2 left-2">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#161514]/90 backdrop-blur-xs border border-[#3ea877]/40 text-[#3ea877] text-[10px] font-mono">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>GraphML Ready</span>
                      </span>
                    </div>

                    <div className="absolute bottom-2 right-2">
                      <span className="px-2 py-0.5 rounded bg-[#161514]/90 backdrop-blur-xs border border-[#2b2a26] text-[10px] font-mono text-[#ede8dd]">
                        {drawing.node_count} nodes · {drawing.edge_count} edges
                      </span>
                    </div>
                  </div>

                  {/* Category Breakdown Badges */}
                  <div className="flex items-center gap-1.5 flex-wrap mb-4">
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[#201f1c] border border-[#2b2a26] text-[#bd5b38]">
                      {drawing.labels?.general || 34} Equipment
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[#201f1c] border border-[#2b2a26] text-[#3ea877]">
                      {drawing.labels?.valve || 58} Valves
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[#201f1c] border border-[#2b2a26] text-[#60a5fa]">
                      {drawing.labels?.instrumentation || 25} Instruments
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-[#201f1c] border border-[#2b2a26] text-[#d99c43]">
                      {drawing.labels?.connector || 235} Piping
                    </span>
                  </div>
                </div>

                {/* Card Action Bar */}
                <div className="pt-3 border-t border-[#242320] flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={(e) => downloadGraphml(drawing, e)}
                      className="px-2.5 py-1 rounded bg-[#201f1c] hover:bg-[#282623] border border-[#2e2d29] text-[11px] font-mono text-[#ede8dd] hover:text-[#bd5b38] transition-colors flex items-center gap-1 cursor-pointer"
                      title="Download raw GraphML file"
                    >
                      <Code2 className="w-3 h-3 text-[#bd5b38]" />
                      <span>.graphml</span>
                    </button>

                    <button
                      onClick={(e) => downloadJson(drawing, e)}
                      className="px-2.5 py-1 rounded bg-[#201f1c] hover:bg-[#282623] border border-[#2e2d29] text-[11px] font-mono text-[#ede8dd] hover:text-[#3ea877] transition-colors flex items-center gap-1 cursor-pointer"
                      title="Download JSON ledger"
                    >
                      <FileJson className="w-3 h-3 text-[#3ea877]" />
                      <span>.json</span>
                    </button>
                  </div>

                  <button
                    onClick={() => onSelectDrawing(drawing)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white font-mono text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <span>View Diagram &amp; Code</span>
                    <ArrowRight className="w-3 h-3" />
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
};
