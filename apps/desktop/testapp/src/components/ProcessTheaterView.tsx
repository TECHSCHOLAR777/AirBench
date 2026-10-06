import React, { useEffect, useRef } from 'react';
import { 
  ProcessTheaterState 
} from '../utils/processTheater';
import { 
  Loader2, 
  CheckCircle2, 
  Terminal 
} from 'lucide-react';

interface ProcessTheaterViewProps {
  title: string;
  subtitle?: string;
  state: ProcessTheaterState;
  className?: string;
  compact?: boolean;
}

export const ProcessTheaterView: React.FC<ProcessTheaterViewProps> = ({
  title,
  subtitle,
  state,
  className = '',
  compact = false
}) => {
  const terminalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [state.logs.length]);

  const activePhase = state.phases[state.currentPhaseIndex] || state.phases[0];

  return (
    <div className={`flex flex-col font-mono text-xs text-[#ede8dd] space-y-4 ${className}`}>
      {/* Clean Header */}
      {!compact && (
        <div className="space-y-1.5 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#bd5b38]/15 border border-[#bd5b38]/30 text-[#bd5b38] text-[11px] font-semibold">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>{activePhase?.name || 'Processing'} Active</span>
          </div>
          <h2 className="text-xl font-serif text-[#ede8dd] tracking-tight font-normal">
            {title}
          </h2>
          {subtitle && (
            <p className="text-xs text-[#8e8982] max-w-lg mx-auto font-sans">
              {subtitle}
            </p>
          )}
        </div>
      )}

      {/* Progress Bar & Milestone Status */}
      <div className="bg-[#141312] border border-[#282725] rounded-xl p-4 sm:p-5 space-y-4 shadow-sm">
        {/* Progress percent header */}
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-[#ede8dd] font-semibold">
            <span className="w-2 h-2 rounded-full bg-[#bd5b38] animate-ping" />
            <span>{activePhase?.name || 'Processing...'}</span>
          </div>
          <span className="text-[#3ea877] font-semibold font-mono text-sm">
            {state.progressPercent}%
          </span>
        </div>

        {/* Primary Clean Progress Bar */}
        <div className="w-full h-2.5 bg-[#1f1e1c] rounded-full overflow-hidden border border-[#2e2d29]">
          <div 
            className="h-full bg-gradient-to-r from-[#bd5b38] via-[#d99c43] to-[#3ea877] transition-all duration-300 ease-out"
            style={{ width: `${state.progressPercent}%` }}
          />
        </div>

        {/* Simplified Phase Milestones: pending -> running -> done */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-1">
          {state.phases.map((phase, idx) => {
            const isPending = phase.status === 'pending';
            const isRunning = phase.status === 'running';
            const isDone = phase.status === 'done';

            return (
              <div 
                key={phase.id}
                className={`p-2.5 rounded-lg border transition-all flex items-center gap-2.5 ${
                  isRunning 
                    ? 'bg-[#bd5b38]/10 border-[#bd5b38]/60 shadow-xs' 
                    : isDone 
                    ? 'bg-[#181716] border-[#2e2d29] text-[#ede8dd]' 
                    : 'bg-[#11100f] border-[#1d1c1a] opacity-40 text-[#757069]'
                }`}
              >
                <div className="shrink-0">
                  {isDone && (
                    <CheckCircle2 className="w-4 h-4 text-[#3ea877]" />
                  )}
                  {isRunning && (
                    <Loader2 className="w-4 h-4 text-[#bd5b38] animate-spin" />
                  )}
                  {isPending && (
                    <div className="w-4 h-4 rounded-full border border-[#35332f] flex items-center justify-center text-[10px] text-[#757069]">
                      {idx + 1}
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className={`text-[11.5px] font-medium truncate ${
                    isRunning ? 'text-[#ede8dd]' : isDone ? 'text-[#dcd7cd]' : 'text-[#757069]'
                  }`}>
                    {phase.name}
                  </div>
                  <div className="text-[9.5px] uppercase tracking-wider text-[#757069]">
                    {isRunning ? (
                      <span className="text-[#bd5b38]">Active</span>
                    ) : isDone ? (
                      <span className="text-[#3ea877]">Complete</span>
                    ) : (
                      'Pending'
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Low-Level Terminal Logs (YOLO inference, EasyOCR tags, vectorization) */}
      <div className="bg-[#100f0e] border border-[#282725] rounded-xl p-3.5 font-mono text-xs space-y-2 shadow-inner">
        <div className="flex items-center justify-between pb-2 border-b border-[#22211e] text-[10px] text-[#757069]">
          <div className="flex items-center gap-1.5 font-semibold text-[#8e8982]">
            <Terminal className="w-3.5 h-3.5 text-[#bd5b38]" />
            <span>EXECUTION LOG</span>
          </div>
          <span className="text-[9.5px] text-[#3ea877]">Isolated Local Runtime</span>
        </div>

        <div className="max-h-44 overflow-y-auto space-y-1.5 text-[11px] font-mono leading-relaxed pt-1 select-text">
          {state.logs.map((log) => (
            <div key={log.id} className="flex items-start gap-2">
              <span className="text-[#63605a] text-[10px] whitespace-nowrap mt-0.5">{log.time}</span>
              <span className={`break-all ${
                log.level === 'success' 
                  ? 'text-[#3ea877]' 
                  : log.level === 'kernel' 
                  ? 'text-[#60a5fa]' 
                  : log.level === 'debug' 
                  ? 'text-[#d99c43]' 
                  : 'text-[#dcd7cd]'
              }`}>
                {log.text}
              </span>
            </div>
          ))}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
};
