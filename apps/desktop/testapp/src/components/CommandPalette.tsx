import React, { useState, useEffect, useRef } from 'react';
import { PageView } from '../types';
import { 
  Search, 
  Terminal, 
  GitBranch, 
  BookOpen, 
  CheckSquare, 
  ShieldCheck, 
  Home, 
  Server, 
  Play, 
  FileText, 
  X,
  ExternalLink
} from 'lucide-react';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (view: PageView) => void;
  onRunStarter: (prompt: string) => void;
  onConnectNode: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  onNavigate,
  onRunStarter,
  onConnectNode
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  const items = [
    // Navigation
    {
      category: 'Navigation',
      label: 'Home — Sovereign Task Command',
      icon: Home,
      action: () => { onNavigate('home'); onClose(); },
      keywords: 'home query prompt assistant'
    },
    {
      category: 'Navigation',
      label: 'P&ID — Schematic Digitization & Symbol Detection',
      icon: GitBranch,
      action: () => { onNavigate('pid'); onClose(); },
      keywords: 'pid schematic drawing cad symbols crude'
    },
    {
      category: 'Navigation',
      label: 'Sandbox Workspace — Python 3.11 Rust Enclave',
      icon: Terminal,
      action: () => { onNavigate('sandbox'); onClose(); },
      keywords: 'sandbox python code compute math script solver'
    },
    {
      category: 'Navigation',
      label: 'Knowledge Base — Standard Operating Procedures',
      icon: BookOpen,
      action: () => { onNavigate('knowledge'); onClose(); },
      keywords: 'knowledge sop procedures documents standards'
    },
    {
      category: 'Navigation',
      label: 'Review Queue — Session Deliverables & Exports',
      icon: CheckSquare,
      action: () => { onNavigate('review'); onClose(); },
      keywords: 'review deliverables answers memos exports'
    },
    {
      category: 'Navigation',
      label: 'Network Monitor — Cryptographic Sovereignty Audit',
      icon: ShieldCheck,
      action: () => { onNavigate('network'); onClose(); },
      keywords: 'network audit trace egress tls sockets loopback'
    },
    {
      category: 'Navigation',
      label: 'Node and Settings — mTLS Connection Proof',
      icon: Server,
      action: () => { onNavigate('node-settings'); onClose(); },
      keywords: 'node settings certs host connection proof'
    },
    // Tasks & Actions
    {
      category: 'Engineering Tasks',
      label: 'Execute: Analyze P&ID loop telemetry',
      icon: Play,
      action: () => { onRunStarter('Analyze P&ID loop telemetry'); onClose(); },
      keywords: 'analyze pid telemetry loop valves sensors'
    },
    {
      category: 'Engineering Tasks',
      label: 'Execute: Run Python thermal simulation',
      icon: Play,
      action: () => { onRunStarter('Run Python thermal simulation'); onClose(); },
      keywords: 'thermal heat exchanger simulation lmtd python'
    },
    {
      category: 'Engineering Tasks',
      label: 'Execute: Audit network security egress',
      icon: Play,
      action: () => { onRunStarter('Audit network security egress'); onClose(); },
      keywords: 'audit security egress network packets zero leak'
    },
    {
      category: 'Engineering Tasks',
      label: 'Execute: Draft compliance verification memo',
      icon: FileText,
      action: () => { onRunStarter('Draft compliance verification memo'); onClose(); },
      keywords: 'draft compliance memo verification report'
    },
    {
      category: 'Node Actions',
      label: 'Connect AirBench-Node-01 (127.0.0.1:8000)',
      icon: Server,
      action: () => { onConnectNode(); onClose(); },
      keywords: 'connect node loopback local enclave'
    }
  ];

  const filteredItems = items.filter(item => 
    item.label.toLowerCase().includes(query.toLowerCase()) ||
    item.keywords.toLowerCase().includes(query.toLowerCase()) ||
    item.category.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => (prev + 1) % (filteredItems.length || 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => (prev - 1 + filteredItems.length) % (filteredItems.length || 1));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredItems[selectedIndex]) {
          filteredItems[selectedIndex].action();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, filteredItems, selectedIndex, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/70 backdrop-blur-xs p-4 animate-in fade-in duration-100">
      <div 
        className="w-full max-w-xl bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden flex flex-col font-mono"
        onClick={e => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#282725] bg-[#1a1918]">
          <Search className="w-4 h-4 text-[#8e8982]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => { setQuery(e.target.value); setSelectedIndex(0); }}
            placeholder="Type a command or jump to view..."
            className="flex-1 bg-transparent text-sm text-[#ede8dd] placeholder-[#63605a] focus:outline-none"
          />
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Results List */}
        <div className="max-h-80 overflow-y-auto p-2 space-y-1">
          {filteredItems.length === 0 ? (
            <div className="p-6 text-center text-xs text-[#757069]">
              No matching commands or routes found
            </div>
          ) : (
            filteredItems.map((item, idx) => {
              const Icon = item.icon;
              const isSelected = idx === selectedIndex;
              return (
                <div
                  key={idx}
                  onClick={item.action}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  className={`flex items-center justify-between px-3 py-2 rounded text-xs cursor-pointer transition-colors ${
                    isSelected ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]' : 'text-[#a8a39a] hover:bg-[#1f1e1c]'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`w-4 h-4 ${isSelected ? 'text-[#bd5b38]' : 'text-[#757069]'}`} />
                    <span>{item.label}</span>
                  </div>
                  <span className="text-[10px] uppercase tracking-wider text-[#63605a]">
                    {item.category}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Footer shortcuts */}
        <div className="px-4 py-2 bg-[#141312] border-t border-[#262422] flex items-center justify-between text-[10px] text-[#63605a]">
          <div className="flex items-center gap-3">
            <span>↑↓ to navigate</span>
            <span>↵ to select</span>
            <span>esc to dismiss</span>
          </div>
          <span>AirBench Sovereign Shell</span>
        </div>
      </div>
    </div>
  );
};
