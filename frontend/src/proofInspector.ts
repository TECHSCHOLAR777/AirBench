import type { ArtifactPreview, SafePreview } from "./intakeBridge";
import type { EvidenceRef, FactEnvelope, ProvenanceRef } from "./protocol";

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
  const inputs = fact.derivation.inputFactIds.length > 0 ? ` from ${fact.derivation.inputFactIds.join(", ")}` : "";
  return `${fact.derivation.method}${inputs}`;
}

function boundedText(value: string): string {
  const limit = 512;
  return value.length <= limit ? value : `${value.slice(0, limit)} [truncated in compact view]`;
}
