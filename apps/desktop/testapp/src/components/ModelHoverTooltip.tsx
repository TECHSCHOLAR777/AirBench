import React, { useState, useRef, useEffect } from 'react';
import { Cpu, ShieldCheck, Zap, Sparkles } from 'lucide-react';

export interface ModelDetails {
  id: string;
  fullName: string;
  shortName: string;
  developer: string;
  parameters: string;
  contextWindow: string;
  specialization: string;
  enclaveRuntime: string;
  badgeColor: string;
}

export const MODEL_REGISTRY: Record<string, ModelDetails> = {
  'gemma-4-31b': {
    id: 'gemma-4-31b',
    fullName: 'Gemma 4 31B Instruct',
    shortName: 'Gemma 4 31B',
    developer: 'Google DeepMind (Open Weights)',
    parameters: '31 Billion Dense',
    contextWindow: '128,000 tokens',
    specialization: 'Agentic tool-use, multi-step engineering planning, schema validation, and tool function calling.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Quant: Q4_K_M | Zero Egress',
    badgeColor: '#bd5b38'
  },
  'gemma-4-26b-a4b': {
    id: 'gemma-4-26b-a4b',
    fullName: 'Gemma 4 26B-A4B MoE',
    shortName: 'Gemma 4 26B-A4B',
    developer: 'Google DeepMind (Open Weights)',
    parameters: '26 Billion (Active 4B)',
    contextWindow: '64,000 tokens',
    specialization: 'Fast-lane / quick queries, low-latency execution, tool dispatch, and dual-stage routing.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Quant: Q4_K_M | Zero Egress',
    badgeColor: '#f59e0b'
  },
  'closed-frontier': {
    id: 'closed-frontier',
    fullName: 'Closed Frontier Orchestrator',
    shortName: 'Frontier Agentic Chain',
    developer: 'Sovereign Enclave Isolated Proxy',
    parameters: 'Frontier Scale Ensemble',
    contextWindow: '200,000 tokens',
    specialization: 'Long multi-step agentic chains, complex process synthesis, cross-system hazard analysis (where open models lag).',
    enclaveRuntime: 'Hardware loopback proxy 127.0.0.1:8000 | Zero-Telemetry Protocol',
    badgeColor: '#e11d48'
  },
  'gemma-4-vlm-pipeline': {
    id: 'gemma-4-vlm-pipeline',
    fullName: 'Gemma 4 31B + 26B-A4B VLM Pipeline',
    shortName: 'Gemma 4 Dual VLM',
    developer: 'DeepMind Open Pipeline',
    parameters: '31B Heavy + 26B Fast Pipeline',
    contextWindow: '128,000 visual tokens',
    specialization: 'Scanned document & drawing reading (VLM), CAD blueprint interpretation, multi-resolution raster-to-vector spatial parsing.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Multimodal Enclave',
    badgeColor: '#8b5cf6'
  },
  'paddle-ocr-vl': {
    id: 'paddle-ocr-vl',
    fullName: 'PaddleOCRVL (Text & Coordinates)',
    shortName: 'PaddleOCRVL',
    developer: 'PaddlePaddle Open Ecosystem',
    parameters: 'High-Precision Vision-OCR',
    contextWindow: 'Dense Spatial Map',
    specialization: 'Printed text OCR with exact bounding box coordinates and confidence score extraction on engineering drawings.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Local CUDA Kernel',
    badgeColor: '#06b6d4'
  },
  'trocr-large-gemma4': {
    id: 'trocr-large-gemma4',
    fullName: 'TrOCR-Large + Gemma 4 Ensemble',
    shortName: 'TrOCR + Gemma 4',
    developer: 'Microsoft Research & DeepMind',
    parameters: '558M TrOCR + Gemma 4',
    contextWindow: 'Line-Level Transcription',
    specialization: 'Handwriting recognition, operator field markups, redline notations, and cursive maintenance logs.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Local CUDA Kernel',
    badgeColor: '#ec4899'
  },
  'yolo-pid': {
    id: 'yolo-pid',
    fullName: 'YOLOv8 / YOLO11 (Fine-Tuned for P&ID)',
    shortName: 'YOLO11 P&ID',
    developer: 'Ultralytics (Enclave Fine-Tuned)',
    parameters: 'Real-Time Vector Detection',
    contextWindow: 'Full Drawing Matrix',
    specialization: 'P&ID symbol detection: ISA-5.1 valves (gate, globe, check, ball), centrifugal pumps, transmitters, and control actuators.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | TensorRT Engine',
    badgeColor: '#10b981'
  },
  'relationformer': {
    id: 'relationformer',
    fullName: 'Relationformer (P&ID Topology Reconstruction)',
    shortName: 'Relationformer',
    developer: 'Topological Graph Research',
    parameters: 'Graph-Transformer Relation Network',
    contextWindow: 'Full Graph Topology',
    specialization: 'P&ID connectivity and topology reconstruction, process line tracing, segment crossing resolution, and GraphML generation.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Local PyTorch Enclave',
    badgeColor: '#6366f1'
  },
  'bge-m3': {
    id: 'bge-m3',
    fullName: 'BGE-M3 (Dense + Sparse Multilingual Embedding)',
    shortName: 'BGE-M3',
    developer: 'BAAI (Open Weights)',
    parameters: '568 Million (1024d Dense + Sparse)',
    contextWindow: '8,192 tokens',
    specialization: 'Embedding & retrieval (RAG) across industrial SOP manuals, technical dossiers, and engineering standards.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | FP16 Zero Egress',
    badgeColor: '#3ea877'
  },
  'bge-reranker-v2-m3': {
    id: 'bge-reranker-v2-m3',
    fullName: 'bge-reranker-v2-m3 (Cross-Encoder)',
    shortName: 'bge-reranker-v2-m3',
    developer: 'BAAI (Open Weights)',
    parameters: '568 Million Cross-Encoder',
    contextWindow: '8,192 tokens',
    specialization: 'Reranking retrieved chunks with fine-grained cross-attention relevance scoring prior to synthesis.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | FP16 Zero Egress',
    badgeColor: '#14b8a6'
  },
  'qwen2.5-coder-7b': {
    id: 'qwen2.5-coder-7b',
    fullName: 'Qwen 2.5 Coder 7B Instruct',
    shortName: 'qwen2.5-coder-7b',
    developer: 'Alibaba Cloud (Open Weights)',
    parameters: '7.61 Billion',
    contextWindow: '32,768 tokens',
    specialization: 'Python code synthesis, Colebrook-White hydraulic numerical solvers, AST generation, and algorithm execution.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Quant: Q4_K_M | Zero Egress',
    badgeColor: '#bd5b38'
  },
  'deepseek-coder-6.7b': {
    id: 'deepseek-coder-6.7b',
    fullName: 'DeepSeek Coder 6.7B Instruct',
    shortName: 'deepseek-coder-6.7b',
    developer: 'DeepSeek AI (Open Weights)',
    parameters: '6.70 Billion',
    contextWindow: '16,384 tokens',
    specialization: 'Static AST analysis, invariant boundary checking, memory egress audits, and technical compliance memorandum synthesis.',
    enclaveRuntime: 'Hardware loopback 127.0.0.1:8000 | Quant: Q4_K_M | Zero Egress',
    badgeColor: '#3b82f6'
  },
  'auto': {
    id: 'auto',
    fullName: 'AirBench Sovereign Dynamic Dispatcher',
    shortName: 'Auto Dispatcher',
    developer: 'AirBench Sovereign Kernel',
    parameters: 'Dynamic Multi-Model Router',
    contextWindow: 'Full Enclave Scope',
    specialization: 'Analyzes query semantic intent and delivers automatic zero-latency dispatch across Gemma 4, YOLO, Relationformer, and BGE-M3.',
    enclaveRuntime: 'Local hardware supervisor | Zero Egress',
    badgeColor: '#3ea877'
  }
};

