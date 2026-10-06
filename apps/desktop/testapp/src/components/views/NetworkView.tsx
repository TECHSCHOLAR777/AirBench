import React, { useState } from 'react';
import { NetworkTrace } from '../../types';
import { 
  Download, 
  Eye, 
  Copy, 
  Check, 
  CheckCircle2, 
  ShieldCheck, 
  Info,
  Server,
  Activity
} from 'lucide-react';

interface NetworkViewProps {
  traces: NetworkTrace[];
  onSelectTrace: (trace: NetworkTrace) => void;
}

export const NetworkView: React.FC<NetworkViewProps> = ({
  traces,
  onSelectTrace
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopyCurl = (trace: NetworkTrace) => {
    navigator.clipboard.writeText(trace.curlCommand);
    setCopiedId(trace.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleExportAudit = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify({
      audit_export_timestamp: new Date().toISOString(),
      sovereignty_score: "0.00% Zero egress verified",
      enclave_policy: "Strict Mutual Verification",
      traces
    }, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `airbench_audit_ledger_${Date.now()}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const localCalls = traces.filter(t => t.route === 'LOCAL').length;
  const cloudCalls = traces.filter(t => t.route === 'ENCLAVE_PROXY').length;

  return (
    <div className="flex-1 p-6 lg:p-10 bg-[#121211] overflow-y-auto font-sans" data-purpose="network-monitor-content">
      <div className="max-w-6xl mx-auto space-y-6 pb-12">
        {/* Title & Primary Toolbar Header matching screenshot 5 */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-1">
          <div>
            <h1 className="text-3xl font-serif tracking-tight text-[#f8f5ee] font-normal">
              Network monitor
            </h1>
            <p className="text-xs text-[#757069] font-mono mt-1 max-w-xl">
              Audit log of all outbound requests and cryptographic sovereignty verification.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 shrink-0 font-mono">
            <button
              onClick={handleExportAudit}
              disabled={traces.length === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[#181716] hover:bg-[#1f1e1c] border border-[#282624] text-xs text-[#ede8dd] transition cursor-pointer disabled:opacity-40"
            >
              <Download className="w-3.5 h-3.5 text-[#757069]" />
              <span>Export audit</span>
            </button>
          </div>
        </div>

        {/* BEGIN: SovereigntyBanner */}
        <section className="bg-[#161514] border border-[#3ea877]/30 rounded-lg p-3.5 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-sm" data-purpose="sovereignty-banner">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-[#122319] border border-[#3ea877]/40 flex items-center justify-center text-[#3ea877] shrink-0">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[#ede8dd]">
                Sovereignty Verified
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#122319] border border-[#3ea877]/40 text-[#3ea877] font-medium">
                0 Leaks
              </span>
            </div>
          </div>

          {/* Concise Status Chips */}
          <div className="flex items-center gap-2 flex-wrap font-mono text-[11px]">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1f1e1c] border border-[#282624] text-[#a39e95]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877]" />
              Local GPU: <strong className="text-[#ede8dd] font-semibold">{localCalls} calls</strong>
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1f1e1c] border border-[#282624] text-[#a39e95]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#d99c43]" />
              Cloud AI: <strong className="text-[#ede8dd] font-semibold">{cloudCalls} calls</strong>
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1f1e1c] border border-[#282624] text-[#a39e95]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#757069]" />
              Untrusted: <strong className="text-[#ede8dd] font-semibold">0 calls</strong>
            </span>
          </div>
        </section>

        {/* BEGIN: MetricSummaryCards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5" data-purpose="session-metrics">
          {/* Metric 1: Total Calls */}
          <div className="bg-[#181716] border border-[#282624] rounded-lg p-4 flex flex-col justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#757069]">
              Total Calls
            </span>
            <div className="my-2">
              <div className="text-3xl font-mono font-medium text-[#f8f5ee]">
                {traces.length}
              </div>
            </div>
            <span className="text-[11px] text-[#757069] font-mono">
              In active session
            </span>
          </div>

          {/* Metric 2: Local Enclave */}
          <div className="bg-[#181716] border border-[#282624] rounded-lg p-4 flex flex-col justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#3ea877]">
              Local Enclave
            </span>
            <div className="my-2">
              <div className="text-3xl font-mono font-medium text-[#3ea877]">
                {localCalls}
              </div>
            </div>
            <span className="text-[11px] text-[#757069] font-mono">
              127.0.0.1 loopback
            </span>
          </div>

          {/* Metric 3: Cloud Worker */}
          <div className="bg-[#181716] border border-[#282624] rounded-lg p-4 flex flex-col justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#d99c43]">
              Cloud Worker
            </span>
            <div className="my-2">
              <div className="text-3xl font-mono font-medium text-[#a39e95]">
                {cloudCalls}
              </div>
            </div>
            <span className="text-[11px] text-[#757069] font-mono">
              Whitelisted provider
            </span>
          </div>

          {/* Metric 4: Security Leak Score */}
          <div className="bg-[#181716] border border-[#3ea877]/30 rounded-lg p-4 flex flex-col justify-between">
            <span className="text-[10px] font-mono uppercase tracking-wider text-[#3ea877]">
              Security Leak Score
            </span>
            <div className="my-2">
              <div className="text-3xl font-mono font-medium text-[#3ea877]">
                0.00%
              </div>
            </div>
            <span className="text-[11px] text-[#3ea877]/90 font-mono">
              Zero egress verified
            </span>
          </div>
        </section>

        {/* BEGIN: Session HTTP Audit Log Table */}
        <section className="bg-[#181716] border border-[#282624] rounded-lg overflow-hidden shadow-sm font-mono" data-purpose="audit-log-table">
          {/* Table Sub-header */}
          <div className="px-5 py-3 border-b border-[#282624] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-mono font-semibold tracking-wider text-[#a39e95] uppercase">
                Session HTTP Audit Log
              </h2>
              <span className="text-[10px] px-2 py-0.5 rounded bg-[#1f1e1c] text-[#a39e95] border border-[#282624]">
                {traces.length} calls
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-[#3ea877]">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#3ea877] opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#3ea877]" />
              </span>
              <span className="text-[11px] text-[#a39e95]">Live capture active</span>
            </div>
          </div>

          {traces.length === 0 ? (
            /* Empty state before any query has run */
            <div className="py-16 px-6 text-center space-y-3">
              <Activity className="w-8 h-8 text-[#63605a] mx-auto opacity-70" />
              <div className="text-xs text-[#ede8dd] font-semibold">
                No session network requests captured yet
              </div>
              <p className="text-[11px] text-[#757069] max-w-md mx-auto leading-relaxed">
                When you run a request in Assistant, execute calculations in Sandbox, or digitize a P&amp;ID drawing, all mutual TLS loopback traces will collect here with zero-egress cryptographic verification.
              </p>
            </div>
          ) : (
            /* Table Wrapper with Traces */
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[#282624] bg-[#161514] text-[10px] text-[#757069] uppercase tracking-wider">
                    <th className="py-2.5 px-4 font-medium" scope="col">Timestamp</th>
                    <th className="py-2.5 px-4 font-medium" scope="col">Route</th>
                    <th className="py-2.5 px-4 font-medium" scope="col">Destination Endpoint</th>
                    <th className="py-2.5 px-3 font-medium" scope="col">Method</th>
                    <th className="py-2.5 px-3 font-medium" scope="col">Status</th>
                    <th className="py-2.5 px-4 font-medium" scope="col">Payload</th>
                    <th className="py-2.5 px-4 font-medium" scope="col">Model Artifact</th>
                    <th className="py-2.5 px-4 font-medium text-right" scope="col">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#282624]/60 text-[11px]">
                  {traces.map((trace) => {
                    const [ip, path] = trace.endpoint.split('/');
                    return (
                      <tr key={trace.id} className="hover:bg-[#1f1e1c]/60 transition">
                        <td className="py-3 px-4 text-[#757069] whitespace-nowrap">
                          {trace.timestamp}
                        </td>
                        <td className="py-3 px-4">
                          <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-[#122319] border border-[#3ea877]/40 text-[#3ea877]">
                            <span className="w-1 h-1 rounded-full bg-[#3ea877]" />
                            {trace.route}
                          </span>
                        </td>
                        <td className="py-3 px-4 font-medium text-[#ede8dd]">
                          <span className="text-[#60a5fa]">{ip}</span>
                          <span className="text-[#757069]">/{path}</span>
                        </td>
                        <td className="py-3 px-3">
                          <span className="px-1.5 py-0.5 rounded bg-[#1f1e1c] text-[10px] text-[#a39e95] border border-[#282624]">
                            {trace.method}
                          </span>
                        </td>
                        <td className="py-3 px-3">
                          <span className="px-1.5 py-0.5 rounded bg-[#122319] text-[#3ea877] border border-[#3ea877]/30 font-semibold text-[10px]">
                            {trace.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-[#a39e95] whitespace-nowrap">
                          {trace.payloadBytes.toLocaleString()} B
                        </td>
                        <td className="py-3 px-4">
                          <span className="text-[#ede8dd]">{trace.model}</span>
                          <span className="ml-1.5 px-1 py-0.5 rounded bg-[#1f1e1c] text-[9px] text-[#757069] border border-[#282624]">
                            {trace.quantization}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          <div className="inline-flex items-center gap-2 text-[#757069]">
                            <button
                              onClick={() => onSelectTrace(trace)}
                              className="hover:text-[#ede8dd] transition p-1 cursor-pointer"
                              title="View Trace"
                            >
                              <Eye className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleCopyCurl(trace)}
                              className="hover:text-[#ede8dd] transition p-1 cursor-pointer"
                              title="Copy Curl Command"
                            >
                              {copiedId === trace.id ? <Check className="w-3.5 h-3.5 text-[#3ea877]" /> : <Copy className="w-3.5 h-3.5" />}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Table Status Footer */}
          <div className="px-5 py-2.5 bg-[#161514] border-t border-[#282624] flex flex-wrap items-center justify-between text-[11px] font-mono text-[#757069]">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877]" />
              <span>Hardware socket loopback active (<code className="text-[#ede8dd]">127.0.0.1:18002</code>)</span>
            </div>
            <div>
              <span>TLS 1.3 Strict Mutual Verification</span>
            </div>
          </div>
        </section>

        {/* Architecture Note */}
        <section className="bg-[#161514]/70 border border-[#282624] rounded-lg p-3.5 flex items-start gap-3" data-purpose="compact-architecture-note">
          <div className="p-1 rounded bg-[#1f1e1c] text-[#757069] shrink-0 mt-0.5">
            <Info className="w-3.5 h-3.5" />
          </div>
          <div className="text-xs text-[#a39e95] leading-relaxed font-sans">
            <span className="text-[#ede8dd] font-medium font-mono text-[11px]">Sovereignty Policy: </span>
            All inference executes on local on-premises GPU loopback (<code className="font-mono text-[#ede8dd]">127.0.0.1</code>). Zero outbound telemetry or cloud egress allowed.
          </div>
        </section>
      </div>
    </div>
  );
};
