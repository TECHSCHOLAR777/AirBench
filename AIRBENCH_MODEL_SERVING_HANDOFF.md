
# AirBench Model Serving and Repository Integration Handoff

**Audience:** AirBench developers integrating the desktop application, AirBench Node, model router, and the already deployed vLLM endpoints  
**SSH alias:** `mmmut-server`  
**Model host:** `workstation-04`  
**Model-serving root:** `/home/workstation-04/airbench-serving`  
**Document date:** 2026-09-13  
**Credentials:** supplied separately; never add SSH keys, passwords, tokens, or private signing keys to this document or the repository

## 1. Outcome and current status

Two open-weight multimodal Gemma models are downloaded, integrity-checked, running through vLLM, and reachable only through the model host's loopback interface. Both OpenAI-compatible endpoints have passed health, model-discovery, and chat-completion checks.

| Lane | Model | vLLM served name | Remote loopback URL | SSH-forwarded URL | Status |
|---|---|---|---|---|---|
| Efficient | Gemma 4 E2B instruction QAT W4A16 | `airbench-gemma-4-e2b` | `http://127.0.0.1:8001` | `http://127.0.0.1:18001` | Verified |
| Capable | Gemma 4 12B instruction QAT W4A16 | `airbench-gemma-4-12b` | `http://127.0.0.1:8002` | `http://127.0.0.1:18002` | Verified |

The model serving layer is ready for application integration. The repository is **not yet fully integrated with both live endpoints**. In particular, the current `ModelRouter` stores adapters by `adapter_id`, while both vLLM instances correctly identify as `airbench.vllm`. That data structure cannot distinguish two endpoints using the same adapter implementation. Section 8 specifies the required repository change.

The current setup is appropriate for a controlled demo. It is not yet evidence of a production air-gapped deployment because the Docker bridge can still have outbound connectivity, the endpoints do not have API authentication, service lifecycle is manual, and the new exact model targets have not completed AirBench qualification and signing.

## 2. Architectural boundary: what connects to what

AirBench is a desktop application backed by an organization-operated AirBench Node. The desktop must not call vLLM directly. The Node owns orchestration, policy, file intake, routing, verification, tool authorization, and audit records; vLLM only performs model inference.

```text
AirBench Desktop
       |
       | AirBench Node protocol
       v
AirBench Node
  |- file intake / clearance / taint
  |- orchestrator and verification loop
  |- resource admission and model router
  |- append-only provenance ledger
  `- vLLM backend adapters
          | OpenAI-compatible HTTP, internal only
          +--> Gemma 4 E2B  :8001
          `--> Gemma 4 12B  :8002
```

Do not put model-selection logic, raw model credentials, or vLLM URLs in the React desktop UI. The UI connects to a Node profile. The Node selects a qualified target and invokes it through the backend adapter contract.

## 3. Important ownership and safety rules

The server is shared. Follow these rules every time:

1. Never stop, restart, signal, reconfigure, or remove a process or container unless its name begins with `airbench-` and the change is part of an approved AirBench task.
2. The existing host Ollama process is owned by another workload. It has been seen as PID `358130`, serving `nomic-embed-text:latest` on `127.0.0.1:11434`, and using about 986 MiB of VRAM. The PID may change after a restart; identify by command and ownership, not only by PID.
3. REALPDE jobs have also used this GPU. If they reappear, do not kill them. Queue or postpone an AirBench model restart if memory is insufficient.
4. Do not publish ports `8001` or `8002` on `0.0.0.0`, a public IP, a router, Cloudflare Tunnel, or a reverse proxy. They currently have no application-level API key.
5. Never run `docker system prune`, broad `docker stop`, broad `docker rm`, or GPU process-kill commands on this shared workstation.
6. Model files are mounted read-only into serving containers. Keep that property.
7. Capture logs before replacing a failed AirBench container. Removing a container discards its local container log.

## 4. Connect and verify the existing deployment

### 4.1 Log in

From a developer machine with the separately supplied SSH configuration:

```bash
ssh mmmut-server
```

On the remote machine:

```bash
export AIRBENCH_SERVING_ROOT=/home/workstation-04/airbench-serving

hostname
nvidia-smi
docker ps --filter name=airbench-vllm
curl -sS --fail --write-out '\nE2B HTTP %{http_code}\n' http://127.0.0.1:8001/health
curl -sS --fail --write-out '\n12B HTTP %{http_code}\n' http://127.0.0.1:8002/health
```

Expected result: both health requests return `HTTP 200`, and the two containers are `Up`.

Confirm the identities exposed by vLLM:

