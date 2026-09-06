# AirBench Frontend Interaction Analysis and Simplification

## 1. What was studied

This is a product-pattern analysis, not a visual imitation exercise. AirBench has a different trust model and a different job, but Claude and Codex are useful references for reducing interaction friction.

Primary sources reviewed:

- [Codex app overview](https://openai.com/index/introducing-the-codex-app/)
- [Codex Academy overview](https://openai.com/academy/codex/)
- [Claude Code CLI reference](https://code.claude.com/docs/en/cli-usage)
- [Claude Code security model](https://code.claude.com/docs/en/security)
- [Claude Code getting started](https://docs.anthropic.com/en/docs/claude-code/getting-started)

## 2. What makes these products feel professional

### Claude and Claude Code

The important interaction pattern is not decoration. It is the direct relationship between a request, the current work context, an action, and a permission boundary.

Claude Code is deliberately action-oriented. It can inspect a project, edit files, run tests, resume a session, and expose structured output. Its security model distinguishes read-only work from actions that change files or run commands, and asks for permission where the action warrants it. This creates a simple user mental model: the agent is working in a known place, and the user knows when it needs authority.

Useful patterns for AirBench:

- one persistent task context instead of many dashboard panels;
- a clear composer or request surface;
- readable activity updates rather than raw internal reasoning;
- resumable work;
- permission or review gates close to the action;
- technical detail available on demand;
- a strong distinction between suggestion, action, and completed result.

What AirBench must change:

- Claude Code's permissions are interactive user permissions. AirBench must add deterministic Node policy, clearance, domain-pack risk, verification, and ledger gates.
- Claude Code assumes an engineering workspace. AirBench must make files, sources, confidence, clearance, and deliverables understandable to non-engineers.
- AirBench cannot inherit cloud endpoints, auto-update behavior, telemetry, or arbitrary MCP access.

### Codex

The Codex app's strongest product pattern is task management at the right level of abstraction. The user delegates a task, can supervise progress, can manage multiple agents or worktrees, and can review the resulting work. Skills package repeatable workflows and resources. The interface supports long-running work without requiring the user to keep the entire process in their head.

Useful patterns for AirBench:

- a task is the durable unit of work;
- parallel activity is hidden behind a coherent task surface;
- the user can inspect progress without seeing every internal token;
- reusable skills make behavior consistent;
- isolated work contexts prevent unrelated tasks from colliding;
- outputs are reviewable artifacts, not only chat messages;
- a review queue is a better return path than a stream of notifications.

What AirBench must change:

- Codex's worktrees and cloud or local coding environments are not the AirBench execution model. AirBench uses the Python Node, a bounded harness, local tools, and a signed ledger.
- Codex users are usually developers. AirBench's default user should not need to understand worktrees, models, branches, or tool names.
- The AirBench task cannot be considered done after a model response. Evidence, verification, clearance, deterministic values, render checks, and approval state are part of the result.

## 3. Shared interaction principles to adopt

### 3.1 One task surface

The user should have one place to describe the outcome and then follow the same task into planning, execution, evidence, review, and delivery. Separate dashboards for each internal framework increase cognitive load and make AirBench look like an AI control panel.

### 3.2 Progressive disclosure

The ordinary user sees:

- what AirBench is doing;
- what it needs;
- what it found;
- what is ready;
- what needs approval.

The operator can open:

- worker roles;
- execution mode;
- model capability and actual model;
- tool calls;
- source hashes;
- event IDs;
- signatures and resource leases.

Both views come from the same Node state. The detail view is not a second product.

### 3.3 Reviewable outputs

Claude and Codex make it easy to continue from the work that was just done. AirBench should make that continue path a verified artifact, source drawer, review checklist, and explicit approval action.

### 3.4 Trust before action

The user should not discover after submitting a sensitive document that the Node is not trusted, the clearance is insufficient, or the ledger is unavailable. Connection, intake, and review gates are shown before consequential actions.

### 3.5 Calm activity

No typing simulation, animated swarm, fake live token stream, or wall of logs. Use a short chronological activity line with expandable evidence. This is more trustworthy and more useful to a non-technical user.

## 4. What currently makes the AirBench mockup feel AI-sloppy

The current direction is visually competent but has too many signs of an AI dashboard:

1. The left navigation and the prototype tab switcher duplicate navigation.
2. Home has a greeting, large composer, recent work card, and Node readiness dashboard at the same visual weight.
3. GPU capacity and qualified-model counts appear in the ordinary user path even when they do not help the task.
4. Many status pills compete with the task title.
5. The live task screen gives equal visual weight to internal workers and user outcomes.
6. Audit uses KPI cards even though the important question is whether the record can be verified.
7. The UI exposes too many screens as peers when several are really modes or drawers of one task.
8. Technical terms such as “server-authoritative”, “vision worker”, and model names appear before the user needs them.
9. Decorative icon glyphs and mojibake in the prototype reduce perceived quality.

## 5. Simplification decisions

### New primary navigation

```text
Work
  Home
  Tasks
  Review

Records
  Artifacts
  History
  Audit

Administration
  Node and settings
```

Projects become a filter and grouping inside Tasks. New Task is the primary action on Home and Tasks, not a permanent peer in the rail. Domain Pack Administration is an administrator-only settings surface.

### One task workspace

Plan Review, Live Task, Evidence and Sources, and technical routing become modes or drawers inside the Task workspace:

- `Overview`: outcome, current status, next action.
- `Plan`: stages, required evidence, risk, and authority.
- `Activity`: concise chronological progress.
- `Sources`: evidence and provenance drawer.
- `Technical`: workers, routing, tools, hardware, and ledger details.

The user does not navigate away from the task to understand it.

### Home becomes a starting point

Home contains:

- one outcome-first composer;
- one Continue work list;
- one compact Needs your review row;
- one quiet connected-node line.

It does not contain GPU meters, model counts, a multi-card readiness dashboard, or generic productivity metrics.

### Review becomes a decision surface

Review Queue is a simple list of deliverables that need the current user's decision. Artifact Review is document-first, with evidence in a right-side drawer and a persistent approval bar. The user does not need to understand the harness to approve a document.

### Administration is intentionally hidden from the default path

Node health, model qualification, routing, network policy, hardware capacity, and domain-pack administration remain available to authorized users, but they are not presented as a normal task dashboard.

## 6. Revised visual direction

- Use one large work surface with a quiet side rail.
- Keep the top bar to breadcrumb, node state, and one command entry.
- Prefer text links and simple rows over repeated cards.
- Use one accent color for the active action and status semantics for attention.
- Remove gradients, oversized hero language, decorative badges, and repeated metrics.
- Use sentence-case labels that describe the user's next action.
- Keep technical detail behind `Details`, `Sources`, or `Technical view` disclosures.
- Fix all character encoding at the source. Product UI must contain proper UTF-8 or ASCII fallback text, never mojibake.

## 7. AirBench-specific advantages that should remain visible

Simplification must not hide AirBench's actual value. The user must still be able to see:

- the node is internal and trusted;
- a task is running as a parallel, pipelined, or serial virtual team when relevant;
- a finding has a source, confidence, clearance, taint, and derivation;
- values in deliverables are calculated by the system;
- review is required before release;
- the work is backed by a signed ledger;
- no external network path was permitted.

These appear as concise status lines and expandable proof, not as seven permanent dashboard panels.

## 8. Simplified acceptance test

A non-technical user should be able to complete the inspection-report task with this path:

1. Open Home.
2. Describe the desired approval note.
3. Attach the scanned report.
4. Confirm the plain-language plan.
5. Follow one task workspace while AirBench works.
6. Open a finding's source when needed.
7. Review the generated document.
8. Approve or return it.

If the user must learn the difference between a model router, worker, context packet, ledger projection, or GPU residency before completing that path, the interface is still too technical.
