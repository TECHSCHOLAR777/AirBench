import type { IntakeManifest } from "./intakeBridge";

export type IntakeUiState =
  | "idle"
  | "uploading"
  | "processing"
  | "ready"
  | "rejected"
  | "unsupported"
  | "oversized"
  | "partial"
  | "clearance_mismatch"
  | "failed";

export interface IntakeStatusCopy {
  label: string;
  title: string;
  detail: string;
  retryable: boolean;
}

const STATUS_COPY: Record<IntakeUiState, IntakeStatusCopy> = {
  idle: { label: "Ready for File Intake", title: "Source selected", detail: "Send this file to the approved Node for validation.", retryable: false },
  uploading: { label: "Sending to File Intake", title: "Sending source to File Intake", detail: "The desktop is handing the file to the approved Node. It is not parsing the file.", retryable: false },
  processing: { label: "Processing", title: "File Intake is still processing", detail: "The Node accepted the source, but OCR or vision processing is not complete yet.", retryable: true },
  ready: { label: "Accepted by File Intake", title: "Source accepted", detail: "The Node returned a manifest and a safe preview. The source remains untrusted data.", retryable: false },
  rejected: { label: "Rejected by File Intake", title: "Source was rejected", detail: "The Node did not accept this source for the requested task.", retryable: true },
  unsupported: { label: "Unsupported source", title: "File type is not supported", detail: "Choose a PDF or image format supported by the organization's File Intake policy.", retryable: true },
  oversized: { label: "File too large", title: "Source exceeds the upload limit", detail: "Choose a smaller file or ask an administrator about the configured query-upload limit.", retryable: true },
  partial: { label: "Accepted, preview pending", title: "Source accepted, but preview is not available", detail: "The Node accepted the source manifest, but the safe preview could not be completed. Launch is paused until the source is ready.", retryable: true },
  clearance_mismatch: { label: "Clearance mismatch", title: "Source clearance is above this session", detail: "The Node returned a clearance that this approved session cannot receive. No task can use this source.", retryable: false },
  failed: { label: "File Intake needs attention", title: "File Intake could not complete", detail: "The approved Node did not return a usable intake result. No local parser or fallback path was used.", retryable: true },
};

export function intakeStatusCopy(state: IntakeUiState): IntakeStatusCopy {
  return STATUS_COPY[state];
}

export function intakeStateFromManifest(manifest: Pick<IntakeManifest, "ocr_status" | "vision_status">): "processing" | "ready" {
  const statuses = [manifest.ocr_status, manifest.vision_status];
  return statuses.some((status) => status === "pending" || status === "running") ? "processing" : "ready";
}

function errorMessage(error: unknown): string {
  if (typeof error === "string") return error.toLowerCase();
  if (error instanceof Error) return error.message.toLowerCase();
  if (error && typeof error === "object" && "message" in error && typeof error.message === "string") {
    return error.message.toLowerCase();
  }
  return "";
}

export function classifyIntakeFailure(error: unknown, manifestAccepted = false): Exclude<IntakeUiState, "idle" | "uploading" | "processing" | "ready"> {
  const message = errorMessage(error);
  if (message.includes("clearance")) return "clearance_mismatch";
  if (message.includes("larger") || message.includes("too large") || message.includes("http 413") || message.includes("upload limit")) return "oversized";
  if (message.includes("unsupported") || message.includes("http 415")) return "unsupported";
  if (message.includes("http 4") || message.includes("rejected") || message.includes("denied")) return "rejected";
  if (manifestAccepted || message.includes("interrupted") || message.includes("partial") || message.includes("preview")) return "partial";
  return "failed";
}
