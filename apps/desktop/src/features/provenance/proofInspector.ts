import type { ArtifactPreview, SafePreview } from "../intake/intakeBridge";
import type { EvidenceRef, FactEnvelope, ProvenanceRef } from "../../platform/events/protocol";

export type ProofSelection =
  | { kind: "evidence"; evidence: EvidenceRef }
  | { kind: "fact"; fact: FactEnvelope }
  | { kind: "source_preview"; preview: SafePreview }
  | { kind: "artifact"; artifactId: string };

export interface ProofDetail {
  label: string;
  value: string;
  technical?: boolean;
}

export type ArtifactPreviewRequestState = "idle" | "loading" | "ready" | "failed";
export type ArtifactDownloadRequestState = "idle" | "downloading" | "downloaded" | "failed";

export interface BoundaryState {
  tone: "neutral" | "active" | "attention" | "blocked";
  label: string;
  detail: string;
  recovery: {
    preserved: string;
    retry: string;
    nextAction: string;
  };
}

export function artifactPreviewBoundaryState(state: ArtifactPreviewRequestState, hasPreview: boolean): BoundaryState {
  if (state === "loading") {
    return {
      tone: "active",
      label: "Requesting a read-only preview",
      detail: "The approved Node is preparing a preview. The original file is not opened by the desktop.",
      recovery: {
        preserved: "The artifact reference and task context remain unchanged.",
        retry: "Wait for this Node request; the desktop will not duplicate it locally.",
        nextAction: "Wait for the Node result or use a Node-authorized retry.",
      },
    };
  }
  if (state === "failed") {
    return {
      tone: "blocked",
      label: "Preview unavailable",
      detail: "The approved Node did not return a safe artifact preview.",
      recovery: {
        preserved: "The artifact reference and provenance remain; the original file was not opened.",
        retry: "No automatic retry is performed when preview safety is unproven.",
        nextAction: "Check the Node result and request a new preview through the approved path.",
      },
    };
  }
  if (state === "ready" && hasPreview) {
    return {
      tone: "active",
      label: "Read-only Node preview",
      detail: "This is Node-returned data, not the original document and not an approval decision.",
      recovery: {
        preserved: "Preview metadata, provenance, clearance, and taint remain attached.",
        retry: "Request again only through the approved Node path.",
        nextAction: "Inspect the preview; approval and verification remain Node-supplied.",
      },
    };
  }
  if (state === "ready") {
    return {
      tone: "attention",
      label: "Preview not supplied",
      detail: "The Node has not returned a safe preview for this artifact.",
      recovery: {
        preserved: "The artifact reference remains visible; no document content is shown.",
        retry: "Do not retry locally while the Node preview contract is absent.",
        nextAction: "Wait for the Node to supply a safe preview reference.",
      },
    };
  }
  return {
    tone: "neutral",
    label: "Preview not requested",
    detail: "The desktop will show content only after the approved Node returns a safe, read-only preview.",
    recovery: {
      preserved: "No artifact bytes have been opened or saved by the desktop.",
      retry: "No request has started, so no retry is needed.",
      nextAction: "Request a read-only preview through the approved Node path.",
    },
  };
}

export function artifactDownloadBoundaryState(state: ArtifactDownloadRequestState): BoundaryState {
  if (state === "downloading") {
    return {
      tone: "active",
      label: "Checking download permission",
      detail: "The Node is checking permission and will save a copy only if allowed.",
      recovery: {
        preserved: "No local copy is saved until the Node returns a permitted receipt.",
        retry: "Do not duplicate the permission request while this check is in progress.",
        nextAction: "Wait for the Node decision and its ledgered download result.",
      },
    };
  }
  if (state === "downloaded") {
    return {
      tone: "active",
      label: "Download saved",
      detail: "The Node returned a download receipt and the desktop saved the permitted copy.",
      recovery: {
        preserved: "The saved byte count, content hash, and ledger reference remain visible.",
        retry: "Request another copy only through the approved Node path.",
        nextAction: "Use the permitted local copy under organizational handling policy.",
      },
    };
  }
  if (state === "failed") {
    return {
      tone: "blocked",
      label: "Download not completed",
      detail: "The Node denied the request or the local save did not complete.",
      recovery: {
        preserved: "No unverified or unauthorized download is treated as complete.",
        retry: "No automatic retry is performed after a denial or incomplete local save.",
        nextAction: "Review the Node result and ledger reference before requesting again.",
      },
    };
  }
  return {
    tone: "neutral",
    label: "Request permitted download",
    detail: "The Node must authorize this request before the desktop can save a copy.",
    recovery: {
      preserved: "No local artifact copy exists from this request.",
      retry: "A request has not started, so no retry is needed.",
      nextAction: "Request permission through the approved Node path.",
    },
  };
}

export function proofSelectionTitle(selection: ProofSelection): string {
  switch (selection.kind) {
    case "evidence":
      return "Source evidence";
    case "fact":
      return "Node-projected finding";
    case "source_preview":
      return "Query-upload preview";
    case "artifact":
      return "Artifact preview";
  }
}

