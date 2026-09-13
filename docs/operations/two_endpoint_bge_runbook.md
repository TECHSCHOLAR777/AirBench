# AirBench Two-Endpoint Gemma + BGE Runbook

Status of the two deployed vLLM Gemma endpoints (efficient + capable lanes) and the
local BGE retrieval stack, what is already implemented, what is left, and exactly how
to run, measure, evaluate, and fill the remaining placeholders.

Commit: `d1e380ee` on branch `DeepFinal`.

---

## 1. What is implemented

### Contracts (`src/contracts`)
- `LocalEndpointBinding` (`model/local_endpoint.py`): loopback-only deployment identity
  (`endpoint_id`, `target_id`, `base_url`, `served_model_name`, adapter id/version).
- `ModelRouter` resolves an adapter by `target_id` first (`endpoint_bindings`), then by
  `adapter_id` (legacy map) — the two-endpoint collision fix. Provenance carries
  `endpoint_id`; `VllmAdapter` records it.
- `NODE_COMMAND_TYPES` adds `model.call`, `task.approve_artifact`, `task.return_artifact`.
- Quantization normalizer accepts `w4a16` (QAT compressed-tensors).

### Node (`src/airbench/node`)
- `model_serving.py`: composes the signed roster into an endpoint-bound `ModelRouter`,
  readiness probes, and `declared_limit_admission`; opt-in via env.
- `task_planning.py`: deterministic `PlanProposal` (one model step per permitted worker
  capability + an independent verification step) committed through the orchestrator, plus
  hardware admission via `AdmissionController`, recorded as `team.resource_plan.*`.
- `api.py`: `model.call` command route (`POST /api/v1/tasks/{id}/model-call`) with
  idempotent replay and bounded error mapping; `NodeApiService` carries the router,
  planner, and retrieval runtime.
- `server.py`: opt-in composition of model serving, planning, and retrieval, with a
  read-only `GET /api/v1/node/model-serving` and `GET /api/v1/node/retrieval`.

### Retrieval (BGE-M3 + bge-reranker-v2-m3)
- `knowledge/embedding_runtime.py`: real local adapters behind the existing
  `EmbeddingProvider`/`Reranker` interfaces (`local_embedding_provider`, `local_reranker`,
  `build_retrieval_runtime`, `retrieval_runtime_from_env`). Local directory only;
  repository ids are rejected. TensorFlow is disabled and the torch stack is preloaded
  before File Intake (`pypdf`) to avoid a Windows native crash.

### Desktop
- Rust `node_transport.rs` now routes `task.approve_artifact` / `task.return_artifact`
  (previously built by TypeScript but rejected).

### Tooling (`scripts/`)
- `start_demo_node.ps1` — starts the Node with all demo env (`-Retrieval` for BGE).
- `run_two_endpoint_demo.py` — drives `create -> authorize -> plan -> approve ->
  model-call -> route-trace` over the Node HTTP API.
- `airbench_qualify.py` — evaluation harness: scores cases, writes a record, prints the
  `qualification_hash`, and updates the roster (`--write-roster`) and the qualification
  matrix (`--write-matrix`).
- `airbench_retrieval_demo.py` — indexes a corpus, runs BGE search + rerank, prints cited
  excerpts, and produces BGE `qualification_hash` values (`--qualify`, `--write-roster`).
- `airbench_hardware_profile.py` — measures the host/GPU and fills the hardware profile.
- `airbench_demo_roster.py` — builds a signed demo roster (`--include-retrieval` adds BGE).
- `airbench_hash.py` — hashes model artifacts (`--target`, `AIRBENCH_MODEL_STORE`).
- `airbench_sign.py` — signs a roster (`--roster/--key/--out`).

### Config / evidence
- `profiles/hardware/workstation_04.json` — active hardware profile.
- `models/roster/v0/model_roster.yaml` — candidate Gemma targets (E2B efficient, 12B
  capable) + BGE role hashes; reference targets still placeholders.
- `models/roster/demo/two_endpoint_roster.yaml` — signed, loadable demo roster.
- `qualifications/records/` — BGE qualification records.

