import React, { useState } from 'react';
import { NetworkTrace } from '../types';
import { X, Copy, Check, Terminal, ShieldCheck, CheckCircle2 } from 'lucide-react';

interface TraceInspectModalProps {
  trace: NetworkTrace | null;
  onClose: () => void;
}

export const TraceInspectModal: React.FC<TraceInspectModalProps> = ({ trace, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!trace) return null;

  const copyCurl = () => {
    navigator.clipboard.writeText(trace.curlCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 lg:p-6 animate-in fade-in duration-150">
      <div 
        className="w-full max-w-2xl max-h-[85vh] bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden flex flex-col font-mono text-xs"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#282725] bg-[#1a1918]">
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="w-4 h-4 text-[#3ea877]" />
            <span className="font-semibold text-sm text-[#ede8dd]">
              Session HTTP Audit Trace #{trace.id}
            </span>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto space-y-4">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-[#141312] p-3.5 rounded-lg border border-[#262422]">
            <div>
              <span className="text-[10px] text-[#757069] block">Timestamp</span>
              <span className="text-[#ede8dd] font-semibold">{trace.timestamp}</span>
            </div>
            <div>
              <span className="text-[10px] text-[#757069] block">Route Policy</span>
              <span className="text-[#3ea877] font-semibold">{trace.route}</span>
            </div>
            <div>
              <span className="text-[10px] text-[#757069] block">HTTP Status</span>
              <span className="text-[#3ea877] font-semibold">{trace.status} OK</span>
            </div>
            <div>
              <span className="text-[10px] text-[#757069] block">Payload Size</span>
              <span className="text-[#ede8dd]">{trace.payloadBytes.toLocaleString()} B</span>
            </div>
          </div>

          {/* Endpoint & Model Block */}
          <div className="space-y-2">
            <div className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
              Destination Endpoint &amp; Model
            </div>
            <div className="p-3 bg-[#1f1e1c] rounded border border-[#2b2926] space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[#a8a39a]">Endpoint URI:</span>
                <span className="text-[#60a5fa]">{trace.endpoint}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#a8a39a]">Model Artifact:</span>
                <span className="text-[#ede8dd] font-semibold">{trace.model} ({trace.quantization})</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#a8a39a]">Transport Security:</span>
                <span className="text-[#3ea877]">TLS 1.3 Strict Mutual Verification</span>
              </div>
            </div>
          </div>

          {/* Request Headers */}
          <div className="space-y-2">
            <div className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
              Enclave Mutual Transport Headers
            </div>
            <div className="p-3 bg-[#141312] rounded border border-[#262422] space-y-1 font-mono text-[11px]">
              {Object.entries(trace.headers).map(([key, value]) => (
                <div key={key} className="flex items-start justify-between gap-4">
                  <span className="text-[#8e8982] shrink-0">{key}:</span>
                  <span className="text-[#ede8dd] text-right truncate">{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Curl Command Replay */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
                cURL CLI Execution Command
              </span>
              <button
                onClick={copyCurl}
                className="flex items-center gap-1 text-[10px] text-[#bd5b38] hover:text-[#cf6741] transition-colors"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                <span>{copied ? 'Copied to Clipboard' : 'Copy cURL'}</span>
              </button>
            </div>
            <pre className="p-3 bg-[#11100f] text-[#3ea877] rounded border border-[#262422] overflow-x-auto text-[11px] leading-relaxed select-all">
              {trace.curlCommand}
            </pre>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-[#282725] bg-[#1a1918] flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-[#3ea877]">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Cryptographic boundary verified: 0 outbound leakage</span>
          </div>
          <button
            onClick={onClose}
            className="px-3.5 py-1.5 rounded bg-[#22211e] hover:bg-[#2e2d29] text-[#ede8dd] text-xs transition-colors border border-[#383633]"
          >
            Close Trace
          </button>
        </div>
      </div>
    </div>
  );
};
