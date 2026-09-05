# Domain Pack Framework

## Purpose

The domain pack is what turns the general AirBench engine into a working assistant for one specific field, without touching the engine. It is the single boundary that makes AirBench a platform instead of a refinery tool. This document defines exactly what a pack contains, how the engine loads it, and the rule that keeps the boundary clean.

## The boundary rule

The core engine must contain zero sector knowledge. No physics assumption, no medical term, no financial rule, nothing field specific, ever lives in the engine. Everything a sector needs lives in its pack, behind this contract. If a pack cannot express something the sector needs, the fix is to widen the contract for all packs, not to special case the engine. This rule is what lets a new industry be a weekend of pack authoring rather than a fork of the product.

## What a pack contains

A pack is a signed bundle of declarations and assets. It has seven parts.

1. **World schema.** The definition of what the organization's world is made of: the object types, the link types between them, and which documents are the authoritative source for each. For a refinery this is equipment, tags, lines, and connections, sourced from diagrams. For a hospital it is patients, conditions, and medications. The World Model Engine reads this to know what graph to build. See `world_model_engine.md`.

2. **Document profiles.** The kinds of documents the field uses, how to recognize each, and which ingestion strategy each takes. This drives the Knowledge and Retrieval Engine's routing so the pack decides, by rule, what is a procedure versus a datasheet versus a report.

3. **Field rules.** The checks that decide whether an answer is valid beyond being well written, expressed as executable checks the Verification Framework can run. Dosage and interaction limits for a hospital, exposure limits for a bank, clause existence for a law office, engineering limits for a plant.

4. **Decision types.** What a decision looks like in this field, so the Consistency Engine can record and compare them: the features that describe a case, the rule a decision cites, and the authority level that made it.

5. **Risk model.** The mapping from an action to its worst case harm, its reversibility, and the human authority required for it, so the Autonomy Governor can grade autonomy by rule instead of by guess. This is where the pack encodes what counts as serious in the field.

6. **Deliverable templates.** The fixed shapes of the field's outputs, the approval note, the case summary, the credit memo, so the Deliverable Engine renders into a form the organization already trusts.

7. **Clearance and role model.** The classification tiers and roles of the field, mapped to the organization's own identity system, so retrieval and sign off respect need to know.

## What the engine provides, so the pack stays small

The pack author never writes plumbing. The engine already provides the sovereign runtime, the agent loop, the serving and routing, the memory and audit ledger, the retrieval mechanics, the check runner, the consistency bookkeeping, the autonomy scoring, and the qualification harness. The pack only supplies the field specific declarations above. A good pack is mostly configuration and a set of checks, not a codebase.

## How a pack is loaded

A pack is versioned and signed like a model. It is verified against a pinned key before it loads, so a tampered or unauthorized pack cannot run. Loading a pack registers its schema, profiles, rules, decision types, risk model, templates, and clearance model with the corresponding engine components. Two packs never share state. A single deployment normally runs one pack, since a deployment serves one organization.

## Interfaces

Input to the framework: a signed pack bundle.

Output: a set of registered declarations that each engine component reads at runtime. The framework exposes to the engine a stable set of lookups, for example "what object types exist," "what checks apply to this fact type," "what is the risk class of this action," and "what template does this deliverable use." The engine calls these lookups and never hard codes an answer.

## Failure handling

If a pack fails signature verification, it does not load and the system runs on the last good pack or refuses to start, with the failure recorded. If a pack declares something the engine cannot honor, the load fails loudly rather than silently ignoring it, because a silently half loaded pack is how a field rule gets skipped. A pack update is staged and qualified before it replaces the running pack, the same way a model is qualified, so a bad rule cannot reach production unreviewed.

## Why this is the most important design decision

Every novelty in AirBench, the world model, the field checks, the consistency engine, the risk graded autonomy, is only general because it reads from the pack instead of hard coding a sector. The pack contract is therefore the thing to design most carefully and change most slowly. Get it right and AirBench serves any regulated field. Get it wrong and every new customer becomes a rebuild.
