# Consistency Engine

## Purpose

Every organization that makes repeated judgment calls builds up a history of past decisions, and the real value in that history is not copying it, it is staying consistent and catching drift. The Consistency Engine keeps the organization's decisions consistent over time, surfaces the relevant past ones when a new decision is being made, and flags when the organization is about to decide differently for no good reason.

This is deliberately not a "suggest a similar past answer" feature. That approach just repeats the organization's past mistakes with confidence. This engine is built to prevent that.

## Where it sits

Core engine. What a decision looks like in the field, the features that describe a case and the rule it cites, comes from the domain pack's decision types. It is called by the Orchestration Engine before a decision is finalized, and it reads and writes decision records through the Memory and Audit Ledger.

## What it records

Every decision the organization makes through the system becomes a structured record, not a blob of text. A record holds the features that describe the case, the decision that was made, the rule or authority it cited, who made it and at what level, and, when it later becomes known, the outcome, including whether it was ever overturned. Records are linked to the objects in the World Model Engine they concerned, so the system can find decisions about the same thing, not just decisions with similar wording.

## How it works

When a new decision is forming, the engine does three things that make it more than a lookup.

1. **Find genuinely comparable cases.** It retrieves past decisions about the same or similar objects and situations, using both the structured features and the links in the world model, not just text similarity.

2. **Distinguish.** For each comparable case, it surfaces how the current case differs, especially on any feature that matters for safety or compliance. A past decision that differs on a material point is not treated as binding. This is the step that stops a shallow match from becoming bad advice.

3. **Check authority and currency.** A past decision that the current rules have since overridden is marked superseded and is never cited as valid. A decision's weight also depends on who made it and whether its outcome was good. A past decision that led to a bad outcome is downweighted or flagged, not held up as precedent.

The first scope keeps this deliberately useful but bounded. It compares a new decision against a small set of structured, same-object or same-case records, checks that their cited rule and authority are still current, and explains material differences. Outcome capture is optional evidence rather than a trained weighting system, and the engine is advisory unless a domain-pack rule explicitly requires a deviation review.

The valuable behavior is the deviation flag. When the new decision differs from comparable past decisions and nothing material distinguishes them, the engine says so and asks for the deviation to be justified. This turns the system into an auditor of the organization's own consistency, which is exactly what internal review and regulators want.

## Why it actually compounds

It compounds because the structure grows, not because the pile of notes grows. Even the first bounded set of linked decision records can show whether a proposed decision concerns the same object, cites the same rule, and departs on a material feature. A later full version can add outcome-aware weighting and drift analytics; the first scope does not pretend that unobserved outcomes are reliable labels.

## Interfaces

Input: a forming decision, described in the pack's decision type.

Output: the comparable past decisions, how each differs, any superseded ones, and a deviation flag with the cases that triggered it. All recorded.

## Failure handling

It never asserts a precedent as binding on its own, it surfaces and flags for review. It guards against shallow matching through the distinguish step and checks currency before using a record. A decision with no known outcome is weak evidence, not strong evidence. The full outcome-aware and drift-detection behavior is deferred until the deployment has enough structured decision history.

## What is core and what is pack

Core: the decision record store, the comparison and distinguish logic, the authority and currency handling, the deviation flag, the links to the world model.

Pack: what a decision looks like in the field, which features matter, and how authority levels map.
