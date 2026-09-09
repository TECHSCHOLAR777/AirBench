import { describe, expect, it } from "vitest";
import type { ArtifactPreview, SafePreview } from "../intake/intakeBridge";
import type { EvidenceRef, FactEnvelope } from "../../platform/events/protocol";
import {
  artifactDownloadBoundaryState,
  artifactPreviewBoundaryState,
  artifactPreviewDetails,
  confidenceSignal,
  formatFactValue,
  proofDetails,
  reconcileProofSelection,
  proofSignals,
  sourcePreviewAvailability,
  taintSignal,
} from "./proofInspector";

const evidence: EvidenceRef = {
  schemaVersion: "0.1",
  compatibilityId: "airbench-node-protocol",
  evidenceId: "evidence-1",
  contentHash: "9f1e",
  source: {
    schemaVersion: "0.1",
    compatibilityId: "airbench-node-protocol",
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
  compatibilityId: "airbench-node-protocol",
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

  it("turns low confidence, taint, missing location, and supersession into explicit review cues", () => {
    const signals = proofSignals({
      kind: "fact",
      fact: {
        ...fact,
        confidence: 0.4,
        taint: "contaminated",
        source: { ...fact.source, location: null },
        supersededBy: "fact-replacement-1",
      },
    });

    expect(signals.map((signal) => signal.label)).toEqual([
      "Low confidence, 40%",
      "Contaminated source data",
      "Exact source region not supplied",
      "Finding superseded",
    ]);
    expect(signals.every((signal) => signal.detail.length > 0)).toBe(true);
  });

  it("keeps confidence and taint cues presentation-only", () => {
    expect(confidenceSignal(0.94).detail).toContain("not an approval");
    expect(confidenceSignal(0.7).tone).toBe("attention");
    expect(taintSignal("untrusted").detail).toContain("never as instructions");
    expect(taintSignal("clean").detail).toContain("no authority");
    expect(taintSignal("future-taint").tone).toBe("blocked");
    expect(proofSignals({ kind: "artifact", artifactId: "artifact-1" })).toEqual([]);
  });

  it("refreshes selected records from the current Node projection", () => {
    const revisedEvidence = { ...evidence, confidence: 0.41, source: { ...evidence.source, sourceVersion: "revision-5" } };
    const refreshed = reconcileProofSelection({ kind: "evidence", evidence }, [revisedEvidence], [], null);
    expect(refreshed).toEqual({ kind: "evidence", evidence: revisedEvidence });
    expect(reconcileProofSelection({ kind: "evidence", evidence }, [], [], null)).toBeNull();
    expect(reconcileProofSelection({ kind: "source_preview", preview: sourcePreview }, [], [], null)).toBeNull();
    expect(reconcileProofSelection({ kind: "source_preview", preview: sourcePreview }, [], [], { ...sourcePreview, text: "revised preview" })).toMatchObject({ preview: { text: "revised preview" } });
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

  it("describes the artifact preview boundary without claiming artifact approval", () => {
    expect(artifactPreviewBoundaryState("idle", false)).toEqual({
      tone: "neutral",
      label: "Preview not requested",
      detail: "The desktop will show content only after the approved Node returns a safe, read-only preview.",
      recovery: {
        preserved: "No artifact bytes have been opened or saved by the desktop.",
        retry: "No request has started, so no retry is needed.",
        nextAction: "Request a read-only preview through the approved Node path.",
      },
    });
    expect(artifactPreviewBoundaryState("loading", false)).toEqual({
      tone: "active",
      label: "Requesting a read-only preview",
      detail: "The approved Node is preparing a preview. The original file is not opened by the desktop.",
      recovery: {
        preserved: "The artifact reference and task context remain unchanged.",
        retry: "Wait for this Node request; the desktop will not duplicate it locally.",
        nextAction: "Wait for the Node result or use a Node-authorized retry.",
      },
    });
    expect(artifactPreviewBoundaryState("ready", true)).toEqual({
      tone: "active",
      label: "Read-only Node preview",
      detail: "This is Node-returned data, not the original document and not an approval decision.",
      recovery: {
        preserved: "Preview metadata, provenance, clearance, and taint remain attached.",
        retry: "Request again only through the approved Node path.",
        nextAction: "Inspect the preview; approval and verification remain Node-supplied.",
      },
    });
    expect(artifactPreviewBoundaryState("ready", false)).toEqual({
      tone: "attention",
      label: "Preview not supplied",
      detail: "The Node has not returned a safe preview for this artifact.",
      recovery: {
        preserved: "The artifact reference remains visible; no document content is shown.",
        retry: "Do not retry locally while the Node preview contract is absent.",
        nextAction: "Wait for the Node to supply a safe preview reference.",
      },
    });
    expect(artifactPreviewBoundaryState("failed", false)).toEqual({
      tone: "blocked",
      label: "Preview unavailable",
      detail: "The approved Node did not return a safe artifact preview.",
      recovery: {
        preserved: "The artifact reference and provenance remain; the original file was not opened.",
        retry: "No automatic retry is performed when preview safety is unproven.",
        nextAction: "Check the Node result and request a new preview through the approved path.",
      },
    });
  });

  it("keeps download permission with the Node and separates it from local save state", () => {
    expect(artifactDownloadBoundaryState("idle")).toEqual({
      tone: "neutral",
      label: "Request permitted download",
      detail: "The Node must authorize this request before the desktop can save a copy.",
      recovery: {
        preserved: "No local artifact copy exists from this request.",
        retry: "A request has not started, so no retry is needed.",
        nextAction: "Request permission through the approved Node path.",
      },
    });
    expect(artifactDownloadBoundaryState("downloading")).toEqual({
      tone: "active",
      label: "Checking download permission",
      detail: "The Node is checking permission and will save a copy only if allowed.",
      recovery: {
        preserved: "No local copy is saved until the Node returns a permitted receipt.",
        retry: "Do not duplicate the permission request while this check is in progress.",
        nextAction: "Wait for the Node decision and its ledgered download result.",
      },
    });
    expect(artifactDownloadBoundaryState("downloaded")).toEqual({
      tone: "active",
      label: "Download saved",
      detail: "The Node returned a download receipt and the desktop saved the permitted copy.",
      recovery: {
        preserved: "The saved byte count, content hash, and ledger reference remain visible.",
        retry: "Request another copy only through the approved Node path.",
        nextAction: "Use the permitted local copy under organizational handling policy.",
      },
    });
    expect(artifactDownloadBoundaryState("failed")).toEqual({
      tone: "blocked",
      label: "Download not completed",
      detail: "The Node denied the request or the local save did not complete.",
      recovery: {
        preserved: "No unverified or unauthorized download is treated as complete.",
        retry: "No automatic retry is performed after a denial or incomplete local save.",
        nextAction: "Review the Node result and ledger reference before requesting again.",
      },
    });
  });
});
