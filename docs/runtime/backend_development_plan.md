# AirBench Backend Development Plan

## Purpose

This is the execution plan for completing the first AirBench backend end to end. The GitHub issue hierarchy is the active tracker. The `M1` through `M10` parent issues are backend milestones, and their native sub-issues are the implementation units.

## Implementation baseline

- Language: Python.
- Backend style: a modular Python control plane with strict internal contracts, not one network service per framework.
- API layer: a local Python HTTP API around the orchestrator.
- Model servers: separate local vLLM or NVIDIA NIM services behind the Python backend adapter.
- Sandbox: a separate restricted execution boundary.
- Stores: local, clearance-aware persistence for the ledger, artifacts, evidence, retrieval projections, and world-model projections.
- Packaging: one-node offline deployment first. Distributed deployment remains a later hardening milestone.

All Python dependencies, model-serving runtimes, document libraries, fonts, and container images must be pinned and included in the offline supply-chain record.

## Milestone dependency graph

```text
M1 Contracts
  -> M2 Ledger
  -> M3 Orchestrator
  -> M5 Router and serving
  -> M6 Tools and sandbox
  -> M7 Intake, retrieval, and world model

M2 Ledger + M3 Orchestrator
  -> M4 Harness and worker teams

M1 + M2 + M3 + M5 + M6 + M7
  -> M8 Verification, autonomy, and consistency

M3 + M4 + M5 + M6 + M7 + M8
  -> M9 Deliverables and refinery vertical slice

M9
  -> M10 Hardening, deployment, and backend-complete acceptance
```

## Parallel work lanes

After M1 contracts are frozen, these streams can proceed in parallel:

- M2 ledger implementation;
- M5 model registry, router, and backend adapters;
- M6 sandbox and Tool Gateway;
- M7 File Intake, retrieval, and World Model interfaces.

M3 can begin with fake model and tool adapters after the first M1 contracts are stable. M4 depends on the orchestrator transition and resource interfaces. M8 can begin with deterministic fixtures while the real intake and model integrations are being completed, but its final integration is serial after M2 through M7.

M9 and M10 are serial integration milestones. They are not parallel feature-development streams because each proves the complete backend boundary produced by the earlier milestones.

## Python completion standard

Every sub-issue must provide:

- typed Python interfaces and schema validation;
- unit tests for normal and failure paths;
- contract tests at every module boundary;
- ledger events for consequential operations;
- deterministic fixtures where model output is not required;
- resource and timeout handling;
- no-network tests for code and untrusted-file paths;
- documentation of the accepted input and output contract.

The backend is complete only when the clean-node end-to-end acceptance run passes in both the available parallel execution mode and the serial virtual-team mode.