export function proofSelectionDescription(selection: ProofSelection): string {
  switch (selection.kind) {
    case "evidence":
      return `Evidence ${selection.evidence.evidenceId} from ${selection.evidence.source.sourceDocumentId}.`;
    case "fact":
      return `Finding ${selection.fact.factId} from ${selection.fact.source.sourceDocumentId}.`;
    case "source_preview":
      return "A Node-generated preview of the selected query upload. Its content remains untrusted data.";
    case "artifact":
      return `Node-generated preview requested for ${selection.artifactId}.`;
  }
}

export function formatProvenanceLocation(location: ProvenanceRef["location"]): string {
  if (!location) return "Source region not supplied";
  const parts = [
    location.page ? `Page ${location.page}` : null,
    location.span ? `Span ${location.span}` : null,
    location.cell ? `Cell ${location.cell}` : null,
    location.region ? `Region ${location.region}` : null,
  ].filter((item): item is string => Boolean(item));
  return parts.length > 0 ? parts.join(" / ") : "Source region not supplied";
}

export function provenanceDetails(provenance: ProvenanceRef): ProofDetail[] {
  return [
    { label: "Source", value: provenance.sourceDocumentId },
    { label: "Version", value: provenance.sourceVersion },
    { label: "Location", value: formatProvenanceLocation(provenance.location) },
    { label: "Method", value: provenance.extractionMethod },
    { label: "Observed", value: provenance.observedAt ?? "Not supplied", technical: true },
    { label: "Ingested", value: provenance.ingestedAt, technical: true },
    { label: "Source ledger", value: provenance.ledgerEventRef, technical: true },
  ];
}

export function proofDetails(selection: ProofSelection): ProofDetail[] {
  switch (selection.kind) {
    case "evidence":
      return [
        { label: "Evidence ID", value: selection.evidence.evidenceId, technical: true },
        { label: "Content hash", value: selection.evidence.contentHash, technical: true },
        { label: "Confidence", value: formatConfidence(selection.evidence.confidence) },
        { label: "Clearance", value: selection.evidence.clearance },
        { label: "Taint", value: selection.evidence.taint },
        ...provenanceDetails(selection.evidence.source),
      ];
    case "fact":
      return [
        { label: "Fact ID", value: selection.fact.factId, technical: true },
        { label: "Schema", value: selection.fact.schemaVersion, technical: true },
        { label: "Value", value: formatFactValue(selection.fact.value, selection.fact.unit) },
        { label: "Confidence", value: formatConfidence(selection.fact.confidence) },
        { label: "Clearance", value: selection.fact.clearance },
        { label: "Taint", value: selection.fact.taint },
        { label: "Derivation", value: formatDerivation(selection.fact) },
        { label: "Parent facts", value: selection.fact.parentFactIds.length > 0 ? selection.fact.parentFactIds.join(", ") : "None supplied", technical: true },
        { label: "Supersession", value: selection.fact.supersededBy ?? "Current", technical: true },
        ...provenanceDetails(selection.fact.source),
      ];
    case "source_preview":
      return [
        { label: "Preview reference", value: selection.preview.preview_ref, technical: true },
        { label: "Preview type", value: selection.preview.preview_kind },
        { label: "Source hash", value: selection.preview.source_hash, technical: true },
        { label: "Source region", value: selection.preview.source_region },
        { label: "Confidence", value: formatConfidence(selection.preview.confidence) },
        { label: "Clearance", value: selection.preview.clearance },
        { label: "Taint", value: selection.preview.taint },
        { label: "Ledger", value: selection.preview.ledger_event_ref, technical: true },
      ];
    case "artifact":
      return [{ label: "Artifact ID", value: selection.artifactId, technical: true }];
  }
}

export function artifactPreviewDetails(preview: ArtifactPreview): ProofDetail[] {
  return [
    { label: "Artifact ID", value: preview.artifact_id, technical: true },
    { label: "Preview type", value: preview.preview_kind },
    { label: "Clearance", value: preview.clearance },
    { label: "Taint", value: preview.taint },
    { label: "Ledger", value: preview.ledger_event_ref, technical: true },
  ];
}

export function sourcePreviewAvailability(selection: ProofSelection): string | null {
  if (selection.kind === "source_preview") return null;
  if (selection.kind === "artifact") return "Artifact previews are supplied separately by the Node.";
  return "The current Node evidence contract does not supply a safe source-preview reference for this record.";
}

export function formatFactValue(value: unknown, unit: string | null): string {
  let rendered: string;
  if (value === null || value === undefined) {
    rendered = "No value supplied";
  } else if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    rendered = boundedText(String(value));
  } else {
    rendered = "Structured value supplied by Node";
  }
  return unit ? `${rendered} ${unit}` : rendered;
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatDerivation(fact: FactEnvelope): string {
  if (!fact.derivation) return "Source-derived or method not supplied";
  const method = typeof fact.derivation.method === "string" ? fact.derivation.method : "Derivation method not supplied";
  const inputFactIds = Array.isArray(fact.derivation.inputFactIds)
    ? fact.derivation.inputFactIds.filter((value): value is string => typeof value === "string")
    : [];
  const inputs = inputFactIds.length > 0 ? ` from ${inputFactIds.join(", ")}` : "";
  return `${method}${inputs}`;
}

function boundedText(value: string): string {
  const limit = 512;
  return value.length <= limit ? value : `${value.slice(0, limit)} [truncated in compact view]`;
}