```bash
curl -sS --fail http://127.0.0.1:8001/v1/models | python3 -m json.tool
curl -sS --fail http://127.0.0.1:8002/v1/models | python3 -m json.tool
```

Expected model IDs are `airbench-gemma-4-e2b` and `airbench-gemma-4-12b` respectively. A healthy endpoint exposing the wrong model is **not ready** for AirBench.

### 4.2 Inspect without disrupting other work

```bash
docker ps -a \
  --filter name=airbench-vllm-e2b \
  --filter name=airbench-vllm-12b

docker logs --tail 200 airbench-vllm-e2b
docker logs --tail 200 airbench-vllm-12b

nvidia-smi \
  --query-compute-apps=pid,process_name,used_memory \
  --format=csv

nvidia-smi \
  --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.free,power.draw \
  --format=csv
```

Do not infer process ownership from `docker ps` alone: Ollama and some research workloads run directly on the host.

### 4.3 Create the SSH tunnel for local development

Run this on the developer machine, not inside the SSH session:

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18001:127.0.0.1:8001 \
  -L 127.0.0.1:18002:127.0.0.1:8002 \
  mmmut-server
```

Keep that terminal open. In another local terminal:

```bash
curl -sS --fail --write-out '\nE2B HTTP %{http_code}\n' http://127.0.0.1:18001/health
curl -sS --fail --write-out '\n12B HTTP %{http_code}\n' http://127.0.0.1:18002/health
```

Both calls have already been verified to return HTTP 200. If the local port is occupied, choose another local port but keep the remote side unchanged, for example `-L 28001:127.0.0.1:8001`.

### 4.4 Smoke-test chat completions

E2B through the local tunnel:

```bash
curl -sS --fail --max-time 180 \
  http://127.0.0.1:18001/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "airbench-gemma-4-e2b",
    "messages": [{"role": "user", "content": "Reply with exactly AIRBENCH_OK and nothing else."}],
    "temperature": 0,
    "max_tokens": 64
  }' | python3 -m json.tool
```

12B through the local tunnel:

```bash
curl -sS --fail --max-time 180 \
  http://127.0.0.1:18002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "airbench-gemma-4-12b",
    "messages": [{"role": "user", "content": "Reply with exactly AIRBENCH_12B_OK and nothing else."}],
    "temperature": 0,
    "max_tokens": 64
  }' | python3 -m json.tool
```

These exact tests have passed.

## 5. Verified deployment inventory

### 5.1 Host and runtime

| Item | Verified value |
|---|---|
| OS | Ubuntu 24.04.3 LTS |
| Kernel | Linux 6.17.0-1032-oem |
| GPU | NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition |
| GPU UUID | `GPU-c68aba4d-f69e-6f8d-6cac-622c76d348b7` |
| Compute capability | 12.0 |
| VRAM reported by `nvidia-smi` | 97,887 MiB |
| NVIDIA driver | 595.84 |
| Host CUDA compatibility | 13.2 |
| Host RAM | approximately 125 GiB |
| NVIDIA Container Toolkit | 1.20.0 |
| Container image | `vllm/vllm-openai:v0.28.0-ubuntu2404` |
| Local image ID | `sha256:f8fe15a8039343336945db10494eaad80ef941fe2b2a5fa6649fa38636051a65` |
| Local image size | 8,634,217,765 bytes |
| vLLM | 0.28.0 |
| PyTorch in image | 2.13.0+cu130 |
| CUDA runtime in image | 13.0 |

The local image ID above is evidence about the inspected local image. Before production qualification, also capture and pin the registry `RepoDigest`; do not treat a mutable image tag as an immutable supply-chain identity.

### 5.2 Model artifacts

#### Gemma 4 E2B

- Source repository: `google/gemma-4-E2B-it-qat-w4a16-ct`
- Pinned Hugging Face revision: `971342c08f607aa7779983f6b5289778b5d271a7`
- Local directory: `/home/workstation-04/airbench-serving/models/gemma-4-e2b-it-w4a16-ct`
- `model.safetensors` size: 8,316,306,646 bytes
- `model.safetensors` SHA-256: `93177bfc1b53823f2e01c7cebc3b94f65d189e373a647d086112f614ba448ab9`
- `config.json` SHA-256: `d1b2018bd9bd9459ce40b2998c0e32ab7df693053520cfbccdcf47a93cd4410d7`
- `tokenizer.json` SHA-256: `cc8d3a0ce36466ccc1278bf987df5f71db1719b9ca6b4118264f45cb627bfe0f`
- `tokenizer_config.json` SHA-256: `b8045a4576903e86903291d5cbdd4adfc8859e9ce3c98621bdbd957f73ed394b`
- `chat_template.jinja` SHA-256: `0a2c8073c878ab1da004bee933a998606537bbb62016310352c7285c3f01c5b5`

#### Gemma 4 12B

- Source repository: `google/gemma-4-12B-it-qat-w4a16-ct`
- Pinned Hugging Face revision: `1d2c2d7f2466070e69d6fb3fd5ce9a7d75f2f6ee`
- Local directory: `/home/workstation-04/airbench-serving/models/gemma-4-12b-it-w4a16-ct`
- `model.safetensors` size: 10,264,229,896 bytes
- `model.safetensors` SHA-256: `60b6e3989502969d8ae04185d72ecbbc7db63978d5af747a493d53895aa6bfa3`
- Size and SHA-256 were checked against the pinned Hugging Face LFS metadata.

The weight hash alone is not a complete AirBench model identity. Qualification must hash a deterministic manifest containing every required artifact: weights, config, tokenizer, processor configuration, generation configuration, chat template, quantization metadata, runtime image digest, launch settings, prompt/tool schemas, hardware profile, and qualification pack version.

## 6. Service lifecycle and reproducible launch commands

The existing containers have no automatic restart policy. This was deliberate for a shared laboratory GPU: a workstation reboot must not cause AirBench to seize GPU memory before other owners coordinate usage.

### 6.1 Normal restart of existing containers

First inspect GPU users and container state. If the two containers merely stopped and their definitions are still present:

```bash
docker start airbench-vllm-e2b
docker start airbench-vllm-12b
```

Start one, wait until `/health` returns 200, then start the other. If other owners are using most of the GPU, start only the target needed for the test.

### 6.2 Recreate E2B only when necessary

Do not run this while a container with the same name exists. If recreation is approved, first save its logs and inspect the existing configuration. Remove only that exact AirBench container, never unrelated containers.

```bash
export AIRBENCH_SERVING_ROOT=/home/workstation-04/airbench-serving

