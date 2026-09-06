# AirBench M5.1–M5.3 — Implementation, Progress & Setup Guide

This document provides a comprehensive overview of the **M5.1 (Model Registry, Artifacts & Worker Qualifications)**, **M5.2 (Hardware-Aware Scheduling & Admission)**, and **M5.3 (Provider-Neutral Backend Contract)** milestones, summarizing implemented contracts, frozen model artifacts, acceptance matrices, and setup instructions.

---

## 1. Executive Summary & Architecture

AirBench is designed for sensitive, air-gapped industrial environments (such as refinery and PSU inspection reviews). The M5 milestones guarantee that:

1. **Deterministic Authority**: Control and state transition remain strictly inside the deterministic Python orchestrator and admission controller; models act as constrained, single-turn workers.
2. **Provider-Neutral Routing**: Model serving (vLLM / NIM or a future approved endpoint) is decoupled from the router through normalized `ModelCallRequest`, `RoutingDecision`, and `BackendRequest`/`BackendResponse` contracts. The deterministic fake backend provides an offline conformance seam.
3. **Supply-Chain Immutability**: No target is ever referenced by a mutable tag (`latest`), an unverified container, or an unrecorded local directory. Every model weight, tokenizer, and chat template is pinned to its SHA-256 digest.
4. **Role-Specific Qualification**: Qualification is non-transferable (`qualified(target, role_A) != qualified(target, role_B)`). A lead reasoning model cannot be routed code execution or verification tasks without distinct, validated certificates.
5. **Hardware-Aware Admission**: Physical hardware is treated as a signed budget. Multi-agent teams are admitted in `parallel` when reservations fit, or serialized safely into a `serial_virtual_team` without dropping worker contexts, clearance, or the independent verifier.
6. **Non-Bypassable Verifier Invariant**: High-consequence workflows always require an independent verifier. If verifier capacity cannot be reserved, admission immediately halts with `admission=stopped` and emits `completion.blocked`.
7. **Zero-Egress Startup**: No remote API calls, telemetry, Hugging Face, NGC, or background update checks are permitted.

---

## 2. Frozen Model Roster (v0 Reference Bundle)

All 6 reference model targets for the refinery/PSU inspection slice have been downloaded, inspected, and hashed to exact SHA-256 digests:

| Target ID | Family & Variant | Role / Scope | Format & Quantization | Primary Artifact SHA-256 Digest |
|---|---|---|---|---|
| `gemma4-31b-it-q4` | Gemma 4 31B Instruction-Tuned | Lead Worker / High-Quality Reasoning | GGUF (Q4_0) | `179cfb99212709597eae5929112cfca677e1bbf566178b479ae1da0c4772874b` |
| `gemma4-26b-a4b-4bit` | Gemma 4 26B A4B Instruction-Tuned | Workstation Lead / Reasoning Fast Lane | GGUF (Q4_0 QAT) | `3eca3b8f6d7baf218a7dd6bba5fb59a56ee25fe2d567b6f5f589b4f697eca51d` |
| `qwen3-coder-30b-a3b-4bit` | Qwen3-Coder 30B A3B Instruct | Code Worker / Executable Sandbox Calculations | Safetensors (AWQ INT4, 6 shards) | `c0b64626f59e9c7bafa334570427b0438faca29875f87d322bc9c705d3391ff8` |
| `qwen2.5-vl-7b-4bit` | Qwen2.5-VL 7B Instruct | Vision / OCR Evidence Extraction | Safetensors (AWQ INT4, 2 shards) | `81d797f3f3a625d6c2479dbf9276156c7e31cc3c7a8fdf3e8194d8f4810c4c1a` |
| `bge-m3` | BAAI BGE-M3 | Embedding Service (Dense + Sparse) | PyTorch Bin (BF16 native) | `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38` |
| `bge-reranker-v2-m3` | BAAI BGE-Reranker-v2-M3 | Retrieval Reranking Service | Safetensors (BF16 native) | `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286` |

---

## 3. Implemented Deliverables

### Contracts & Controllers
* [`contracts/model_registry.py`](contracts/model_registry.py): `ModelTarget` and `ModelRegistry` implementing HMAC-SHA256 manifest verification, on-disk tamper validation (`local_storage_hash`), path traversal protection, role/modality/clearance eligibility filtering, and mutable tag rejection.
* [`contracts/admission.py`](contracts/admission.py): `AdmissionController`, `AdmissionRequest`, `HardwareMeasurement`, `AdmissionDecision`, and `ReleaseRecord` managing parallel vs. serial virtual-team scheduling, VRAM/RAM/KV-cache budgeting, priority queues (`interactive_high_consequence` down to `background_ingestion`), and verifier capacity reservation.
* [`contracts/backend.py`](contracts/backend.py): Provider-neutral backend request/response, capability, usage, error, streaming, cancellation, and provenance contracts plus the deterministic `FakeBackend`.
* [`contracts/router.py`](contracts/router.py) and [`contracts/orchestrator.py`](contracts/orchestrator.py): Qualification-first target selection and orchestrator-owned route recording, backend invocation, retries, and queued/rejected outcomes.
* [`contracts/models.py`](contracts/models.py): Added M5.1 and M5.2 ledger events to `LEDGER_EVENT_TYPES` and extended `HardwareProfile` with execution modes, egress verification, and sandbox parameters.
* [`contracts/ledger_event_catalog.yaml`](contracts/ledger_event_catalog.yaml): Cataloged all ~45 lifecycle events across model qualification, serving, and hardware scheduling.

