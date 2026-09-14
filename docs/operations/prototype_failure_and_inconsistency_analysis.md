# AirBench Prototype Failure and Inconsistency Analysis

Date: 2026-09-14  
Scope: local Python Node, durable ledger, File Intake, task execution, model-serving bindings, retrieval/knowledge base, and desktop integration.

## Executive conclusion

The absence of a pre-existing knowledge base is **not** the reason the prototype stopped during the reported run.

The primary failure was an authority configuration defect:

```text
insufficient_authority: the operator lacks the required role human_reviewer
```

The Node had already recorded plan approval and then failed while authorizing the execution action. The API returned an untyped HTTP 500, so the desktop kept polling a task that no longer had a useful forward transition.

That authority defect has been corrected by:

- explicitly setting `AIRBENCH_OPERATOR_ROLES=human_reviewer` in the demo launcher;
- treating an empty inherited role variable as unset and defaulting it to `human_reviewer` for the demo configuration;
- preserving the pack-defined role requirement rather than granting a broader role.

A second live defect was found while exercising the running Node: new tasks with identical natural-language requests could receive the same task ID. The durable ledger then rejected the second task. New API-created tasks now derive their task identity from the command idempotency key, so retries replay the same task while distinct submissions receive distinct tasks.

## Reproduction evidence

### Failure reproduced from the supplied log

The recorded request sequence was:

1. Create task: `201 Created`.
2. Authorize task: `202 Accepted`.
3. Plan became ready.
4. Approve plan: `500 Internal Server Error`.
5. The stack trace ended in `LocalNodeAutonomyService.authorize`.
6. The authority check rejected the missing `human_reviewer` role.
7. The desktop continued polling events, route trace, and task projections.

This is a control-plane failure. It occurs before retrieval quality or knowledge-base contents can affect the execution result.

### Live Node checks

The Node started successfully after its model-roster hashing delay and reported:

- signed refinery domain pack loaded;
- SQLite world-model graph enabled;
- consistency service enabled;
- autonomy governor enabled;
- P&ID adapter composed;
- two model-serving endpoint bindings registered;
- File Intake enabled;
- Deliverable Engine enabled;
- task execution enabled.

The first live multipart probe declared the wrong byte count. File Intake correctly returned:

```text
source_size_mismatch
```

Because the upload was rejected, later authorization correctly returned:

```text
task_execution_prepare_failed
task-bound File Intake must be committed before authorization
```

This was a probe error followed by an expected safety rejection, not a knowledge-base failure.

After correcting the upload size and restarting the Node with the task-ID fix,
the complete live path reached task creation, upload, authorization, and plan
approval. Execution then failed because the model-serving readiness projection
reported both tunneled endpoints as `unhealthy` / `not_ready`. The Node had
model bindings configured, but the SSH tunnel or remote vLLM containers were
not reachable at that moment. This is an external runtime readiness issue,
not a retrieval or knowledge-base issue.

## Inconsistency and defect inventory

| Area | Inconsistency or defect | Effect | Classification | Status |
|---|---|---|---|---|
| Operator authority | Demo startup did not explicitly set the pack-required `human_reviewer` role, and an empty inherited environment variable could erase the default | Approval was recorded, execution authorization failed, and the client saw HTTP 500 | Code/config defect | Fixed |
| Approval ordering | Approval was committed before the execution authorization path completed | A failed authorization could leave the task looking approved while no deliverable was produced | Control-flow defect | Guarded by authority configuration; should remain covered by regression tests |
| Task identity | Natural-language request, principal, and domain pack alone determined task ID | Two distinct submissions with the same request collided in the durable ledger | Code defect | Fixed |
| Intake probe | The client must declare the exact uploaded byte count | Incorrect multipart metadata is rejected | Contract enforcement, not a defect | Expected |
| Knowledge-base population | The configured Chroma store can start with zero indexed chunks | Retrieval returns no evidence until documents are ingested | Deployment/data readiness issue | Expected; does not block task creation or basic planning |
| Model startup | The Node hashes model-roster assets before binding HTTP | Startup takes roughly one minute in the current Windows environment | Operational latency | Expected but should be shown clearly in the UI/startup guide |
| Port lifecycle | Starting a second Node while the first process still owns port `8765` produces WinError 10048 | The second Node exits and the operator may think the code failed | Operational issue | Stop the old Node or use a different port |
| Remote model tunnel | Model endpoint health depends on the SSH tunnel and remote containers | The Node can start but model calls can fail if `18001/18002` are not reachable | Environment dependency | Must be checked before task execution |
| P&ID optional runtime | Real P&ID execution imports optional vision dependencies and Ultralytics settings | The opt-in model test was blocked by the local Ultralytics settings directory permission | Environment/test setup issue | Not an accuracy result |
| P&ID evaluation | The repository has weights but no labelled P&ID ground truth | mAP, OCR CER/WER, edge F1, and graph edit distance cannot be honestly reported | Missing evaluation data | Open |
| Retrieval evaluation | The repository has retrieval code but no judged query/document relevance set | Precision, recall, nDCG, and answer support coverage cannot be honestly reported | Missing evaluation data | Open |
| Model benchmark | Endpoint health was checked, but generation repetitions, VRAM sampling, concurrency ramp-up, and fallback injections were not run | Hardware table values remain unmeasured | Missing benchmark run | Open |
| Desktop test invocation | Vitest does not support the Jest-style `--runInBand` flag | The command fails before tests run | Test command issue | Use `npm run test` without that flag |
| Full-suite runtime | The backend suite contains approximately 660 tests and can exceed one shell wait window | Partial progress output must not be mistaken for a passing suite | Tool/runtime limitation | Run by test groups or with a longer-lived runner |

