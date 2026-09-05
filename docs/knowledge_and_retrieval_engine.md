# Knowledge and Retrieval Engine

## Purpose

This engine is how the organization's documents become usable knowledge and how the system finds the right facts when working. It covers two halves: getting documents in and indexed, and getting the right pieces back out at work time with their sources.

## Where it sits

Core engine. What counts as a document type and how each is handled is declared by the domain pack. It writes into the stores and feeds the World Model Engine the authoritative documents. It is called by the Orchestration Engine as a tool during work.

## Ingestion, getting documents in

All file parsing and understanding happens in the shared File Intake Layer, not here, so that bulk ingestion and query time uploads read files through exactly the same machinery and can never drift apart. See `file_intake_layer.md`. This engine is the bulk caller of that layer, setting the destination to the permanent stores. What follows is what this engine does with the layer's output.

1. **Call the intake layer.** The engine hands each file to the File Intake Layer with the bulk switches: permanent destination, trusted persistence, and the heavier offline enrichment profile. The layer returns the parsed, structured content and a manifest. The manifest is the document's identity, type, version, effective date, source and how trusted it is, clearance, and a fingerprint for duplicates, and it drives everything downstream.

2. **Route by strategy.** A rule over the manifest picks one of a small fixed set of handling strategies. Clean text is chunked by section with surrounding context kept, keeping tables whole and never splitting a value from its unit. Scanned or visually complex pages are handled as images. Authoritative documents are also sent to the World Model Engine to build the graph.

3. **Store.** Text pieces and image pages are indexed for search, each carrying the manifest's source, clearance, and version. Everything is written through the Memory and Audit Ledger.

Versioning, provenance, and consistency are first class. A new version marks the old one superseded so nothing cites a dead document. User added or system generated documents enter only through a confirmation gate, tagged lower trust. Deleting a document creates an immutable tombstone and removes its pieces and graph nodes from the current projections in one transaction. A file uploaded during a query is parsed by the same File Intake Layer but with the session switches, so it stays scoped to that task unless promoted here through the gate.

The first local connector is a controlled directory or removable-media import with stable source IDs and revision fingerprints. The connector imports source metadata and hands files to the File Intake Layer; it does not parse files itself. Connectors for document-management systems, mail exports, and network shares are future extensions and must use the same interface.

## Retrieval, getting facts back

Retrieval runs when the Orchestration Engine needs facts during work.

1. **Understand and scope.** The request is checked against the user's clearance first, and simple lookups are separated from questions that need several parts pulled together.

2. **Search.** Meaning based search and exact keyword search run together and are combined, because exact identifiers only match on keywords while concepts match on meaning. Results are filtered to the current version and the user's clearance inside the search itself, not after.

3. **Structured questions go to the world model.** Anything about how things connect or depend on each other is answered by the World Model Engine, since plain search cannot follow those links.

4. **Rerank and return.** The combined results are reordered by true relevance and the surrounding section is returned, not just the matching line. Every returned fact carries its source and confidence.

5. **Honesty.** If nothing clears the relevance bar, the engine returns that the answer is not in the knowledge base rather than forcing a weak match. This is a feature, not a failure.

## The rule that keeps it fast and safe

Retrieval returns typed evidence references. A result is either `UntrustedEvidence` or a trusted `FactEnvelope` reference, with source, confidence, clearance, version, and provenance intact. Retrieval cannot turn an uploaded document into an instruction or silently upgrade its trust.

Models are used offline during ingestion to enrich pieces, and at work time only to understand a hard question, to rerank, and to write the final answer. Models are never put in the middle of the retrieval loop, because that would make retrieval slow, non repeatable, and exposed to manipulation.

## Interfaces

Input: documents to ingest, and search requests carrying the user's clearance.

Output: indexed knowledge, and search results carrying source, confidence, version, and clearance.

## Failure handling

A document that will not parse goes to a review queue, never a silent drop, because a customer notices immediately when a file is missing. Low confidence extractions are flagged. A retrieved document that came from an untrusted source is labeled so the rest of the system treats it as data, never as instructions.

## What is core and what is pack

Core: the parser, the manifest, the strategy runner, the search and rerank mechanics, the version and clearance handling.

Pack: the document profiles, which documents are authoritative, and the clearance model.

## Harness access

Research, reasoning, and verification workers access knowledge through clearance-filtered retrieval requests. The Knowledge and Retrieval Engine returns typed evidence references and bounded excerpts with source, confidence, clearance, and taint intact.

Workers cannot bypass retrieval controls by reading the index or document store directly. A team may run independent searches, but every query, result set, reranking decision, and evidence handoff is recorded and remains subject to the same clearance and provenance gates.
