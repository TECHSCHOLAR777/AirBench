export type PageView = 'home' | 'pid' | 'sandbox' | 'knowledge' | 'review' | 'network' | 'node-settings';

export interface EnclaveNode {
  id: string;
  hostname: string;
  status: 'READY' | 'CONNECTED' | 'STANDBY';
  host: string;
  latency: string;
  policy: string;
  fingerprint: string;
  certificateIssuer: string;
  expires: string;
}

export interface SopDocument {
  id: string;
  code: string;
  title: string;
  rev: string;
  pages: number;
  category: 'Maintenance' | 'Quality' | 'Safety' | 'Process' | 'Inspection' | 'Engineering' | 'Operations' | 'Environmental';
  status: 'Indexed';
  passagesCount: number;
  lastUpdated: string;
  sections: {
    heading: string;
    text: string;
  }[];
}

export interface PidSchematic {
  id: string;
  title: string;
  dwg: string;
  rev: string;
  sheet: string;
  symbolsCount: number;
  status: 'Topology mapped' | 'Reconstruction sync' | 'Drafting queued';
  statusTone: 'emerald' | 'amber' | 'dim';
  exportState: string;
  category: string;
  previewUrl?: string;
  symbols: {
    id: string;
    tag: string;
    type: string;
    description: string;
    coordinates: string;
    specs: string;
  }[];
  connections: {
    from: string;
    to: string;
    lineTag: string;
    spec: string;
  }[];
}

export type DeliverableFormat = 'auto' | 'docx' | 'pptx' | 'xlsx' | 'pdf' | 'md' | 'py';

export interface ReviewDeliverable {
  id: string;
  title: string;
  type: 'Document' | 'Code' | 'P&ID Schema' | 'Audit Memo' | 'Calculation' | 'Presentation' | 'Spreadsheet' | 'PDF';
  format?: DeliverableFormat;
  sourceRoute: string;
  timestamp: string;
  summary: string;
  content: string;
  metadata: {
    wordCount?: number;
    exitCode?: number;
    confidenceScore?: string;
    tokens?: number;
    slidesCount?: number;
    rowsCount?: number;
  };
  sourceFile?: {
    name: string;
    extension: string;
    dataUrl: string;
  };
}

export interface AttachedFileMeta {
  id: string;
  name: string;
  size: number;
  type: 'doc' | 'ppt' | 'excel' | 'pdf' | 'md' | 'code' | 'other';
  extension: string;
  contentPreview?: string;
  dataUrl?: string;
}

export interface NetworkTrace {
  id: string;
  timestamp: string;
  route: 'LOCAL' | 'ENCLAVE_PROXY' | 'BLOCKED';
  endpoint: string;
  method: 'POST' | 'GET';
  status: number;
  payloadBytes: number;
  model: string;
  quantization: string;
  headers: Record<string, string>;
  curlCommand: string;
}

export interface SandboxScript {
  id: string;
  name: string;
  type: string;
  timestamp: string;
  size: string;
  description: string;
  code: string;
  expectedOutput: string;
  variables: Record<string, number | string>;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  timestamp: string;
  text: string;
  route?: string;
  deliverable?: ReviewDeliverable;
  isStreaming?: boolean;
  isGenerating?: boolean;
  generatingPhase?: string;
  roundRobinInfo?: {
    keyIndex: number;
    totalKeys: number;
    keyMasked: string;
    provider?: string;
  };
  attachedFiles?: AttachedFileMeta[];
}

export interface ConversationSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  model: string;
  deliverableType: string;
  messages: ChatMessage[];
  lastQuerySnippet: string;
  pinned?: boolean;
}
