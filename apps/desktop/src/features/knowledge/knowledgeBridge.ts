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
  clearance: KnowledgeClearance;
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

export interface GraphReviewItem {
  candidate_id: string;
  fact_id: string;
  reason: string;
  enqueued_at: string;
  confidence: number;
  clearance: KnowledgeClearance;
  source_ref: string;
}

export interface GraphReviewQueueResponse {
  count: number;
  items: GraphReviewItem[];
}

type KnowledgeClearance = "public" | "internal" | "restricted" | "secret";
type KnowledgeTaint = "clean" | "untrusted" | "contaminated";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function requireReference(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim() || value.length > 512 || value.includes("\0")) {
    throw new Error(`The Node returned an invalid ${label} reference.`);
  }
  return value;
}

function requireKnowledgeClearance(value: unknown, approvedContext: string, label: string): KnowledgeClearance {
  const levels: KnowledgeClearance[] = ["public", "internal", "restricted", "secret"];
  if (!levels.includes(value as KnowledgeClearance) || !levels.includes(approvedContext as KnowledgeClearance)) {
    throw new Error(`The Node returned an invalid ${label} clearance.`);
  }
  if (levels.indexOf(value as KnowledgeClearance) > levels.indexOf(approvedContext as KnowledgeClearance)) {
    throw new Error(`The Node returned ${label} above the approved clearance.`);
  }
  return value as KnowledgeClearance;
}

function requireConfidence(value: unknown, label: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    throw new Error(`The Node returned an invalid ${label} confidence.`);
  }
  return value;
}

function requireKnowledgeTaint(value: unknown, label: string): KnowledgeTaint {
  if (value !== "clean" && value !== "untrusted" && value !== "contaminated") {
    throw new Error(`The Node returned an invalid ${label} taint.`);
  }
  return value;
}

function requireOptionalText(value: unknown, label: string, maximum: number): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "string" || value.length > maximum || value.includes("\0")) {
    throw new Error(`The Node returned an invalid ${label}.`);
  }
  return value;
}

function requireOptionalBoundedInteger(value: unknown, label: string, minimum: number, maximum: number): number | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < minimum || value > maximum) {
    throw new Error(`The knowledge ${label} is invalid.`);
  }
  return value;
}

function validateSearchRequest(request: { query: string; mode?: KnowledgeMode; top_k?: number; entity_id?: string; relation?: string; key?: string; max_depth?: number }): void {
  if (typeof request.query !== "string" || !request.query.trim() || request.query.length > 4096 || request.query.includes("\0")) {
    throw new Error("Knowledge search text is invalid.");
  }
  if (request.mode !== undefined && !["text", "graph", "hybrid"].includes(request.mode)) {
    throw new Error("Knowledge search mode is invalid.");
  }
  requireOptionalBoundedInteger(request.top_k, "result limit", 1, 20);
  requireOptionalBoundedInteger(request.max_depth, "graph depth", 0, 5);
  requireOptionalText(request.entity_id, "entity filter", 256);
  requireOptionalText(request.relation, "relation filter", 128);
  requireOptionalText(request.key, "graph key", 256);
}

export function validateKnowledgeEvidence(value: unknown, approvedContext: string, label: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`The Node returned an invalid ${label} record.`);
  requireReference(value.source_ref, `${label} source`);
  requireConfidence(value.confidence, label);
  requireKnowledgeClearance(value.clearance, approvedContext, label);
  requireKnowledgeTaint(value.taint, label);
  return value;
}

function approved(profile: ApprovedNodeProfileReference) {
  if (!profile.approvedByPolicy) throw new Error("The Node profile is not approved by policy.");
  return toNativeNodeProfileReference(profile);
}

export async function fetchKnowledgeStatus(profile: ApprovedNodeProfileReference): Promise<KnowledgeStatus> {
  const approvedProfile = approved(profile);
  const value = await invoke<unknown>("fetch_knowledge_status", { profileId: approvedProfile.profile_id });
  if (!isRecord(value) || typeof value.configured !== "boolean" || typeof value.status !== "string" || !value.status.trim()) {
    throw new Error("The Node returned an invalid knowledge status.");
  }
  if (value.indexed_chunks !== undefined) requireOptionalBoundedInteger(value.indexed_chunks, "indexed chunk count", 0, Number.MAX_SAFE_INTEGER);
  if (value.store_chunk_count !== undefined) requireOptionalBoundedInteger(value.store_chunk_count, "stored chunk count", 0, Number.MAX_SAFE_INTEGER);
  return value as KnowledgeStatus;
}

export async function searchKnowledge(
  profile: ApprovedNodeProfileReference,
  request: { query: string; mode?: KnowledgeMode; top_k?: number; entity_id?: string; relation?: string; key?: string; max_depth?: number },
): Promise<KnowledgeSearchResponse> {
  validateSearchRequest(request);
  const approvedProfile = approved(profile);
  const value = await invoke<unknown>("search_knowledge", { profileId: approvedProfile.profile_id, body: request });
  const requestedMode = request.mode ?? "text";
  if (!isRecord(value) || value.query !== request.query || value.mode !== requestedMode) throw new Error("The Node returned an invalid knowledge search.");
  const responseClearance = requireKnowledgeClearance(value.clearance, profile.clearanceContext, "search");
  if (!Array.isArray(value.results) || !Array.isArray(value.graph_results) || value.results.length > 100 || value.graph_results.length > 100) {
    throw new Error("The Node returned invalid knowledge result lists.");
  }
  if (!Number.isSafeInteger(value.result_count) || value.result_count !== value.results.length || !Number.isSafeInteger(value.graph_result_count) || value.graph_result_count !== value.graph_results.length) {
    throw new Error("The Node returned inconsistent knowledge result counts.");
  }
  const clearance = profile.clearanceContext;
  value.results.forEach((item, index) => validateKnowledgeEvidence(item, clearance, `knowledge result ${index + 1}`));
  value.graph_results.forEach((item, index) => validateKnowledgeEvidence(item, clearance, `knowledge graph result ${index + 1}`));
  return { ...value, clearance: responseClearance, mode: requestedMode } as unknown as KnowledgeSearchResponse;
}