### Schemas & Manifests
* [`contracts/model_qualification.schema.yaml`](contracts/model_qualification.schema.yaml): Strict JSON Schema for qualification certificates.
* [`contracts/hardware_profile.schema.yaml`](contracts/hardware_profile.schema.yaml): Schema defining host hardware, GPU, CPU, RAM, scratch, isolation policy, and execution modes.
* [`contracts/team_resource_plan.schema.yaml`](contracts/team_resource_plan.schema.yaml): Schema for committed, immutable resource plans before worker execution.
* [`models/roster/v0/model_roster.yaml`](models/roster/v0/model_roster.yaml): Deterministically signed offline roster manifest with HMAC-SHA256 signature `29546ad6d01f260a34c5a857d597844e85436045b6a2bfefa0b4029b718092a7`.
* [`qualifications/model_qualification_matrix.yaml`](qualifications/model_qualification_matrix.yaml): 8 distinct role certificates for the 6 targets with populated artifact digests.
* [`benchmarks/quantization_matrix.yaml`](benchmarks/quantization_matrix.yaml): Quantization matrix mapping precision and artifact hashes.
* [`benchmarks/model_hardware_results.yaml`](benchmarks/model_hardware_results.yaml): Benchmark structure tracking latency, throughput, VRAM, and concurrency across hardware profiles.
* [`benchmarks/backend_compatibility_matrix.yaml`](benchmarks/backend_compatibility_matrix.yaml): Conformance matrix for vLLM and NIM adapters.
* [`acceptance/model_roster_matrix.yaml`](acceptance/model_roster_matrix.yaml) & [`acceptance/hardware_scheduling_matrix.yaml`](acceptance/hardware_scheduling_matrix.yaml): Traceability matrices mapping every issue requirement to tests, observable results, and ledger events.

### Test Suite
* M5.3 focused tests pass 12/12. The full standard-library discovery currently finds 137 tests: 135 pass and 2 require the declared PyYAML dependency to be installed in the active environment.

---

## 4. Setup Guide for New Contributors & Clean Nodes

Follow these steps to set up and verify the M5 environment on any machine:

### Step 1: Environment Setup
Ensure you have Python 3.11+ installed:

```bash
# Clone repository
git clone <repo-url>
cd AirBench

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install project dependencies
pip install -e .
pip install pyyaml pytest
```

### Step 2: Running Automated Tests
Run the test suite to verify that all contracts, admission arithmetic, and role isolations pass:

```bash
python -m pytest -v
```
All 85 tests should pass synchronously in ~3 seconds using deterministic fixtures (no model weights or GPU required).

### Step 3: Downloading Model Weights (Offline Model Bundle)
To run live serving or re-verify local artifact hashes, download the models to `airbench-models/` (this directory is ignored by Git):

```bash
# Gemma 4 31B Q4 (lead reasoning)
huggingface-cli download google/gemma-4-31b-it-q4 --local-dir airbench-models/gemma4-31b-it-q4

# Gemma 4 26B A4B (workstation fast lane)
huggingface-cli download google/gemma-4-26b-it-qat-q4_0-gguf --local-dir airbench-models/gemma4-26b-a4b-4bit --include "*.gguf"

# Qwen3-Coder 30B A3B AWQ (code worker)
huggingface-cli download Qwen/Qwen3-Coder-30B-A3B-Instruct-AWQ --local-dir airbench-models/qwen3-coder-30b-a3b-awq

# Qwen2.5-VL 7B AWQ (vision / OCR)
huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct-AWQ --local-dir airbench-models/qwen2.5-vl-7b-awq

# BAAI BGE-M3 (embeddings)
huggingface-cli download BAAI/bge-m3 --local-dir airbench-models/bge-m3

# BAAI BGE-Reranker-v2-M3 (reranking)
huggingface-cli download BAAI/bge-reranker-v2-m3 --local-dir airbench-models/bge-reranker-v2-m3
```

### Step 4: Verifying Supply-Chain Hashes
Run the offline hashing tool to verify that your downloaded files match the frozen digests in `model_roster.yaml`:

```bash
python airbench_hash.py
```

### Step 5: Generating Keys & Re-Signing Manifests
If you modify any model parameters or certificates, re-generate HMAC signatures:

```bash
# Generate local 32-byte secret key if not present (never commit this file)
python -c "import secrets; open('.airbench_signing_key','wb').write(secrets.token_bytes(32))"

# Re-sign roster and generate patches
python airbench_sign.py
```

---

## 5. What Remains for M5 (Hardware Benchmark Next Steps)

The code, contracts, schemas, and static checks are complete. The only remaining tasks are **empirical runtime measurements** on the target GPU machine:

1. **Host Hardware Probing**: Run `nvidia-smi` and system commands to populate physical CPU/GPU/RAM specs into `profiles/hardware/target_96gb_vram.yaml`.
2. **Offline vLLM Startup**: Launch vLLM with `--network none` to prove zero-egress operation and record container digests in `benchmarks/backend_compatibility_matrix.yaml`.
3. **Runtime Latency & VRAM Benchmarks**: Record actual cold load times, peak VRAM usage under load, and prompt/generation tokens/sec in `benchmarks/model_hardware_results.yaml`.
4. **Domain Evaluation**: Run refinery inspection prompt sets to record empirical accuracy and structured output pass rates in `qualifications/model_qualification_matrix.yaml`.