### Tests
`test_m53_local_endpoints.py`, `test_m53_model_call_route.py`,
`test_m53_node_model_serving.py`, `test_task_planning.py`, `test_retrieval_runtime.py`,
plus additions to `test_m54_adapters.py`. Full suite passes.

---

## 2. What is still remaining

| Placeholder | Where | Blocks demo? | How to fill |
| --- | --- | --- | --- |
| `cpu_model`, `measurement_hash` | `profiles/hardware/workstation_04.json` | No | Run `airbench_hardware_profile.py --write` on the GPU box |
| Gemma role `certificate_id`, `qualification_hash` | `models/roster/v0/model_roster.yaml` (E2B/12B `qualified_roles`) | Yes for real qualification | `airbench_qualify.py ... --write-roster` |
| Gemma cert fields (scores, hashes, signature, timestamp) | `qualifications/model_qualification_matrix.yaml` | No | `airbench_qualify.py ... --write-matrix` |
| `qualification_signature` | roster Gemma targets | Yes for roster load | `airbench_demo_roster.py` (re-signs) |
| Reference targets (31B, 26B, Qwen coder/VL) | roster + qualification matrix + `benchmarks/*.yaml` | No (unused) | Fill only if/when you add those models |
| `target_96gb_vram.yaml` | `profiles/hardware/` | No (old reference) | Ignore, or fill on the box |
| Gemma license acceptance | ops process | No | Accept the Gemma license on Hugging Face |

---

## 3. SSH and the demo, step by step

### 3.1 One-time setup (dev machine)
```powershell
winget install --id Cloudflare.cloudflared
```
SSH config at `C:\Users\ALG\.ssh\config`:
```
Host mmmut-server
         HostName ssh-mmmut.aimsdtu.in
         User workstation-04
         ProxyCommand cloudflared access ssh --hostname %h
         PasswordAuthentication yes
```

### 3.2 Terminal 1 — verify the model servers (then `exit`)
```bash
ssh mmmut-server
export AIRBENCH_SERVING_ROOT=/home/workstation-04/airbench-serving
hostname; nvidia-smi
docker ps --filter name=airbench-vllm
curl -sS --fail -w '\nE2B %{http_code}\n' http://127.0.0.1:8001/health
curl -sS --fail -w '\n12B %{http_code}\n' http://127.0.0.1:8002/health
curl -sS --fail http://127.0.0.1:8001/v1/models
curl -sS --fail http://127.0.0.1:8002/v1/models
exit
```
Expected: 200 on both, served names `airbench-gemma-4-e2b` / `airbench-gemma-4-12b`.

### 3.3 Terminal 2 — SSH tunnel (keep open)
```powershell
ssh -N -L 127.0.0.1:18001:127.0.0.1:8001 -L 127.0.0.1:18002:127.0.0.1:8002 mmmut-server
```

### 3.4 Terminal 3 — start the Node (keep open)
```powershell
cd C:\Users\ALG\Downloads\SIH2026\AirBench-Deep
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1            # Gemma lanes only
# or, with the BGE retrieval stack:
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 -Retrieval
```
Wait ~35s for `Starting AirBench Node ...` before running anything else (the Node
re-hashes the signed model files at startup).

### 3.5 Terminal 4 — checks and demo
```powershell
cd C:\Users\ALG\Downloads\SIH2026\AirBench-Deep
curl.exe -sS http://127.0.0.1:8765/api/v1/node/readiness
curl.exe -sS http://127.0.0.1:8765/api/v1/node/model-serving
curl.exe -sS http://127.0.0.1:8765/api/v1/node/retrieval        # '-Retrieval' only

python scripts\run_two_endpoint_demo.py --token demo-token --subject demo.operator

# BGE retrieval with citations
python scripts\airbench_retrieval_demo.py --model-store "$PWD\airbench-models"
```

---

## 4. Measure, evaluate, and fill the placeholders

