---
name: airbench-doc-context
description: Select and read the AirBench architecture documents that govern a changed module, issue, or milestone, then report the applicable invariants and contracts.
metadata:
  short-description: Route the agent to the right architecture docs
---

# AirBench document context

Use whenever a task touches AirBench architecture, contracts, Python modules, tests, or documentation.

Read `docs/agent_development_workflow.md` and select the document bundle for the owning M milestone. Always include `docs/architecture_design.md` and `docs/domain_pack_framework.md` when ownership is unclear.

Do not summarize every document by default. Extract only the rules that affect the task and record the file names and relevant headings in the working plan. Identify:

- the owner of each decision;
- inputs and outputs;
- state transitions;
- provenance fields;
- ledger events;
- failure and escalation behavior;
- core versus domain-pack boundary;
- security and no-egress requirements.

If the implementation and documents disagree, stop and surface the disagreement. Do not resolve it by inventing a third contract.

