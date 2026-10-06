import React, { useState, useEffect } from 'react';
import { 
  PageView, 
  EnclaveNode, 
  SopDocument, 
  SandboxScript, 
  NetworkTrace, 
  ReviewDeliverable, 
  ChatMessage,
  ConversationSession,
  DeliverableFormat,
  AttachedFileMeta
} from './types';
import { 
  INITIAL_NODES, 
  INITIAL_DOCUMENTS, 
  INITIAL_SANDBOX_FILES, 
  INITIAL_NETWORK_TRACES, 
  INITIAL_DELIVERABLES
} from './data/mockData';
import { PidCorpusDrawing, PID_CORPUS_DRAWINGS } from './data/pidCorpus';
import { executeModelInference } from './services/inferenceService';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { CommandPalette } from './components/CommandPalette';
import { InspectCertModal } from './components/InspectCertModal';
import { SopReaderModal } from './components/SopReaderModal';
import { TraceInspectModal } from './components/TraceInspectModal';
import { IngestDocModal } from './components/IngestDocModal';
import { QuickCalcModal } from './components/QuickCalcModal';
import { resolveModelKey } from './components/ModelHoverTooltip';

import { HomeView } from './components/views/HomeView';
import { PidView } from './components/views/PidView';
import { PidDigitizationViewer } from './components/views/PidDigitizationViewer';
import { SandboxView } from './components/views/SandboxView';
import { KnowledgeView } from './components/views/KnowledgeView';
import { ReviewView } from './components/views/ReviewView';
import { NetworkView } from './components/views/NetworkView';
import { NodeSettingsView } from './components/views/NodeSettingsView';