### 4.1 Hardware profile (run on the GPU box)
The script refuses to overwrite if the detected GPU differs from the profile.
```bash
cd <repo on the GPU box>
python3 scripts/airbench_hardware_profile.py --write
```
Fills `cpu_model`, `cpu_cores`, `ram_bytes`, GPU fields, `measurement_hash`,
`network_check_id`; validates against the `HardwareProfile` contract.

### 4.2 Gemma qualification (dev machine, tunnel open)
```powershell
python scripts\airbench_qualify.py --target-id airbench-gemma-4-e2b --role reasoning --endpoint http://127.0.0.1:18001 --served-model airbench-gemma-4-e2b --write-roster --write-matrix --container-digest sha256:<vllm-image-id>
python scripts\airbench_qualify.py --target-id airbench-gemma-4-12b --role reasoning --endpoint http://127.0.0.1:18002 --served-model airbench-gemma-4-12b --write-roster --write-matrix --container-digest sha256:<vllm-image-id>
python scripts\airbench_qualify.py --target-id airbench-gemma-4-12b --role lead_worker --endpoint http://127.0.0.1:18002 --served-model airbench-gemma-4-12b --write-roster --write-matrix --container-digest sha256:<vllm-image-id>

$env:AIRBENCH_MODEL_STORE="C:\airbench-models"
python scripts\airbench_demo_roster.py
```
- Container id:
  ```bash
  docker inspect --format '{{index .RepoDigests 0}}' vllm/vllm-openai:v0.28.0-ubuntu2404
  ```
- Use your own evaluation set:
  ```powershell
  python scripts\airbench_qualify.py --eval-file acceptance\qualification_eval.example.yaml ...
  ```
  Add `metric: <name>` to cases to populate named benchmark scores.
- Records land in `qualifications/records/<target>.<role>.json`.
- Restart Terminal 3 after re-signing so the Node loads the updated roster.

### 4.3 BGE retrieval qualification
```powershell
python scripts\airbench_retrieval_demo.py --model-store "$PWD\airbench-models" --qualify --write-roster
```
Writes `qualifications/records/bge-m3.embedding_service.json` and
`...reranking_service.json` and fills the BGE role `qualification_hash` values.
BGE is already verified: `recall@3 = 1.00`, `mrr = 1.000`.

### 4.4 Reference models (only if you add them)
```powershell
# hash + roster artifact digests
$env:AIRBENCH_MODEL_STORE="<store>"; python scripts\airbench_hash.py --target <target-id>
# container digest for a vLLM-served target
docker inspect --format '{{index .RepoDigests 0}}' <image>
```
Then run `airbench_qualify.py` for each role and, for BGE, `airbench_retrieval_demo.py`.

### 4.5 Performance benchmarks (optional)
`benchmarks/model_hardware_results.yaml`, `backend_compatibility_matrix.yaml`,
`quantization_matrix.yaml` hold measured performance for the six reference targets.
They are not used by the two-Gemma + BGE demo. Fill from real benchmark runs when you
make a performance claim.

---

## 5. Placeholder checklist

- [ ] `profiles/hardware/workstation_04.json`: `cpu_model`, `measurement_hash` (box).
- [ ] Gemma roster roles: `certificate_id`, `qualification_hash` (harness).
- [ ] Gemma roster: `qualification_signature` (demo roster tool).
- [ ] Qualification matrix Gemma certs (harness `--write-matrix`).
- [ ] BGE roster roles (retrieval demo `--write-roster`). Done locally.
- [ ] Gemma license acceptance (HF account).
- [ ] Reference targets + benchmarks: only when adding those models.

## 6. Known operational notes
- Node startup re-hashes ~18.5 GB (Gemma) and, with `-Retrieval`, BGE too; wait ~35s.
- Gemmas live in `C:\airbench-models`; BGE lives in `<repo>\airbench-models`.
  `AIRBENCH_RETRIEVAL_MODEL_STORE` (set by `start_demo_node.ps1 -Retrieval`) separates them.
- To list BGE inside the signed model roster, consolidate the stores and run
  `airbench_demo_roster.py --include-retrieval`.
- The desktop never calls vLLM directly; the Node is the only model client.