export function resolveModelKey(identifier?: string): string {
  if (!identifier) return 'auto';
  const lower = identifier.toLowerCase();
  if (lower.includes('31b') || (lower.includes('gemma') && !lower.includes('26b') && !lower.includes('vlm'))) return 'gemma-4-31b';
  if (lower.includes('26b') || lower.includes('a4b') || lower.includes('fast-lane')) return 'gemma-4-26b-a4b';
  if (lower.includes('frontier') || lower.includes('closed') || lower.includes('multi-step') || lower.includes('chain')) return 'closed-frontier';
  if (lower.includes('vlm') || lower.includes('scanned') || (lower.includes('gemma') && lower.includes('drawing'))) return 'gemma-4-vlm-pipeline';
  if (lower.includes('paddle') || (lower.includes('ocr') && !lower.includes('trocr'))) return 'paddle-ocr-vl';
  if (lower.includes('trocr') || lower.includes('handwriting') || lower.includes('markup')) return 'trocr-large-gemma4';
  if (lower.includes('yolo') || lower.includes('symbol')) return 'yolo-pid';
  if (lower.includes('relationformer') || lower.includes('topology') || lower.includes('connectivity')) return 'relationformer';
  if (lower.includes('rerank')) return 'bge-reranker-v2-m3';
  if (lower.includes('bge') || lower.includes('embed') || lower.includes('retriev')) return 'bge-m3';
  if (lower.includes('qwen2.5') || lower.includes('qwen')) return 'qwen2.5-coder-7b';
  if (lower.includes('deepseek')) return 'deepseek-coder-6.7b';
  if (lower.includes('auto')) return 'auto';
  return 'gemma-4-31b';
}

