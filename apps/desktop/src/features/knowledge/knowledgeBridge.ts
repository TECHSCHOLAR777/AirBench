import { invoke } from "@airbench/tauri-invoke";
import { toNativeNodeProfileReference } from "../../platform/node/nodeBridge";
import type { ApprovedNodeProfileReference } from "../../platform/node/nodeConnection";

export type KnowledgeMode = "text" | "graph" | "hybrid";

export interface KnowledgeStatus {
  configured: boolean;
  status: string;
  indexed_chunks?: number;
  vector_store?: string;
  graph?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface KnowledgeSearchResponse {
  query: string;
  mode: KnowledgeMode;
  clearance: string;
  result_count: number;
  graph_result_count: number;
  results: Array<Record<string, unknown>>;
  graph_results: Array<Record<string, unknown>>;
}

export interface KnowledgeIngestResponse {
  status: "completed" | "partial" | "failed";
  file_count: number;
  chunk_count: number;
  failure_count: number;
  files?: Array<Record<string, unknown>>;
  failures?: Array<Record<string, unknown>>;
}

function approved(profile: ApprovedNodeProfileReference) {
  if (!profile.approvedByPolicy) throw new Error("The Node profile is not approved by policy.");
  return toNativeNodeProfileReference(profile);
}

export async function fetchKnowledgeStatus(profile: ApprovedNodeProfileReference): Promise<KnowledgeStatus> {
  const value = await invoke<KnowledgeStatus>("fetch_knowledge_status", { ...approved(profile) });
  if (typeof value?.configured !== "boolean" || typeof value.status !== "string") throw new Error("The Node returned an invalid knowledge status.");
  return value;
}

export async function searchKnowledge(
  profile: ApprovedNodeProfileReference,
  request: { query: string; mode?: KnowledgeMode; top_k?: number; entity_id?: string; relation?: string; key?: string; max_depth?: number },
): Promise<KnowledgeSearchResponse> {
  if (!request.query.trim() || request.query.length > 4096) throw new Error("Knowledge search text is invalid.");
  const value = await invoke<KnowledgeSearchResponse>("search_knowledge", { profileId: profile.profileId, body: request });
  if (typeof value?.query !== "string" || !["text", "graph", "hybrid"].includes(value.mode)) throw new Error("The Node returned an invalid knowledge search.");
  if (!Array.isArray(value.results) || !Array.isArray(value.graph_results)) throw new Error("The Node returned invalid knowledge result lists.");
  return value;
}

export async function queryKnowledgeGraph(
  profile: ApprovedNodeProfileReference,
  request: { entity_id?: string; relation?: string; key?: string; max_depth?: number; limit?: number },
): Promise<{ result_count: number; facts: Array<Record<string, unknown>> }> {
  const value = await invoke<{ result_count: number; facts: Array<Record<string, unknown>> }>("query_knowledge_graph", { profileId: profile.profileId, body: request });
  if (!Number.isInteger(value?.result_count) || !Array.isArray(value.facts)) throw new Error("The Node returned an invalid knowledge graph response.");
  return value;
}

export async function ingestKnowledgeFolder(profile: ApprovedNodeProfileReference): Promise<KnowledgeIngestResponse> {
  const value = await invoke<KnowledgeIngestResponse>("ingest_knowledge_folder", { profileId: profile.profileId });
  if (!value || !["completed", "partial", "failed"].includes(value.status)) throw new Error("The Node returned an invalid knowledge ingestion status.");
  if (!Number.isInteger(value.file_count) || !Number.isInteger(value.chunk_count) || !Number.isInteger(value.failure_count)) {
    throw new Error("The Node returned an invalid knowledge ingestion summary.");
  }
  return value;
}
