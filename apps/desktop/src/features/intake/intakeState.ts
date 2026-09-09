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
  recovery: {
    preserved: string;
    retry: string;
    nextAction: string;
  };
}

const STATUS_COPY: Record<IntakeUiState, IntakeStatusCopy> = {
  idle: { label: "Ready for File Intake", title: "Source selected", detail: "Send this file to the approved Node for validation.", retryable: false, recovery: { preserved: "The selected source has not been sent or parsed by the desktop.", retry: "No intake request has started, so no retry is needed.", nextAction: "Send the source to the approved Node for File Intake." } },
  uploading: { label: "Sending to File Intake", title: "Sending source to File Intake", detail: "The desktop is handing the file to the approved Node. It is not parsing the file.", retryable: false, recovery: { preserved: "The selected source remains attached to this task draft.", retry: "Do not duplicate the request while the Node is receiving it.", nextAction: "Wait for the Node to return an intake result." } },
  processing: { label: "Processing", title: "File Intake is still processing", detail: "The Node accepted the source, but OCR or vision processing is not complete yet.", retryable: false, recovery: { preserved: "The Node manifest and source identity remain attached; the preview is not final.", retry: "Wait for the current OCR or vision result before requesting another intake.", nextAction: "Wait for the Node processing result, or remove the source if you no longer want to use it." } },
  ready: { label: "Accepted by File Intake", title: "Source accepted", detail: "The Node returned a manifest and a safe preview. The source remains untrusted data.", retryable: false, recovery: { preserved: "The manifest, safe preview, source hash, clearance, and taint remain visible.", retry: "No retry is needed for an accepted source.", nextAction: "Review the Node-generated preview before launching the task." } },
  rejected: { label: "Rejected by File Intake", title: "Source was rejected", detail: "The Node did not accept this source for the requested task.", retryable: true, recovery: { preserved: "The rejected source is not added to the task's accepted intake set.", retry: "Retry only after changing the source or request that caused the Node rejection.", nextAction: "Review the Node rejection and choose another source if permitted." } },
  unsupported: { label: "Unsupported source", title: "File type is not supported", detail: "Choose a PDF or image format supported by the organization's File Intake policy.", retryable: true, recovery: { preserved: "The unsupported file is not parsed or sent through a fallback parser.", retry: "Choose a supported source before trying again.", nextAction: "Choose a PDF or image allowed by the approved File Intake policy." } },
  oversized: { label: "File too large", title: "Source exceeds the upload limit", detail: "Choose a smaller file or ask an administrator about the configured query-upload limit.", retryable: true, recovery: { preserved: "The oversized source is not accepted into the task intake set.", retry: "Retry only with a source within the Node's configured limit.", nextAction: "Choose a smaller source or ask an administrator about the limit." } },
  partial: { label: "Accepted, preview pending", title: "Source accepted, but preview is not available", detail: "The Node accepted the source manifest, but the safe preview could not be completed. Launch is paused until the source is ready.", retryable: false, recovery: { preserved: "The accepted manifest and source provenance remain available; launch remains paused.", retry: "Do not replace the accepted manifest with a local or unverified preview.", nextAction: "Wait for a Node-authorized preview result or remove the source." } },
  clearance_mismatch: { label: "Clearance mismatch", title: "Source clearance is above this session", detail: "The Node returned a clearance that this approved session cannot receive. No task can use this source.", retryable: false, recovery: { preserved: "The source remains blocked and its restricted content is not displayed.", retry: "Do not retry from this session or lower the clearance locally.", nextAction: "Use an approved session with the required clearance, if policy permits." } },
  failed: { label: "File Intake needs attention", title: "File Intake could not complete", detail: "The approved Node did not return a usable intake result. No local parser or fallback path was used.", retryable: true, recovery: { preserved: "No usable manifest was accepted, and the desktop did not parse or substitute the source.", retry: "Retry only through the approved Node path after checking the connection state.", nextAction: "Recheck the Node, then request File Intake again if the Node permits it." } },
};

export function intakeStatusCopy(state: IntakeUiState): IntakeStatusCopy {
  return STATUS_COPY[state];
}

export function intakeStateFromManifest(manifest: Pick<IntakeManifest, "ocr_status" | "vision_status">): "processing" | "ready" | "partial" {
  const statuses = [manifest.ocr_status, manifest.vision_status];
  if (statuses.some((status) => status === "pending" || status === "running")) return "processing";
  return statuses.every((status) => status === "completed" || status === "not_applicable") ? "ready" : "partial";
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