docker run -d \
  --name airbench-vllm-e2b \
  --gpus all \
  --user "$(id -u):$(id -g)" \
  --cap-drop ALL \
  --security-opt no-new-privileges=true \
  --shm-size 8g \
  -p 127.0.0.1:8001:8000 \
  -e HOME=/cache \
  -e XDG_CACHE_HOME=/cache \
  -e HF_HOME=/cache/huggingface \
  -e TORCH_HOME=/cache/torch \
  -e HF_HUB_DISABLE_TELEMETRY=1 \
  -e VLLM_NO_USAGE_STATS=1 \
  -e DO_NOT_TRACK=1 \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  -v "$AIRBENCH_SERVING_ROOT/models/gemma-4-e2b-it-w4a16-ct:/model:ro" \
  -v "$AIRBENCH_SERVING_ROOT/cache:/cache" \
  vllm/vllm-openai:v0.28.0-ubuntu2404 \
  --model /model \
  --served-model-name airbench-gemma-4-e2b \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --kv-cache-memory-bytes 4294967296 \
  --gpu-memory-utilization 0.70 \
  --max-model-len 8192 \
  --max-num-seqs 4 \
  --limit-mm-per-prompt '{"image":2}' \
  --enforce-eager
```

### 6.3 Recreate 12B only when necessary

```bash
export AIRBENCH_SERVING_ROOT=/home/workstation-04/airbench-serving

docker run -d \
  --name airbench-vllm-12b \
  --gpus all \
  --user "$(id -u):$(id -g)" \
  --cap-drop ALL \
  --security-opt no-new-privileges=true \
  --shm-size 8g \
  -p 127.0.0.1:8002:8000 \
  -e HOME=/cache \
  -e XDG_CACHE_HOME=/cache \
  -e HF_HOME=/cache/huggingface \
  -e TORCH_HOME=/cache/torch \
  -e HF_HUB_DISABLE_TELEMETRY=1 \
  -e VLLM_NO_USAGE_STATS=1 \
  -e DO_NOT_TRACK=1 \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  -v "$AIRBENCH_SERVING_ROOT/models/gemma-4-12b-it-w4a16-ct:/model:ro" \
  -v "$AIRBENCH_SERVING_ROOT/cache:/cache" \
  vllm/vllm-openai:v0.28.0-ubuntu2404 \
  --model /model \
  --served-model-name airbench-gemma-4-12b \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --kv-cache-memory-bytes 4294967296 \
  --gpu-memory-utilization 0.70 \
  --max-model-len 8192 \
  --max-num-seqs 4 \
  --limit-mm-per-prompt '{"image":2}' \
  --enforce-eager
