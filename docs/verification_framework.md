# Verification Framework

## Purpose

A well written answer can still be wrong in a way that matters. In a plant a number can be cited correctly and still break a physical limit. In a hospital a dose can read fluently and still be unsafe. The Verification Framework checks that an answer is valid by the rules of the field, not just that it is grounded in a document. This is the difference between AirBench and a chatbot that sounds right.

## Where it sits

Core engine. The framework is a runner for checks. The checks themselves come from the domain pack's field rules, so the same runner enforces engineering limits for a plant, dosage limits for a hospital, or exposure limits for a bank. It is called by the Orchestration Engine after steps and before a deliverable is finalized.

## What a check is

A check is an executable rule that takes a fact or a set of facts and returns pass, fail, or needs review, with a reason. Checks come in a few general families, and the pack fills each family with its field's specifics.

Checks consume typed `FactEnvelope` values or typed `UntrustedEvidence` references. A check result records the input fact IDs, rule version, evidence quality, confidence floor, and exact reason. A model-written assertion without a source or typed value is not a fact eligible for a passing domain check.

- **Unit and format checks.** A quantity carries the right unit, an identifier has the right shape, a value is the right type. Catches the most common silent errors.
- **Bound checks.** A value sits inside an allowed range, a design limit, a safe operating window, a policy threshold. The bounds come from the pack, often from the World Model Engine for a specific object.
- **Consistency checks against the world model.** A claimed fact agrees with the organization's own recorded reality. A claim that contradicts the world model is flagged, not used. This is also the main defense against a poisoned or wrong document quietly setting a value.
- **Cross fact checks.** A set of facts is internally coherent, for example a total equals its parts, or a set of steps respects an ordering rule.
- **Rule and standard checks.** The answer complies with a written rule of the field, for example a required clause is present, a required approval exists, a prohibited combination is absent.

## How it runs

The orchestrator hands the framework the facts a step produced and the kind of thing they are. The framework asks the pack which checks apply to that kind, runs them, and returns the combined result with reasons. A fail stops the step and feeds the orchestrator's retry and escalation path. A needs review routes to review. Numbers that will appear in a deliverable are computed in the sandbox, not authored as free text by a model, and the framework verifies the rendered values still match the computed source and still pass the bounds. Code execution results are checked against the sandbox manifest and declared tests before they become evidence.

## Why this is a framework, not a feature

Because the checks are supplied by the pack and run by a shared runner, adding a field means writing that field's checks, not changing the engine. A check is small, testable, and auditable on its own. The set of checks a deployment runs is itself part of what gets qualified and recorded, so an organization can prove which rules were enforced on a given deliverable.

## Interfaces

Input: facts to verify and their kind.

Output: pass, fail, or needs review, each with a reason, recorded in the Memory and Audit Ledger.

## Failure handling

A check that cannot run, for example because it needs a fact the world model does not have, returns needs review rather than a silent pass, because a skipped check is how an unsafe answer escapes. Confidence flows through: a check that relied on a low confidence fact returns a result carrying that low confidence, so the answer downstream never looks more certain than its weakest input.

## What is core and what is pack

Core: the check runner, the families of check types, the result handling, the number verification in deliverables.

Pack: the actual checks, the bounds, and which checks apply to which kinds of facts.
