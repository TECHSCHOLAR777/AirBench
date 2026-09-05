# World Model Engine

## Purpose

Most private AI systems treat the organization's documents as a pile of text to search. The World Model Engine does something different. It reads the organization's authoritative records and builds a structured, connected, queryable picture of that organization's actual world, so the assistant reasons over real linked facts instead of guessing from paragraphs.

This is AirBench's version of an ontology, but it is not hand modeled by consultants over months. It is built automatically from the organization's own documents, and it remembers how that world changed over time.

## Where it sits

Core engine. The shape of the world it builds is defined entirely by the domain pack's world schema, so the same engine builds an equipment graph for a plant, a patient graph for a hospital, or a contract graph for a law office. It feeds the Orchestration Engine and the Verification Framework with structured answers, and it is one of the two things retrieval can draw on, the other being plain document search.

## What it produces

A property graph. Objects are the things in the field, for example a valve, a patient, an account, or a contract. Links are the real relationships, for example connects to, is prescribed, is exposed to, or supersedes. Every object and link carries the source it came from, a confidence score, a clearance label, and time information. The engine serves questions over this graph that plain text search cannot answer, for example what is downstream of this thing, what depends on this, or what changed since a date.

For the first scope this is a bounded evidence graph, not an attempt to infer the whole organization. The domain pack supplies a small set of object and link types, and extraction begins with explicit identifiers and high-value relationships. The graph earns its USP by answering linked and time-scoped questions that text search cannot answer; it does not need unrestricted ontology induction to be useful.

## How it works

1. **Extraction.** Authoritative documents are turned into graph fragments. The pack says which documents are authoritative and what objects and links to look for. The first scope uses typed text/table evidence and explicit identifiers. The later drawing pipeline may supply graph fragments through the same interface. The engine does not care how a fragment was produced, only that it arrives typed, sourced, clearance-labelled, and confidence-bearing.

2. **Reconciliation.** New fragments are merged into the existing graph using stable identifiers, source revision, effective date, and pack-declared authority. When a new fragment conflicts with what is already there, the engine does not overwrite. It records the new fact and marks the old one as superseded, keeping both. Ambiguous identity matches and low-confidence conflicts remain unresolved and are flagged for review rather than applied silently.

3. **Time.** Every fact carries three kinds of time: when the change was true in the real world, when the system learned it, and which document revision introduced it. This lets the engine answer what the world looked like at any past moment, which matters for any investigation after the fact.

4. **Serving.** The engine answers structured queries for the rest of the system: a bounded traversal, dependency question, or point-in-time question. It returns the matching objects and links as evidence-bearing records, with the query path and weakest relevant confidence visible downstream. A graph answer is advisory unless a domain rule explicitly makes that graph fact a required check.

## The forward looking part

The graph is not just a static map, it is the organization's long term structured memory of its own world, and its value compounds because three things build on it.

First, it is the substrate the Verification Framework checks against. A claim that contradicts the world model is caught, not because a model doubted it, but because it disagrees with the organization's own recorded reality.

Second, it is what the Consistency Engine hangs decisions on. Past decisions are linked to the objects they concerned, so the system can find not just similar text but decisions about the same thing.

Third, because it is time aware, it becomes an investigation tool in its own right. After an incident, the organization can ask the graph to reconstruct exactly what it believed about the affected objects at the time, with the sources.

None of this needs model retraining. The intelligence lives in the structured, sourced, time aware graph, which is auditable and can be corrected, not baked into weights that cannot be inspected.

## Interfaces

Input: typed graph fragments from extractors, each with source, confidence, clearance, and time.

Output: answers to structured queries, each carrying confidence and respecting the caller's clearance. Every write goes through the Memory and Audit Ledger so the graph's history is itself provable.

## Failure handling

Extraction is never trusted blindly. Low confidence fragments and conflicting reconciliations go to human review, and human corrections become the record and also improve the extractors. A query that would rely on a fact above the caller's clearance returns without it rather than leaking. If the graph cannot answer confidently, it says so, so the caller can fall back to document search or to a human.

## What is core and what is pack

Core: the graph store, the reconciliation logic, the time model, the query serving, the confidence and clearance handling, the human review loop.

Pack: what the objects and links are, which documents are authoritative, and what the extraction targets are.

## Harness access

Worker teams query the World Model Engine through typed, clearance-filtered interfaces. They receive facts and graph fragments with confidence, source, valid time, and clearance. Workers cannot mutate the world model directly.

A proposed graph change becomes a candidate fact or fragment and follows the same provenance, consistency, verification, and ledger gates as any other write. Parallel workers may produce independent candidates, but only the orchestrator and the owning engine can commit a state transition.