```

`--kv-cache-memory-bytes` fixes the serving cache at 4 GiB per model. In vLLM 0.28 this overrides `--gpu-memory-utilization` for the actual KV-cache size, but the utilization value still matters during startup memory checks. The 12B server initially failed the default 0.92 free-memory guard while the GPU was shared; `0.70` resolved it.

`--enforce-eager` is a conservative choice for predictable memory during this demo. It gives up CUDA-graph/compile optimizations. Change it only after repeatable memory and concurrency benchmarks.

### 6.4 Intentional shutdown

Only when authorized:

```bash
docker stop airbench-vllm-e2b airbench-vllm-12b
```

This stops only AirBench containers and leaves Ollama and other host workloads untouched. Do not add a container-removal command to routine shutdown instructions.

## 7. Demo integration topology

There are two valid development arrangements. Pick one and record it in the demo evidence.

### Option A: fastest developer integration

Run the repository and AirBench Node on the developer machine. Keep the two SSH forwards from Section 4 open. Configure Node-side vLLM adapters with:

```text
E2B  base URL: http://127.0.0.1:18001
E2B  model:    airbench-gemma-4-e2b

12B  base URL: http://127.0.0.1:18002
12B  model:    airbench-gemma-4-12b
```

The desktop still talks only to its local AirBench Node. The Node talks through SSH-forwarded loopback ports to vLLM.

```text
Developer machine                         mmmut-server
+------------------------------+          +-------------------------+
| Desktop -> local Node         |  SSH     | 127.0.0.1:8001 -> E2B  |
| Node -> 127.0.0.1:18001 ------+--------->| 127.0.0.1:8002 -> 12B  |
| Node -> 127.0.0.1:18002 ------+--------->|                         |
+------------------------------+          +-------------------------+
```

Use this for rapid iteration. Describe it honestly as a secured lab/demo transport, not as proof that the entire system is installed within one organization's air-gapped boundary.

### Option B: stronger final demo

Run the AirBench Node on `mmmut-server` beside vLLM. The Node calls `127.0.0.1:8001` and `127.0.0.1:8002`. Expose only the Node to the desktop through one SSH tunnel. For example, if the Node listens on remote loopback port 9443:

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:19443:127.0.0.1:9443 \
  mmmut-server
```

The desktop Node profile then points to `http://127.0.0.1:19443` using the repository's approved loopback transport rules. Use the actual Node port and approved profile generated by the project; `9443`/`19443` are examples until the team's Node launch issue fixes them.

This is the recommended final demo shape because raw model endpoints stay behind the Node boundary.

## 8. Required repository integration work

Work in the repository must follow `AirBench/AGENTS.md`: obtain an assigned GitHub issue, start from current `main`, use the required task-start and planning workflow, keep the scope narrow, run the required validation, and submit through the repository's review process. Do not copy credentials, private keys, or machine-specific secrets into Git.

### 8.1 Preserve the existing contract boundary

Relevant implementation and design files include:

- `src/contracts/adapters/vllm_adapter.py`
- `src/contracts/model/router.py`
- `src/contracts/model/model_registry.py`
- `src/airbench/node/api.py`
- `docs/foundations/07_serving_and_routing.md`
- `docs/runtime/backend_adapter_contract.md`
- `docs/assurance/model_qualification_framework.md`
- `docs/assurance/sovereignty_and_security.md`
- `docs/delivery/deployment_and_scale.md`
- `models/roster/v0/model_roster.yaml`
- `profiles/hardware/target_96gb_vram.yaml`
- `benchmarks/model_hardware_results.yaml`
- `benchmarks/backend_compatibility_matrix.yaml`

The existing `VllmAdapter` already supports health/readiness checks, OpenAI-compatible chat completion, streaming, cancellation, images, structured outputs, typed failures, and ledger events. Reuse it. Do not add an unrelated model client in the desktop or Node API handler.

Node's runtime environment must include:

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

`VllmAdapter` deliberately refuses calls without both values in production mode.

### 8.2 Fix the two-endpoint routing blocker

Current behavior:

```python
ModelRouter(registry, adapters={adapter.adapter_id: adapter}, ...)
```

and routing performs:

```python
adapter = self.adapters.get(target.adapter_id)
```

Both endpoint instances have `adapter_id == "airbench.vllm"`. A normal mapping therefore overwrites one with the other. A real two-lane deployment cannot be integrated by merely constructing two `VllmAdapter` objects.

Implement an endpoint-binding registry under a dedicated issue. The clean design is:

```text
ModelTarget
  |- target_id: qualified model/runtime/hardware identity
  |- adapter_id: adapter implementation identity (airbench.vllm)
  `- endpoint_binding_ref: deployment-specific binding

