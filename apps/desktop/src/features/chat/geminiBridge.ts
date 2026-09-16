import { invoke } from "@airbench/tauri-invoke";
import { invokeOrThrow } from "../../lib/errors";

class InvalidBridgeResponse extends Error {
  readonly code = "invalid_bridge_response";
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new InvalidBridgeResponse(`The desktop process returned an invalid ${label}.`);
  return value as Record<string, unknown>;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string") throw new InvalidBridgeResponse(`The desktop process returned an invalid ${label}.`);
  return value;
}

function requireNumber(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new InvalidBridgeResponse(`The desktop process returned an invalid ${label}.`);
  return value;
}

function requireBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") throw new InvalidBridgeResponse(`The desktop process returned an invalid ${label}.`);
  return value;
}

export interface ChatTurn {
  role: "user" | "assistant";
  text: string;
}

export interface ChatAttachment {
  fileName: string;
  mimeType: string;
  base64Data: string;
}

export async function sendChatMessage(history: ChatTurn[], message: string, attachment: ChatAttachment | null): Promise<string> {
  const raw = await invokeOrThrow(invoke<unknown>("gemini_chat", {
    history: history.map((turn) => ({ role: turn.role, text: turn.text })),
    message,
    attachment: attachment ? { mime_type: attachment.mimeType, base64_data: attachment.base64Data } : null,
  }));
  const record = requireRecord(raw, "chat reply");
  return requireString(record.text, "chat reply text");
}

export async function pickChatAttachment(): Promise<ChatAttachment | null> {
  const raw = await invokeOrThrow(invoke<unknown>("pick_chat_attachment"));
  if (raw === null || raw === undefined) return null;
  const record = requireRecord(raw, "attachment");
  return {
    fileName: requireString(record.file_name, "attachment file name"),
    mimeType: requireString(record.mime_type, "attachment mime type"),
    base64Data: requireString(record.base64_data, "attachment data"),
  };
}

export interface DocumentSection {
  heading: string;
  body: string;
}

export interface DocumentTable {
  headers: string[];
  rows: string[][];
}

export interface GeneratedDocumentRequest {
  format: "docx" | "xlsx" | "pptx" | "pdf";
  title: string;
  sections: DocumentSection[];
  table: DocumentTable | null;
}

export interface GeneratedDocumentResult {
  filePath: string;
  byteSize: number;
  cancelled: boolean;
}

export async function generateDocument(request: GeneratedDocumentRequest): Promise<GeneratedDocumentResult> {
  const raw = await invokeOrThrow(invoke<unknown>("generate_document", {
    format: request.format,
    title: request.title,
    sections: request.sections,
    table: request.table,
  }));
  const record = requireRecord(raw, "document result");
  return {
    filePath: requireString(record.file_path, "document file path"),
    byteSize: requireNumber(record.byte_size, "document byte size"),
    cancelled: requireBoolean(record.cancelled, "document cancellation flag"),
  };
}

/**
 * If a worker reply is the special {"generate_document": {...}} envelope
 * described in the system instruction (see src-tauri/src/gemini.rs), parse
 * it into a typed request. Returns null for a normal prose/markdown reply.
 */
export function parseGenerateDocumentReply(text: string): GeneratedDocumentRequest | null {
  const trimmed = text.trim();
  if (!trimmed.startsWith("{")) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const envelope = (parsed as Record<string, unknown>).generate_document;
  if (typeof envelope !== "object" || envelope === null) return null;
  const record = envelope as Record<string, unknown>;
  const format = record.format;
  if (format !== "docx" && format !== "xlsx" && format !== "pptx" && format !== "pdf") return null;
  const title = typeof record.title === "string" ? record.title : "Untitled document";
  const sectionsRaw = Array.isArray(record.sections) ? record.sections : [];
  const sections: DocumentSection[] = sectionsRaw
    .filter((entry): entry is Record<string, unknown> => typeof entry === "object" && entry !== null)
    .map((entry) => ({
      heading: typeof entry.heading === "string" ? entry.heading : "",
      body: typeof entry.body === "string" ? entry.body : "",
    }));
  let table: DocumentTable | null = null;
  const tableRaw = record.table;
  if (typeof tableRaw === "object" && tableRaw !== null) {
    const tableRecord = tableRaw as Record<string, unknown>;
    if (Array.isArray(tableRecord.headers)) {
      table = {
        headers: tableRecord.headers.map((header) => String(header)),
        rows: Array.isArray(tableRecord.rows)
          ? tableRecord.rows.map((row) => (Array.isArray(row) ? row.map((cell) => String(cell)) : []))
          : [],
      };
    }
  }
  return { format, title, sections, table };
}
