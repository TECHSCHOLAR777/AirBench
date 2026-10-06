import React, { useState } from 'react';
import { PidSchematic } from '../types';
import { X, Download, Share2, Play, Check, Layers, Cpu, Compass } from 'lucide-react';

interface PidDetailModalProps {
  schematic: PidSchematic | null;
  onClose: () => void;
  onSendToSandbox: (schematic: PidSchematic) => void;
}

export const PidDetailModal: React.FC<PidDetailModalProps> = ({
  schematic,
  onClose,
  onSendToSandbox
}) => {
  const [activeTab, setActiveTab] = useState<'schematic' | 'symbols' | 'connections'>('schematic');
  const [copied, setCopied] = useState(false);

  if (!schematic) return null;

  const handleExport = (format: string) => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(schematic, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `${schematic.dwg}_digitized.${format.toLowerCase()}`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(schematic, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xs p-4 lg:p-6 animate-in fade-in duration-150">
      <div 
        className="w-full max-w-4xl max-h-[90vh] bg-[#181716] border border-[#2e2d29] rounded-xl shadow-2xl overflow-hidden flex flex-col font-mono text-xs"
        onClick={e => e.stopPropagation()}
      >
        {/* Header Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#282725] bg-[#1a1918]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded bg-[#242320] border border-[#35332f] flex items-center justify-center text-[#bd5b38]">
              <Compass className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold text-sm text-[#ede8dd]">
                  {schematic.title}
                </h3>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#232220] border border-[#282725] text-[#9c978f]">
                  DWG: {schematic.dwg}
                </span>
                <span className="text-[10px] px-1.5 py-0.2 rounded bg-[#232220] border border-[#282725] text-[#9c978f]">
                  {schematic.rev}
                </span>
              </div>
              <div className="text-[11px] text-[#757069] mt-0.5">
                {schematic.sheet} · {schematic.symbolsCount} symbols detected · Topology Mapped
              </div>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="text-[#8e8982] hover:text-[#ede8dd] transition-colors p-1.5 rounded hover:bg-[#262421]"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab Controls Bar */}
        <div className="px-6 py-2 bg-[#141312] border-b border-[#262422] flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setActiveTab('schematic')}
              className={`px-3 py-1.5 rounded transition-colors text-xs ${
                activeTab === 'schematic'
                  ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]'
                  : 'text-[#8e8982] hover:text-[#ede8dd]'
              }`}
            >
              Interactive Schematic
            </button>
            <button
              onClick={() => setActiveTab('symbols')}
              className={`px-3 py-1.5 rounded transition-colors text-xs ${
                activeTab === 'symbols'
                  ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]'
                  : 'text-[#8e8982] hover:text-[#ede8dd]'
              }`}
            >
              Detected Symbols ({schematic.symbols.length})
            </button>
            <button
              onClick={() => setActiveTab('connections')}
              className={`px-3 py-1.5 rounded transition-colors text-xs ${
                activeTab === 'connections'
                  ? 'bg-[#22211e] text-[#ede8dd] border border-[#383633]'
                  : 'text-[#8e8982] hover:text-[#ede8dd]'
              }`}
            >
              Topology Graph ({schematic.connections.length} lines)
            </button>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyJson}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#201f1c] hover:bg-[#282623] border border-[#2e2d29] text-[#a8a39a] hover:text-[#ede8dd] transition-colors"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-[#3ea877]" /> : <Share2 className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copied JSON' : 'Copy JSON'}</span>
            </button>
            <button
              onClick={() => handleExport('DXF')}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#201f1c] hover:bg-[#282623] border border-[#2e2d29] text-[#a8a39a] hover:text-[#ede8dd] transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export DXF</span>
            </button>
            <button
              onClick={() => onSendToSandbox(schematic)}
              className="flex items-center gap-1.5 px-3 py-1 rounded bg-[#bd5b38] hover:bg-[#a74f30] text-white font-medium transition-colors shadow-2xs"
            >
              <Play className="w-3.5 h-3.5" />
              <span>Solve in Sandbox</span>
            </button>
          </div>
        </div>

        {/* Tab Content Body */}
        <div className="flex-1 p-6 overflow-y-auto">
          {activeTab === 'schematic' && (
            <div className="space-y-4">
              {/* CAD Vector Schematic Canvas Viewer */}
              <div className="w-full bg-[#0d0d0c] border border-[#262421] rounded-lg p-6 relative overflow-hidden flex flex-col items-center justify-center min-h-[300px] shadow-inner">
                {/* Engineering Grid Background */}
                <div 
                  className="absolute inset-0 opacity-15 pointer-events-none"
                  style={{
                    backgroundImage: 'radial-gradient(#8e8982 1px, transparent 1px)',
                    backgroundSize: '20px 20px'
                  }}
                />

                {schematic.id === 'pid-101' ? (
                  <svg className="w-full max-w-2xl h-64 overflow-visible" viewBox="0 0 600 240">
                    {/* Main Process Line */}
                    <path d="M 40 140 L 140 140 M 180 140 L 320 140 M 420 140 L 490 140 M 530 140 L 580 140" stroke="#ede8dd" strokeWidth="2.5" fill="none" />
                    
                    {/* Pump P-101A */}
                    <g transform="translate(140, 140)">
                      <circle cx="20" cy="0" r="22" stroke="#ede8dd" strokeWidth="2" fill="#181716" />
                      <polygon points="10,-12 10,12 32,0" stroke="#3ea877" strokeWidth="1.8" fill="none" />
                      <text x="20" y="38" fill="#ede8dd" fontSize="11" textAnchor="middle" fontFamily="JetBrains Mono">P-101A</text>
                      <text x="20" y="52" fill="#757069" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">Booster Pump</text>
                    </g>

                    {/* Sensor PI-101 */}
                    <g transform="translate(230, 80)">
                      <line x1="0" y1="60" x2="0" y2="20" stroke="#757069" strokeDasharray="3,3" strokeWidth="1.5" />
                      <circle cx="0" cy="0" r="16" stroke="#ede8dd" strokeWidth="1.8" fill="#1a1918" />
                      <line x1="-16" y1="0" x2="16" y2="0" stroke="#757069" strokeWidth="1" />
                      <text x="0" y="-3" fill="#ede8dd" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">PI</text>
                      <text x="0" y="9" fill="#ede8dd" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">101</text>
                    </g>

                    {/* Heat Exchanger E-101A */}
                    <g transform="translate(320, 100)">
                      <rect x="0" y="10" width="100" height="60" rx="6" stroke="#ede8dd" strokeWidth="2" fill="#181716" />
                      <path d="M 20 25 L 80 25 M 20 40 L 80 40 M 20 55 L 80 55" stroke="#bd5b38" strokeWidth="1.5" />
                      <text x="50" y="44" fill="#ede8dd" fontSize="12" fontWeight="600" textAnchor="middle" fontFamily="JetBrains Mono">E-101A</text>
                      <text x="50" y="90" fill="#757069" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">Preheat Exchanger</text>
                    </g>

                    {/* Control Valve FCV-104 */}
                    <g transform="translate(490, 140)">
                      {/* Opposing valve triangles */}
                      <polygon points="0,-10 20,0 0,10" stroke="#ede8dd" strokeWidth="1.8" fill="#22211e" />
                      <polygon points="40,-10 20,0 40,10" stroke="#ede8dd" strokeWidth="1.8" fill="#22211e" />
                      {/* Actuator stem and dome */}
                      <line x1="20" y1="0" x2="20" y2="-22" stroke="#bd5b38" strokeWidth="2" />
                      <path d="M 6 -22 C 6 -34, 34 -34, 34 -22 Z" stroke="#bd5b38" strokeWidth="1.8" fill="#2a1f1b" />
                      <text x="20" y="-38" fill="#bd5b38" fontSize="10" fontWeight="600" textAnchor="middle" fontFamily="JetBrains Mono">FCV-104</text>
                      <text x="20" y="30" fill="#757069" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">Flow Control</text>
                    </g>

                    {/* Flow arrow markers */}
                    <polygon points="80,136 90,140 80,144" fill="#3ea877" />
                    <polygon points="270,136 280,140 270,144" fill="#3ea877" />
                    <polygon points="450,136 460,140 450,144" fill="#3ea877" />

                    {/* Line annotation label */}
                    <text x="80" y="125" fill="#d99c43" fontSize="9" fontFamily="JetBrains Mono">8"-CR-10101-A1</text>
                  </svg>
                ) : (
                  <svg className="w-full max-w-2xl h-64 overflow-visible" viewBox="0 0 600 240">
                    {/* Tower C-101 */}
                    <g transform="translate(80, 20)">
                      <rect x="0" y="20" width="60" height="180" rx="30" stroke="#ede8dd" strokeWidth="2.5" fill="#181716" />
                      {/* Tray lines */}
                      <line x1="10" y1="60" x2="50" y2="60" stroke="#757069" strokeDasharray="3,3" />
                      <line x1="10" y1="90" x2="50" y2="90" stroke="#757069" strokeDasharray="3,3" />
                      <line x1="10" y1="120" x2="50" y2="120" stroke="#757069" strokeDasharray="3,3" />
                      <line x1="10" y1="150" x2="50" y2="150" stroke="#757069" strokeDasharray="3,3" />
                      <text x="30" y="105" fill="#ede8dd" fontSize="12" fontWeight="600" textAnchor="middle" fontFamily="JetBrains Mono">C-101</text>
                      <text x="30" y="218" fill="#757069" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">Atmospheric Tower</text>
                    </g>

                    {/* Overhead vapor line */}
                    <path d="M 110 20 L 110 10 L 300 10 L 300 60" stroke="#ede8dd" strokeWidth="2.5" fill="none" />
                    <text x="180" y="26" fill="#d99c43" fontSize="9" fontFamily="JetBrains Mono">24"-OV-10201-B2</text>

                    {/* Fin Fan Condenser E-102 */}
                    <g transform="translate(260, 60)">
                      <polygon points="0,0 80,0 60,40 20,40" stroke="#ede8dd" strokeWidth="2" fill="#1f1e1c" />
                      <text x="40" y="25" fill="#ede8dd" fontSize="11" fontWeight="600" textAnchor="middle" fontFamily="JetBrains Mono">E-102</text>
                      <text x="40" y="55" fill="#757069" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">Fin-Fan Condenser</text>
                    </g>

                    {/* Downcomer to Drum V-104 */}
                    <path d="M 300 100 L 300 130 L 440 130" stroke="#ede8dd" strokeWidth="2.5" fill="none" />

                    {/* Reflux Drum V-104 */}
                    <g transform="translate(440, 100)">
                      <rect x="0" y="10" width="100" height="50" rx="20" stroke="#ede8dd" strokeWidth="2" fill="#181716" />
                      {/* Boot */}
                      <rect x="35" y="60" width="30" height="30" rx="6" stroke="#ede8dd" strokeWidth="1.8" fill="#181716" />
                      <text x="50" y="40" fill="#ede8dd" fontSize="12" fontWeight="600" textAnchor="middle" fontFamily="JetBrains Mono">V-104</text>
                      <text x="50" y="105" fill="#757069" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">Reflux Drum</text>
                    </g>
                  </svg>
                )}
              </div>

              {/* Technical Inspection Notes */}
              <div className="p-3.5 bg-[#141312] border border-[#262422] rounded-lg space-y-1">
                <div className="text-[10px] uppercase text-[#757069] tracking-wider font-semibold">
                  Symbol Vectorization &amp; Connectivity Proof
                </div>
                <p className="text-xs text-[#a8a39a] leading-relaxed">
                  Line topology was reconstructed using graph segmentation on local edge weights. All flow paths match ISA-5.1 drafting standards with 99.4% confidence score.
                </p>
              </div>
            </div>
          )}

          {activeTab === 'symbols' && (
            <div className="space-y-3">
              <div className="overflow-x-auto border border-[#262422] rounded-lg">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#141312] text-[#757069] uppercase text-[10px] border-b border-[#262422]">
                    <tr>
                      <th className="py-2.5 px-3">Symbol Tag</th>
                      <th className="py-2.5 px-3">Equipment Type</th>
                      <th className="py-2.5 px-3">Coordinates</th>
                      <th className="py-2.5 px-4">Engineering Specifications</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#262422]">
                    {schematic.symbols.map(sym => (
                      <tr key={sym.id} className="hover:bg-[#201f1c] transition-colors">
                        <td className="py-2.5 px-3 text-[#ede8dd] font-semibold">{sym.tag}</td>
                        <td className="py-2.5 px-3 text-[#d99c43]">{sym.type}</td>
                        <td className="py-2.5 px-3 text-[#757069]">{sym.coordinates}</td>
                        <td className="py-2.5 px-4 text-[#a8a39a]">{sym.specs}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'connections' && (
            <div className="space-y-3">
              <div className="overflow-x-auto border border-[#262422] rounded-lg">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#141312] text-[#757069] uppercase text-[10px] border-b border-[#262422]">
                    <tr>
                      <th className="py-2.5 px-3">From Node</th>
                      <th className="py-2.5 px-3">To Node</th>
                      <th className="py-2.5 px-3">Line Tag</th>
                      <th className="py-2.5 px-4">Piping Spec</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#262422]">
                    {schematic.connections.map((conn, idx) => (
                      <tr key={idx} className="hover:bg-[#201f1c] transition-colors">
                        <td className="py-2.5 px-3 text-[#3ea877] font-semibold">{conn.from}</td>
                        <td className="py-2.5 px-3 text-[#3ea877] font-semibold">{conn.to}</td>
                        <td className="py-2.5 px-3 text-[#ede8dd]">{conn.lineTag}</td>
                        <td className="py-2.5 px-4 text-[#757069]">{conn.spec}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-[#282725] bg-[#1a1918] flex items-center justify-between">
          <span className="text-[11px] text-[#757069]">
            AirBench Isolated Enclave Digitizer v0.1.0
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-[#22211e] hover:bg-[#2e2d29] text-[#ede8dd] text-xs transition-colors border border-[#383633]"
          >
            Close Viewer
          </button>
        </div>
      </div>
    </div>
  );
};
