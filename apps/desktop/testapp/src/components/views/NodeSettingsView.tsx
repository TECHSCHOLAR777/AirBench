import React from 'react';
import { EnclaveNode, PageView } from '../../types';
import { 
  ShieldCheck, 
  Server, 
  RotateCcw, 
  Lock, 
  ArrowLeft, 
  HardDrive
} from 'lucide-react';

interface NodeSettingsViewProps {
  nodes: EnclaveNode[];
  activeNode: EnclaveNode | null;
  onSelectNode: (node: EnclaveNode) => void;
  onDisconnectNode: () => void;
  onInspectCert: (node: EnclaveNode) => void;
  onNavigate: (view: PageView) => void;
}

export const NodeSettingsView: React.FC<NodeSettingsViewProps> = ({
  nodes,
  activeNode,
  onSelectNode,
  onDisconnectNode,
  onInspectCert,
  onNavigate
}) => {
  return (
    <div className="flex-1 overflow-y-auto bg-[#121211] p-6 lg:px-16 flex flex-col items-center font-sans" data-purpose="node-settings-viewport">
      <div className="max-w-4xl w-full flex flex-col gap-7 pb-16">
        {/* Title block */}
        <section className="flex flex-col gap-1.5 pt-2" data-purpose="page-header">
          <span className="text-[11px] font-mono tracking-widest text-[#bd5b38] uppercase font-semibold">
            Trusted Execution
          </span>
          <h1 className="text-3xl lg:text-4xl text-[#ede8dd] font-serif font-normal tracking-tight">
            Node and settings
          </h1>
        </section>

        {/* ConnectionProofCard */}
        <section className="bg-[#181716] border border-[#282725] rounded-lg p-5 shadow-sm font-mono" data-purpose="connection-proof">
          <div className="flex items-start gap-3.5 pb-4 border-b border-[#282725]">
            <div className={`p-2 rounded bg-[#1f1e1c] border border-[#2b2926] mt-0.5 ${activeNode ? 'text-[#3ea877]' : 'text-[#d99c43]'}`}>
              {activeNode ? <ShieldCheck className="w-5 h-5" /> : <HardDrive className="w-5 h-5" />}
            </div>
            <div className="flex-1">
              <div className="text-[10px] uppercase tracking-widest text-[#757069]">
                Connection Proof
              </div>
              <h3 className="text-base font-semibold text-[#ede8dd] mt-0.5">
                {activeNode ? `Enclave Active: ${activeNode.hostname}` : 'No approved Node connection'}
              </h3>
              <p className="text-xs text-[#8e8982] mt-1 leading-normal font-sans">
                {activeNode
                  ? 'Cryptographic loopback established on local hardware socket. Hardware sandbox isolation, capability routing, and zero-egress audit ledger verified.'
                  : 'Connect an approved Node to initialize cryptographic loopback. Handshake fields remain sealed until an active peer connection is established.'}
              </p>
            </div>
          </div>

          {/* Proof parameters summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 text-xs font-mono">
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase text-[#757069]">Preserved state</span>
              <span className="text-[#ede8dd]">Local only, no leakage</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase text-[#757069]">Cryptographic Handshake</span>
              <span className={`flex items-center gap-1.5 ${activeNode ? 'text-[#3ea877]' : 'text-[#d99c43]'}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${activeNode ? 'bg-[#3ea877]' : 'bg-[#d99c43] animate-pulse'}`} />
                {activeNode ? 'Enclave peer verified' : 'Awaiting node peer'}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[10px] uppercase text-[#757069]">Required profile</span>
              <span className="text-[#ede8dd]">Admin enrolled enclave</span>
            </div>
          </div>
        </section>

        {/* NodeOperationalStatus */}
        <section className="bg-[#181716] border border-[#282725] rounded-lg p-5 flex flex-col gap-4 font-mono" data-purpose="operational-status">
          <div className="flex items-start gap-3.5">
            <div className="p-2 rounded bg-[#1f1e1c] border border-[#2b2926] text-[#757069] mt-0.5">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-[#757069]">
                Node Operational Status
              </div>
              <h3 className="text-base font-semibold text-[#ede8dd] mt-0.5">
                {activeNode ? 'Hardware and capability qualification online' : 'Operational status requires a verified Node'}
              </h3>
              <p className="text-xs text-[#8e8982] mt-1 font-sans">
                {activeNode 
                  ? 'Hardware, sandbox isolation, capability qualification, and router telemetry verified on loopback socket.'
                  : 'Hardware, sandbox isolation, capability qualification, and router telemetry remain sealed until an approved connection is established.'}
              </p>
            </div>
          </div>

          {/* Status matrix grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-2 text-xs">
            <div className="bg-[#1f1e1c] border border-[#2b2926] rounded p-3 flex items-center justify-between">
              <span className="text-[#8e8982]">Hardware &amp; capacity</span>
              <span className={`text-[11px] px-2 py-0.5 rounded border ${
                activeNode ? 'bg-[#3ea877]/10 text-[#3ea877] border-[#3ea877]/30' : 'bg-[#181716] text-[#757069] border-[#282725]'
              }`}>
                {activeNode ? '4x GPU (96 GB) READY' : 'CONNECTION REQUIRED'}
              </span>
            </div>

            <div className="bg-[#1f1e1c] border border-[#2b2926] rounded p-3 flex items-center justify-between">
              <span className="text-[#8e8982]">Sandbox health</span>
              <span className={`text-[11px] px-2 py-0.5 rounded border ${
                activeNode ? 'bg-[#3ea877]/10 text-[#3ea877] border-[#3ea877]/30' : 'bg-[#181716] text-[#757069] border-[#282725]'
              }`}>
                {activeNode ? 'RUST RT ISOLATED' : 'CONNECTION REQUIRED'}
              </span>
            </div>

            <div className="bg-[#1f1e1c] border border-[#2b2926] rounded p-3 flex items-center justify-between">
              <span className="text-[#8e8982]">Qualified capability catalog</span>
              <span className={`text-[11px] px-2 py-0.5 rounded border ${
                activeNode ? 'bg-[#3ea877]/10 text-[#3ea877] border-[#3ea877]/30' : 'bg-[#181716] text-[#757069] border-[#282725]'
              }`}>
                {activeNode ? 'LEVEL 4 QUALIFIED' : 'CONNECTION REQUIRED'}
              </span>
            </div>

            <div className="bg-[#1f1e1c] border border-[#2b2926] rounded p-3 flex items-center justify-between">
              <span className="text-[#8e8982]">Router decision history</span>
              <span className={`text-[11px] px-2 py-0.5 rounded border ${
                activeNode ? 'bg-[#3ea877]/10 text-[#3ea877] border-[#3ea877]/30' : 'bg-[#181716] text-[#757069] border-[#282725]'
              }`}>
                {activeNode ? '0 EGRESS AUDITED' : 'CONNECTION REQUIRED'}
              </span>
            </div>
          </div>
        </section>

        {/* Model Routing Policy Card */}
        <section className="bg-[#181716] border border-[#282725] rounded-lg p-5 flex items-start gap-3.5 font-mono" data-purpose="routing-policy">
          <div className="p-2 rounded bg-[#1f1e1c] border border-[#2b2926] text-[#757069] mt-0.5 shrink-0">
            <Lock className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest text-[#60a5fa]">
              Model Routing
            </div>
            <h3 className="text-sm font-semibold text-[#ede8dd] mt-0.5">
              Routing authority stays with the Node
            </h3>
            <p className="text-xs text-[#8e8982] mt-1 leading-relaxed font-sans">
              AirBench requests a qualified capability for each task. Model preference remains unavailable until the Node supplies a cryptographic clearance-filtered catalog.
            </p>
          </div>
        </section>

        {/* Approved Nodes Directory */}
        <section className="flex flex-col gap-3 font-mono" data-purpose="approved-nodes-list">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-[#ede8dd]">
                Approved Nodes
              </h3>
              <p className="text-xs text-[#757069] mt-0.5 font-sans">
                These profiles were provisioned and signed by your organization administrator.
              </p>
            </div>
            <button 
              onClick={() => {}} 
              className="text-xs text-[#8e8982] hover:text-[#ede8dd] flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reload</span>
            </button>
          </div>

          {/* Node Profiles List */}
          <div className="flex flex-col gap-2.5">
            {nodes.map(node => {
              const isSelected = activeNode?.id === node.id;
              return (
                <div
                  key={node.id}
                  className={`bg-[#181716] transition-all border rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 ${
                    isSelected
                      ? 'border-[#3ea877]/60 shadow-xs'
                      : 'border-[#282725] hover:border-[#383633]'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`w-2.5 h-2.5 rounded-full mt-1.5 ${
                      isSelected ? 'bg-[#3ea877] ring-4 ring-[#3ea877]/20' : 'bg-[#757069]'
                    }`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[#ede8dd]">
                          {node.hostname}
                        </span>
                        <span className={`text-[10px] px-1.5 py-0.2 rounded border ${
                          isSelected 
                            ? 'bg-[#3ea877]/10 text-[#3ea877] border-[#3ea877]/40'
                            : 'bg-[#22211e] text-[#8e8982] border-[#2e2d29]'
                        }`}>
                          {isSelected ? 'CONNECTED' : node.status}
                        </span>
                      </div>
                      <div className="text-xs text-[#757069] mt-1 flex flex-wrap gap-x-4 gap-y-1">
                        <span>Host: {node.host}</span>
                        <span>Latency: {node.latency}</span>
                        <span>Policy: {node.policy}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-end md:self-auto">
                    <button
                      onClick={() => onInspectCert(node)}
                      className="bg-[#1f1e1c] hover:bg-[#282724] text-[#ede8dd] px-3 py-1.5 rounded border border-[#2b2926] text-xs transition-colors cursor-pointer"
                    >
                      Inspect cert
                    </button>
                    {isSelected ? (
                      <button
                        onClick={onDisconnectNode}
                        className="bg-[#242320] hover:bg-[#2a2926] text-[#ede8dd] px-3.5 py-1.5 rounded border border-[#383633] text-xs font-medium transition-colors cursor-pointer"
                      >
                        Disconnect
                      </button>
                    ) : (
                      <button
                        onClick={() => onSelectNode(node)}
                        className="bg-[#bd5b38] hover:bg-[#a74f30] text-white px-3.5 py-1.5 rounded text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
                      >
                        Connect Node
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Security notice card */}
          <div className="bg-[#181716]/60 border border-[#282725] rounded-lg p-3.5 flex items-center justify-between text-xs mt-1">
            <div className="flex items-center gap-2 text-[#8e8982] font-sans">
              <Lock className="w-4 h-4 text-[#757069] shrink-0" />
              <span>Node catalog signature enforced: Untrusted or ad-hoc IP endpoints cannot be mounted.</span>
            </div>
            <span className="text-[#bd5b38] hover:underline ml-2 cursor-pointer font-mono">
              Try reload
            </span>
          </div>
        </section>

        {/* Approved Enclave Model Roster */}
        <section className="flex flex-col gap-3 font-mono" data-purpose="enclave-models-roster">
          <div className="flex items-center justify-between pb-1 border-b border-[#282725]">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10.5px] uppercase tracking-wider text-[#757069]">
                Hardware Loopback Registry • 10 Active Models & Specialized Pipelines
              </span>
              <h3 className="text-base font-semibold text-[#ede8dd] font-sans">
                Approved Enclave Model Roster
              </h3>
            </div>
            <span className="text-[10.5px] px-2.5 py-1 rounded bg-[#1f1e1c] border border-[#2b2926] text-[#3ea877] font-semibold">
              Zero Cloud Telemetry
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 pt-1">
            {[
              {
                id: 'gemma-4-31b',
                category: 'Agentic Tool-Use / Planning',
                name: 'Gemma 4 31B Instruct',
                role: 'High-capacity agentic tool-use, multi-step engineering planning, schema validation, and structured action synthesis.',
                quant: 'Q4_K_M',
                badgeColor: '#bd5b38'
              },
              {
                id: 'gemma-4-26b-a4b',
                category: 'Fast-Lane / Quick Queries',
                name: 'Gemma 4 26B-A4B MoE',
                role: 'Sub-50ms fast-lane responses, quick engineering queries, tool execution, and dual-stage adaptive routing.',
                quant: 'Active 4B',
                badgeColor: '#f59e0b'
              },
              {
                id: 'closed-frontier',
                category: 'Long Multi-Step Chains',
                name: 'Closed Frontier Orchestrator',
                role: 'Long multi-step agentic chains, complex cross-subsystem thermodynamic synthesis (where open models lag).',
                quant: 'Ensemble',
                badgeColor: '#e11d48'
              },
              {
                id: 'gemma-4-vlm-pipeline',
                category: 'Scanned Drawing Reading (VLM)',
                name: 'Gemma 4 31B+26B-A4B Pipeline',
                role: 'Scanned document & drawing reading VLM: adaptive heavy/fast pipeline for CAD raster-to-vector spatial parsing.',
                quant: 'Dual-Stage VLM',
                badgeColor: '#8b5cf6'
              },
              {
                id: 'paddle-ocr-vl',
                category: 'Printed Text OCR',
                name: 'PaddleOCRVL',
                role: 'Printed text OCR with pixel-precise bounding box coordinates, spatial clustering, and confidence scoring.',
                quant: 'FP16',
                badgeColor: '#06b6d4'
              },
              {
                id: 'trocr-large-gemma4',
                category: 'Handwriting Recognition',
                name: 'TrOCR-Large + Gemma 4',
                role: 'Field markups, handwritten maintenance logs, cursive engineering notes on drawings, and redline transcription.',
                quant: 'Hybrid OCR',
                badgeColor: '#ec4899'
              },
              {
                id: 'yolo-pid',
                category: 'P&ID Symbol Detection',
                name: 'YOLOv8 / YOLO11 (Fine-Tuned)',
                role: 'Fine-tuned ISA-5.1 symbol detection: valves (gate, globe, check, ball), centrifugal pumps, transmitters, control actuators.',
                quant: 'TensorRT',
                badgeColor: '#10b981'
              },
              {
                id: 'relationformer',
                category: 'P&ID Topology Reconstruction',
                name: 'Relationformer',
                role: 'P&ID connectivity and topology reconstruction, process line tracing, segment crossing resolution, and GraphML generation.',
                quant: 'PyTorch Graph',
                badgeColor: '#6366f1'
              },
              {
                id: 'bge-m3',
                category: 'Embedding / Retrieval (RAG)',
                name: 'BGE-M3 (1024d Dense + Sparse)',
                role: 'Multi-lingual, multi-function dense & sparse vector retrieval across industrial SOP manuals and safety standards.',
                quant: 'FP16',
                badgeColor: '#3ea877'
              },
              {
                id: 'bge-reranker-v2-m3',
                category: 'Reranking Retrieved Chunks',
                name: 'bge-reranker-v2-m3',
                role: 'Cross-encoder chunk reranker with fine-grained cross-attention relevance scoring prior to final synthesis.',
                quant: 'FP16',
                badgeColor: '#14b8a6'
              },
              {
                id: 'qwen2.5-coder-7b',
                category: 'Numerical Solver & Python',
                name: 'Qwen 2.5 Coder 7B Instruct',
                role: 'Python sandbox code synthesis, Darcy-Weisbach / Colebrook-White friction solvers, and algorithm execution.',
                quant: 'Q4_K_M',
                badgeColor: '#bd5b38'
              }
            ].map(m => (
              <div 
                key={m.id}
                className="p-3.5 rounded-xl bg-[#181716] border border-[#282723] hover:border-[#3d3a33] transition-colors flex flex-col justify-between gap-2.5 group relative"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-[9.5px] uppercase tracking-wider font-semibold block" style={{ color: m.badgeColor }}>
                      {m.category}
                    </span>
                    <h4 className="font-semibold text-xs text-[#ede8dd] mt-0.5">
                      {m.name}
                    </h4>
                  </div>
                  <span 
                    className="px-2 py-0.5 rounded text-[10px] font-semibold border shrink-0"
                    style={{ 
                      color: m.badgeColor, 
                      backgroundColor: `${m.badgeColor}15`,
                      borderColor: `${m.badgeColor}40`
                    }}
                  >
                    {m.quant}
                  </span>
                </div>

                <p className="text-[11px] text-[#8e8982] font-sans leading-relaxed">
                  {m.role}
                </p>

                <div className="pt-2 border-t border-[#242220] flex items-center justify-between text-[10px] text-[#757069]">
                  <span>Loopback 127.0.0.1:8000</span>
                  <span className="text-[#3ea877] font-medium flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877]" />
                    Zero-Egress
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Footer Navigation */}
        <section className="pt-2 flex items-center justify-between border-t border-[#282725] font-mono text-xs" data-purpose="footer-actions">
          <button
            onClick={() => onNavigate('home')}
            className="bg-[#181716] hover:bg-[#22211e] border border-[#282725] text-[#ede8dd] px-4 py-2 rounded flex items-center gap-2 transition-colors cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return home</span>
          </button>
          <div className="text-[11px] text-[#757069]">
            Sovereignty Policy: Local loopback isolation 127.0.0.1
          </div>
        </section>
      </div>
    </div>
  );
};
