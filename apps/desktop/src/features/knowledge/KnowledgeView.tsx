import { useEffect, useState } from "react";
import { fetchGraphReviewQueue, fetchKnowledgeStatus, ingestKnowledgeFolder, resolveGraphReview, searchKnowledge, type GraphReviewQueueResponse, type KnowledgeIngestResponse, type KnowledgeSearchResponse, type KnowledgeStatus } from "./knowledgeBridge";
import { uploadSelectedPidFile, type PidExtractionResponse } from "../intake/intakeBridge";
import { invoke } from "@airbench/tauri-invoke";
import { buildCreateTaskCommand } from "../tasks/taskComposer";
import { createTask } from "../../platform/node/nodeCommands";
import type { ApprovedNodeProfileReference } from "../../platform/node/nodeConnection";

export function KnowledgeView({ profile, nodeConnected, subject, domainPackRef }: { profile: ApprovedNodeProfileReference | null; nodeConnected: boolean; subject: string | null; domainPackRef: string | null; }) {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"text" | "graph" | "hybrid">("hybrid");
  const [result, setResult] = useState<KnowledgeSearchResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);
  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestResult, setIngestResult] = useState<KnowledgeIngestResponse | null>(null);
  const [pidBusy, setPidBusy] = useState(false);
  const [pidResult, setPidResult] = useState<PidExtractionResponse | null>(null);
  const [reviewQueue, setReviewQueue] = useState<GraphReviewQueueResponse | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewActionId, setReviewActionId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setStatus(null);
    setResult(null);
    setIngestResult(null);
    setReviewQueue(null);
    setMessage(null);
    if (!profile || !nodeConnected) {
      setStatusBusy(false);
      return () => { active = false; };
    }
    setStatusBusy(true);
    fetchKnowledgeStatus(profile)
      .then((value) => { if (active) setStatus(value); })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "Knowledge status is unavailable."); })
      .finally(() => { if (active) setStatusBusy(false); });
    return () => { active = false; };
  }, [profile, nodeConnected]);

  async function refreshReviewQueue() {
    if (!profile || !nodeConnected) return;
    setReviewBusy(true);
    try {
      setReviewQueue(await fetchGraphReviewQueue(profile));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The P&ID review queue is unavailable.");
    } finally {
      setReviewBusy(false);
    }
  }

  useEffect(() => {
    void refreshReviewQueue();
    // The queue is a Node projection; refresh whenever the approved profile changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile, nodeConnected]);

  async function submit() {
    if (!profile || !query.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      setResult(await searchKnowledge(profile, { query, mode, top_k: 8 }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Knowledge search failed.");
    } finally {
      setBusy(false);
    }
  }

  async function ingestFolder() {
    if (!profile) return;
    if (profile.transport !== "loopback") {
      setMessage("Bulk ingestion is disabled here because a remote Node cannot read a laptop folder path.");
      return;
    }
    setIngestBusy(true);
    setMessage(null);
    setIngestResult(null);
    try {
      const response = await ingestKnowledgeFolder(profile);
      setIngestResult(response);
      setStatus(await fetchKnowledgeStatus(profile));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Knowledge ingestion failed.");
    } finally {
      setIngestBusy(false);
    }
  }

  async function extractPid() {
    if (!profile || !subject || !domainPackRef) {
      setMessage("Cannot extract P&ID: Node identity or domain pack is missing.");
      return;
    }
    setPidBusy(true);
    setMessage(null);
    setPidResult(null);
    try {
      const selection = await invoke<{ selection_id: string } | null>("pick_query_file");
      if (!selection) return;

      const commandId = `command.create.${crypto.randomUUID()}`;
      const command = buildCreateTaskCommand({
        actor: subject,
        clearance: profile.clearanceContext,
        domainPackRef: domainPackRef,
        request: "Digitize P&ID into knowledge base",
        title: "P&ID Extraction",
        projectRef: null,
        outputContract: "knowledge_graph",
        priority: "normal",
        deadline: null,
        inputManifestRefs: [],
        inputKind: "file",
      }, commandId, `idempotency.${commandId}`);

      const taskResult = await createTask(profile, command);
      const taskId = taskResult.task.task_id;

      const response = await uploadSelectedPidFile(profile, selection.selection_id, taskId);
      setPidResult(response);
      setStatus(await fetchKnowledgeStatus(profile));
      await refreshReviewQueue();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setPidBusy(false);
    }
  }

  async function resolveReview(candidateId: string, accept: boolean) {
    if (!profile) return;
    setReviewActionId(candidateId);
    setMessage(null);
    try {
      await resolveGraphReview(profile, candidateId, accept);
      await refreshReviewQueue();
      setStatus(await fetchKnowledgeStatus(profile));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "The Node did not resolve this review item.");
    } finally {
      setReviewActionId(null);
    }
  }

  return <section className="record-gateway" aria-label="Knowledge base explorer">
    <header><p className="eyebrow">KNOWLEDGE BASE</p><h1>Search governed knowledge</h1><p className="lead">Text and image-derived evidence stays in the vector store, while P&amp;ID entities and relations stay in the world-model graph. Hybrid search shows both.</p></header>
    {!nodeConnected || !profile ? <section className="record-gateway-state record-gateway-state-node_unavailable" role="status"><strong>Connect an approved Node</strong><p>The desktop does not read or parse knowledge files locally.</p></section> : <>
      <section className="workspace-metrics" aria-label="Knowledge status" aria-busy={statusBusy || ingestBusy}><div><span>Node knowledge</span><strong>{statusBusy ? "Checking..." : humanizeToken(status?.status ?? "Unavailable")}</strong></div><div><span>Indexed chunks</span><strong>{status?.indexed_chunks ?? "Not supplied"}</strong></div><div><span>Graph</span><strong>{status?.graph ? "Available" : status ? "Not configured" : "Unavailable"}</strong></div></section>
      <section className="knowledge-ingest-card"><div><p className="eyebrow">CORPUS INGESTION</p><strong>Add an approved Node-visible corpus</strong><p>{profile.transport === "loopback" ? "Choose a folder on this workstation. The local Node will apply its intake, clearance, and provenance rules." : "Bulk ingestion is disabled for this remote profile because a laptop folder is not automatically visible to the Node. Provision the corpus on the Node or use the approved transfer workflow."}</p></div><button className="secondary-button" type="button" onClick={() => void ingestFolder()} disabled={ingestBusy || profile.transport !== "loopback"} title={profile.transport === "loopback" ? "Choose a local folder for the local Node" : "A remote Node cannot read a laptop path"}>{ingestBusy ? "Ingesting..." : profile.transport === "loopback" ? "Choose folder" : "Node folder required"}</button></section>
      <section className="knowledge-ingest-card"><div><p className="eyebrow">P&amp;ID EXTRACTION</p><strong>Digitize a P&amp;ID to the graph</strong><p>Upload a P&amp;ID image to extract its symbols and topological graph into the world model.</p></div><button className="secondary-button" type="button" onClick={() => void extractPid()} disabled={pidBusy}>{pidBusy ? "Extracting..." : "Upload P&ID"}</button></section>
      <section className="worktrace-detail-card" aria-label="P&ID graph review queue"><div className="worktrace-detail-head"><div><p className="eyebrow">GRAPH REVIEW</p><h2>Candidate facts awaiting review</h2><p>Low-confidence or ambiguous P&amp;ID candidates remain outside the committed graph until an operator decides.</p></div><div><span>{reviewQueue?.count ?? "—"} waiting</span><button className="text-button" type="button" onClick={() => void refreshReviewQueue()} disabled={reviewBusy}>{reviewBusy ? "Refreshing..." : "Refresh"}</button></div></div>{reviewQueue?.items.length ? <ul className="worktrace-question-list">{reviewQueue.items.map((item) => <li key={item.candidate_id}><div><strong>{item.fact_id}</strong><small>{item.reason} / {Math.round(item.confidence * 100)}% confidence / {item.clearance} clearance / {item.source_ref}</small><small>Queued {item.enqueued_at}</small></div><span><button className="secondary-button" type="button" onClick={() => void resolveReview(item.candidate_id, true)} disabled={reviewActionId !== null}>{reviewActionId === item.candidate_id ? "Saving..." : "Accept"}</button><button className="text-button" type="button" onClick={() => void resolveReview(item.candidate_id, false)} disabled={reviewActionId !== null}>Reject</button></span></li>)}</ul> : <div className="worktrace-empty">{reviewQueue ? "No P&ID candidates are waiting for a human decision." : "The Node has not returned the review queue yet."}</div>}<p className="worktrace-contract-note">Accept and reject decisions are authenticated by the Node and written to its append-only ledger with the operator identity.</p></section>
      <form className="composer" onSubmit={(event) => { event.preventDefault(); void submit(); }}><label htmlFor="knowledge-query">Question or entity</label><input type="search" id="knowledge-query" name="knowledge-query" aria-label="Question or entity" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. seal leakage or P-101" maxLength={4096} /><select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)} aria-label="Knowledge search mode"><option value="hybrid">Hybrid: text + graph</option><option value="text">Text and images</option><option value="graph">P&amp;ID graph</option></select><button className="primary-button" type="submit" disabled={busy || !query.trim()}>{busy ? "Searching..." : "Search knowledge"}</button></form>
      {message && <p role="alert" className="notice notice-error">{message}</p>}
      {ingestResult && <p className="notice">Indexed {ingestResult.file_count} file{ingestResult.file_count === 1 ? "" : "s"} and {ingestResult.chunk_count} chunk{ingestResult.chunk_count === 1 ? "" : "s"}. {ingestResult.failure_count ? `${ingestResult.failure_count} file${ingestResult.failure_count === 1 ? "" : "s"} need attention.` : "No file failures."}</p>}
      {result && <section className="worktrace-detail-card" aria-live="polite"><div className="worktrace-detail-head"><div><h2>Evidence returned</h2><p>{result.result_count} text/image results, {result.graph_result_count} graph facts</p></div><span>{humanizeToken(result.mode)} search</span></div>{result.result_count === 0 && result.graph_result_count === 0 ? <p className="record-gateway-empty">No governed evidence matched this question.</p> : <div className="workspace-activity">{result.results.map((item, index) => <article key={String(item.citation_id ?? item.chunk_id ?? `evidence-${index}`)}><strong>{String(item.excerpt ?? "Document evidence")}</strong><small>{readableSource(item)}, confidence {readableConfidence(item.confidence)}, {String(item.clearance)} clearance, {String(item.taint)} data</small></article>)}{result.graph_results.map((item, index) => <article key={String(item.fact_id ?? `graph-${index}`)}><strong>{readableGraphValue(item)}</strong><small>{readableSource(item)}, confidence {readableConfidence(item.confidence)}, {String(item.clearance)} clearance, {String(item.taint)} data, P&amp;ID graph</small></article>)}</div>}</section>}
    </>}
  </section>;
}

function readableSource(item: Record<string, unknown>): string {
  const source = item.source_ref ?? item.source_id ?? item.page_id ?? item.intake_id;
  const location = item.source_span ?? item.page_id;
  if (!source) return "Source unavailable";
  return location ? `Source: ${String(source)}, ${String(location)}` : `Source: ${String(source)}`;
}

function readableConfidence(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "Not supplied";
}

function readableGraphValue(item: Record<string, unknown>): string {
  const value = item.value;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const label = record.label ?? record.entity_id ?? record.name ?? record.value;
    if (typeof label === "string" || typeof label === "number") return String(label);
  }
  return "Graph fact";
}

function humanizeToken(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}
