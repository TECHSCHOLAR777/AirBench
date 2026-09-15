# AirBench Operator Startup Guide — aimslab Qwen vLLM

This is the controlled remote-GPU path described in
`AIMSLAB_VLLM_ENDPOINT_HANDOFF.md`. The inference host remains an inference
server only; the AirBench Node runs locally and reaches it through loopback
SSH forwards.

## 1. Prepare signed deployment records

The Qwen roster and attestation are generated from the pinned facts in the
handoff. Regenerate them only when those facts or the deployment version
changes:

```powershell
.venv-deep\Scripts\python.exe scripts\airbench_qwen_aimslab_records.py
```

The roster is candidate-only until role evaluation is completed. A candidate
cannot route by default; the controlled demo requires the explicit
`-AllowCandidateQualification` switch.

## 2. Open the tunnel

Configure the `aimslab` SSH alias using the handoff’s separately distributed
credentials, then keep this window open:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\open_ssh_tunnel.ps1
```

The local loopback bindings are:

```text
127.0.0.1:18001 -> aimslab 127.0.0.1:8001 -> airbench-qwen25-vl-7b
127.0.0.1:18002 -> aimslab 127.0.0.1:8002 -> airbench-qwen3-8b
```

## 3. Prove endpoint identity

```powershell
.venv-deep\Scripts\python.exe scripts\model_endpoint_preflight.py `
  --roster models\roster\aimslab\qwen_vllm_roster.yaml `
  --attestation models\attestations\aimslab_qwen_vllm.yaml `
  --signing-key .airbench_signing_key `
  --attestation-signing-key .airbench_signing_key
```

This checks the signed roster, signed remote artifact/runtime attestation,
`/health`, and exact `/v1/models` identity. Endpoint health alone is not
artifact verification.

## 4. Start the Node

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 `
  -AllowCandidateQualification
```

Omit that switch for a qualification-gated startup. Use `-AllowDegradedLane`
only for transport diagnostics; it does not bypass router qualification.

The Node calls only the local loopback bindings. The desktop continues to call
the Node API and never calls vLLM directly.

## 6. Shared Node on the model host

For the shared knowledge-base deployment, copy the repository application and
the approved corpus to the model host under:

```text
/media/aims-dtu/e6f3d549-768f-4cd9-bdd7-fe600ab3bf81/airbench-serving/airbench-node/
```

Keep model artifacts under `airbench-serving/models/`. The Node's ledger,
intake artifacts, Chroma collection, world-model database, and decision store
belong under `airbench-node/state/`; clients must never open those files.

Provision the local `bge-m3` and `bge-reranker-v2-m3` directories in the model
store before starting retrieval. No runtime download is permitted. Start the
shared Node with:

```bash
export AIRBENCH_BEARER_TOKEN='<operator-token>'
bash scripts/start_shared_node.sh
```

`start_shared_node.sh` validates the catalog, corpus, local retrieval models,
and persistent directories before binding. It is loopback-bound by default;
shared operators must connect through the approved internal HTTPS/authenticated
boundary, never by sharing SQLite or Chroma files.

## 5. Run the governed flow

```powershell
$env:AIRBENCH_BEARER_TOKEN = "<operator-token>"
.venv-deep\Scripts\python.exe scripts\run_two_endpoint_demo.py `
  --token $env:AIRBENCH_BEARER_TOKEN `
  --hardware-profile-ref aimslab-titan-rtx-24gb
```

Inspect `/api/v1/node/model-serving` and the task route trace. A successful
direct vLLM call proves only endpoint behavior; completion requires the Node
route decision, model response, and ledger events.