export default function App() {
  // Navigation & View State
  const [currentView, setCurrentView] = useState<PageView>('home');
  const [activeNode, setActiveNode] = useState<EnclaveNode | null>(INITIAL_NODES[0]);
  const [nodes, setNodes] = useState<EnclaveNode[]>(INITIAL_NODES);

  // Core Data States
  const [documents, setDocuments] = useState<SopDocument[]>(INITIAL_DOCUMENTS);
  
  // P&ID: 2 pre-loaded diagrams from corpus (PID-101 and PID-102), rest added via manual upload
  const [pidDrawings, setPidDrawings] = useState<PidCorpusDrawing[]>(() => PID_CORPUS_DRAWINGS.slice(0, 2));
  const [digitizedDrawingIds, setDigitizedDrawingIds] = useState<string[]>(['0', '1']);
  const [selectedPidDrawing, setSelectedPidDrawing] = useState<PidCorpusDrawing | null>(null);

  const [sandboxFiles, setSandboxFiles] = useState<SandboxScript[]>(INITIAL_SANDBOX_FILES);
  
  // Clean session initial states: conversation chat, review & network traces start empty until queries or actions run!
  const [networkTraces, setNetworkTraces] = useState<NetworkTrace[]>([]);
  const [deliverables, setDeliverables] = useState<ReviewDeliverable[]>([]);
  const [conversationSessions, setConversationSessions] = useState<ConversationSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  // Modals & UI Controls
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [inspectCertNode, setInspectCertNode] = useState<EnclaveNode | null>(null);
  const [selectedDocument, setSelectedDocument] = useState<SopDocument | null>(null);
  const [selectedTrace, setSelectedTrace] = useState<NetworkTrace | null>(null);
  const [ingestModalOpen, setIngestModalOpen] = useState(false);
  const [quickCalcOpen, setQuickCalcOpen] = useState(false);

  // Display toggles
  const [isCompact, setIsCompact] = useState(false);
  const [highContrast, setHighContrast] = useState(false);

  // Keyboard shortcut listeners (Ctrl+K, Ctrl+N, Alt+M)
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      // Ctrl+K or Cmd+K
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(prev => !prev);
      }
      // Ctrl+N or Cmd+N
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewQuery();
      }
      // Alt+M
      if (e.altKey && e.key.toLowerCase() === 'm') {
        e.preventDefault();
        setQuickCalcOpen(prev => !prev);
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, []);

  const handleNewQuery = () => {
    setActiveSessionId(null);
    setCurrentView('home');
  };

  const appendNetworkTrace = (endpoint: string, model: string, payloadBytes: number) => {
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const newTrace: NetworkTrace = {
      id: `trace-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      timestamp: timeStr,
      route: 'LOCAL',
      endpoint,
      method: 'POST',
      status: 200,
      payloadBytes,
      model,
      quantization: 'q4_k_m',
      headers: {
        'Host': '127.0.0.1:8000',
        'Content-Type': 'application/json',
        'X-AirBench-Enclave-Policy': 'Strict-Zero-Egress',
        'X-Node-ID': activeNode?.id || 'node-01'
      },
      curlCommand: `curl -s -X POST http://${endpoint} \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${model}", "enclave": "strict"}'`
    };

    setNetworkTraces(prev => {
      // If empty on first action, seed with authentic local baseline traces + new trace
      if (prev.length === 0) {
        return [newTrace, ...INITIAL_NETWORK_TRACES];
      }
      return [newTrace, ...prev];
    });
  };

  const handleSendMessage = (
    text: string, 
    deliverableType: DeliverableFormat, 
    route: string, 
    attachedFiles?: AttachedFileMeta[]
  ) => {
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      timestamp: timeStr,
      text,
      route,
      attachedFiles
    };

    const tempAssistantId = `msg-gen-${Date.now()}`;
    const tempAssistantMsg: ChatMessage = {
      id: tempAssistantId,
      role: 'assistant',
      timestamp: 'Thinking...',
      text: '',
      route: route.includes('Auto') ? 'Sovereign Router' : route,
      isGenerating: true,
      generatingPhase: 'Processing request...'
    };

    let targetSessionId = activeSessionId;
    const deliverableLabelMap: Record<DeliverableFormat, string> = {
      auto: 'Standard Response',
      docx: 'Word Document (.docx)',
      pptx: 'PowerPoint (.pptx)',
      xlsx: 'Spreadsheet (.xlsx)',
      pdf: 'PDF Document (.pdf)',
      md: 'Markdown (.md)',
      py: 'Python (.py)'
    };
    const deliverableLabel = deliverableLabelMap[deliverableType] || 'Standard Response';

    if (!targetSessionId) {
      targetSessionId = `session-${Date.now()}`;
      const newSession: ConversationSession = {
        id: targetSessionId,
        title: text.length > 52 ? `${text.slice(0, 52)}...` : text,
        createdAt: 'Just now',
        updatedAt: 'Just now',
        model: route,
        deliverableType: deliverableLabel,
        lastQuerySnippet: text,
        messages: [userMsg, tempAssistantMsg]
      };
      setConversationSessions(prev => [newSession, ...prev]);
      setActiveSessionId(targetSessionId);
    } else {
      setConversationSessions(prev => prev.map(s => {
        if (s.id === targetSessionId) {
          return {
            ...s,
            updatedAt: 'Just now',
            lastQuerySnippet: text,
            messages: [...s.messages, userMsg, tempAssistantMsg]
          };
        }
        return s;
      }));
    }

    // Dynamic phase transitions while model generates
    const phaseTimer1 = setTimeout(() => {
      setConversationSessions(prev => prev.map(s => {
        if (s.id === targetSessionId) {
          return {
            ...s,
            messages: s.messages.map(m => m.id === tempAssistantId ? {
              ...m,
              generatingPhase: 'Analyzing prompt...'
            } : m)
          };
        }
        return s;
      }));
    }, 700);

    const phaseTimer2 = setTimeout(() => {
      setConversationSessions(prev => prev.map(s => {
        if (s.id === targetSessionId) {
          return {
            ...s,
            messages: s.messages.map(m => m.id === tempAssistantId ? {
              ...m,
              generatingPhase: 'Synthesizing response...'
            } : m)
          };
        }
        return s;
      }));
    }, 1500);

    const phaseTimer3 = setTimeout(() => {
      setConversationSessions(prev => prev.map(s => {
        if (s.id === targetSessionId) {
          return {
            ...s,
            messages: s.messages.map(m => m.id === tempAssistantId ? {
              ...m,
              generatingPhase: 'Finalizing deliverable...'
            } : m)
          };
        }
        return s;
      }));
    }, 2300);

    // Parse requested model from route if specified
    const requestedModel = resolveModelKey(route);

    const currentSessionObj = conversationSessions.find(s => s.id === targetSessionId);
    const existingMessages = currentSessionObj ? currentSessionObj.messages.filter(m => !m.isGenerating) : [];

    const deliverableTypeCategoryMap: Record<DeliverableFormat, any> = {
      auto: 'Auto',
      docx: 'Document',
      pptx: 'Presentation',
      xlsx: 'Spreadsheet',
      pdf: 'PDF',
      md: 'Document',
      py: 'Code'
    };

    // Execute with realistic generation delay as requested by user
    Promise.all([
      executeModelInference({
        messages: [
          ...existingMessages.map(m => ({ role: m.role, content: m.text })),
          { role: 'user', content: userMsg.text }
        ],
        requestedModel,
        deliverableType: deliverableTypeCategoryMap[deliverableType] || 'Auto',
        attachedFiles
      }),
      new Promise(resolve => setTimeout(resolve, 2500))
    ]).then(([result]) => {
      clearTimeout(phaseTimer1);
      clearTimeout(phaseTimer2);
      clearTimeout(phaseTimer3);

      const titleMatch = result.text.match(/^#+\s*(.+)$/m);
      const deliverableTitle = result.reportFilename 
        ? result.reportFilename.replace(/[_-]/g, ' ').replace(/\.[a-z0-9]+$/i, '').toUpperCase()
        : (titleMatch ? titleMatch[1].trim() : 'Sovereign Technical Deliverable');

      // Determine if a deliverable should be emitted: either user selected a deliverable type,
      // or user uploaded a file and asked for a deliverable format in prompt
      let resolvedDeliverableFormat = deliverableType;
      if (resolvedDeliverableFormat === 'auto') {
        const lower = text.toLowerCase();
        if (lower.includes('in pdf') || lower.includes('to pdf') || lower.includes('as pdf') || lower.includes('pdf deliverable')) {
          resolvedDeliverableFormat = 'pdf';
        } else if (lower.includes('in excel') || lower.includes('to excel') || lower.includes('as excel') || lower.includes('in xlsx') || lower.includes('as sheet')) {
          resolvedDeliverableFormat = 'xlsx';
        } else if (lower.includes('in word') || lower.includes('to word') || lower.includes('as docx') || lower.includes('in docx')) {
          resolvedDeliverableFormat = 'docx';
        } else if (lower.includes('in ppt') || lower.includes('to ppt') || lower.includes('in powerpoint') || lower.includes('as slides')) {
          resolvedDeliverableFormat = 'pptx';
        }
      }

      let newDeliverable: ReviewDeliverable | null = null;

      if (resolvedDeliverableFormat !== 'auto') {
        const firstAttachedWithData = attachedFiles?.find(f => f.dataUrl);
        const resolvedTitle = firstAttachedWithData 
          ? `${firstAttachedWithData.name.replace(/\.[a-zA-Z0-9]+$/, '')}`
          : deliverableTitle;

        newDeliverable = {
          id: `del-${Date.now()}`,
          title: resolvedTitle,
          type: deliverableTypeCategoryMap[resolvedDeliverableFormat] || 'Document',
          format: resolvedDeliverableFormat,
          sourceRoute: result.dispatchedModel,
          timestamp: 'Just now',
          summary: firstAttachedWithData 
            ? `Inter-artifact conversion: ${firstAttachedWithData.name} -> ${resolvedDeliverableFormat.toUpperCase()}`
            : `Synthesized dynamically for: "${text.slice(0, 60)}..."`,
          content: result.text,
          metadata: {
            wordCount: result.text.split(/\s+/).length,
            exitCode: 0,
            confidenceScore: '99.8%',
            tokens: result.tokens
          },
          sourceFile: firstAttachedWithData ? {
            name: firstAttachedWithData.name,
            extension: firstAttachedWithData.extension,
            dataUrl: firstAttachedWithData.dataUrl!
          } : undefined
        };
        // Append to the Review ledger
        setDeliverables(prev => [newDeliverable!, ...prev]);
      }

      const assistantMsg: ChatMessage = {
        id: tempAssistantId,
        role: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: result.text,
        route: result.dispatchedModel,
        deliverable: newDeliverable ?? undefined,
        isGenerating: false
      };

      setConversationSessions(prev => prev.map(s => {
        if (s.id === targetSessionId) {
          return {
            ...s,
            model: result.dispatchedModel,
            messages: s.messages.map(m => m.id === tempAssistantId ? assistantMsg : m)
          };
        }
        return s;
      }));

      // Append real local network trace
      appendNetworkTrace(result.endpoint, result.dispatchedModel, result.text.length * 2);
    }).catch(err => {
      clearTimeout(phaseTimer1);
      clearTimeout(phaseTimer2);
      clearTimeout(phaseTimer3);
      console.error('[App] Model dispatch failed:', err);

      const errorMsg: ChatMessage = {
        id: tempAssistantId,
        role: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: `Unable to complete synthesis: ${err.message || 'Network error'}. Please retry.`,
        route: 'Enclave Fallback',
        isGenerating: false
      };

      setConversationSessions(prev => prev.map(s => {
        if (s.id === targetSessionId) {
          return {
            ...s,
            messages: s.messages.map(m => m.id === tempAssistantId ? errorMsg : m)
          };
        }
        return s;
      }));
    });
  };

  const handleSelectNode = (node: EnclaveNode) => {
    setActiveNode(node);
    setNodes(prev => prev.map(n => ({
      ...n,
      status: n.id === node.id ? 'READY' : 'STANDBY'
    })));
  };

  const handleDisconnectNode = () => {
    setActiveNode(null);
  };

  const handleCrossReferenceFromSop = (doc: SopDocument) => {
    setSelectedDocument(null);
    setCurrentView('home');
  };

  return (
    <div className="flex h-screen bg-[#121211] text-[#ede8dd] overflow-hidden font-sans">
      <Sidebar
        currentView={currentView}
        onViewChange={setCurrentView}
        onNewQuery={handleNewQuery}
        activeNode={activeNode}
        onSelectNode={() => setCurrentView('node-settings')}
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {currentView === 'home' && (
            <HomeView
              sessions={conversationSessions}
              activeSessionId={activeSessionId}
              onSelectSession={(id) => {
                setActiveSessionId(id);
                setCurrentView('home');
              }}
              onNewSession={handleNewQuery}
              onDeleteSession={(id) => {
                setConversationSessions(prev => prev.filter(s => s.id !== id));
                if (activeSessionId === id) setActiveSessionId(null);
              }}
              onClearAllSessions={() => {
                setConversationSessions([]);
                setActiveSessionId(null);
              }}
              onSendMessage={handleSendMessage}
              onNavigate={setCurrentView}
            />
          )}

          {currentView === 'pid' && (
            <PidView
              drawings={pidDrawings}
              digitizedDrawingIds={digitizedDrawingIds}
              onSelectDrawing={(drawing) => setSelectedPidDrawing(drawing)}
              onAddDrawing={(newDrawing) => {
                setPidDrawings(prev => prev.some(d => d.id === newDrawing.id) ? prev : [...prev, newDrawing]);
                setDigitizedDrawingIds(prev => prev.filter(did => did !== newDrawing.id));
              }}
              onDeleteDrawing={(id) => {
                setPidDrawings(prev => prev.filter(d => d.id !== id));
                setDigitizedDrawingIds(prev => prev.filter(did => did !== id));
              }}
              onNavigate={setCurrentView}
            />
          )}

          {currentView === 'sandbox' && (
            <SandboxView
              files={sandboxFiles}
              onOpenQuickCalc={() => setQuickCalcOpen(true)}
              onSaveToReview={(del) => setDeliverables(prev => [del, ...prev])}
              onAppendNetworkTrace={appendNetworkTrace}
            />
          )}

          {currentView === 'knowledge' && (
            <KnowledgeView
              documents={documents}
              onSelectDocument={setSelectedDocument}
              onOpenIngestModal={() => setIngestModalOpen(true)}
            />
          )}

          {currentView === 'review' && (
            <ReviewView
              deliverables={deliverables}
              onNavigate={setCurrentView}
              onClearReview={() => setDeliverables([])}
            />
          )}

          {currentView === 'network' && (
            <NetworkView
              traces={networkTraces}
              onSelectTrace={setSelectedTrace}
            />
          )}

          {currentView === 'node-settings' && (
            <NodeSettingsView
              nodes={nodes}
              activeNode={activeNode}
              onSelectNode={handleSelectNode}
              onDisconnectNode={handleDisconnectNode}
              onInspectCert={setInspectCertNode}
              onNavigate={setCurrentView}
            />
          )}
        </main>
      </div>

      {/* Global Modals */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onNavigate={setCurrentView}
        onRunStarter={(prompt) => {
          setCurrentView('home');
          handleSendMessage(prompt, 'docx', 'Auto Dispatch (Role-Based Router)');
        }}
        onConnectNode={() => handleSelectNode(nodes[0])}
      />

      <InspectCertModal
        node={inspectCertNode}
        onClose={() => setInspectCertNode(null)}
      />

      {selectedPidDrawing && (
        <PidDigitizationViewer
          drawing={selectedPidDrawing}
          isAlreadyDigitized={digitizedDrawingIds.includes(selectedPidDrawing.id)}
          onClose={() => setSelectedPidDrawing(null)}
          onDigitizationComplete={(drawingId) => {
            setDigitizedDrawingIds(prev => prev.includes(drawingId) ? prev : [...prev, drawingId]);
            const newDel: ReviewDeliverable = {
              id: `del-pid-${Date.now()}`,
              title: `${selectedPidDrawing.dwgNumber} Sovereign GraphML Topology`,
              type: 'P&ID Schema',
              sourceRoute: 'Local Enclave Vision RT',
              timestamp: 'Just now',
              summary: `Extracted ${selectedPidDrawing.node_count} nodes and ${selectedPidDrawing.edge_count} topological edges from ${selectedPidDrawing.title}.`,
              content: `# P&ID TOPOLOGY DIGITIZATION REPORT: ${selectedPidDrawing.dwgNumber}\nDrawing: ${selectedPidDrawing.title} (${selectedPidDrawing.tag})\nUnit: ${selectedPidDrawing.unit}\nVerified Nodes: ${selectedPidDrawing.node_count}\nVerified Edges: ${selectedPidDrawing.edge_count}\nValves: ${selectedPidDrawing.labels.valve} | Instrumentation: ${selectedPidDrawing.labels.instrumentation}\nOperating Envelope: ${selectedPidDrawing.qaKnowledge.operatingEnvelope}\nSovereign Integrity: Zero egress mTLS hash verified.`,
              metadata: {
                confidenceScore: '99.7%',
                tokens: 340
              }
            };
            setDeliverables(prev => [newDel, ...prev]);
            appendNetworkTrace('127.0.0.1:8000/v1/embeddings', 'nomic-embed-text', 4096);
          }}
          onSendToSandbox={(title, lineTag) => {
            setSelectedPidDrawing(null);
            setCurrentView('sandbox');
          }}
        />
      )}

      <SopReaderModal
        document={selectedDocument}
        onClose={() => setSelectedDocument(null)}
        onCrossReference={handleCrossReferenceFromSop}
      />

      <TraceInspectModal
        trace={selectedTrace}
        onClose={() => setSelectedTrace(null)}
      />

      <IngestDocModal
        isOpen={ingestModalOpen}
        onClose={() => setIngestModalOpen(false)}
        onIngest={(newDoc) => setDocuments(prev => [newDoc, ...prev])}
      />

      <QuickCalcModal
        isOpen={quickCalcOpen}
        onClose={() => setQuickCalcOpen(false)}
      />
    </div>
  );
}
