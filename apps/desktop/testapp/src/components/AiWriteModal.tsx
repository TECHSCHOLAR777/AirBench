import React, { useState } from 'react';
import { 
  Sparkles, 
  X, 
  Cpu, 
  Play, 
  Plus, 
  Check, 
  Loader2, 
  FileCode, 
  Zap,
  ArrowRight
} from 'lucide-react';
import { aiWriteCode, AiWriteResult } from '../services/sandboxService';
import { ModelHoverTooltip } from './ModelHoverTooltip';

interface AiWriteModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentCode: string;
  onApplyCode: (newCode: string, mode: 'replace' | 'append', autoRun: boolean) => void;
}

export const AiWriteModal: React.FC<AiWriteModalProps> = ({
  isOpen,
  onClose,
  currentCode,
  onApplyCode
}) => {
  const [prompt, setPrompt] = useState('');
  const [modelChoice, setModelChoice] = useState('qwen2.5-coder-7b');
  const [insertionMode, setInsertionMode] = useState<'replace' | 'append'>('replace');
  const [autoRun, setAutoRun] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiWriteResult | null>(null);

  if (!isOpen) return null;

  const quickPrompts = [
    'Simulate Darcy-Weisbach pipe hydraulics and Colebrook-White friction factor',
    'Calculate Log Mean Temperature Difference (LMTD) for shell & tube heat exchanger',
    'Parse sensor telemetry JSON, detect variance anomalies and threshold breaches',
    'Solve 2D incompressible cavity flow Navier-Stokes stream-vorticity iterations'
  ];

  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    setIsLoading(true);
    setError(null);

    try {
      const data = await aiWriteCode({
        prompt: prompt.trim(),
        modelChoice,
        currentCode
      });
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Generation request failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleApply = () => {
    if (!result) return;
    onApplyCode(result.code, insertionMode, autoRun);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 animate-in fade-in duration-100 font-sans">
      <div className="w-full max-w-2xl bg-[#181716] border border-[#2e2d29] rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-4 bg-[#141312] border-b border-[#282725] flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[#bd5b38]/10 text-[#bd5b38] border border-[#bd5b38]/30">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-serif text-base text-[#ede8dd] font-normal">
                AI Code Writer
              </h3>
              <p className="text-[11px] font-mono text-[#8e8982]">
                Synthesize executable Python algorithms via Sovereign Enclave models
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] p-1 rounded transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1 text-xs">
          {!result ? (
            <>
              {/* Model Choice Segmented Selector */}
              <div className="space-y-1.5 font-mono">
                <span className="text-[10.5px] uppercase tracking-wider text-[#757069] block font-semibold">
                  Select Engine
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {[
                    { id: 'qwen2.5-coder-7b', label: 'Qwen 2.5 Coder 7B', tag: 'Python / Math', sub: 'Isolated Kernel' },
                    { id: 'deepseek-coder-6.7b', label: 'DeepSeek Coder 6.7B', tag: 'Logic & AST', sub: 'Zero-Egress' }
                  ].map(m => (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => setModelChoice(m.id)}
                      className={`p-2.5 rounded-xl border text-left transition-all cursor-pointer flex flex-col justify-between ${
                        modelChoice === m.id
                          ? 'bg-[#22201d] border-[#bd5b38] text-[#ede8dd] shadow-sm'
                          : 'bg-[#151413] border-[#292723] hover:border-[#383530] text-[#8e8982]'
                      }`}
                    >
                      <div className="flex items-center justify-between w-full">
                        <span className="font-semibold text-xs text-[#ede8dd]">{m.label}</span>
                        <span className="text-[9px] px-1.5 py-0.2 rounded bg-black/40 text-[#3ea877]">{m.tag}</span>
                      </div>
                      <span className="text-[10px] text-[#757069] mt-1">{m.sub}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Prompt Input */}
              <div className="space-y-1.5">
                <label className="text-[10.5px] font-mono uppercase tracking-wider text-[#757069] block font-semibold">
                  Describe Algorithm or Engineering Routine
                </label>
                <textarea
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder="e.g. Write a Python script to compute pressure loss in an 8-inch crude oil transfer line using Colebrook-White friction..."
                  rows={4}
                  className="w-full p-3 rounded-xl bg-[#141312] border border-[#2b2926] text-[#ede8dd] placeholder-[#5c5852] focus:outline-none focus:border-[#bd5b38] resize-none font-sans text-xs leading-relaxed"
                />
              </div>

              {/* Quick Prompt Ideas */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-mono uppercase text-[#757069] tracking-wider block">
                  Quick Scenarios:
                </span>
                <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
                  {quickPrompts.map((qp, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setPrompt(qp)}
                      className="px-2.5 py-1 rounded-lg bg-[#1a1918] hover:bg-[#22211e] border border-[#282724] text-[#a8a39a] hover:text-[#ede8dd] transition-colors cursor-pointer text-left truncate max-w-full"
                    >
                      &gt; {qp.slice(0, 50)}...
                    </button>
                  ))}
                </div>
              </div>

              {/* Settings: Insertion Mode & Auto-run */}
              <div className="p-3 rounded-xl bg-[#151413] border border-[#262421] flex flex-wrap items-center justify-between gap-3 font-mono text-xs text-[#8e8982]">
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-[#757069]">Destination:</span>
                  <label className="flex items-center gap-1.5 cursor-pointer text-[#ede8dd]">
                    <input 
                      type="radio" 
                      name="mode" 
                      checked={insertionMode === 'replace'} 
                      onChange={() => setInsertionMode('replace')}
                      className="accent-[#bd5b38]"
                    />
                    <span>Replace Sheet</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-[#ede8dd]">
                    <input 
                      type="radio" 
                      name="mode" 
                      checked={insertionMode === 'append'} 
                      onChange={() => setInsertionMode('append')}
                      className="accent-[#bd5b38]"
                    />
                    <span>Append to Code</span>
                  </label>
                </div>

                <label className="flex items-center gap-1.5 cursor-pointer text-[#3ea877] font-medium">
                  <input 
                    type="checkbox" 
                    checked={autoRun} 
                    onChange={e => setAutoRun(e.target.checked)} 
                    className="accent-[#3ea877]"
                  />
                  <span>Execute immediately in Terminal</span>
                </label>
              </div>

              {error && (
                <div className="p-3 rounded-lg bg-[#381616] border border-[#ef4444]/40 text-[#ef4444] text-xs font-mono">
                  {error}
                </div>
              )}
            </>
          ) : (
            /* Result Preview Screen */
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs font-mono text-[#8e8982] pb-1 border-b border-[#282624]">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#3ea877]" />
                  <span className="text-[#ede8dd] font-semibold">Generated by {result.modelUsed}</span>
                </div>
                <span>{result.tokens} tokens · {result.latencyMs} ms</span>
              </div>

              {result.explanation && (
                <p className="text-xs text-[#a8a39a] leading-relaxed font-sans bg-[#151413] p-3 rounded-lg border border-[#262422]">
                  {result.explanation}
                </p>
              )}

              {/* Code block preview */}
              <div className="border border-[#282725] rounded-xl overflow-hidden bg-[#100f0e] font-mono text-xs">
                <div className="px-3 py-1.5 bg-[#141312] border-b border-[#242220] flex items-center justify-between text-[11px] text-[#757069]">
                  <span>python3 code buffer</span>
                  <span className="text-[#3ea877]">Zero-Egress Verified</span>
                </div>
                <pre className="p-4 text-[#d4cfc5] overflow-x-auto max-h-64 whitespace-pre leading-relaxed text-[11.5px]">
                  {result.code}
                </pre>
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="p-4 bg-[#141312] border-t border-[#262422] flex items-center justify-between font-mono text-xs">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[#1e1d1b] hover:bg-[#252421] text-[#ede8dd] border border-[#2b2a26] transition-colors cursor-pointer"
          >
            Cancel
          </button>

          {!result ? (
            <button
              type="button"
              onClick={handleGenerate}
              disabled={isLoading || !prompt.trim()}
              className="flex items-center gap-2 px-5 py-2 rounded-lg bg-[#bd5b38] hover:bg-[#a74f30] disabled:opacity-40 text-white font-medium shadow-md transition-colors cursor-pointer"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Synthesizing...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Generate Code</span>
                </>
              )}
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setResult(null)}
                className="px-3 py-2 rounded-lg bg-[#201f1c] text-[#8e8982] hover:text-[#ede8dd] transition-colors cursor-pointer"
              >
                Refine Prompt
              </button>
              <button
                type="button"
                onClick={handleApply}
                className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-[#3ea877] hover:bg-[#349266] text-white font-medium shadow-md transition-colors cursor-pointer"
              >
                <Check className="w-4 h-4" />
                <span>{autoRun ? 'Apply & Execute Code' : 'Apply to Sheet'}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