EndpointBinding
  |- endpoint_id
  |- target_id
  |- adapter_id + adapter_version
  |- base_url
  |- served_model_name
  `- enabled / signed-or-approved deployment metadata

ModelRouter
  `- resolve target -> endpoint binding -> adapter instance
```

The binding registry should be keyed by `target_id` or by a distinct `endpoint_binding_ref`, not only by adapter implementation ID. Preserve `airbench.vllm` as the honest implementation identity, and record endpoint identity separately in provenance.

At minimum, add tests proving:

1. Two targets using the same adapter implementation can bind to different URLs.
2. Selecting E2B calls only the E2B endpoint; selecting 12B calls only the 12B endpoint.
3. Health/readiness failure of one endpoint does not mark the other endpoint unavailable.
4. The router follows the qualified fallback/escalation policy and never silently downgrades a capable-required task.
5. A readiness response containing the wrong served model ID is rejected.
6. Routing and model-call ledger records contain target ID, endpoint ID, adapter ID/version, artifact identity, and request/response hashes without logging prompt contents or credentials.
7. Configuration and failure messages redact any credential value.

Do not work around this by inventing fake adapter implementation IDs such as `airbench.vllm.e2b` and `airbench.vllm.12b` unless the architecture issue explicitly chooses and documents that contract change.

### 8.3 Add exact candidate targets; do not overwrite qualified identities

The checked-in roster currently describes other reference targets and an older vLLM version. It must not be edited to pretend that these newly served models have already been qualified.

Under an assigned issue:

1. Create candidate target records for the exact E2B and 12B repositories, revisions, artifact manifests, quantization, vLLM 0.28.0 runtime, local image/RepoDigest, 8,192-token context, 4 GiB KV cache, concurrency 4, image limit 2, and this measured hardware profile.
2. Capture a new exact hardware profile for `workstation-04`; do not silently replace a previously signed profile.
3. Add backend compatibility results for Gemma 4 compressed-tensors/Marlin serving on Blackwell.
4. Run role-specific qualification packs through the real adapter and orchestrator path.
5. Record Gemma license acceptance and redistribution constraints.
6. Sign the completed manifests with the organization's external signing key. Never commit the key.
7. Only after successful qualification mark a target eligible for its measured roles, modalities, risk classes, and clearance classes.

Text and one synthetic image test do not qualify a model for confidential engineering, code generation, tool use, or approval-note roles. Tool calling must be tested through the actual parser, Tool Gateway, sandbox, and verification loop before advertising it.

### 8.4 Compose the application runtime

The final application composition must instantiate and connect:

```text
signed roster + hardware profile + qualification records
                         |
                         v
ModelRegistry -> EndpointBindingRegistry -> ModelRouter
                                            |
ResourceAdmissionController ----------------+
                                            |
File Intake -> Orchestrator -> selected VllmAdapter -> vLLM
                  |                    |
                  +-> verifier         +-> typed backend result
                  |
                  +-> ledger/state/artifact stores
                  |
             AirBench Node API <-> Desktop
