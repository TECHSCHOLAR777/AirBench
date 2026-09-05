# Sovereignty and Security

## Purpose

The core promise of AirBench is that the organization's data never leaves its walls, and that this can be proven, not just claimed. This layer enforces that promise, defends the system against manipulation and misuse, and produces the evidence an auditor needs.

## Where it sits

Core engine, cutting across everything. It builds its proofs on the Memory and Audit Ledger, constrains the sandbox the tools run in, and reads the clearance model from the domain pack.

## Sovereignty, made provable not asserted

The claim that nothing leaves is enforced in two ways and proven continuously.

**Enforcement.** The parts of the system that run code and read untrusted documents have no network path out at all, not a blocked one, an absent one. A missing way out cannot leak, while a firewall rule can be misconfigured and no one notices. This is enforced at the operating system level, and observed separately as evidence.

**First-scope proof.** The deployment records local process/model identities, audit-head references, and the results of explicit no-egress checks in the tamper-evident ledger. An offline verifier can replay the local trace. **Full-deployment proof** adds an independently observed, continuously signed machine-state and egress record; that requirement is deferred and recorded in `future_full_fledged_must_have.md`.

## One way ingestion

Untrusted documents enter through a one way path into an isolated space that has no way out, where they are read, parsed, and screened for hidden instructions. Only clean, structured, sourced data crosses back into the trusted side, never raw document text carrying live instructions. This makes a document that tries to trigger data exfiltration structurally unable to, rather than merely watched.

## Defending against manipulation

The main attack on a system like this is not breaking in, it is feeding it a document that manipulates it, or poisoning what it remembers.

- **Instructions in documents are never obeyed.** Everything the system reads is treated as data, never as a command. Models may inspect `UntrustedEvidence`, including OCR text and tables, but it is not placed in the instruction or policy channel. Model output is a proposal. Only the orchestrator can create a `ToolAction`, and every action is checked against the task policy, tool schema, path allowlist, clearance, evidence taint, and autonomy gate before execution. Evidence cannot add tools, permissions, plan steps, or authority.
- **Memory writes are gated.** As covered in the ledger spec, a fact only becomes trusted memory if its source is clean and it does not contradict the world model, which defeats slow poisoning.
- **Tools run under least privilege in a strong sandbox.** The code tool runs with no network in an isolated environment, and the system is given the narrowest set of tools that does the job, because every capability is attack surface. The first code-sandbox contract is a pinned runtime/image, non-root execution, read-only input mounts, an isolated writable scratch directory, no host sockets, no package installation, CPU/RAM/disk/process/time limits, restricted system calls, and a captured input/output manifest. Generated code is not trusted merely because it came from a qualified coder model.

## The model supply chain

A downloaded open model can carry a hidden backdoor, and this is cheap to do. So a model is verified before it runs, its signature and origin checked, its format confirmed safe, and only a model whose fingerprint matches a qualified, signed record is allowed to load. The running model's identity is folded into the local audit evidence; a continuous independently attested model-identity record is a future hardening requirement.

## Tool authority contract

The model is never the security principal for a tool. The orchestrator creates a `ToolAction` only after validating:

- the action type is in the task's immutable `TaskPolicy`;
- every input has a source, clearance, and taint label;
- file paths resolve inside the task workspace or an explicit read-only source mount;
- the action's risk and autonomy requirement have passed;
- resource limits and timeout are present; and
- the action has an idempotency key and an expected output schema.

The execution service then applies the policy independently. It does not receive the model's raw prompt and it does not interpret natural-language tool instructions. It returns a typed result, exit status, resource usage, artifact hashes, and provenance references. A result can be evidence for the next step, but it cannot grant new authority.

The code tool's first-scope environment is fixed and disposable: pinned image and runtime, non-root user, read-only inputs, isolated writable scratch, no network or host sockets, no package installation, bounded CPU/RAM/disk/process/time, restricted system calls, and captured stdout/stderr. Spreadsheet and file tools use the same path and provenance controls even when they do not execute arbitrary code.

## Access from the inside

The worst failure is a leak from inside, because it looks authorized. Access is decided by attributes at the moment of a request, the user's clearance and need to know against the item's labels, not by coarse roles, and it is enforced at the moment facts are retrieved and again when an output is produced, not just when a document is opened. The system must never become a channel that launders a secret into an output for someone not cleared to see it.

## An honest limit

The hardware level confidential computing and independent offline attestation features that strengthen this layer are real but off the common path and depend on the hardware vendor's tooling, some of which prefers to be online. Treat them as a roadmap item with the vendor, not a first-scope claim. The first scope concentrates on typed evidence boundaries, sandbox authority, one-way intake, tamper-evident audit, injection defenses, and model verification. The full independent egress-proof requirements are listed in `future_full_fledged_must_have.md`.

## Interfaces

Input: the running system's activity and the documents entering it.

First-scope output: enforced local isolation, recorded execution and egress-test evidence, and a tamper-evident audit trail. A continuous signed sovereignty record with independent attestation is a full-deployment requirement listed in `future_full_fledged_must_have.md`.

## Failure handling

Enforcement and observation are kept separate, so if the observer is bypassed the enforcement still holds, and if enforcement is somehow changed the observer records it. Offline verification means reference data can go stale, so the system records the staleness rather than pretending it is current.

## What is core and what is pack

Core: the network enforcement, the sovereignty proof, the one way ingestion, the injection defenses, the model verification, the access enforcement points.

Pack: the clearance and need to know model of the field.

## Multi-worker containment

Worker teams do not create a new authority boundary. Each worker receives a scoped capability token tied to the task, team, worker role, clearance, evidence scope, tools, paths, resource lease, and expiry. The Tool Gateway verifies the token again before execution.

Workers use separate contexts and task workspaces. They cannot read another worker's hidden context, open a peer's scratch directory, spawn a process outside the sandbox, call a peer directly, or communicate outside an audited WorkPacket. Shared state is provided only through clearance-filtered ledger, retrieval, World Model, artifact, and tool interfaces.

Concurrency never broadens authority. A team with five workers has no more clearance, tools, or autonomy than the TaskEnvelope allows. A worker cannot use a teammate's failure, result, or capability to bypass a deny or review decision. A majority of workers cannot approve a restricted action.

## Harness hooks are core security controls

The harness lifecycle interceptors around worker start, model calls, tool calls, context compaction, handoffs, barriers, verification, and completion are core-owned security controls. They are not project hooks and cannot be disabled by uploaded files, repositories, prompts, skills, or domain-pack content.

Untrusted documents remain data inside every worker context. They cannot install a hook, alter a TeamPlan, register a tool, grant a capability, or make a worker's output trusted. Domain-pack skills are signed and declarative in the first scope; any executable extension must pass the same approval and sandbox boundary as a tool.
