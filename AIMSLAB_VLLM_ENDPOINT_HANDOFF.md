# AirBench vLLM Endpoint Handoff — `aimslab`

**Audience:** AirBench repository developers  
**Inference host:** `aims-dtu@aims-dtu-lab` through SSH alias `aimslab`  
**Prepared:** 2026-09-15  
**Scope:** Consume the already-deployed vLLM endpoints from local AirBench development machines.

## 1. Responsibility boundary

The inference-host setup is complete. The `aimslab` machine is an inference server only. It does not need an AirBench checkout, Python environment, or AirBench test suite.

Repository developers own:

- opening their own SSH tunnel to `aimslab`;
- integrating the endpoints into their local AirBench checkout;
- creating accurate signed roster/deployment records;
- adapting model-specific request and response behavior;
- running repository tests and the governed Node end-to-end test;
- implementing production authentication, attestation, supervision, and monitoring.

Do not ask the inference-host operator to install or run the AirBench repository.

## 2. Deployment inventory

| Purpose | Remote container | Remote loopback | Developer-local tunnel | Served model ID |
|---|---|---:|---:|---|
| Vision and general multimodal work | `airbench-vllm-qwen25-vl` | `127.0.0.1:8001` | `127.0.0.1:18001` | `airbench-qwen25-vl-7b` |
| Text reasoning and tool calling | `airbench-vllm-qwen3-8b` | `127.0.0.1:8002` | `127.0.0.1:18002` | `airbench-qwen3-8b` |

Both endpoints implement the OpenAI-compatible vLLM API:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

The vLLM ports are deliberately bound only to the inference host's loopback interface. Do not expose ports 8001 or 8002 publicly.

## 3. Pinned deployment facts

### Runtime

- Container image: `vllm/vllm-openai:v0.28.0-ubuntu2404`
- Pinned image digest: `sha256:f8fe15a8039343336945db10494eaad80ef941fe2b2a5fa6649fa38636051a65`
- vLLM: `0.28.0`
- PyTorch in image: `2.13.0+cu130`
- CUDA runtime in image: `13.0`
- Host GPU: NVIDIA TITAN RTX, 24 GB, compute capability 7.5
- Precision: FP16
- Quantization: AWQ
- Maximum model length configured on both services: 4096 tokens
- Maximum concurrent sequences configured on each service: 2
- KV cache configured on each service: 1 GiB

FlashAttention 2 is unavailable on compute capability 7.5. vLLM correctly falls back to Triton attention. That log message is expected and is not a deployment failure.

### Qwen2.5-VL

- Repository: `Qwen/Qwen2.5-VL-7B-Instruct-AWQ`
- Revision: `536a35794df8831aa814970ee8f89eff577e7718`
- Host artifact directory: `/media/aims-dtu/e6f3d549-768f-4cd9-bdd7-fe600ba3bf81/airbench-serving/models/qwen2.5-vl-7b-instruct-awq`
- Multimodal limit: one image and zero videos per prompt
- Image processor bounds: `min_pixels=200704`, `max_pixels=1003520`
- Weight shard SHA-256 values:
  - `model-00001-of-00002.safetensors`: `4f75e3de726546ee43620d1227d3596cd3ba0fdd19f11faeea71de578d2d1052`
  - `model-00002-of-00002.safetensors`: `dae4128bbfd2b8d489e838048edc0bbe6e31f269d9b96fa3effe11cc534b8f0c`
- `tokenizer.json` SHA-256: `5eee858c5123a4279c3e1f7b81247343f356ac767940b2692a928ad929543214`

### Qwen3-8B

- Repository: `Qwen/Qwen3-8B-AWQ`
- Revision: `4da05a8edb55c6046cce958586c33b61da07bb79`
- Host artifact directory: `/media/aims-dtu/e6f3d549-768f-4cd9-bdd7-fe600ba3bf81/airbench-serving/models/qwen3-8b-awq`
- vLLM reasoning parser: `qwen3`
- vLLM tool-call parser: `hermes`
- Automatic tool choice: enabled
- Weight shard SHA-256 values:
  - `model-00001-of-00002.safetensors`: `6e112429856bc65e3837a9f38d6f6b71ffdda832cb46299a12f4fa8f6352516e`
  - `model-00002-of-00002.safetensors`: `20c2d6366ab85c90786ccdd829cd2b9e7d30ef3b2ebbb998280e7e4014b542ff`
