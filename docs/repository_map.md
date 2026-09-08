# Repository map

```text
AirBench/
├── apps/desktop/                 Tauri 2 + React desktop application
│   ├── src/app/                  composition and application entrypoint
│   ├── src/components/           reusable presentation components
│   ├── src/features/             task, intake, provenance, shell, and trace features
│   ├── src/platform/             Node, event, and Tauri integration boundaries
│   ├── src/generated/            generated views of Python contracts
│   ├── src-tauri/                native shell and IPC commands
│   ├── validation/               local Node and desktop validation fixtures
│   └── scripts/                  offline and packaging checks
├── src/                          installable Python source root
│   ├── src/airbench/                 sector-neutral runtime facade
│   │   ├── intake/                single file and multimodal intake boundary
│   │   ├── knowledge/             retrieval and world model
│   │   ├── orchestration/         worker team runtime and context scopes
│   │   ├── tools/                 gateway, file tools, sandbox, and execution
│   │   ├── verification/          deterministic verification runner
│   │   └── node/                  local Node API boundary
│   └── src/contracts/                provider-neutral typed contracts
│       ├── execution/             planning, scheduler, handoffs, orchestration
│       ├── model/                 backend, registry, routing, endpoint profiles
│       ├── provenance/            ledger, projections, and verification exports
│       ├── security/              admission and authorization
│       ├── adapters/              backend adapter implementations
│       └── schemas/               versioned YAML schemas and state tables
├── docs/                         architecture, design, assurance, and evidence
├── engineering_records/          issue plans, decisions, domain-pack records
├── tests/                        Python contract and runtime tests
├── acceptance/                   acceptance fixtures and scenario material
├── benchmarks/                   model and hardware benchmark data
├── models/                       roster and model metadata, never runtime cache
├── profiles/                     approved Node and deployment profiles
├── qualifications/               qualification records and fixtures
└── scripts/                      repository-level generation and signing tools
```

The `src/` layout is deliberate. It prevents tests and repository working-directory state from masking packaging errors while preserving the public import namespaces `airbench` and `contracts`. The desktop app is named by its product role, not by a duplicate repository name.
