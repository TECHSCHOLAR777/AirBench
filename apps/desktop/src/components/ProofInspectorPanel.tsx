import { AppIcon } from "./AppIcon";
import { AdvancedDetails } from "./AdvancedDetails";
import type { ArtifactPreview, DownloadReceipt } from "../features/intake/intakeBridge";
import type { NodeArtifactReview } from "../generated/core_contracts";
import {
  artifactDownloadBoundaryState,
  artifactPreviewBoundaryState,
  artifactPreviewDetails,
  proofDetails,
  proofSignals,
  proofSelectionDescription,
  proofSelectionTitle,
  sourcePreviewAvailability,
  type ArtifactPreviewRequestState,
  type BoundaryState,
  type ProofDetail,
  type ProofSelection,
} from "../features/provenance/proofInspector";

export type ArtifactPreviewState = ArtifactPreviewRequestState;
export type ArtifactLifecycleState = "ready" | "superseded" | "reference_only";

interface ProofInspectorPanelProps {
  selection: ProofSelection | null;
  artifactReview: NodeArtifactReview | null;
  artifactPreview: ArtifactPreview | null;
  artifactPreviewState: ArtifactPreviewState;
  artifactPreviewError: string | null;
  artifactLifecycleState: ArtifactLifecycleState | null;
  downloadState: "idle" | "downloading" | "downloaded" | "failed";
  downloadReceipt: DownloadReceipt | null;
  onDownloadArtifact: (artifactId: string) => void;
  onApproveArtifact: (artifactId: string, reason: string) => void;
  onReturnArtifact: (artifactId: string, reason: string) => void;
  isArtifactCommandPending: boolean;
}

export function ProofInspectorPanel({
    selection,
    artifactReview,
  artifactPreview,
  artifactPreviewState,
  artifactPreviewError,
  artifactLifecycleState,
  downloadState,
  downloadReceipt,
  onDownloadArtifact,
  onApproveArtifact,
  onReturnArtifact,
  isArtifactCommandPending,
}: ProofInspectorPanelProps) {
  return <aside className="proof-inspector" data-testid="proof-inspector" aria-label="Proof inspector">
    <header className="proof-inspector-head">
      <div>
        <p className="eyebrow">PROOF</p>
        <h2>Inspector</h2>
      </div>
      <AppIcon name="shield" size={17} />
    </header>
    {!selection && <EmptyInspector />}
    {selection && <InspectorSelection
      selection={selection}
      artifactReview={artifactReview}
      artifactPreview={artifactPreview}
      artifactPreviewState={artifactPreviewState}
      artifactPreviewError={artifactPreviewError}
      artifactLifecycleState={artifactLifecycleState}
      downloadState={downloadState}
      downloadReceipt={downloadReceipt}
      onDownloadArtifact={onDownloadArtifact}
      onApproveArtifact={onApproveArtifact}
      onReturnArtifact={onReturnArtifact}
      isArtifactCommandPending={isArtifactCommandPending}
    />}
  </aside>;
}

function EmptyInspector() {
  return <div className="proof-inspector-empty">
    <AppIcon name="archive" size={18} />
    <strong>Select a record to inspect its proof.</strong>
    <p>Evidence, findings, query-upload previews, and artifact references keep their Node-provided context here.</p>
  </div>;
}

type InspectorSelectionProps = Omit<ProofInspectorPanelProps, "selection"> & {
  selection: ProofSelection;
  onApproveArtifact: (artifactId: string, reason: string) => void;
  onReturnArtifact: (artifactId: string, reason: string) => void;
  isArtifactCommandPending: boolean;
};

