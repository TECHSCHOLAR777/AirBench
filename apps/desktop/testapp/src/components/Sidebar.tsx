import React, { useState } from 'react';
import { PageView, EnclaveNode } from '../types';
import { 
  Home, 
  GitBranch, 
  Terminal, 
  BookOpen, 
  CheckSquare, 
  ShieldCheck, 
  Plus, 
  Server, 
  ChevronDown,
  CheckCircle2,
  HardDrive
} from 'lucide-react';

interface SidebarProps {
  currentView: PageView;
  onViewChange: (view: PageView) => void;
  onNewQuery: () => void;
  activeNode: EnclaveNode | null;
  onSelectNode: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentView,
  onViewChange,
  onNewQuery,
  activeNode,
  onSelectNode
}) => {
  const [nodeDropdownOpen, setNodeDropdownOpen] = useState(false);

  return (
    <aside 
      className="w-64 bg-[#171615] border-r border-[#262422] flex flex-col justify-between shrink-0 h-full select-none z-20"
      data-purpose="main-sidebar"
    >
      {/* Top Branding & Navigation Links */}
      <div className="p-4 flex flex-col gap-5">
        {/* Brand Logo / Identity */}
        <div 
          onClick={() => onViewChange('home')}
          className="flex items-center gap-3 px-1 pt-1 cursor-pointer group"
        >
          <div className="w-8 h-8 rounded bg-[#242320] border border-[#35332f] flex items-center justify-center font-serif text-lg font-bold text-[#ede8dd] shadow-inner group-hover:border-[#bd5b38]/60 transition-colors">
            A
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold tracking-wide text-[#ede8dd] leading-tight font-sans">
              AirBench
            </span>
            <span className="text-[10px] tracking-wider uppercase text-[#757069] font-mono">
              Sovereign task command
            </span>
          </div>
        </div>

        {/* Action Button: New Query */}
        <button
          onClick={onNewQuery}
          className="w-full flex items-center justify-between px-3 py-2 bg-[#bd5b38] hover:bg-[#a74f30] text-white rounded text-xs font-medium shadow-sm transition-all group cursor-pointer"
          data-purpose="new-query-button"
          type="button"
        >
          <span className="flex items-center gap-1.5 font-sans font-semibold">
            <Plus className="w-3.5 h-3.5 stroke-[2.5]" />
            New query
          </span>
          <span className="text-[10px] font-mono bg-black/25 px-1.5 py-0.5 rounded text-white/90">
            Ctrl N
          </span>
        </button>

        {/* Navigation Menus */}
        <nav className="flex flex-col gap-5">
          {/* Work Section */}
          <div>
            <span className="px-2 text-[10px] font-mono font-semibold tracking-wider uppercase text-[#63605a] block mb-1.5">
              Work
            </span>
            <div className="space-y-0.5">
              <button
                onClick={() => onViewChange('home')}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono transition-colors text-left ${
                  currentView === 'home'
                    ? 'text-[#ede8dd] bg-[#22211e] border border-[#383633]'
                    : 'text-[#9c978f] hover:text-[#ede8dd] hover:bg-[#1f1e1c]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Home className={`w-4 h-4 ${currentView === 'home' ? 'text-[#bd5b38]' : 'text-[#63605a]'}`} />
                  Home
                </span>
                {currentView === 'home' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#bd5b38]" />
                )}
              </button>

              <button
                onClick={() => onViewChange('pid')}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono transition-colors text-left ${
                  currentView === 'pid'
                    ? 'text-[#ede8dd] bg-[#22211e] border border-[#383633]'
                    : 'text-[#9c978f] hover:text-[#ede8dd] hover:bg-[#1f1e1c]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <GitBranch className={`w-4 h-4 ${currentView === 'pid' ? 'text-[#bd5b38]' : 'text-[#63605a]'}`} />
                  P&amp;ID
                </span>
                {currentView === 'pid' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#bd5b38]" />
                )}
              </button>

              <button
                onClick={() => onViewChange('sandbox')}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono transition-colors text-left ${
                  currentView === 'sandbox'
                    ? 'text-[#ede8dd] bg-[#22211e] border border-[#383633]'
                    : 'text-[#9c978f] hover:text-[#ede8dd] hover:bg-[#1f1e1c]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Terminal className={`w-4 h-4 ${currentView === 'sandbox' ? 'text-[#bd5b38]' : 'text-[#63605a]'}`} />
                  Sandbox
                </span>
                {currentView === 'sandbox' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#bd5b38]" />
                )}
              </button>
            </div>
          </div>

          {/* Library Section */}
          <div>
            <span className="px-2 text-[10px] font-mono font-semibold tracking-wider uppercase text-[#63605a] block mb-1.5">
              Library
            </span>
            <div className="space-y-0.5">
              <button
                onClick={() => onViewChange('knowledge')}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono transition-colors text-left ${
                  currentView === 'knowledge'
                    ? 'text-[#ede8dd] bg-[#22211e] border border-[#383633]'
                    : 'text-[#9c978f] hover:text-[#ede8dd] hover:bg-[#1f1e1c]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <BookOpen className={`w-4 h-4 ${currentView === 'knowledge' ? 'text-[#bd5b38]' : 'text-[#63605a]'}`} />
                  Knowledge
                </span>
                {currentView === 'knowledge' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#bd5b38]" />
                )}
              </button>

              <button
                onClick={() => onViewChange('review')}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono transition-colors text-left ${
                  currentView === 'review'
                    ? 'text-[#ede8dd] bg-[#22211e] border border-[#383633]'
                    : 'text-[#9c978f] hover:text-[#ede8dd] hover:bg-[#1f1e1c]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <CheckSquare className={`w-4 h-4 ${currentView === 'review' ? 'text-[#bd5b38]' : 'text-[#63605a]'}`} />
                  Review
                </span>
                {currentView === 'review' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#bd5b38]" />
                )}
              </button>

              <button
                onClick={() => onViewChange('network')}
                className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded text-xs font-mono transition-colors text-left ${
                  currentView === 'network'
                    ? 'text-[#ede8dd] bg-[#22211e] border border-[#383633]'
                    : 'text-[#9c978f] hover:text-[#ede8dd] hover:bg-[#1f1e1c]'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <ShieldCheck className={`w-4 h-4 ${currentView === 'network' ? 'text-[#bd5b38]' : 'text-[#63605a]'}`} />
                  Network
                </span>
                {currentView === 'network' ? (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877] shadow-[0_0_6px_rgba(62,168,119,0.8)]" />
                ) : (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877]/60" />
                )}
              </button>
            </div>
          </div>
        </nav>
      </div>

      {/* Bottom Node & Operator Telemetry */}
      <div className="p-3 border-t border-[#262422] bg-[#141312] flex flex-col gap-2.5">
        {/* Enclave Node Status Box */}
        <div 
          onClick={onSelectNode}
          className="p-2.5 rounded bg-[#1b1a18] border border-[#2b2926] hover:border-[#3d3a35] transition-colors cursor-pointer text-[11px] font-mono group"
          title="Click to manage Node and Settings"
        >
          <div className="flex items-center justify-between text-[#8e8982] mb-1">
            <span className="text-[#ede8dd] font-medium flex items-center gap-1.5">
              <HardDrive className="w-3 h-3 text-[#bd5b38]" />
              On-premises
            </span>
            <span className="text-[10px] text-[#757069]">4 GPU local · 0 AI worker</span>
          </div>
          <div className="flex items-center justify-between pt-1 border-t border-[#262522] text-[10.5px]">
            <div className="flex items-center gap-1.5">
              {activeNode ? (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#3ea877] shadow-[0_0_5px_rgba(62,168,119,0.9)]" />
                  <span className="text-[#dcd7cd] font-medium truncate max-w-[130px]">
                    {activeNode.id === 'node-01' ? 'AirBench Node 01' : 'AirBench Node 02'}
                  </span>
                </>
              ) : (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-[#d99c43] animate-pulse" />
                  <span className="text-[#a6a095]">No Node selected</span>
                </>
              )}
            </div>
            <ChevronDown className="w-3 h-3 text-[#615d57] group-hover:text-[#ede8dd] transition-colors" />
          </div>
        </div>

        {/* Local Operator Account & Build Info */}
        <div className="flex items-center justify-between pt-1 px-1">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-[#2e2c29] text-[10px] font-mono text-[#ede8dd] flex items-center justify-center font-bold border border-[#383633]">
              RG
            </div>
            <div className="flex flex-col">
              <span className="text-xs font-medium text-[#ede8dd] leading-tight">
                Local operator
              </span>
              <span className="text-[10px] font-mono text-[#63605a]">
                Local session
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] font-mono text-[#3ea877] bg-[#3ea877]/10 px-1 py-0.2 rounded border border-[#3ea877]/30">
              Enclave
            </span>
            <span className="text-[10px] font-mono text-[#63605a]">v0.1.0</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
