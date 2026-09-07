import { describe, expect, it } from "vitest";
import type { ArtifactPreview, SafePreview } from "./intakeBridge";
import type { EvidenceRef, FactEnvelope } from "./protocol";
import { artifactPreviewDetails, formatFactValue, proofDetails, sourcePreviewAvailability } from "./proofInspector";

const evidence: EvidenceRef = {
  evidenceId: "evidence-1",
  contentHash: "9f1e",
  source: {
    sourceDocumentId: "inspection-report.pdf",
    sourceVersion: "revision-4",
    location: { page: 2, region: "table:1" },
    extractionMethod: "ocr",
    observedAt: "2026-09-07T01:00:00Z",
    ingestedAt: "2026-09-07T01:02:00Z",
    ledgerEventRef: "ledger-source-1",
  },
  confidence: 0.94,
  clearance: "restricted",
  taint: "untrusted",
};

const fact: FactEnvelope = {
  factId: "fact-1",
  schemaVersion: "0.1",
  value: 12.5,
  unit: "mm",
  source: evidence.source,
  confidence: 0.92,
  clearance: "restricted",
  taint: "untrusted",
  parentFactIds: ["fact-input-1"],
  derivation: { method: "deterministic calculation", inputFactIds: ["fact-input-1"] },
  supersededBy: null,
};

const sourcePreview: SafePreview = {
  preview_ref: "preview-1",
  preview_kind: "text",
  text: "This content remains untrusted data.",
  source_hash: "sha256:source",
  source_region: "page:2;region:table:1",
  confidence: 0.94,
  clearance: "restricted",
  taint: "untrusted",
  ledger_event_ref: "ledger-preview-1",
};

const artifactPreview: ArtifactPreview = {
  artifact_id: "artifact-1",
  preview_kind: "structured_document",
  title: "Inspection approval note",
  blocks: [{ kind: "paragraph", text: "Node-generated artifact text." }],
  clearance: "restricted",
  taint: "untrusted",
  ledger_event_ref: "ledger-artifact-preview-1",
};

describe("proof inspector projections", () => {
  it("retains provenance, confidence, clearance, taint, and ledger identity for evidence", () => {
    const details = proofDetails({ kind: "evidence", evidence });
    expect(details).toEqual(expect.arrayContaining([
      { label: "Evidence ID", value: "evidence-1", technical: true },
      { label: "Content hash", value: "9f1e", technical: true },
      { label: "Confidence", value: "94%" },
      { label: "Clearance", value: "restricted" },
      { label: "Taint", value: "untrusted" },
      { label: "Location", value: "Page 2 / Region table:1" },
      { label: "Source ledger", value: "ledger-source-1", technical: true },
    ]));
  });

  it("renders a fact as Node-projected data with parent and derivation context", () => {
    const details = proofDetails({ kind: "fact", fact });
    expect(details).toEqual(expect.arrayContaining([
      { label: "Value", value: "12.5 mm" },
      { label: "Derivation", value: "deterministic calculation from fact-input-1" },
      { label: "Parent facts", value: "fact-input-1", technical: true },
      { label: "Supersession", value: "Current", technical: true },
    ]));
    expect(formatFactValue({ not: "a scalar" }, null)).toBe("Structured value supplied by Node");
  });

  it("marks safe preview availability honestly instead of inventing a source link", () => {
    expect(sourcePreviewAvailability({ kind: "evidence", evidence })).toContain("does not supply a safe source-preview reference");
    expect(sourcePreviewAvailability({ kind: "source_preview", preview: sourcePreview })).toBeNull();
    expect(sourcePreviewAvailability({ kind: "artifact", artifactId: "artifact-1" })).toContain("supplied separately");
  });

  it("keeps artifact preview metadata separate from unprovided approval or verification state", () => {
    expect(artifactPreviewDetails(artifactPreview)).toEqual([
      { label: "Artifact ID", value: "artifact-1", technical: true },
      { label: "Preview type", value: "structured_document" },
      { label: "Clearance", value: "restricted" },
      { label: "Taint", value: "untrusted" },
      { label: "Ledger", value: "ledger-artifact-preview-1", technical: true },
    ]);
  });
});
