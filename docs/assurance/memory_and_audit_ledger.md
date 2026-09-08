# Memory and Audit Ledger

## Purpose

This is the system's long term memory and its record of everything it did, and it is one thing, not two. Every fact the system learns and every action it takes is written here in a way that cannot be quietly changed, so the organization can both remember and prove. It is the substrate that makes AirBench's promise of proving every step real.

## Where it sits

Core engine. Every other part writes to it: the World Model Engine's facts, the Knowledge Engine's documents, the orchestrator's steps, the router's choices, the checks, the decisions, the autonomy calls, the human sign offs. Sovereignty and Security builds its proofs on top of it. What is sensitive and who may read what comes from the domain pack's clearance model.

## The core rule: nothing is ever mutated

No audit write is an overwrite. Updating or deleting is done by adding a new record that supersedes or tombstones the old one, and the old event stays in the audit history. Search indexes, graph views, and current knowledge views are rebuildable projections over that history; they may remove a deleted item from the current view without erasing the evidence that the deletion happened. This is how the system can reconstruct what it knew and did at any past moment without pretending that every serving index is itself immutable.

All related writes share a transaction ID. An ingestion event, its parsed evidence, graph projection, search projection, and audit event either publish a consistent committed version or remain pending and visible as incomplete. Projection repair is safe because projections are derived from the immutable event stream.

## What every record carries

Each record carries who or what wrote it, which model or tool or human, and with which version, what it was derived from, the sources it came from, when it happened, and its clearance. A model-call event includes the target hash, route decision, prompt/context manifest, response hash, and tool contract. A fact event includes its `FactEnvelope` or evidence reference. Records are chained so that any insertion, deletion, or reordering after the fact is detectable. The first scope uses a verifiable append-only chain and signed exports; hardware-backed key custody and continuous independent attestation are deferred.

## The kinds of memory it holds

- **World facts.** The structured picture from the World Model Engine, with its full history over time.
- **Decisions.** The records the Consistency Engine compares against.
- **Procedures.** How a task was successfully done, captured only from runs that passed their checks and were signed by a human, so a proven good way of doing a task can be replayed. A captured procedure is tied to the document and rule versions it was validated against, and is flagged for recheck when those change.
- **Working notes.** The plan, results, and lesson notes the orchestrator feeds back during a task.
- **The audit trail.** Every step, call, check, decision, and approval.

## Defending the memory itself

Memory is a target. A poisoned fact written once can mislead every later task, and this is a real attack, not a theoretical one. So writes are untrusted until cleared. A candidate fact is only promoted to trusted memory if its source chain is clean, from a signed document, a verified tool result, or a human sign off, and if it does not contradict the world model. A fact derived only from a user conversation is marked low trust and cannot alter procedures or the world model on its own. Because every write is signed and kept, a poisoned entry is also traceable and reversible: you can find which session introduced it and undo everything that flowed from it.

## Reading with clearance

The same store serves everyone, but reads are filtered by clearance at the moment of reading, so a shift operator, a senior engineer, and an auditor see different subsets of one shared memory. This is how the organization keeps a single institutional memory that survives staff turnover without leaking across clearance lines.

## Interfaces

Input: signed, sourced, clearance labeled writes from every engine.

Output: the current view for a given clearance, point in time reconstructions, and a replayable, verifiable audit trail.

## Failure handling

Because it is append only, storage grows and never shrinks, so it uses periodic signed snapshots and tiered cold storage to stay manageable, and it never drops a high consequence record. A write that fails its provenance gate is quarantined, not silently stored. The ledger records a poisoned write too, which is why the provenance gate on writes matters as much as the record itself. Retention and secure erasure rules for full production deployments are deferred and must cover projections, caches, and backups, not only the primary store.

## What is core and what is pack

Core: the append only store, the chaining and sealing, the provenance gate, the clearance filtered reads, the snapshotting.

Pack: the clearance model and what counts as sensitive.

## Sessions, teams, and handoffs

The ledger is also the authoritative session history for the AirBench Harness. It records task, team, worker, stage, and parent-child relationships for every execution. A worker's private context and scratch directory are temporary; they are not authoritative memory.

Team and worker events include:

- TaskEnvelope and TeamPlan versions;
- worker assignments, role, target, and hardware lease;
- context manifests and compaction input/output manifests;
- WorkPacket and handoff hashes;
- join barriers, missing packets, and disagreements;
- tool proposals, tool results, and sandbox manifests;
- verification, evaluator, retry, cancellation, and completion events;
- artifact revisions and evidence-package hashes.

Every handoff preserves source, confidence, clearance, and taint for each fact. A worker cannot pass a fact through an informal peer channel or replace an earlier packet. Handoffs are immutable records with explicit supersession when a later checked result replaces them.

The harness rebuilds context from committed ledger state and verified packets after a restart or compaction. It never treats a model-generated conversation summary as the authoritative task state. Ledger failure prevents the next consequential transition or tool action from being committed.
