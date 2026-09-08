# Model Qualification Framework

## Purpose

In a serious organization you do not just install a new piece of equipment, you qualify it for the job before you trust it, and you recheck it over time. AirBench does the same with models. A model is not simply added, it is tested and cleared for a specific job before it is allowed to do that job, and it is only ever used for the jobs it passed. This turns the multi model design from a technical feature into a process a cautious buyer can trust.

## Where it sits

Core engine. The tasks a model is tested on and the bar it must clear come from the domain pack and the organization's own evaluation set. It governs what Serving and Routing is allowed to do, and it records its certificates in the Memory and Audit Ledger.

## The qualification steps

Qualification runs in three stages, mirroring how equipment is qualified.

1. **Check the model itself.** Verify the model's signature and where it came from, confirm it is in a safe format, confirm its license, and confirm it loads and runs correctly in the sandbox. This is where a tampered or poisoned model is caught before it ever runs.

2. **Test it on the field's jobs.** Run the model against the organization's own evaluation set, job kind by job kind, for example summarizing, extracting, reasoning, or calculating. Score not only whether it is right, but whether it stays faithful to sources, whether it invents numbers, whether it respects constraints, and how it behaves when fed a document that tries to manipulate it. Attempt to break it deliberately.

3. **Watch it on real work before trusting it.** Run it alongside the current model on real tasks, with a human reviewing a sample, before it is promoted to live use.

Qualification is for an exact target, not a model family name. The target identity includes the model artifact hash, quantization, serving runtime, hardware profile, context window, prompt/tool contract, and domain-pack version. Changing any of these creates a new target that must be qualified again.

The qualification record supplies the router with a capability card: task kinds, modalities, tool permissions, minimum evidence quality, context limit, latency envelope, and risk classes for which the target may be selected. A target qualified for summarization is not automatically eligible for planning, coding, calculation, or tool use.

## What qualification produces

A signed certificate that records which model, which exact version, the specific job kinds it is cleared for, the scores it earned, who signed off, and when it must be rechecked. A model can be cleared for one job and not another, for example cleared to summarize but not to calculate.

The evaluation record also keeps paired results for routing calibration: tasks both models pass, tasks only the capable model passes, tasks only the efficient model passes, and tasks both fail. Routing thresholds are selected from these results for the organization's work, not copied from another benchmark.

## How it changes the running system

Two effects make this powerful rather than paperwork.

First, routing obeys qualification. Serving and Routing may only send a task to a model that holds a current certificate for that kind of task. So the system can honestly say nothing runs here that was not cleared for the exact job it is doing.

Second, qualification is not forever. A new model version, a change to the evaluation set, a drift signal from live use, or an incident triggers a recheck. A model that fails a recheck on a job kind is de qualified for that job and dropped from that route, and all of this is recorded.

## Why this is a framework

Because the tests come from the pack and the organization's own evaluation set, and the harness that runs them is shared, a new field qualifies its own models against its own bar without changing the engine. The same harness that qualifies models is the same evaluation harness the organization uses to measure quality, so building it pays off twice.

## Interfaces

Input: a candidate model and the job kinds it is proposed for.

Output: a signed qualification certificate scoping the model to specific jobs, or a rejection, recorded.

## Failure handling

A model that fails the integrity check never runs. A model that passes integrity but fails a job kind is simply not cleared for that job, while it may still be cleared for others. Passing qualification proves the model is fit and genuine, it does not prove it is flawless, so the quality of the evaluation set is what carries the weight, and the set is meant to grow as gaps are found.

A routing classifier that returns invalid or uncertain output is not allowed to select a weaker target; the deterministic router chooses the safer qualified target.

## What is core and what is pack

Core: the qualification steps, the certificate format, the routing enforcement, the recheck triggers, the shared harness.

Pack: the job kinds, the evaluation set, and the passing bar for the field.

## Qualification for worker roles and teams

A target is qualified for an exact worker capability, not merely for a broad task label. For example, qualification for `reasoning_worker` does not automatically qualify the same target for `verification_worker`, `code_worker`, or `vision_worker`. The certificate must name the role, task kinds, modality, tool contract, evidence quality floor, risk classes, context limit, and hardware profile.

Team execution adds an integration qualification layer. It tests that:

- worker assignments preserve source, confidence, clearance, and taint;
- handoff packets satisfy their schemas;
- workers cannot read or mutate peer context;
- the join barrier handles missing and conflicting packets;
- the independent verifier receives a fresh context;
- default-fail completion cannot be set by a model;
- tool and artifact provenance survives retries and compaction;
- parallel, pipelined, and serial modes preserve the same result contract;
- resource exhaustion produces queue, degradation, review, or stop rather than a silent safety reduction.

Team qualification does not make an unqualified target eligible. Every worker assignment still passes the normal target certificate and hardware admission gates.
