# Autonomy Governor

## Purpose

The Autonomy Governor decides, for each action, how much the system may do on its own and when it must stop and hand off to a human. It replaces the crude idea of two buckets, safe and unsafe, with an honest, rule based judgment that any field can trust.

## Where it sits

Core engine. How an action maps to harm, reversibility, and required authority comes from the domain pack's risk model. It is called by the Orchestration Engine before an action is taken or a decision finalized, and it records its reasoning through the Memory and Audit Ledger.

## The three honest questions

For any proposed action the governor answers three questions and combines them.

1. **How bad is it if this is wrong.** The worst case harm of the action, taken from the pack's risk model and, where relevant, from the object in the world model the action touches. Acting on a critical system is high harm by rule, regardless of how routine it looks.

2. **Can it be undone.** Reversibility. An action that can be easily reversed is safer to do alone than one that cannot.

3. **How sure is the system.** Calibrated confidence, drawn from the external checks, the retrieval confidence, and the agreement between models. Crucially, uncertainty is treated as a reason to escalate, not to guess. A low confidence action on something important is treated as high risk.

## What it produces

Not a yes or no gate, but a graded requirement. The higher harm, irreversibility, and uncertainty climb together, the higher the level of human authority required and the more independent checks demanded before the action proceeds. Low harm, reversible, and confident means the system may act alone. Anything serious routes to the right level of human, with the required checks attached.

## The two rules that make it trustworthy

First, the system does not grade its own risk by feeling. The harm and the required authority are set by the pack's rules tied to the kind of action and the object involved. The model may propose an action, but it never certifies that its own action is low risk. This closes the obvious hole where a model waves through something dangerous.

Second, every decision produces a recorded reason. For each action the governor writes why it allowed the system to proceed alone, or why it escalated and to whom, in plain terms: low harm, reversible, high confidence, no special authority needed, or, high harm on a critical object, escalated to this authority. That recorded reason is itself an audit artifact the organization can show a regulator.

## Why this is a framework, not a setting

Because the risk mapping lives in the pack and the scoring logic lives in the engine, a new field defines what is serious for it without changing the engine. A refinery, a hospital, and a bank each supply their own risk model, and the same governor grades autonomy consistently across all of them. The set of rules in force is recorded, so an organization can prove what governed a given action.

## Interfaces

Input: a proposed action, its kind, and the objects it touches, plus the current confidence signals.

Output: allow alone, or escalate to a named authority level, with the required checks and the recorded reason.

## Failure handling

When the governor cannot score an action confidently, it escalates rather than allowing it, because unknown risk is treated as high risk. If the pack's risk model has no entry for an action kind, the action is treated as serious and escalated by default, so a gap in the pack fails safe rather than open.

## What is core and what is pack

Core: the three question scoring, the graded authority output, the self certification block, the recorded reasoning, the fail safe defaults.

Pack: the mapping from action kinds and objects to harm, reversibility, and required authority.
