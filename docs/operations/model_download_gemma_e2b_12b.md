# Two-Endpoint Gemma Demo: Download, Hash & Roster-Fill Guide

> All commands run on **the GPU box** (adjust hostname below) unless marked *dev machine*.

## 1 — SSH loopback forward (run on dev machine)

```powershell
# Forward both model ports from workstation-04 to your local machine.
# Keep this terminal open while the Node is running.
ssh -N -L 18001:127.0.0.1:18001 -L 18002:127.0.0.1:18002 user@workstation-04
```

---

## 2 — Download models (run on workstation-04)

> The handoff (`AIRBENCH_MODEL_SERVING_HANDOFF.md` §5.2) records both models as
> already staged under `/home/workstation-04/airbench-serving/models`. Check
> first; only re-download if they are missing. Use the exact QAT W4A16
> compressed-tensors repositories and pinned revisions — not the base
> `google/gemma-4-*-it` repos.

```bash
export AIRBENCH_SERVING_ROOT=/home/workstation-04/airbench-serving
mkdir -p "$AIRBENCH_SERVING_ROOT/models"

# Gemma is gated: accept the license and authenticate once.
# huggingface-cli login        # paste a read token with Gemma access

# Gemma 4 E2B — Efficient lane
huggingface-cli download google/gemma-4-E2B-it-qat-w4a16-ct \
    --revision 971342c08f607aa7779983f6b5289778b5d271a7 \
    --local-dir "$AIRBENCH_SERVING_ROOT/models/gemma-4-e2b-it-w4a16-ct"

# Gemma 4 12B — Capable lane
huggingface-cli download google/gemma-4-12B-it-qat-w4a16-ct \
    --revision 1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee \
    --local-dir "$AIRBENCH_SERVING_ROOT/models/gemma-4-12b-it-w4a16-ct"
```

Expected `model.safetensors` SHA-256 (from the handoff):
- E2B: `93177bfc1b53823f2e01c7cebc3b94f65d189e373a647d086112f614ba448ab9` (8,316,306,646 bytes)
- 12B: `60b6e3989502969d8ae04185d72ecbbc7db63978d5af747a493d53895aa6bfa3` (10,264,229,896 bytes)

---

## 3 — Hash each artifact file

`AIRBENCH_MODEL_STORE` must be the directory that **contains** the two model
folders (`gemma-4-e2b-it-w4a16-ct`, `gemma-4-12b-it-w4a16-ct`). Run from the
repo root so `scripts\airbench_hash.py` resolves.

Linux / GPU box:
```bash
export AIRBENCH_MODEL_STORE=/home/workstation-04/airbench-serving/models
python3 scripts/airbench_hash.py --target airbench-gemma-4-e2b --target airbench-gemma-4-12b
```
Windows (dev machine):
```powershell
$env:AIRBENCH_MODEL_STORE = "C:\airbench-models"
python scripts\airbench_hash.py --target airbench-gemma-4-e2b --target airbench-gemma-4-12b
```
The tool prints `artifact_digest`, `local_storage_hash`, `tokenizer_digest`, and
`chat_template_digest` and writes `scripts\airbench_hashes_output.yaml`. Copy
those into the roster `PENDING:` fields. It hashes `model.safetensors`,
`tokenizer.json`, and `chat_template.jinja` — the exact files the registry
re-verifies (`AIRBENCH_MODEL_STORE` must be the same tree the Node reads).

Manual cross-check (PowerShell returns uppercase; AirBench needs lowercase):
```powershell
(Get-FileHash -Algorithm SHA256 "C:\airbench-models\gemma-4-e2b-it-w4a16-ct\model.safetensors").Hash.ToLower()
```
Expected E2B `model.safetensors` = `93177bfc…448ab9`; 12B = `60b6e398…a6bfa3`.
The 12B `tokenizer.json` and `chat_template.jinja` may differ from any other
checkpoint — always use your measured values.

---

## 4 — Get the vLLM container digest (run on workstation-04)