function InspectorSelection({
  selection,
  artifactReview,
  artifactPreview,
  artifactPreviewState,
  artifactPreviewError,
  artifactLifecycleState,
  downloadState,
  downloadReceipt,
  onDownloadArtifact,
  onApproveArtifact,
  onReturnArtifact,
  isArtifactCommandPending,
}: InspectorSelectionProps) {
  const preview = selection.kind === "artifact" && artifactPreview?.artifact_id === selection.artifactId ? artifactPreview : null;
  const details = preview ? artifactPreviewDetails(preview) : proofDetails(selection);
  const sourcePreviewNotice = sourcePreviewAvailability(selection);

  return <div className="proof-inspector-content">
    <div className="proof-selection-intro">
      <span className={`proof-kind proof-kind-${selection.kind}`}>{proofSelectionTitle(selection)}</span>
      <strong>{proofSelectionDescription(selection)}</strong>
    </div>

    <ProofSignals selection={selection} />

    {selection.kind === "source_preview" && <section className="proof-preview-safe" aria-label="Node-generated safe source preview">
      <PreviewBoundary tone="active" label="Read-only Node preview" detail="This is Node-returned data from a query upload. It remains untrusted data and is not an instruction." recovery={{ preserved: "The source manifest and provenance remain attached to this preview.", retry: "Request again only through the approved Node path.", nextAction: "Inspect the preview as data; it is not an instruction or approval decision." }} />
      <pre>{selection.preview.text}</pre>
      <small>Preview content remains data and is not executed by the desktop app.</small>
    </section>}

    {selection.kind === "artifact" && (artifactLifecycleState === "ready"
      ? <ArtifactPreviewPanel
        preview={preview}
        state={artifactPreviewState}
        error={artifactPreviewError}
        downloadState={downloadState}
        downloadReceipt={downloadReceipt}
        onDownload={() => onDownloadArtifact(selection.artifactId)}
      />
      : <ArtifactLifecycleBoundary state={artifactLifecycleState} />)}

    {selection.kind === "artifact" && artifactReview?.artifactId === selection.artifactId && <ArtifactReviewPanel review={artifactReview} onApprove={onApproveArtifact} onReturn={onReturnArtifact} isPending={isArtifactCommandPending} />}

    <ProofDetails details={details} />

    {sourcePreviewNotice && <div className="proof-contract-note"><AppIcon name="document" size={15} /><span>{sourcePreviewNotice}</span></div>}

    {(selection.kind === "evidence" || selection.kind === "fact") && <div className="proof-contract-note"><AppIcon name="review" size={15} /><span>Conflict status and reviewer-note actions are not supplied by the current Node evidence contract. This view cannot declare a record conflict-free or edit an existing fact.</span></div>}

    {selection.kind === "artifact" && !artifactReview && <div className="proof-contract-note"><AppIcon name="review" size={15} /><span>The Node has not supplied a review projection for this artifact. Approval, verification, and deterministic-value status remain unavailable.</span></div>}
  </div>;
}

