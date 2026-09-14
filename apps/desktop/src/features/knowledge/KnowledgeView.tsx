import { useEffect, useState } from "react";
import { fetchKnowledgeStatus, ingestKnowledgeFolder, searchKnowledge, type KnowledgeIngestResponse, type KnowledgeSearchResponse, type KnowledgeStatus } from "./knowledgeBridge";
import type { ApprovedNodeProfileReference } from "../../platform/node/nodeConnection";

export function KnowledgeView({ profile, nodeConnected }: { profile: ApprovedNodeProfileReference | null; nodeConnected: boolean }) {
  const [status, setStatus] = useState<KnowledgeStatus | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"text" | "graph" | "hybrid">("hybrid");
  const [result, setResult] = useState<KnowledgeSearchResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);
  const [ingestBusy, setIngestBusy] = useState(false);
  const [ingestResult, setIngestResult] = useState<KnowledgeIngestResponse | null>(null);

  useEffect(() => {
    let active = true;
    if (!profile || !nodeConnected) {
      setStatus(null);
      setResult(null);
      setMessage(null);
      setStatusBusy(false);
      return () => { active = false; };
    }
    setStatusBusy(true);
    setMessage(null);
    fetchKnowledgeStatus(profile)
      .then((value) => { if (active) setStatus(value); })
      .catch((error) => { if (active) setMessage(error instanceof Error ? error.message : "Knowledge status is unavailable."); })
      .finally(() => { if (active) setStatusBusy(false); });
    return () => { active = false; };
  }, [profile, nodeConnected]);

  async function submit() {
    if (!profile || !query.trim()) return;
    setBusy(true); setMessage(null);
    try { setResult(await searchKnowledge(profile, { query, mode, top_k: 8 })); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Knowledge search failed."); }
    finally { setBusy(false); }
  }

  async function ingestFolder() {
    if (!profile) return;
    setIngestBusy(true);
    setMessage(null);
    setIngestResult(null);
    try {
      const response = await ingestKnowledgeFolder(profile);
      setIngestResult(response);
      const refreshed = await fetchKnowledgeStatus(profile);
      setStatus(refreshed);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Knowledge ingestion failed.");
    } finally {
      setIngestBusy(false);
    }
  }

  return <section className="record-gateway" aria-label="Knowledge base explorer">
    <header><p className="eyebrow">KNOWLEDGE BASE</p><h1>Search governed knowledge</h1><p className="lead">Text and image-derived evidence stays in the vector store; P&amp;ID entities and relations stay in the world-model graph. Hybrid search shows both.</p></header>
    {!nodeConnected || !profile ? <section className="record-gateway-state record-gateway-state-node_unavailable" role="status"><strong>Connect an approved Node</strong><p>The desktop does not read or parse knowledge files locally.</p></section> : <>
      <section className="workspace-metrics"><div><span>Node knowledge</span><strong>{statusBusy ? "Checking…" : status?.status ?? "Unavailable"}</strong></div><div><span>Indexed chunks</span><strong>{status?.indexed_chunks ?? "—"}</strong></div><div><span>Graph</span><strong>{status?.graph ? "Ready" : status ? "Not configured" : "Unavailable"}</strong></div></section>
      <section className="knowledge-ingest-card"><div><p className="eyebrow">CORPUS INGESTION</p><strong>Add an approved local corpus</strong><p>Select the configured knowledge folder through the native picker. Files remain governed by the Node’s intake, clearance, and provenance rules.</p></div><button className="secondary-button" type="button" onClick={() => void ingestFolder()} disabled={ingestBusy}>{ingestBusy ? "Ingesting…" : "Choose folder"}</button></section>
      <form className="composer" onSubmit={(event) => { event.preventDefault(); void submit(); }}><label htmlFor="knowledge-query">Question or entity</label><input type="search" id="knowledge-query" name="knowledge-query" aria-label="Question or entity" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. seal leakage or P-101" /><select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)} aria-label="Knowledge search mode"><option value="hybrid">Hybrid: text + graph</option><option value="text">Text and images</option><option value="graph">P&amp;ID graph</option></select><button className="primary-button" type="submit" disabled={busy || !query.trim()}>{busy ? "Searching…" : "Search knowledge"}</button></form>
      {message && <p role="alert" className="notice notice-error">{message}</p>}
      {ingestResult && <p className="notice">Indexed {ingestResult.file_count} file{ingestResult.file_count === 1 ? "" : "s"} and {ingestResult.chunk_count} chunk{ingestResult.chunk_count === 1 ? "" : "s"}. {ingestResult.failure_count ? `${ingestResult.failure_count} file${ingestResult.failure_count === 1 ? "" : "s"} need attention.` : "No file failures."}</p>}
      {result && <section className="worktrace-detail-card"><div className="worktrace-detail-head"><div><h2>Evidence returned</h2><p>{result.result_count} text/image results · {result.graph_result_count} graph facts</p></div></div>{result.result_count === 0 && result.graph_result_count === 0 ? <p className="record-gateway-empty">No governed evidence matched this question.</p> : <div className="workspace-activity">{result.results.map((item, index) => <article key={String(item.citation_id ?? item.chunk_id ?? `evidence-${index}`)}><strong>{String(item.excerpt ?? "Document evidence")}</strong><small>{readableSource(item)} · confidence {String(item.confidence ?? "—")} · {String(item.taint ?? "untrusted")}</small></article>)}{result.graph_results.map((item, index) => { const value = item.value as Record<string, unknown> | undefined; return <article key={String(item.fact_id ?? `graph-${index}`)}><strong>{String(value?.label ?? value?.entity_id ?? "Graph fact")}</strong><small>{readableSource(item)} · confidence {String(item.confidence ?? "—")} · P&amp;ID graph</small></article>; })}</div>}</section>}
    </>}
  </section>;
}

function readableSource(item: Record<string, unknown>): string {
  const source = item.source_ref ?? item.source_id ?? item.page_id ?? item.intake_id;
  return source ? `Source: ${String(source)}` : "Source unavailable";
}