```bash
# The handoff (§5.1) records the running image as vLLM 0.28.0. Pull if needed.
docker pull vllm/vllm-openai:v0.28.0-ubuntu2404

# Get the immutable registry digest (pin this, not the mutable tag).
docker inspect --format='{{index .RepoDigests 0}}' vllm/vllm-openai:v0.28.0-ubuntu2404
# Example output: vllm/vllm-openai@sha256:abc123...
# Copy the sha256: part into serving.container_digest in model_roster.yaml.

# Local image ID already observed on the GPU box (handoff §5.1):
# sha256:f8fe15a8039343336945db10494eaad80ef941fe2b2a5fa6649fa38636051a65
```

---

## 5 — Start vLLM endpoints (run on workstation-04)

> **Use the exact launch commands in `AIRBENCH_MODEL_SERVING_HANDOFF.md` §6.2
> (E2B) and §6.3 (12B).** Those are the verified commands. The important
> corrections to earlier drafts are:
>
> - one 96 GB GPU: use `--gpus all`; do **not** use `--gpus device=0` / `device=1`.
> - image is `vllm/vllm-openai:v0.28.0-ubuntu2404`.
> - model paths are `$AIRBENCH_SERVING_ROOT/models/gemma-4-e2b-it-w4a16-ct` and
>   `.../gemma-4-12b-it-w4a16-ct`, mounted read-only at `/model`.
> - keep `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; keep `--cap-drop ALL`,
>   `--security-opt no-new-privileges=true`, the host UID/GID, and the writable
>   `/cache` mount.
> - ports stay loopback-only: `-p 127.0.0.1:8001:8000` (E2B) and
>   `-p 127.0.0.1:8002:8000` (12B).

> **No-egress requirement**: both containers have `HF_HUB_OFFLINE=1` and
> `TRANSFORMERS_OFFLINE=1`. This is verified by `VllmAdapter` before any call.

---

## 6 — Fill in the roster, then re-sign (run on dev machine)

After filling all `PENDING:` and `REPLACE_WITH_MEASURED:` values:

```python
# Re-sign model_roster.yaml
import hashlib, hmac, json, yaml

KEY = open('.airbench_signing_key', 'rb').read()   # keep secret
roster = yaml.safe_load(open('models/roster/v0/model_roster.yaml'))
# ModelRegistry.load_roster_file signs over the whole document EXCEPT the
# top-level `signature` key. Do NOT remove registry_id/manifest_version/valid_until.
body = {k: v for k, v in roster.items() if k != 'signature'}
canonical = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
sig = hmac.new(KEY, canonical, hashlib.sha256).hexdigest()
print('signature:', sig)
# Paste the output into the signature: field at the bottom of model_roster.yaml
```

---

## 7 — Fill in qualification matrix, then re-sign certificates

For each `PENDING:cert-gemma4-*` entry in
`qualifications/model_qualification_matrix.yaml`:

1. Run the qualification harness:
   ```bash
   python -m airbench.qualify \
       --target airbench-gemma-4-e2b \
       --role reasoning \
       --fixtures tests/fixtures/
   ```
2. Fill in the `benchmark_scores`, `pass_rates`, `safety_results`, and
   `qualified_at` from the harness report.
3. Sign the certificate using the same signing key pattern as step 6.

---

## 8 — Environment variables for the AirBench Node (run on dev machine)

```powershell
# Required
$env:AIRBENCH_NODE_IDENTITY       = "node.demo.local"
$env:AIRBENCH_BEARER_TOKEN        = "<your-token>"
$env:AIRBENCH_DOMAIN_PACK_REF     = "refinery-psu-v0"
$env:AIRBENCH_CLEARANCE           = "internal"
$env:AIRBENCH_SUBJECT             = "demo.operator"
$env:AIRBENCH_POLICY_VERSION_HASH = "<your-policy-hash>"

# Model serving (defaults point to loopback forwards from step 1)
$env:AIRBENCH_MODEL_E2B_URL         = "http://127.0.0.1:18001"
$env:AIRBENCH_MODEL_12B_URL         = "http://127.0.0.1:18002"
$env:AIRBENCH_MODEL_E2B_TARGET_ID   = "airbench-gemma-4-e2b"
$env:AIRBENCH_MODEL_12B_TARGET_ID   = "airbench-gemma-4-12b"
$env:AIRBENCH_MODEL_E2B_SERVED_NAME = "airbench-gemma-4-e2b"
$env:AIRBENCH_MODEL_12B_SERVED_NAME = "airbench-gemma-4-12b"
```

