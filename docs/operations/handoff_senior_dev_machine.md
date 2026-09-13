# AirBench Two-Endpoint Gemma Serving: Senior Handoff

**Repo:** TECHSCHOLAR777/AirBench (local: AirBench-Deep)
**Date:** 2026-09-13
**For:** Senior developer on the dev machine

---

## CONFIRM FIRST: GPU box hostname

The GPU box is referenced as `workstation-04` from an earlier session note.
**Verify the actual hostname or IP with ALG before running anything.**
Replace every occurrence of `workstation-04` in the commands below with the real value.

---

## 1 - What was implemented (tests: 491 passed, 0 failed)

### NEW: src/airbench/node/model_serving.py
Composition layer. Owns the only place in the Node that creates VllmAdapter instances.
- `LocalEndpointSpec` - typed endpoint config, validates via LocalEndpointBinding contract
- `ModelServingConfig` - reads env vars: AIRBENCH_MODEL_E2B_URL, AIRBENCH_MODEL_12B_URL etc.
- `build_model_router()` - creates one VllmAdapter per endpoint, wires endpoint_bindings

### NEW: tests/test_m53_node_model_serving.py
8 tests covering spec validation, env factory, bad-URL rejection, two-binding distinctness.
No live GPU required.

### MODIFIED: models/roster/v0/model_roster.yaml
- Added target airbench-gemma-4-e2b (routing_tier: efficient, demo port 18001)
- Added target airbench-gemma-4-12b (routing_tier: capable, demo port 18002)
- FIXED: adapter_id changed from "airbench-vllm-adapter" to "airbench.vllm" in ALL 6
  existing vLLM targets (31B, 26B, Qwen3-Coder, Qwen2.5-VL). Old value would have caused
  ModelRouter to return None for every routing decision.
- FIXED: adapter_version changed from "0.1.0" to "0.5" in all 6 targets.

### MODIFIED: qualifications/model_qualification_matrix.yaml
Three PENDING: skeleton certificates appended:
- cert-gemma4-e2b-reasoning-v0
- cert-gemma4-12b-reasoning-v0
- cert-gemma4-12b-lead-v0

### NEW: docs/operations/model_download_gemma_e2b_12b.md
Full GPU-box runbook (download, hash, docker, sign, env vars).

---

## 2 - Why endpoint_bindings (key design decision)

VllmAdapter has a class constant adapter_id = "airbench.vllm". Two instances of the
same class share the same adapter_id. If they were stored in the old adapters dict
keyed by adapter_id, the second would overwrite the first.

The fix: ModelRouter accepts endpoint_bindings: dict[target_id, adapter_instance].
The router resolves by target_id first, then falls back to adapters by adapter_id.
Both keys are distinct (airbench-gemma-4-e2b vs airbench-gemma-4-12b) so there is
no collision.

---

## 3 - What you must do (GPU access required)

### Step 1: SSH loopback forward (dev machine, keep terminal open)
```
ssh -N -L 18001:127.0.0.1:18001 -L 18002:127.0.0.1:18002 user@workstation-04
```

### Step 2: Download models (GPU box, only if not already staged)
```
export AIRBENCH_SERVING_ROOT=/home/workstation-04/airbench-serving
huggingface-cli download google/gemma-4-E2B-it-qat-w4a16-ct \
  --revision 971342c08f607aa7779983f6b5289778b5d271a7 \
  --local-dir "$AIRBENCH_SERVING_ROOT/models/gemma-4-e2b-it-w4a16-ct"
huggingface-cli download google/gemma-4-12B-it-qat-w4a16-ct \
  --revision 1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee \
  --local-dir "$AIRBENCH_SERVING_ROOT/models/gemma-4-12b-it-w4a16-ct"
```
See `model_download_gemma_e2b_12b.md` for the verified hashes and the exact
vLLM `v0.28.0-ubuntu2404` launch commands.

### Step 3: Hash artifacts (GPU box), paste into model_roster.yaml
```
sha256sum /airbench-models/gemma-4-e2b-it/*.safetensors
sha256sum /airbench-models/gemma-4-e2b-it/tokenizer.json
sha256sum /airbench-models/gemma-4-e2b-it/tokenizer_config.json
sha256sum /airbench-models/gemma-4-12b-it/*.safetensors
sha256sum /airbench-models/gemma-4-12b-it/tokenizer.json
sha256sum /airbench-models/gemma-4-12b-it/tokenizer_config.json
```

### Step 4: Get vLLM image digest (GPU box)
```
docker pull vllm/vllm-openai:v0.28.0-ubuntu2404
docker inspect --format "{{index .RepoDigests 0}}" vllm/vllm-openai:v0.28.0-ubuntu2404
```
Paste the sha256: value into every container_digest PENDING in roster + qual matrix.

### Step 5: Start vLLM containers (GPU box, HF offline enforced)
Use the exact verified commands in `AIRBENCH_MODEL_SERVING_HANDOFF.md` §6.2/§6.3.
Key points: one 96 GB GPU so use `--gpus all` (not `device=0`/`device=1`); ports
stay loopback-only (`127.0.0.1:8001` / `127.0.0.1:8002`); models mount read-only
at `/model`; keep `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

### Step 6: Fill all PENDING: in roster, re-sign (dev machine)
Run this Python snippet after filling in all hash values:
```python
import hashlib, hmac, json, yaml
KEY = open('.airbench_signing_key', 'rb').read()
roster = yaml.safe_load(open('models/roster/v0/model_roster.yaml'))
# Sign over the whole document except the top-level `signature` key only.
# Do NOT drop registry_id/manifest_version/valid_until or verification fails.
body = {k: v for k, v in roster.items() if k != 'signature'}
sig = hmac.new(KEY, json.dumps(body, sort_keys=True,
               separators=(',',':')).encode(), hashlib.sha256).hexdigest()