function ArtifactReviewPanel({ review, onApprove, onReturn, isPending }: { review: NodeArtifactReview; onApprove: (artifactId: string, reason: string) => void; onReturn: (artifactId: string, reason: string) => void; isPending: boolean }) {
  const showActions = (review.approvalState === "pending" || review.approvalState === "needs_review")
    && review.approvalBlockingReasons.length === 0;
  return <section className="proof-artifact-review" aria-label="Node artifact review">
    <div className="proof-artifact-review-head"><div><span className="proof-artifact-review-kicker">DELIVERABLE RECORD</span><strong>{review.status.replaceAll("_", " ")}</strong></div><span className={`proof-review-badge proof-review-badge-${review.approvalState}`}>{review.approvalState.replaceAll("_", " ")}</span></div>
    <dl className="proof-artifact-review-grid">
      <div><dt>Verification</dt><dd>{review.verificationStatus}</dd></div>
      <div><dt>Structure</dt><dd>{review.structuralCheck}</dd></div>
      <div><dt>Visual check</dt><dd>{review.visualCheck}</dd></div>
      <div><dt>Confidence</dt><dd>{Math.round(review.confidence * 100)}%</dd></div>
      <div><dt>Format</dt><dd>{review.fileFormat.toUpperCase()}</dd></div>
      <div><dt>Size</dt><dd>{review.byteSize.toLocaleString()} bytes</dd></div>
    </dl>
    {review.approvalBlockingReasons.length > 0 && <div className="proof-artifact-review-blockers" role="status"><strong>Review still required</strong><ul>{review.approvalBlockingReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div>}
    {showActions && <div className="proof-artifact-review-actions"><button type="button" className="primary-button compact-button" onClick={() => onApprove(review.artifactId, "Operator approved the artifact.")} disabled={isPending}>{isPending ? "Approving..." : "Approve artifact"}</button><button type="button" className="secondary-button compact-button" onClick={() => onReturn(review.artifactId, "Operator requested revision.")} disabled={isPending}>{isPending ? "Returning..." : "Return for revision"}</button></div>}
    <div className="proof-artifact-review-provenance"><span>Provenance retained</span><small>{review.sourceRefs.length} source reference{review.sourceRefs.length === 1 ? "" : "s"} / {review.evidenceRefs.length} evidence / {review.verificationRefs.length} verification / {review.deterministicValueRefs.length} deterministic value binding{review.deterministicValueRefs.length === 1 ? "" : "s"}</small><AdvancedDetails><small>Template {review.templateId} v{review.templateVersion} / ledger {review.ledgerEventRef}</small></AdvancedDetails></div>
  </section>;
}

function ArtifactPreviewPanel({ preview, state, error, downloadState, downloadReceipt, onDownload }: {
  preview: ArtifactPreview | null;
  state: ArtifactPreviewState;
  error: string | null;
  downloadState: "idle" | "downloading" | "downloaded" | "failed";
  downloadReceipt: DownloadReceipt | null;
  onDownload: () => void;
}) {
  const previewBoundary = artifactPreviewBoundaryState(state, Boolean(preview));
  if (state !== "ready" || !preview) return <div className={`proof-preview-state proof-preview-state-${previewBoundary.tone}`} role={state === "loading" ? "status" : state === "failed" ? "alert" : undefined}>
    <PreviewBoundary {...previewBoundary} />
    {state === "failed" && <>
      <p>{error ?? previewBoundary.detail}</p>
      <small>No original document content was opened in the desktop app.</small>
    </>}
  </div>;

  const downloadBoundary = artifactDownloadBoundaryState(downloadState);

  return <section className="proof-artifact-preview" aria-label="Node-generated artifact preview">
    <PreviewBoundary {...previewBoundary} />
    <div className="proof-artifact-preview-head"><span>Preview content</span><strong>{preview.title}</strong></div>
    <div className="proof-artifact-blocks">{preview.blocks.map((block, index) => <div key={`${block.kind}-${index}`}><span>{block.kind}</span><p>{block.text}</p></div>)}</div>
    <div className="proof-artifact-actions">
      <div className={`proof-download-state proof-download-state-${downloadBoundary.tone}`} role={downloadState === "failed" ? "alert" : downloadState === "downloading" ? "status" : undefined}>
        <AppIcon name={downloadState === "failed" ? "shield" : "document"} size={14} />
        <div><strong>{downloadBoundary.label}</strong><span>{downloadBoundary.detail}</span></div>
      </div>
      <button className="secondary-button compact-button" type="button" onClick={onDownload} disabled={downloadState === "downloading"}>{downloadState === "downloading" ? "Checking permission..." : downloadState === "downloaded" ? "Request again" : "Request permitted download"}</button>
      {downloadReceipt && <small>Local save: {downloadReceipt.byte_size} bytes. Ledger {downloadReceipt.ledger_event_ref}.</small>}
    </div>
  </section>;
}

function PreviewBoundary({ tone, label, detail, recovery }: BoundaryState) {
  return <div className={`proof-preview-boundary proof-preview-boundary-${tone}`}>
    <AppIcon name={tone === "blocked" ? "shield" : "document"} size={14} />
    <div><strong>{label}</strong><p>{detail}</p><dl className="proof-recovery-guidance" aria-label="Safe recovery guidance"><div><dt>Preserved</dt><dd>{recovery.preserved}</dd></div><div><dt>Retry</dt><dd>{recovery.retry}</dd></div><div><dt>Next</dt><dd>{recovery.nextAction}</dd></div></dl></div>
  </div>;
}

function ArtifactLifecycleBoundary({ state }: { state: ArtifactLifecycleState | null }) {
  const superseded = state === "superseded";
  return <div className={`proof-preview-state proof-preview-state-${superseded ? "blocked" : "neutral"}`} role={superseded ? "alert" : "status"}>
    <PreviewBoundary
      tone={superseded ? "blocked" : "attention"}
      label={superseded ? "Artifact superseded" : "Artifact reference only"}
      detail={superseded
        ? "The Node has recorded a newer artifact state. Preview and download are unavailable for this record."
        : "The Node has supplied an artifact reference but not a ready lifecycle event. Preview and download remain unavailable."}
      recovery={{
        preserved: "The artifact identity and ordered Node record remain visible.",
        retry: "No local retry is performed while the artifact is not Node-authorized for review.",
        nextAction: superseded ? "Select the current Node artifact record." : "Wait for the Node to supply a ready artifact record.",
      }}
    />
  </div>;
}

function ProofSignals({ selection }: { selection: ProofSelection }) {
  const signals = proofSignals(selection);
  if (signals.length === 0) return null;
  return <section className="proof-signal-panel" aria-label="Proof reading cues">
    <div className="proof-signal-head"><span>Reading cues</span><small>Presentation cues from Node fields</small></div>
    <ul>{signals.map((signal) => <li key={`${signal.label}-${signal.detail}`} className={`proof-signal proof-signal-${signal.tone}`}><span className="proof-signal-marker" aria-hidden="true" /><div><strong>{signal.label}</strong><p>{signal.detail}</p></div></li>)}</ul>
  </section>;
}

function ProofDetails({ details }: { details: ProofDetail[] }) {
  return <dl className="proof-detail-list">{details.map((detail) => <div key={`${detail.label}-${detail.value}`} className={detail.technical ? "is-technical" : ""}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}</dl>;
}