- `tokenizer.json` SHA-256: `aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4`

## 4. SSH access

Credentials are distributed separately. A developer's local `~/.ssh/config` should contain:

```sshconfig
Host aimslab
    HostName ssh.aimsdtu.in
    User aims-dtu
    PasswordAuthentication yes
    ProxyCommand cloudflared access ssh --hostname %h
```

Where possible, production access should replace password authentication with individually issued SSH keys.

## 5. Open the model tunnels

Run this command on the developer machine that runs the AirBench Node. Do not run it inside an existing `aimslab` shell.

```bash
ssh -NT \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18001:127.0.0.1:8001 \
  -L 127.0.0.1:18002:127.0.0.1:8002 \
  aimslab
```

Keep this terminal open while developing or demonstrating AirBench.

The resulting path is:

```text
local AirBench Node
  -> 127.0.0.1:18001 -> SSH -> aimslab 127.0.0.1:8001 -> Qwen2.5-VL
  -> 127.0.0.1:18002 -> SSH -> aimslab 127.0.0.1:8002 -> Qwen3-8B
```

## 6. Connectivity checks

Run these checks on the developer machine after opening the tunnel:

```bash
curl -sS --fail --write-out '\nQWEN25_VL HTTP %{http_code}\n' \
  http://127.0.0.1:18001/health

curl -sS --fail --write-out '\nQWEN3 HTTP %{http_code}\n' \
  http://127.0.0.1:18002/health

curl -sS --fail http://127.0.0.1:18001/v1/models | python3 -m json.tool
curl -sS --fail http://127.0.0.1:18002/v1/models | python3 -m json.tool
```

Success criteria:

- both health requests return HTTP 200;
- port 18001 reports `airbench-qwen25-vl-7b`;
- port 18002 reports `airbench-qwen3-8b`.

If Python is unavailable, omit `| python3 -m json.tool`; the raw JSON is sufficient.

## 7. Direct API examples

### Qwen2.5-VL text request

```bash
curl -sS --fail --max-time 300 \
  http://127.0.0.1:18001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "airbench-qwen25-vl-7b",
    "messages": [{
      "role": "user",
      "content": "Reply with exactly AIRBENCH_VL_OK and nothing else."
    }],
    "temperature": 0,
    "max_tokens": 64
  }'
```

### Qwen3 deterministic non-thinking request

```bash
curl -sS --fail --max-time 300 \
  http://127.0.0.1:18002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "airbench-qwen3-8b",
    "messages": [{
      "role": "user",
      "content": "Reply with exactly AIRBENCH_QWEN3_OK and nothing else."
    }],
    "chat_template_kwargs": {"enable_thinking": false},
    "temperature": 0,
    "max_tokens": 64
  }'
```

The `chat_template_kwargs` setting is important for deterministic demo requests. If reasoning mode is intentionally enabled, the AirBench adapter must explicitly handle vLLM's separate reasoning field and its additional token/latency budget.

## 8. Required AirBench repository integration

These tasks belong to the repository developers.

### 8.1 Endpoint configuration

The checked-in `ModelServingConfig` currently exposes legacy two-lane environment names. They may be overridden temporarily:

```bash
export AIRBENCH_MODEL_E2B_URL=http://127.0.0.1:18001
export AIRBENCH_MODEL_E2B_SERVED_NAME=airbench-qwen25-vl-7b

export AIRBENCH_MODEL_12B_URL=http://127.0.0.1:18002
export AIRBENCH_MODEL_12B_SERVED_NAME=airbench-qwen3-8b
```

`AIRBENCH_MODEL_E2B_TARGET_ID` and `AIRBENCH_MODEL_12B_TARGET_ID` must exactly match the `target_id` values in the new signed Qwen roster. Do not put served model names into these fields unless the roster deliberately uses the same values.