```

Build this in the Node/application composition layer. The transport handler should delegate to orchestration; it should not assemble provider payloads itself. Likewise, a model response is a proposal. It cannot directly approve an action, bypass clearance/taint checks, invoke a tool outside the gateway, or become an authoritative engineering result without verification.

### 8.5 Suggested routing policy for the first integrated demo

Treat this as a proposal to validate, not as a qualification result:

- Route settled, low-risk, mechanical text tasks to E2B for latency and throughput.
- Route image/document interpretation, harder synthesis, and accuracy-sensitive reasoning to 12B.
- If verification fails or returns `needs_review`, escalate the same task stage to 12B and keep the route sticky for that stage.
- If policy requires the capable target and it is unavailable, queue or reject with a review reason. Never silently fall back to E2B.
- Human approval remains required wherever the AirBench policy requires it.

The E2B image smoke test once described a rectangle as a square. That is a concrete reason to keep semantic verification and capable-lane escalation even though E2B successfully emitted schema-valid JSON.

## 9. Structured output and multimodal integration

Use vLLM's OpenAI-compatible `response_format` with a JSON schema whenever the Node expects a typed handoff. Prompting the model to “return JSON” is insufficient: the 12B smoke test returned correct content inside a Markdown fence when only prompt instructions were used.

The adapter should validate the parsed result again against the AirBench contract. Schema-constrained decoding guarantees shape, not factual correctness.

For images:

1. Ingest the file through AirBench File Intake.
2. Enforce file type, size, malware/quarantine, clearance, and taint rules before model access.
3. Pass only an approved Node-managed reference or encoded content through the backend request contract.
4. Never let vLLM fetch an arbitrary user-provided internet URL.
5. Record content hashes and provenance metadata, not confidential raw image bytes, in the ledger.
6. Verify extracted observations against the source image and route uncertainty for human review.

The servers are configured for at most two images per prompt and 8,192 total model tokens. The application must enforce limits before sending the request; do not depend on an eventual vLLM error as admission control.

## 10. Measured baseline and routing evidence

The following is a small comparative baseline, not a capacity guarantee. Both tests used eight random text prompts, 256 input tokens, 64 output tokens, maximum concurrency four, unlimited request rate, and seed 42. The benchmark warned that sampling temperature was not explicitly forced, so record a fixed decoding configuration in future qualification runs.

| Metric | E2B | 12B |
|---|---:|---:|
| Successful requests | 8 | 8 |
| Failed requests | 0 | 0 |
| Duration | 2.99 s | 3.63 s |
| Request throughput | 2.67 req/s | 2.20 req/s |
| Output throughput | 171.13 tok/s | 141.04 tok/s |
| Total token throughput | 882.07 tok/s | 735.80 tok/s |
| Mean TTFT | 90.10 ms | 120.55 ms |
| Median TTFT | 86.40 ms | 130.37 ms |
| P99 TTFT | 106.73 ms | 139.56 ms |
| Mean TPOT | 22.30 ms | 26.88 ms |
| P99 TPOT | 22.83 ms | 27.70 ms |

In this small run, E2B provided about 21% more request/output throughput, about 25% lower mean time-to-first-token, and about 17% lower mean time-per-output-token. Do not convert those figures into a concurrent-user promise. Real capacity depends on prompt length, output length, image count/resolution, tool schemas, decoding settings, queueing policy, and other GPU users.

At one idle observation with both vLLM servers, Ollama, and the desktop display active, the GPU reported 30,595 MiB used and 66,622 MiB free. The E2B engine used approximately 14,296 MiB and the 12B engine approximately 14,784 MiB. This supports concurrent residency on the 96 GB workstation, not unlimited concurrent generation.

## 11. Demo versus production

| Concern | Controlled demo | Production on-premises deployment |
|---|---|---|
| Location | Lab GPU reached by SSH | Organization-owned server(s) inside its security boundary |
| Desktop connection | Loopback Node or SSH-forwarded Node | Internal HTTPS/mTLS Node endpoint with organizational identity and authorization |
| Model endpoint | Loopback, optionally through developer SSH tunnel | Loopback on same host or isolated inference subnet; never public |
| Model authentication | None; protected by loopback and SSH | Authenticated service identity, firewall policy, least privilege, rotation/revocation |
| Egress | Offline env flags; Docker network may still route out | Deny-by-default network with measured DNS/HTTP denial evidence |
| Artifacts | Downloaded online once, pinned revision and verified weights | Signed offline appliance bundle, approved media, local registry, full manifest verification |
| Lifecycle | Manual starts; no auto-restart on shared GPU | Approved service manager/cluster policy, health checks, controlled restart, rollback |
| Routing | Candidate E2B/12B policy | Only signed, current, role-specific qualified targets admitted |
| Capacity | Small baseline; manual coordination | Measured reservations, queues, backpressure, SLOs, saturation policy |
| Observability | Docker logs and manual `nvidia-smi` | Internal metrics/logs/audit, retention, alerting, no telemetry egress |
| Secrets | SSH credential outside repo | Secret manager or protected files, service credentials, key rotation |
| Availability | Single host, no HA | Graceful degradation on one node; replicas across nodes where required |
| Updates | Manual image/model staging | Signed offline update, verify, stage, canary/acceptance, rollback to last good bundle |
| Claims allowed | “Private lab-hosted inference over SSH” | “Sovereign/on-prem” only after isolation, supply chain, qualification, and audit controls pass |

The company's private network and inference network may use the same physical infrastructure. They do not have to be separate physical networks. Production should still create a logical trust boundary using host firewall rules, VLANs/security groups, service identities, and allowlisted flows: desktop to Node, Node to model servers, and only approved store/tool traffic. Workstations should not be able to call raw inference ports directly.

### Recommended production shape

```text
Employee network
  AirBench Desktop
        |
        | internal TLS/mTLS, authenticated Node protocol
        v
Service subnet / host
  AirBench Node + orchestration + stores + audit
        |
        | allowlisted internal service traffic only
        v
Inference host/subnet
  vLLM replicas / specialist model services
        X no internet route, no public listener