export async function queryKnowledgeGraph(
  profile: ApprovedNodeProfileReference,
  request: { entity_id?: string; relation?: string; key?: string; max_depth?: number; limit?: number },
): Promise<{ result_count: number; facts: Array<Record<string, unknown>> }> {
  requireOptionalBoundedInteger(request.max_depth, "graph depth", 0, 5);
  requireOptionalBoundedInteger(request.limit, "result limit", 1, 200);
  requireOptionalText(request.entity_id, "entity filter", 256);
  requireOptionalText(request.relation, "relation filter", 128);
  requireOptionalText(request.key, "graph key", 256);
  const approvedProfile = approved(profile);
  const value = await invoke<unknown>("query_knowledge_graph", { profileId: approvedProfile.profile_id, body: request });
  if (!isRecord(value) || !Number.isSafeInteger(value.result_count) || !Array.isArray(value.facts) || value.result_count !== value.facts.length || value.facts.length > 200) {
    throw new Error("The Node returned an invalid knowledge graph response.");
  }
  value.facts.forEach((item, index) => validateKnowledgeEvidence(item, profile.clearanceContext, `knowledge graph fact ${index + 1}`));
  return value as unknown as { result_count: number; facts: Array<Record<string, unknown>> };
}

export async function ingestKnowledgeFolder(profile: ApprovedNodeProfileReference): Promise<KnowledgeIngestResponse> {
  const approvedProfile = approved(profile);
  const value = await invoke<unknown>("ingest_knowledge_folder", { profileId: approvedProfile.profile_id });
  if (!isRecord(value) || !["completed", "partial", "failed"].includes(String(value.status))) throw new Error("The Node returned an invalid knowledge ingestion status.");
  if (![value.file_count, value.chunk_count, value.failure_count].every((count) => Number.isSafeInteger(count) && (count as number) >= 0)) {
    throw new Error("The Node returned an invalid knowledge ingestion summary.");
  }
  if (value.files !== undefined && !Array.isArray(value.files)) throw new Error("The Node returned invalid ingested file records.");
  if (value.failures !== undefined && !Array.isArray(value.failures)) throw new Error("The Node returned invalid knowledge failure records.");
  return value as unknown as KnowledgeIngestResponse;
}

export async function fetchGraphReviewQueue(profile: ApprovedNodeProfileReference): Promise<GraphReviewQueueResponse> {
  const approvedProfile = approved(profile);
  const value = await invoke<unknown>("fetch_graph_review_queue", { profileId: approvedProfile.profile_id });
  if (!isRecord(value) || !Number.isSafeInteger(value.count) || (value.count as number) < 0 || !Array.isArray(value.items) || value.count !== value.items.length || value.items.length > 200) {
    throw new Error("The Node returned an invalid graph review queue.");
  }
  const items = value.items.map((item, index) => {
    if (!isRecord(item)) throw new Error(`The Node returned an invalid graph review item ${index + 1}.`);
    const candidateId = requireReference(item.candidate_id, `graph review candidate ${index + 1}`);
    const factId = requireReference(item.fact_id, `graph review fact ${index + 1}`);
    const reason = requireOptionalText(item.reason, `graph review reason ${index + 1}`, 4096);
    const enqueuedAt = requireOptionalText(item.enqueued_at, `graph review time ${index + 1}`, 128);
    const sourceRef = requireReference(item.source_ref, `graph review source ${index + 1}`);
    const confidence = requireConfidence(item.confidence, `graph review ${index + 1}`);
    const clearance = requireKnowledgeClearance(item.clearance, profile.clearanceContext, `graph review ${index + 1}`);
    if (!reason || !enqueuedAt) throw new Error(`The Node returned incomplete graph review item ${index + 1}.`);
    return { candidate_id: candidateId, fact_id: factId, reason, enqueued_at: enqueuedAt, confidence, clearance, source_ref: sourceRef };
  });
  return { count: items.length, items };
}

export async function resolveGraphReview(profile: ApprovedNodeProfileReference, candidateId: string, accept: boolean): Promise<{ candidate_id: string; decision: "accept" | "reject"; fact_id: string | null }> {
  const normalizedCandidateId = requireReference(candidateId, "graph review candidate");
  const approvedProfile = approved(profile);
  const value = await invoke<unknown>("resolve_graph_review", {
    profileId: approvedProfile.profile_id,
    body: { candidate_id: normalizedCandidateId, accept },
  });
  if (!isRecord(value) || value.candidate_id !== normalizedCandidateId || (value.decision !== "accept" && value.decision !== "reject") || (value.fact_id !== null && typeof value.fact_id !== "string")) {
    throw new Error("The Node returned an invalid graph review decision.");
  }
  return value as { candidate_id: string; decision: "accept" | "reject"; fact_id: string | null };
}
