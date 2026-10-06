import React, { useState } from 'react';
import { X, Calculator, ArrowRight, Check, Sparkles, Loader2, Copy } from 'lucide-react';
import { solveCalculation } from '../services/inferenceService';

interface QuickCalcModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyResult?: (val: string) => void;
}

export const QuickCalcModal: React.FC<QuickCalcModalProps> = ({
  isOpen,
  onClose,
  onApplyResult
}) => {
  const [calcTab, setCalcTab] = useState<'ai_calc' | 'pressure' | 'reynolds' | 'units'>('ai_calc');

  // AI Calculator state
  const [aiPrompt, setAiPrompt] = useState('Calculate pressure drop in 85m 6-inch pipe with 140 m3/h gas oil');
  const [aiSolution, setAiSolution] = useState<string | null>(null);
  const [aiModelUsed, setAiModelUsed] = useState<string | null>(null);
  const [isSolving, setIsSolving] = useState(false);
  const [copiedSolution, setCopiedSolution] = useState(false);

  // Darcy Weisbach state
  const [dwFlow, setDwFlow] = useState(90); // m3/h
  const [dwDia, setDwDia] = useState(101.6); // mm
  const [dwLen, setDwLen] = useState(47.5); // m
  const [dwRho, setDwRho] = useState(850); // kg/m3

  // Unit converter state
  const [valFrom, setValFrom] = useState(10);
  const [unitCategory, setUnitCategory] = useState<'pressure' | 'flow' | 'temp'>('pressure');

  if (!isOpen) return null;

  const handleSolveAi = async () => {
    if (!aiPrompt.trim()) return;
    setIsSolving(true);
    try {
      const res = await solveCalculation(aiPrompt.trim());
      setAiSolution(res.solution);
      setAiModelUsed(res.modelUsed);
    } catch (err: any) {
      console.warn('AI Calc failed:', err);
    } finally {
      setIsSolving(false);
    }
  };

  const handleCopySolution = () => {
    if (!aiSolution) return;
    navigator.clipboard.writeText(aiSolution);
    setCopiedSolution(true);
    setTimeout(() => setCopiedSolution(false), 2000);
  };

  // Hydraulic calculation
  const q_m3s = dwFlow / 3600;
  const d_m = dwDia / 1000;
  const area = Math.PI * (d_m / 2) ** 2;
  const velocity = area > 0 ? q_m3s / area : 0;
  const re = (dwRho * velocity * d_m) / 0.004;
  const f_est = re > 4000 ? 0.021 : 64 / (re || 1);
  const dp_kpa = d_m > 0 ? (f_est * (dwLen / d_m) * (dwRho * velocity ** 2 / 2)) / 1000 : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div 
        className="w-full max-w-2xl bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col max-h-[90vh]"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#282725] bg-[#1a1918]">
          <div className="flex items-center gap-2">
            <Calculator className="w-4 h-4 text-[#bd5b38]" />
            <span className="font-semibold text-sm text-[#ede8dd]">
              Engineering Calculator &amp; Matrix Utility
            </span>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switch */}
        <div className="px-5 py-2 bg-[#141312] border-b border-[#262422] flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setCalcTab('ai_calc')}
            className={`px-3 py-1 rounded transition-colors flex items-center gap-1.5 cursor-pointer ${
              calcTab === 'ai_calc' ? 'bg-[#22211e] text-[#ede8dd] border border-[#bd5b38]/50 text-[#bd5b38]' : 'text-[#8e8982] hover:text-[#ede8dd]'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-[#bd5b38]" />
            <span>Enclave AI Solver</span>
          </button>
          <button
            onClick={() => setCalcTab('pressure')}
            className={`px-3 py-1 rounded transition-colors cursor-pointer ${
              calcTab === 'pressure' ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]' : 'text-[#8e8982] hover:text-[#ede8dd]'
            }`}
          >
            Hydraulic Gradient
          </button>
          <button
            onClick={() => setCalcTab('reynolds')}
            className={`px-3 py-1 rounded transition-colors cursor-pointer ${
              calcTab === 'reynolds' ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]' : 'text-[#8e8982] hover:text-[#ede8dd]'
            }`}
          >
            Flow Regime &amp; Re
          </button>
          <button
            onClick={() => setCalcTab('units')}
            className={`px-3 py-1 rounded transition-colors cursor-pointer ${
              calcTab === 'units' ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]' : 'text-[#8e8982] hover:text-[#ede8dd]'
            }`}
          >
            Industrial Units
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4 overflow-y-auto flex-1">
          {calcTab === 'ai_calc' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-[10.5px] uppercase tracking-wider text-[#757069] block font-semibold">
                  Engineering Formula &amp; Unit Solver
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={aiPrompt}
                    onChange={e => setAiPrompt(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSolveAi(); }}
                    placeholder="e.g. Calculate required pump head for 160 m3/h at 5.5 bar differential..."
                    className="flex-1 bg-[#141312] border border-[#2b2926] rounded px-3 py-2 text-[#ede8dd] focus:outline-none focus:border-[#bd5b38]"
                  />
                  <button
                    type="button"
                    onClick={handleSolveAi}
                    disabled={isSolving || !aiPrompt.trim()}
                    className="px-4 py-2 bg-[#bd5b38] hover:bg-[#a74f30] disabled:opacity-40 text-white rounded font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
                  >
                    {isSolving ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Solving...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>Solve</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Quick Prompt Ideas */}
              <div className="flex flex-wrap gap-1.5">
                {[
                  'Calculate LMTD for 180°C hot in, 110°C out vs 35°C cold in, 88°C out',
                  'Reynolds number for 2.1 m/s water through 150mm pipe at 20°C',
                  'Ideal gas volumetric density of Methane at 15 bar and 40°C'
                ].map((s, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setAiPrompt(s);
                      setAiSolution(null);
                    }}
                    className="text-[10px] px-2 py-0.5 rounded bg-[#1f1e1c] text-[#8e8982] hover:text-[#ede8dd] border border-[#2c2a26] transition-colors cursor-pointer text-left truncate max-w-full"
                  >
                    &gt; {s}
                  </button>
                ))}
              </div>

              {/* Solution Output Box */}
              {aiSolution && (
                <div className="p-4 bg-[#141312] border border-[#33312c] rounded-xl space-y-2 text-xs">
                  <div className="flex items-center justify-between pb-2 border-b border-[#262422]">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#3ea877]" />
                      <span className="text-[#ede8dd] font-semibold">{aiModelUsed || 'qwen2.5-coder-7b'}</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleCopySolution}
                      className="flex items-center gap-1 px-2 py-0.5 rounded bg-[#201f1c] hover:bg-[#282623] text-[#ede8dd] text-[11px] cursor-pointer"
                    >
                      {copiedSolution ? (
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
                  </div>
                  <div className="text-[#e2ded5] leading-relaxed whitespace-pre-wrap font-sans text-xs pt-1">
                    {aiSolution}
                  </div>
                </div>
              )}
            </div>
          )}

          {calcTab === 'pressure' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-[#757069] block mb-1">Flow Rate (m³/h)</label>
                  <input
                    type="number"
                    value={dwFlow}
                    onChange={e => setDwFlow(Number(e.target.value))}
                    className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-1.5 text-[#ede8dd]"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-[#757069] block mb-1">Pipe Inner Dia (mm)</label>
                  <input
                    type="number"
                    value={dwDia}
                    onChange={e => setDwDia(Number(e.target.value))}
                    className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-1.5 text-[#ede8dd]"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-[#757069] block mb-1">Equivalent Length (m)</label>
                  <input
                    type="number"
                    value={dwLen}
                    onChange={e => setDwLen(Number(e.target.value))}
                    className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-1.5 text-[#ede8dd]"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-[#757069] block mb-1">Fluid Density (kg/m³)</label>
                  <input
                    type="number"
                    value={dwRho}
                    onChange={e => setDwRho(Number(e.target.value))}
                    className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-1.5 text-[#ede8dd]"
                  />
                </div>
              </div>

              {/* Solved Results */}
              <div className="p-4 bg-[#141312] border border-[#262422] rounded-lg space-y-2">
                <div className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
                  Solved Hydraulic Drop
                </div>
                <div className="grid grid-cols-3 gap-2 text-center pt-1">
                  <div className="p-2 bg-[#1b1a18] rounded border border-[#2a2925]">
                    <div className="text-[10px] text-[#757069]">Velocity</div>
                    <div className="text-sm font-semibold text-[#ede8dd] mt-0.5">{velocity.toFixed(3)} m/s</div>
                  </div>
                  <div className="p-2 bg-[#1b1a18] rounded border border-[#2a2925]">
                    <div className="text-[10px] text-[#757069]">Reynolds</div>
                    <div className="text-sm font-semibold text-[#3ea877] mt-0.5">{Math.round(re).toLocaleString()}</div>
                  </div>
                  <div className="p-2 bg-[#1b1a18] rounded border border-[#2a2925]">
                    <div className="text-[10px] text-[#757069]">Delta P</div>
                    <div className="text-sm font-semibold text-[#bd5b38] mt-0.5">{dp_kpa.toFixed(2)} kPa</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {calcTab === 'reynolds' && (
            <div className="space-y-3">
              <div className="text-xs text-[#a8a39a] leading-relaxed">
                Calculates flow turbulence index based on Darcy-Weisbach formulation:
                <code className="text-[#3ea877] block mt-1 bg-[#141312] p-2 rounded border border-[#262422]">
                  Re = (ρ * v * D) / μ
                </code>
              </div>
              <div className="p-3 bg-[#141312] rounded border border-[#262422] space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-[#757069]">Re &lt; 2,300:</span>
                  <span className="text-[#ede8dd]">Laminar Regime (f = 64/Re)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#757069]">2,300 &le; Re &le; 4,000:</span>
                  <span className="text-[#d99c43]">Critical Transition Zone</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-[#757069]">Re &gt; 4,000:</span>
                  <span className="text-[#3ea877]">Fully Turbulent (Colebrook-White)</span>
                </div>
              </div>
            </div>
          )}

          {calcTab === 'units' && (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="flex-1">
                  <label className="text-[10px] text-[#757069] block mb-1">Input Value</label>
                  <input
                    type="number"
                    value={valFrom}
                    onChange={e => setValFrom(Number(e.target.value))}
                    className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-1.5 text-[#ede8dd]"
                  />
                </div>
                <div className="w-40">
                  <label className="text-[10px] text-[#757069] block mb-1">Dimension</label>
                  <select
                    value={unitCategory}
                    onChange={e => setUnitCategory(e.target.value as any)}
                    className="w-full bg-[#141312] border border-[#282725] rounded px-3 py-1.5 text-[#ede8dd]"
                  >
                    <option value="pressure">Pressure</option>
                    <option value="flow">Flow Rate</option>
                    <option value="temp">Temperature</option>
                  </select>
                </div>
              </div>

              {unitCategory === 'pressure' && (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2.5 bg-[#141312] rounded border border-[#262422]">
                    <span className="text-[#757069] text-[10px] block">bar gauge</span>
                    <span className="text-[#ede8dd] font-semibold">{valFrom} bar</span>
                  </div>
                  <div className="p-2.5 bg-[#141312] rounded border border-[#262422]">
                    <span className="text-[#757069] text-[10px] block">Kilopascals (kPa)</span>
                    <span className="text-[#3ea877] font-semibold">{(valFrom * 100).toFixed(1)} kPa</span>
                  </div>
                  <div className="p-2.5 bg-[#141312] rounded border border-[#262422]">
                    <span className="text-[#757069] text-[10px] block">Pounds / sq in (psi)</span>
                    <span className="text-[#ede8dd] font-semibold">{(valFrom * 14.5038).toFixed(2)} psi</span>
                  </div>
                  <div className="p-2.5 bg-[#141312] rounded border border-[#262422]">
                    <span className="text-[#757069] text-[10px] block">Atmospheres (atm)</span>
                    <span className="text-[#ede8dd] font-semibold">{(valFrom * 0.986923).toFixed(3)} atm</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-[#282725] bg-[#1a1918] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white text-xs font-semibold transition-colors cursor-pointer"
          >
            Close Calculator
          </button>
        </div>
      </div>
    </div>
  );
};
