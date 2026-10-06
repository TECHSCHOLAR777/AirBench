import React, { useState, useRef, useEffect } from 'react';
import { PageView, EnclaveNode } from '../types';
import { 
  Search, 
  Cpu, 
  Monitor, 
  ChevronDown, 
  Check, 
  Sliders, 
  Maximize2, 
  Minimize2,
  ShieldCheck,
  AlertTriangle
} from 'lucide-react';

interface HeaderProps {
  currentView: PageView;
  onOpenCommand: () => void;
  activeNode: EnclaveNode | null;
  onSelectNode: () => void;
  isCompact: boolean;
  onToggleCompact: () => void;
  highContrast: boolean;
  onToggleHighContrast: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  currentView,
  onOpenCommand,
  activeNode,
  onSelectNode,
  isCompact,
  onToggleCompact,
  highContrast,
  onToggleHighContrast
}) => {
  const [displayMenuOpen, setDisplayMenuOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const getBreadcrumbLabel = (view: PageView): string => {
    switch (view) {
      case 'home': return 'Home';
      case 'pid': return 'P&ID';
      case 'sandbox': return 'Sandbox Workspace';
      case 'knowledge': return 'Knowledge';
      case 'review': return 'Review';
      case 'network': return 'Network monitor';
      case 'node-settings': return 'Node and settings';
      default: return 'Home';
    }
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setDisplayMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
        setIsFullscreen(false);
      }
    }
  };

  return (
    <header 
      className="h-12 border-b border-[#242320] px-6 lg:px-8 flex items-center justify-between bg-[#141312]/95 backdrop-blur shrink-0 z-10"
      data-purpose="top-header"
    >
      {/* Breadcrumbs */}
      <div className="flex items-center gap-2 text-xs font-mono">
        <span className="text-[#8e8982] hover:text-[#ede8dd] transition-colors cursor-pointer">
          AirBench
        </span>
        <span className="text-[#4d4a45]">/</span>
        <span className="text-[#ede8dd] font-medium">
          {getBreadcrumbLabel(currentView)}
        </span>
      </div>

      {/* Header Pills & Actions */}
      <div className="flex items-center gap-2.5">
        {/* Command Palette Trigger */}
        <button
          onClick={onOpenCommand}
          className="flex items-center gap-2 px-2.5 py-1 rounded bg-[#1b1a18] hover:bg-[#22211e] border border-[#2e2d29] hover:border-[#383633] text-xs font-mono text-[#a8a39a] hover:text-[#ede8dd] transition-all cursor-pointer shadow-2xs"
          type="button"
          title="Open Sovereign Command Palette"
        >
          <Search className="w-3.5 h-3.5 text-[#757069]" />
          <span>Command</span>
          <kbd className="text-[10px] bg-black/40 px-1.5 py-0.2 rounded border border-[#282725] text-[#8e8982]">
            Ctrl K
          </kbd>
        </button>

        {/* Node Path Indicator Button */}
        <button
          onClick={onSelectNode}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono transition-all cursor-pointer border ${
            activeNode
              ? 'bg-[#1b1a18] border-[#3ea877]/40 text-[#ede8dd] hover:border-[#3ea877]'
              : 'bg-[#211a12] border-[#523e1e] text-[#d99c43] hover:border-[#855f26]'
          }`}
          title="Click to view Node Connection Proof and Settings"
          type="button"
        >
          {activeNode ? (
            <ShieldCheck className="w-3.5 h-3.5 text-[#3ea877]" />
          ) : (
            <AlertTriangle className="w-3.5 h-3.5 text-[#d99c43]" />
          )}
          <span className="text-[9.5px] uppercase text-[#757069] font-semibold tracking-wider">
            Node path
          </span>
          <span className={`font-medium ${activeNode ? 'text-[#3ea877]' : 'text-[#d99c43]'}`}>
            {activeNode ? 'Enclave Verified' : 'Unverified'}
          </span>
        </button>

        {/* Display Options Menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setDisplayMenuOpen(!displayMenuOpen)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1b1a18] hover:bg-[#22211e] border border-[#2e2d29] hover:border-[#383633] text-xs font-mono text-[#a8a39a] hover:text-[#ede8dd] transition-all cursor-pointer"
            type="button"
          >
            <Monitor className="w-3.5 h-3.5 text-[#757069]" />
            <span>Display</span>
            <ChevronDown className={`w-3 h-3 text-[#757069] transition-transform ${displayMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {displayMenuOpen && (
            <div className="absolute right-0 mt-1.5 w-56 rounded-md bg-[#1a1918] border border-[#2e2d29] shadow-xl py-1 z-30 font-mono text-xs text-[#ede8dd]">
              <div className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-[#757069] border-b border-[#282725]">
                Display &amp; Viewport
              </div>

              <button
                onClick={onToggleCompact}
                className="w-full px-3 py-2 text-left flex items-center justify-between hover:bg-[#242320] transition-colors"
              >
                <span>Compact density</span>
                {isCompact && <Check className="w-3.5 h-3.5 text-[#bd5b38]" />}
              </button>

              <button
                onClick={onToggleHighContrast}
                className="w-full px-3 py-2 text-left flex items-center justify-between hover:bg-[#242320] transition-colors"
              >
                <span>High contrast outlines</span>
                {highContrast && <Check className="w-3.5 h-3.5 text-[#bd5b38]" />}
              </button>

              <button
                onClick={toggleFullscreen}
                className="w-full px-3 py-2 text-left flex items-center justify-between hover:bg-[#242320] transition-colors border-t border-[#282725]"
              >
                <span>Toggle fullscreen</span>
                {isFullscreen ? <Minimize2 className="w-3.5 h-3.5 text-[#8e8982]" /> : <Maximize2 className="w-3.5 h-3.5 text-[#8e8982]" />}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