## Why the knowledge base is not the cause of the reported failure

The execution path is ordered approximately as follows:

```text
task.create
  -> file intake / task-bound manifest
  -> task.authorize
  -> deterministic plan and hardware admission
  -> human authority / autonomy authorization
  -> task.approve_plan
  -> Node-owned execution
  -> verification and deliverable rendering
```

Knowledge retrieval is only used when the admitted plan contains a knowledge or evidence-retrieval step. A task can therefore be created, receive an upload, be planned, and pass the human authority gate without a populated knowledge base.

The knowledge base becomes necessary when the task asks the system to:

- answer from local manuals or prior correspondence;
- cite retrieved text or images;
- use P&ID graph relationships from previously ingested drawings;
- compare current evidence with historical decisions;
- ground a generated deliverable in a local corpus.

An empty knowledge base should produce an explicit `no evidence` or `needs review` state for those retrieval-dependent tasks. It should not produce a stuck planning state or an authority exception.

## What the current prototype can do without a knowledge base

The following path is implemented and covered by integration tests:

1. Create a task.
2. Upload a task-bound file through File Intake.
3. Preserve the source hash, media type, taint, clearance, and manifest.
4. Authorize the task.
5. Produce and commit a deterministic plan.
6. Apply hardware admission.
7. Approve the plan with the configured human reviewer role.
8. Execute the Node-owned task path.
9. Produce and verify a deliverable.
10. Display the artifact for review and accept or reject sign-off.

The production composition test passes this synthetic path end to end using a local test backend and structural deliverable template.

## What requires a populated knowledge base

| Capability | Empty knowledge base behavior | Required data |
|---|---|---|
| Local-manual question answering | No grounded answer; needs review or no evidence | Manuals, SOPs, correspondence, indexed text chunks |
| Text retrieval | Zero or insufficient results | Ingested text/PDF/DOCX/TXT sources and embeddings |
| Image retrieval | No matching image evidence | Ingested images/pages and image metadata/vector records |
| P&ID historical context | No historical graph context | P&ID graph fragments, symbols, tags, relations, revisions |
| Current P&ID upload | Can run through the P&ID adapter without a pre-existing KB | Drawing file, optional vision runtime, signed legend |
| Consistency checks | Limited to currently committed world-model facts | Prior decisions and committed facts |
| Evidence-backed deliverable | Only task-local evidence is available | Task upload and/or indexed approved sources |

## Relevant corrected implementation points

### Operator role configuration

`src/airbench/node/server.py` now treats a blank `AIRBENCH_OPERATOR_ROLES` value as unset and resolves it to the demo role `human_reviewer`.

`scripts/start_demo_node.ps1` now sets:

```powershell
$env:AIRBENCH_OPERATOR_ROLES = "human_reviewer"
```

An explicitly non-empty role list remains authoritative for least-privilege deployments.

### Task identity

`src/airbench/node/api.py` now passes a task ID derived from the command idempotency key into the orchestrator. This gives the required behavior:

- retrying the same command returns the same task;
- submitting a new command with the same request text creates a new task;
- the durable ledger does not receive two unrelated `task.created` events for one task identity.

## Current verification evidence

### Passing backend checks

- Node API task identity regression: passed.
- Production composition workflow: passed.
- Task planning: passed.
- Acceptance tests: passed.
- Ledger replay and chain verification: passed on synthetic acceptance data.
- No-egress checks: passed.
- Autonomy checks: passed.
- Model-serving composition and routing checks: passed.
- Knowledge and P&ID integration checks: passed for the deterministic/integration paths.

### Passing frontend checks

- Generated frontend contracts: current.
- UI validation: passed.
- Accessibility validation: passed.
- Tauri configuration validation: passed.
- TypeScript compilation: passed.
- Rust `cargo check --offline`: passed.

### Still not proven by the current repository

- real-model generation through the remote vLLM endpoints;
- stable end-to-end latency under repeated generation;
- model VRAM and concurrency limits;
- retrieval quality on judged queries;
- P&ID accuracy on labelled drawings;
- research-quality ablation percentages;
- real desktop Tauri/WebDriver execution against a live Node.

## Correct end-to-end test interpretation

For a valid test, the operator must ensure all of the following:

1. Only one Node owns port `8765`.
2. Both SSH tunnels and remote model containers are healthy if model serving is enabled.
3. The Node has restarted after code or environment changes.
4. The uploaded file's declared size exactly equals the uploaded bytes.
5. The task request uses a new command ID and idempotency key for each new submission.
6. The task is uploaded before authorization when execution is enabled.
7. The plan reaches `ready` before approval.
8. The authenticated operator has the pack-required role.
9. The UI connects to the same Node identity and bearer token.
10. Retrieval-dependent tasks have an ingested corpus if grounded local evidence is expected.

## Final diagnosis

The reported “stuck at ledger entry recorded” behavior was caused by a sequence of control-plane defects and test/deployment conditions, not by an empty knowledge base:

1. Missing human-reviewer authority caused approval execution to fail.
2. The client continued polling after the failed command.
3. A malformed upload probe caused File Intake to reject the source.
4. Repeated identical requests exposed a task-ID collision in durable storage.
5. A second Node launch can fail when the previous process still owns the port.

The knowledge base is a separate readiness requirement for retrieval-grounded answers. It is not a prerequisite for the basic upload-to-plan-to-deliverable prototype path.