print('signature:', sig)
```
Paste the output into the signature: field at the bottom of model_roster.yaml.

### Step 7: Set env vars and start Node (dev machine, PowerShell)
```powershell
$env:AIRBENCH_NODE_IDENTITY       = "node.demo.local"
$env:AIRBENCH_BEARER_TOKEN        = "<any-random-token>"
$env:AIRBENCH_DOMAIN_PACK_REF     = "refinery-psu-v0"
$env:AIRBENCH_CLEARANCE           = "internal"
$env:AIRBENCH_SUBJECT             = "demo.operator"
$env:AIRBENCH_POLICY_VERSION_HASH = "policy-v0.1"

# Enable the two-lane model router (no-egress env is enforced by the adapter)
$env:AIRBENCH_MODEL_SERVING_ENABLED = "1"
$env:AIRBENCH_MODEL_ROSTER_PATH     = "$PWD\models\roster\demo\two_endpoint_roster.yaml"
$env:AIRBENCH_MODEL_SIGNING_KEY_PATH= "$PWD\.airbench_signing_key"
$env:AIRBENCH_MODEL_STORE           = "C:\airbench-models"   # or the GPU-box path
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"

# These default correctly; only override if you used different ports
$env:AIRBENCH_MODEL_E2B_URL         = "http://127.0.0.1:18001"
$env:AIRBENCH_MODEL_12B_URL         = "http://127.0.0.1:18002"
$env:AIRBENCH_MODEL_E2B_TARGET_ID   = "airbench-gemma-4-e2b"
$env:AIRBENCH_MODEL_12B_TARGET_ID   = "airbench-gemma-4-12b"
$env:AIRBENCH_MODEL_E2B_SERVED_NAME = "airbench-gemma-4-e2b"
$env:AIRBENCH_MODEL_12B_SERVED_NAME = "airbench-gemma-4-12b"

# Enable deterministic Node planning + declared hardware admission so
# create -> authorize -> plan ready -> approve -> model-call works.
$env:AIRBENCH_TASK_PLANNER_ENABLED  = "1"
$env:AIRBENCH_HARDWARE_PROFILE_PATH = "$PWD\profiles\hardware\workstation_04.json"

# Enable the local retrieval stack (BGE-M3 embeddings + bge-reranker-v2-m3).
# These are already staged under airbench-models and already hashed in the roster.
$env:AIRBENCH_RETRIEVAL_ENABLED     = "1"
$env:AIRBENCH_RETRIEVAL_INDEX_PATH  = "$PWD\retrieval-index.json"
$env:AIRBENCH_EMBEDDING_DIR         = "bge-m3"
$env:AIRBENCH_RERANKER_DIR          = "bge-reranker-v2-m3"

.venv-deep\Scripts\python.exe -m airbench.node.server
```

> Retrieval runtime dependency note: `transformers` needs `huggingface-hub<1.0`,
> but the `hf` download CLI may have installed `1.31.0`. Once your downloads are
> finished, align the versions:
> ```powershell
> python -m pip install -U "huggingface-hub>=0.34.0,<1.0" sentence-transformers transformers torch
> python -m pip uninstall -y torchvision   # its pinned torch build mismatches and breaks transformers
> ```
> The code already disables TensorFlow for these local models and preloads the
> torch stack before File Intake (`pypdf`), which avoids a Windows native crash
> from the import order. Both BGE models were verified to load and embed
> (BGE-M3 dense dimension 1024). The real-model test is gated:
> ```powershell
> $env:AIRBENCH_TEST_REAL_BGE="1"
> python -m pytest tests/test_retrieval_runtime.py -q -k real_bge
> ```

---

## 4 - Invariant checklist before merge

- adapter_id = "airbench.vllm" in ALL roster vLLM targets (check: grep adapter_id models/roster)
- adapter_version = "0.5" in ALL roster vLLM targets
- HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 in BOTH Docker run commands
- No PENDING: or REPLACE_WITH_MEASURED: values remain in roster for production
- SSH forward open before Node starts
- vLLM /health returns 200 on both ports before Node starts
- pytest passes: .venv-deep\Scripts\python.exe -m pytest (expect 491 passed)

---

## 5 - Smoke test (after all setup complete)

```
curl http://127.0.0.1:18001/health                      # E2B -> 200
curl http://127.0.0.1:18002/health                      # 12B -> 200
curl http://127.0.0.1:8765/api/v1/node/readiness        # Node -> 200
curl http://127.0.0.1:8765/api/v1/node/model-serving    # both endpoints healthy+ready
curl http://127.0.0.1:8765/api/v1/node/retrieval        # bge-m3 + reranker ready
```

Governed command chain over the Node API (no auth shown for brevity; every
POST needs `Authorization: Bearer <token>` and the matching `actor`):

```
POST /api/v1/tasks                       -> create
POST /api/v1/tasks/{id}/authorize        -> Node plans + admits (planner enabled)
GET  /api/v1/tasks/{id}/plan             -> plan_state: ready
POST /api/v1/tasks/{id}/approve          -> task.plan.approved
POST /api/v1/tasks/{id}/model-call       -> routing decision + model.responded
GET  /api/v1/tasks/{id}/route-trace      -> desktop shows the selected lane
```
Each POST is a typed `NodeCommandEnvelope`; `expected_sequence` must equal the
current task event count and `idempotency_key` makes replays safe.
