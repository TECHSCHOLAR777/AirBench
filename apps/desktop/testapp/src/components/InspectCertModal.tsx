import React from 'react';
import { EnclaveNode } from '../types';
import { ShieldCheck, X, Copy, Check, Lock, CheckCircle2 } from 'lucide-react';

interface InspectCertModalProps {
  node: EnclaveNode | null;
  onClose: () => void;
}

export const InspectCertModal: React.FC<InspectCertModalProps> = ({ node, onClose }) => {
  const [copied, setCopied] = React.useState(false);

  if (!node) return null;

  const copyFingerprint = () => {
    navigator.clipboard.writeText(node.fingerprint);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div 
        className="w-full max-w-xl bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden font-mono text-xs flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-[#282725] bg-[#1a1918]">
          <div className="flex items-center gap-2.5">
            <Lock className="w-4 h-4 text-[#3ea877]" />
            <span className="font-semibold text-sm text-[#ede8dd]">
              Cryptographic Certificate Proof
            </span>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
          {/* Node Identity Banner */}
          <div className="p-3 rounded-lg bg-[#201f1c] border border-[#2e2d29] flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
                Target Node Hostname
              </div>
              <div className="text-sm font-semibold text-[#ede8dd] mt-0.5">
                {node.hostname}
              </div>
              <div className="text-[11px] text-[#3ea877] mt-0.5 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Zero-Egress Sovereign Enclave Pinning</span>
              </div>
            </div>
            <span className="text-[10px] px-2 py-0.5 rounded bg-[#3ea877]/10 text-[#3ea877] border border-[#3ea877]/30">
              {node.status}
            </span>
          </div>

          {/* Certificate Field Matrix */}
          <div className="space-y-3 bg-[#141312] p-4 rounded-lg border border-[#262422]">
            <div>
              <span className="text-[10px] uppercase text-[#757069] block">
                Certificate Issuer &amp; Authority
              </span>
              <span className="text-xs text-[#ede8dd] break-all">
                {node.certificateIssuer}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-1 border-t border-[#262422]">
              <div>
                <span className="text-[10px] uppercase text-[#757069] block">Local Socket</span>
                <span className="text-xs text-[#d99c43]">{node.host}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase text-[#757069] block">mTLS Latency</span>
                <span className="text-xs text-[#ede8dd]">{node.latency}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-1 border-t border-[#262422]">
              <div>
                <span className="text-[10px] uppercase text-[#757069] block">Cipher Suite</span>
                <span className="text-xs text-[#ede8dd]">TLS_AES_256_GCM_SHA384</span>
              </div>
              <div>
                <span className="text-[10px] uppercase text-[#757069] block">Validity Horizon</span>
                <span className="text-xs text-[#ede8dd]">Until {node.expires}</span>
              </div>
            </div>

            <div className="pt-1 border-t border-[#262422]">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] uppercase text-[#757069]">
                  SHA-256 Public Key Fingerprint
                </span>
                <button
                  onClick={copyFingerprint}
                  className="flex items-center gap-1 text-[10px] text-[#bd5b38] hover:text-[#cf6741] transition-colors"
                >
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              </div>
              <div className="p-2 rounded bg-[#1c1b18] border border-[#2b2926] text-[11px] text-[#9c978f] break-all select-all font-mono">
                {node.fingerprint}
              </div>
            </div>
          </div>

          {/* Enclave Policy Guarantee */}
          <div className="text-[11px] text-[#8e8982] leading-relaxed bg-[#1f1e1c] p-3 rounded border border-[#2a2925]">
            <strong className="text-[#ede8dd]">Sovereign Assurance:</strong> This node runs under signed hardware-level loopback isolation. Memory buffers and inference artifacts are cryptographically scrubbed after execution and never routed to non-enrolled network peers.
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-5 py-3 border-t border-[#282725] bg-[#1a1918] flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white text-xs font-semibold transition-colors"
          >
            Acknowledge Proof
          </button>
        </div>
      </div>
    </div>
  );
};