For maintainability, replace the E2B/12B-specific configuration with a typed endpoint list or mapping. The current names are legacy labels, not accurate descriptions of these models.

### 8.2 Create a dedicated Qwen deployment roster

Do not reuse or rename the signed Gemma demo roster. Create a dedicated two-target roster containing the actual:

- repositories and pinned revisions listed above;
- artifact filenames and combined artifact digests;
- tokenizer, chat-template, and image-processor hashes where required;
- image/runtime digest;
- `vllm-0.28.0` runtime and `airbench.vllm` adapter version;
- 4096-token deployed context limit;
- supported modalities and roles;
- target-specific tool parser;
- qualification records and expiry;
- hardware profile for the Titan RTX deployment.

Suggested role split:

- Qwen2.5-VL: `vision_worker`, text and image modalities;
- Qwen3-8B: `reasoning`, `lead_worker`, and any tool/code role that has actually passed the corresponding evaluation.

Candidate demo signatures are not production qualification. Production roles require measured evaluation evidence.

### 8.3 Resolve remote artifact verification correctly

The current `ModelRegistry.load_roster_file()` verifies model bytes under the Node's local `AIRBENCH_MODEL_STORE`. That does not match this deployment: the AirBench Node is local to each developer, while the model bytes live only on `aimslab`.

Do not create dummy local model files, skip hashes silently, or claim that `/v1/models` proves artifact integrity.

Choose and document one legitimate design:

1. **Recommended:** create a signed deployment attestation on `aimslab`. It should bind the target ID, repository, revision, artifact hashes, container digest, served model ID, endpoint policy, and timestamp. The local Node verifies that signed attestation plus live endpoint identity without downloading the weights.
2. Run the governed AirBench Node on the inference host and tunnel only the Node API to developer machines.
3. Mount or copy the verified model store to the Node machine. This is acceptable but operationally inefficient and defeats the remote-serving benefit.

Any bypass of artifact verification must be explicit, demo-only, fail-closed by default, and impossible to activate accidentally in production.

### 8.4 Bind model-specific adapter behavior

The adapter created for each endpoint must use the selected roster target's configuration.

- Pass `ToolCallParserRegistry.get(target.tool_call_parser)` to `VllmAdapter`.
- Qwen3 should use the Hermes parser for native tool calls in this deployment.
- Add a target-specific request option for `chat_template_kwargs.enable_thinking`.
- Use `enable_thinking=false` for deterministic demo traffic unless a task explicitly requests reasoning mode.
- Advertise only capabilities and modalities actually present in the signed target.
- Ensure vision content reaches only Qwen2.5-VL.
- Do not let endpoint labels such as `ep.e2b.local` or `ep.12b.local` become semantic routing inputs.

The currently checked-in builder creates endpoint-specific adapters, which solves the prior shared-adapter collision, but it does not yet bind the target's tool parser.

### 8.5 Repository validation expected from developers

At minimum, add or update tests for:

- two targets with distinct endpoint bindings;
- readiness identity mismatch failing closed;
- Qwen2.5-VL text and image request encoding;
- Qwen3 deterministic non-thinking payload construction;
- native Qwen3/Hermes tool-call normalization;
- signed remote deployment-attestation acceptance;
- invalid, stale, mismatched, or missing attestation rejection;
- tunnel loss and endpoint timeout behavior;
- routing by role and modality;
- no direct frontend-to-vLLM traffic;
- no prompt, credential, or SSH secret leakage into logs or ledger events.

After unit tests, run one governed Node flow through `POST /api/v1/tasks/{id}/model-call` and verify the route trace and ledger events. Direct `curl` calls to vLLM prove endpoint behavior, not full AirBench governance.

## 9. Verified deployment evidence

The following checks have already passed on 2026-09-15:

- Docker GPU visibility and FP16 CUDA matrix multiplication;
- exact model revision and Hugging Face LFS hash verification;
- both `/health` endpoints returning HTTP 200;
- both `/v1/models` endpoints returning their expected served IDs;
- Qwen2.5-VL text generation;
- Qwen2.5-VL image recognition using a red-square test image;
- Qwen3 deterministic non-thinking generation;
- Qwen3 native tool-call generation;
- simultaneous four-request load across both services.

Concurrent test result:

- four of four requests passed;
- Qwen2.5-VL image request: 2.392 seconds;
- Qwen2.5-VL 2090-token text request: 2.712 seconds;
- two simultaneous Qwen3 approximately 2084-token requests: 2.902 and 2.905 seconds;
- peak GPU utilization: 100%;
- peak GPU memory: 16,176 MiB;
- minimum free GPU memory: 7,839 MiB;
- peak temperature: 58 degrees C;
- peak measured power: 250.49 W;
- both endpoints remained healthy after the test.

This qualifies the hosting layer for integration and a controlled demo. It is not evidence that the AirBench repository integration or model-role qualification is complete.

## 10. Demo versus production

| Area | Controlled demo | Production |
|---|---|---|
| Connectivity | Developer opens a foreground SSH tunnel | Supervised tunnel/VPN or another authenticated private transport with automatic recovery |
| Authentication | Credentials distributed separately; password may be temporarily used | Individual SSH keys, rotation, revocation, least privilege, and audited access |
| vLLM exposure | Loopback only | Keep private; never expose unauthenticated vLLM directly to the Internet |
| Containers | Manually launched and observed | Restart policy plus rootless Docker/systemd supervision and boot verification |
| Roster | Clearly marked candidate records may support a demo | Signed, measured, non-stale qualification records only |
| Artifact integrity | Explicit demo attestation may be accepted under a demo policy | Signed host attestation with replay protection, identity binding, expiry, and audit evidence |
| Capacity | Two sequences per endpoint; 4096-token context; measured demo load | Load test against expected concurrency, queue limits, timeouts, and back-pressure policy |
| Monitoring | Manual health checks and `nvidia-smi` | Automated endpoint, GPU, temperature, memory, latency, error-rate, disk, and tunnel monitoring |
| Availability | Operator keeps the host and tunnel running | Documented recovery, restart, update, rollback, and incident procedures |
| Qualification | Functional endpoint checks | Role-specific quality, safety, security, and regression evaluation |

## 11. Operational cautions

- Do not modify, restart, or prune the unrelated `quda_*` containers.
- Do not run a broad `docker system prune`; the host contains unrelated images, volumes, and build cache.
- The root filesystem that stores rootless Docker data was approximately 97% full after downloading the vLLM image. Monitor it carefully.
- Model files live on the large external ext4 volume, not the nearly full root filesystem.
- The running AirBench containers were initially created for qualification. Before declaring production readiness, record their complete inspected configuration and apply a supervised restart policy through an approved operations change.
- Keep the vLLM image digest, model revisions, launch parameters, and signed deployment attestation synchronized. A change to any one of them is a new deployment version.

## 12. Completion criteria for the repository team

Repository integration is complete only when:

1. both tunneled endpoints are healthy and identity-checked;
2. the Node loads a truthful signed Qwen deployment roster/attestation;
3. model artifacts are verified without pretending remote files are local;
4. role, modality, clearance, risk, and hardware eligibility fail closed;
5. Qwen3 tool calls and thinking mode are handled intentionally;
6. a governed Node task routes to each applicable model;
7. route decisions and responses appear in the append-only ledger;
8. the desktop calls only the Node, never vLLM directly;
9. tunnel failure produces a typed unavailable/degraded state;
10. demo-only switches cannot be enabled accidentally in production.

## 13. Current repository reference

The locally inspected AirBench checkout was:

- branch: `main`
- commit: `897a5237e9910307b26ea2c5ec3d74fb322a9719`
- worktree: clean at inspection time
- no repository files were changed as part of the inference-host setup

There was no assigned GitHub issue for the Qwen remote-deployment integration. Developers should create or identify the governing issue and follow the repository's `airbench-start-task`, planning, testing, security, router, review, and finish workflows before implementation.