```

For a first single-host installation, Node and vLLM can run on the same machine and communicate over loopback or an internal container network. At larger scale, replicate whole models across GPUs/nodes behind target-aware routing. Do not split a model across slow links merely to claim scale. The Node remains the control plane and applies queueing, reservations, backpressure, verification, and provenance.

## 12. Hardening steps before a production or sovereignty claim

1. Build all source, wheels, images, models, packs, and trust metadata into a signed offline bundle.
2. Pin images by registry digest and record SBOMs and vulnerability-review evidence.
3. Generate deterministic full artifact manifests and verify them before every activation.
4. Remove outbound routes/DNS from the runtime network. `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` are defense in depth, not network isolation.
5. Test denied DNS and HTTPS from each service container while independently monitoring network attempts.
6. Give the Node an allowed path to model endpoints without giving those endpoints general egress.
7. Add authenticated internal TLS or mTLS for cross-host traffic. For truly same-host loopback, restrict process/user access and firewall rules.
8. Run Node/model services as dedicated non-root service accounts with read-only artifacts, minimal Linux capabilities, no host socket, and constrained writable volumes.
9. Move runtime configuration from ad hoc shell history to a reviewed deployment manifest. Keep URLs non-secret; keep credentials in an approved secret store.
10. Add internal metrics for queue depth, request latency, token throughput, GPU memory, GPU utilization, model readiness, errors, and verifier outcomes. Disable external telemetry.
11. Define resource reservations and safe concurrency per exact workload. Reject or queue before out-of-memory conditions.
12. Exercise backup/restore, signed update, failed-update rollback, model-unavailable behavior, and audit reconstruction.
13. Complete qualification for each model/role/modality/risk/hardware/runtime combination and expire/revoke certificates when any identity component changes.
14. Conduct penetration, prompt-injection, malicious-document, data-exfiltration, and tool-sandbox tests.

## 13. 24 GB backup machine constraints

The 24 GB Titan RTX backup cannot reproduce the 96 GB workstation's simultaneous two-model residency. The two vLLM engines currently consume roughly 29 GiB together before meaningful concurrent KV growth.

- Run E2B or 12B individually, not both simultaneously.
- Each measured model currently occupies roughly 14–15 GiB on the Blackwell workstation with a 4 GiB KV cache, leaving plausible 24 GB headroom individually. Re-measure on the Titan RTX; memory use and supported kernels can differ.
- Titan RTX is Turing/SM 7.5 and does not provide native BF16 support. Requalify the launch with `--dtype half` (FP16); do not copy the Blackwell `--dtype bfloat16` setting.
- Reduce KV cache, maximum context, maximum sequences, or image limits if measured headroom is unsafe.
- Use AirBench's serial virtual-team mode: keep logical roles and typed handoffs, but load/use one model at a time or route all roles to one qualified smaller model.
- Measure cold-start/model-swap time and include it in the demo and admission policy.
- If an unrelated process is consuming GPU memory, coordinate with its owner. Never terminate it to make room.

The backup is useful for failover demonstrations and development, but it must have its own hardware profile, runtime compatibility tests, benchmarks, and qualification records.

## 14. MoE model path

Do not add a third model until the two verified endpoints work end to end through Node, router, verifier, and ledger. MoE can improve quality per active compute, but all experts usually remain resident in memory; it is not automatically smaller or faster. Runtime kernels and quantization support matter.

A discovered candidate is `google/gemma-4-26B-A4B-it-qat-q4_0-gguf` at revision `d1c082be9cf3c8a514acf63b8761f4b41935842e`. Its model GGUF is 14,439,363,584 bytes and multimodal projector is 1,194,828,160 bytes. This artifact has **not** been qualified with the current vLLM compressed-tensors serving path. GGUF may require a different supported vLLM path or a llama.cpp-family backend, which would need a separate adapter/runtime compatibility record.

For a future vLLM MoE trial, prefer an officially published or otherwise trusted compressed-tensors/AWQ artifact explicitly supported by the pinned vLLM version. A third-party quantization adds a supply-chain and quality-qualification burden. Benchmark total residency, prefill/decode throughput, structured output, multimodal behavior, tool parsing, and real AirBench tasks before choosing it.

## 15. Troubleshooting

### Endpoint is unreachable locally

1. Confirm the SSH tunnel terminal is still open.
2. Run `ssh -v mmmut-server` if authentication or forwarding fails.
3. On the server, check `docker ps` and remote `/health` first.
4. Check whether local ports 18001/18002 are occupied; change only the local side if needed.

### Container exited

```bash
docker ps -a --filter name=airbench-vllm-e2b --filter name=airbench-vllm-12b
docker logs --tail 300 airbench-vllm-e2b
docker logs --tail 300 airbench-vllm-12b
nvidia-smi
```

Do not immediately delete/recreate it. Preserve the failure log and determine whether the cause is permissions, GPU memory, incompatible runtime/kernel, corrupt files, or wrong arguments.

### Cache permission error

The earlier E2B attempt failed because a non-root, capability-dropped container could not write the default cache location. The corrected launch uses the host user's UID/GID and points `HOME`, `XDG_CACHE_HOME`, `HF_HOME`, and `TORCH_HOME` to the writable `/cache` mount.

### vLLM says it cannot infer the device

A `vllm --version` probe without `--gpus all` can initialize enough of vLLM to fail device detection. Use `--gpus all` for GPU-dependent probes. GPU access has been validated with both the NVIDIA CUDA container and PyTorch inside the vLLM container.

### Startup says insufficient free GPU memory

Inspect all GPU processes first. Do not kill other owners' processes. The recommended launch includes `--gpu-memory-utilization 0.70` and a fixed 4 GiB KV cache. If it still cannot start safely, run one AirBench model at a time or wait for the GPU owner.

### Multimodal warmup warning or first-request delay

The 12B startup logged a multimodal warmup failure, but a real image request completed successfully. The first applicable request may trigger Triton compilation and have a one-time latency spike. Warm the exact production request shapes during controlled startup, then begin accepting traffic. Treat a successful real request as compatibility evidence, not as permission to ignore repeated runtime errors.

### JSON is fenced or factually wrong

Use `response_format`/JSON Schema and validate it in the adapter/orchestrator. Schema validity does not verify semantics. Run the verifier and escalate or request human review when facts are uncertain.

### Expected vLLM performance messages

The current runtime selected compressed-tensors/Marlin kernels. It selected Triton attention because the faster FA4 path was not available for Gemma 4's heterogeneous attention heads. Eager mode disables compile/CUDA graph optimizations. Record these as runtime evidence; do not change them during qualification without creating a new exact runtime identity and benchmark.

## 16. Acceptance checklist for the junior team

### Serving handoff

- [ ] SSH access works through alias `mmmut-server`.
- [ ] No credentials or private keys are committed.
- [ ] Existing non-AirBench workloads are identified and untouched.
- [ ] Both remote `/health` calls return HTTP 200.
- [ ] `/v1/models` returns the exact expected served name for each port.
- [ ] Both local SSH-forwarded health calls return HTTP 200.
- [ ] A text completion succeeds through each forwarded endpoint.
- [ ] A schema-constrained response succeeds through each endpoint.
- [ ] A real approved image passes File Intake and a multimodal call through the adapter path.

### Repository integration

- [ ] Work has an assigned GitHub issue and follows `AGENTS.md`.
- [ ] Desktop communicates only with AirBench Node.
- [ ] Node calls models only through the backend adapter contract.
- [ ] Two target-specific endpoint bindings are implemented; no adapter-ID collision remains.
- [ ] Exact E2B and 12B candidate target and hardware records exist without overwriting prior identities.
- [ ] Resource admission enforces measured context, image, KV, and concurrency limits.
- [ ] E2B/12B selection, escalation, queueing, and unavailable-target tests pass.
- [ ] Structured responses are contract-validated and semantically verified.
- [ ] Ledger records identity and hashes without confidential prompt content.
- [ ] UI, Node, router, adapter, and end-to-end test suites pass.

### Final demo

- [ ] The team states whether it used Option A or Option B and which execution mode was active.
- [ ] Ports 8001/8002 remain loopback-only.
- [ ] The demo shows desktop -> Node -> router -> vLLM -> verifier -> artifact/ledger, not a direct curl presented as product integration.
- [ ] A verification failure visibly escalates or requests review.
- [ ] The team labels the lab transport and remaining production gaps honestly.
- [ ] Logs, model manifests, benchmark command/settings, and test results are retained as evidence.

### Production gate

- [ ] Full signed offline bundle and immutable image digests are verified.
- [ ] Network egress denial is independently demonstrated.
- [ ] Cross-host authentication/TLS and authorization are active.
- [ ] Role-specific signed qualification is current for every admitted target.
- [ ] Capacity, queueing, failure, update, rollback, backup, and restore tests pass.
- [ ] Security review and organizational approval are complete.

## 17. Definition of done

Integration is complete only when a user can submit an approved task in the desktop, the Node preserves its clearance and taint, the router selects the correct exact qualified endpoint, the model returns a typed proposal, verification runs, the result becomes a Node-managed artifact, and the desktop can display/download that artifact with a complete non-sensitive provenance trail. Both model endpoints must be independently health-checked, resource-admitted, and failure-isolated.

A pair of working `/v1/chat/completions` endpoints is the serving foundation. It is not, by itself, the AirBench product or a production sovereignty claim.
