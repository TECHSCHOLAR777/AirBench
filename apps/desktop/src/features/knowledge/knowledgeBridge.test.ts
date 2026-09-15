import { beforeEach, describe, expect, it, vi } from "vitest";

const { invokeMock } = vi.hoisted(() => ({ invokeMock: vi.fn() }));
vi.mock("@airbench/tauri-invoke", () => ({ invoke: invokeMock }));

import { fetchGraphReviewQueue, resolveGraphReview, searchKnowledge, validateKnowledgeEvidence } from "./knowledgeBridge";
import type { ApprovedNodeProfile } from "../../platform/node/nodeConnection";

const profile: ApprovedNodeProfile = {
  profileId: "profile-1",
  displayName: "Plant Node",
  endpoint: "http://127.0.0.1:9443",
  transport: "loopback",
  nodeIdentity: "node-1",
  protocolVersion: "0.1",
  clearanceContext: "restricted",
  certificatePinSha256: null,
  trustedCaPem: null,
  credentialRef: "fixture-user",
  approvedByPolicy: true,
};

const evidence = {
  source_ref: "manual:inspection-sop:v3",
  confidence: 0.94,
  clearance: "restricted",
  taint: "clean",
  text: "Inspect the isolation valve before maintenance.",
};

describe("knowledge response boundary", () => {
  beforeEach(() => invokeMock.mockReset());

  it("accepts clearance-safe evidence and rejects incomplete provenance", () => {
    expect(validateKnowledgeEvidence(evidence, "restricted", "knowledge result")).toEqual(evidence);
    expect(() => validateKnowledgeEvidence({ ...evidence, source_ref: "" }, "restricted", "knowledge result")).toThrow(/source reference/);
    expect(() => validateKnowledgeEvidence({ ...evidence, clearance: "secret" }, "restricted", "knowledge result")).toThrow(/above the approved clearance/);
    expect(() => validateKnowledgeEvidence({ ...evidence, confidence: 1.5 }, "restricted", "knowledge result")).toThrow(/confidence/);
  });

  it("validates the complete search response before exposing it to the view", async () => {
    invokeMock.mockResolvedValueOnce({ query: "isolation valve", mode: "hybrid", clearance: "restricted", result_count: 1, graph_result_count: 1, results: [evidence], graph_results: [{ ...evidence, source_ref: "graph:valve-12" }] });
    await expect(searchKnowledge(profile, { query: "isolation valve", mode: "hybrid" })).resolves.toMatchObject({ result_count: 1, graph_result_count: 1 });
    expect(invokeMock).toHaveBeenCalledWith("search_knowledge", { profileId: "profile-1", body: { query: "isolation valve", mode: "hybrid" } });
  });

  it("rejects a response whose declared clearance or mode is unsafe", async () => {
    invokeMock.mockResolvedValueOnce({ query: "valve", mode: "text", clearance: "secret", result_count: 0, graph_result_count: 0, results: [], graph_results: [] });
    await expect(searchKnowledge(profile, { query: "valve", mode: "text" })).rejects.toThrow(/above the approved clearance/);

    invokeMock.mockResolvedValueOnce({ query: "valve", mode: "graph", clearance: "restricted", result_count: 0, graph_result_count: 0, results: [], graph_results: [] });
    await expect(searchKnowledge(profile, { query: "valve", mode: "text" })).rejects.toThrow(/invalid knowledge search/);
  });

  it("rejects malformed search controls before invoking the Node", async () => {
    await expect(searchKnowledge(profile, { query: "  " })).rejects.toThrow(/search text/);
    await expect(searchKnowledge(profile, { query: "valve", top_k: 0 })).rejects.toThrow(/result limit/);
    await expect(searchKnowledge(profile, { query: "valve", max_depth: 6 })).rejects.toThrow(/graph depth/);
    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("blocks a response whose declared count does not match its records", async () => {
    invokeMock.mockResolvedValueOnce({ query: "valve", mode: "text", clearance: "restricted", result_count: 2, graph_result_count: 0, results: [evidence], graph_results: [] });
    await expect(searchKnowledge(profile, { query: "valve" })).rejects.toThrow(/inconsistent knowledge result counts/);
  });

  it("validates the authenticated graph review queue and resolution", async () => {
    invokeMock.mockResolvedValueOnce({
      count: 1,
      items: [{ candidate_id: "candidate-1", fact_id: "fact-1", reason: "ambiguous tag", enqueued_at: "2026-01-01T00:00:00Z", confidence: 0.4, clearance: "restricted", source_ref: "upload:pid.png#page-1" }],
    });
    await expect(fetchGraphReviewQueue(profile)).resolves.toEqual({
      count: 1,
      items: [{ candidate_id: "candidate-1", fact_id: "fact-1", reason: "ambiguous tag", enqueued_at: "2026-01-01T00:00:00Z", confidence: 0.4, clearance: "restricted", source_ref: "upload:pid.png#page-1" }],
    });
    invokeMock.mockResolvedValueOnce({ candidate_id: "candidate-1", decision: "accept", fact_id: "fact-1" });
    await expect(resolveGraphReview(profile, "candidate-1", true)).resolves.toEqual({ candidate_id: "candidate-1", decision: "accept", fact_id: "fact-1" });
    expect(invokeMock).toHaveBeenLastCalledWith("resolve_graph_review", { profileId: "profile-1", body: { candidate_id: "candidate-1", accept: true } });
  });
});