interface ModelHoverTooltipProps {
  modelId?: string;
  children: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  className?: string;
}

export const ModelHoverTooltip: React.FC<ModelHoverTooltipProps> = ({
  modelId,
  children,
  position = 'top',
  className = ''
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const key = resolveModelKey(modelId);
  const model = MODEL_REGISTRY[key] || MODEL_REGISTRY['auto'];

  return (
    <div 
      ref={containerRef}
      className={`relative inline-flex items-center ${className}`}
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
      onFocus={() => setIsOpen(true)}
      onBlur={() => setIsOpen(false)}
    >
      {children}

      {isOpen && (
        <div 
          className={`absolute z-50 w-72 p-3 bg-[#181715] border border-[#38352f] rounded-xl shadow-2xl text-left pointer-events-none animate-in fade-in zoom-in-95 duration-150 ${
            position === 'top' 
              ? 'bottom-full left-1/2 -translate-x-1/2 mb-2' 
              : position === 'bottom'
              ? 'top-full left-1/2 -translate-x-1/2 mt-2'
              : position === 'left'
              ? 'right-full top-1/2 -translate-y-1/2 mr-2'
              : 'left-full top-1/2 -translate-y-1/2 ml-2'
          }`}
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2 pb-2 border-b border-[#282622] font-mono">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[#8e8982] flex items-center gap-1 font-semibold">
                <Cpu className="w-3 h-3 text-[#3ea877]" />
                <span>Sovereign Enclave Model</span>
              </div>
              <div className="font-semibold text-xs text-[#ede8dd] mt-0.5">
                {model.fullName}
              </div>
            </div>
            <span 
              className="px-1.5 py-0.5 rounded text-[9px] font-mono font-medium border"
              style={{ 
                color: model.badgeColor, 
                backgroundColor: `${model.badgeColor}15`,
                borderColor: `${model.badgeColor}40`
              }}
            >
              {model.parameters}
            </span>
          </div>

          {/* Body specs */}
          <div className="py-2 space-y-1.5 text-[11px] font-sans text-[#a8a39a] leading-relaxed">
            <p>{model.specialization}</p>
            <div className="flex items-center gap-2 pt-1 text-[10px] font-mono text-[#757069]">
              <span>Context: <strong className="text-[#ede8dd]">{model.contextWindow}</strong></span>
              <span>·</span>
              <span>Dev: <strong className="text-[#ede8dd]">{model.developer.split(' ')[0]}</strong></span>
            </div>
          </div>

          {/* Footer Enclave Tag */}
          <div className="pt-2 border-t border-[#262421] flex items-center gap-1.5 text-[9.5px] font-mono text-[#3ea877]">
            <ShieldCheck className="w-3 h-3 text-[#3ea877] shrink-0" />
            <span className="truncate">{model.enclaveRuntime}</span>
          </div>
        </div>
      )}
    </div>
  );
};
