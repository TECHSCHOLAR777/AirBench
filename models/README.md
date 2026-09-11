# AirBench model storage

AirBench keeps one canonical runtime copy of every qualified model. The
runtime model server reads only the directory supplied by
`AIRBENCH_MODEL_STORE`; it does not read a Hugging Face cache and it never
downloads a model while serving a task.

## Storage roles

| Location | Role | Retention |
| --- | --- | --- |
| `AIRBENCH_MODEL_STORE` | Verified, immutable runtime artifacts | Keep on the GPU host |
| Hugging Face hub cache | Connected-machine acquisition scratch space | Remove after staging and verification |
| Temporary staging directory | Interrupted-download recovery during provisioning | Remove after a successful stage |

The Hugging Face cache is not a second runtime store. Keeping it beside the
runtime store indefinitely doubles the weight storage and can cause future
downloads to look successful while the actual serving path still points at an
older copy.

## Canonical layout

The directory names below are the `artifact_path` values in the signed v0
roster:

```text
<AIRBENCH_MODEL_STORE>/
  gemma4-31b-it-q4/
  gemma4-26b-a4b-4bit/
  qwen3-coder-30b-a3b-awq/
  qwen2.5-vl-7b-awq/
```

The signed roster remains the authority for qualification, digests, roles,
runtime compatibility, and declared required files. The storage utility only
checks that those declared files exist and that acquisition-cache bytes are
already present in the canonical store.

## Provisioning rule

Provisioning is performed on a connected staging machine or by importing a
verified offline bundle. Serving is a separate offline phase.

1. Set `AIRBENCH_MODEL_STORE` to the canonical runtime directory.
2. Download into a disposable cache, never the user's global HF cache. For
   example, use the Hugging Face CLI with `--cache-dir` under a temporary
   `AirBench-model-staging` directory and `--local-dir` under the canonical
   store.
3. Complete the transfer and verify the declared files and hashes.
4. Run the local audit below for the selected roster targets.
5. Remove the disposable acquisition cache only after the audit passes.
6. Copy or attach only the canonical model store to the air-gapped GPU host.

The runtime image and Node configuration must not contain HF credentials,
remote repository URLs as active endpoints, or a cache fallback. A missing or
tampered canonical artifact is a startup failure, not a reason to download a
replacement.

## Audit and cleanup

The repository utility is local-only and performs no network I/O. It hashes
the canonical files and compares them with the selected HF cache blobs. A
cache blob is prunable only when its content and size match a canonical file,
all declared runtime files are present, and no incomplete download exists.
Unmatched metadata or incomplete downloads are retained.

PowerShell example for the four large first-scope targets:

```powershell
$env:AIRBENCH_MODEL_STORE = 'C:\AirBench-models'
$env:AIRBENCH_HF_CACHE = 'C:\Users\HP\.cache\huggingface\hub'
python scripts/model_store.py audit `
  --target-id gemma4-31b-it-q4 `
  --target-id gemma4-26b-a4b-4bit `
  --target-id qwen3-coder-30b-a3b-4bit `
  --target-id qwen2.5-vl-7b-4bit `
  --cache-repository gemma4-31b-it-q4=google/gemma-4-31B-it-qat-q4_0-gguf `
  --cache-repository gemma4-26b-a4b-4bit=google/gemma-4-26B-A4B-it-qat-q4_0-gguf `
  --cache-repository qwen3-coder-30b-a3b-4bit=QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ
```

The two overrides are needed on the current workstation because those two
artifacts were staged from quantized repositories whose cache names differ
from the repository fields in the draft roster. The override only locates the
on-disk cache for byte-level cleanup; it does not qualify the artifact or
change the signed roster. That source-identity discrepancy must be resolved
and re-signed before production model admission.

Review the report first. The explicit cleanup command removes only proven
duplicate blobs from those selected cache repositories:

```powershell
python scripts/model_store.py prune `
  --target-id gemma4-31b-it-q4 `
  --target-id gemma4-26b-a4b-4bit `
  --target-id qwen3-coder-30b-a3b-4bit `
  --target-id qwen2.5-vl-7b-4bit `
  --cache-repository gemma4-31b-it-q4=google/gemma-4-31B-it-qat-q4_0-gguf `
  --cache-repository gemma4-26b-a4b-4bit=google/gemma-4-26B-A4B-it-qat-q4_0-gguf `
  --cache-repository qwen3-coder-30b-a3b-4bit=QuantTrio/Qwen3-Coder-30B-A3B-Instruct-AWQ `
  --apply
```

The command never removes `AIRBENCH_MODEL_STORE`, repository build output,
the GPU host's model files, or unselected cache repositories. It is safe to
run the audit repeatedly. The prune command intentionally requires
`--apply` and fails closed when a target or cache repository cannot be proven
safe.

## Current workstation migration

The two legacy Gemma directories were renamed to the signed roster paths:
`gemma-4-31b-q4_0` became `gemma4-31b-it-q4`, and
`gemma-4-26b-a4b-q4_0` became `gemma4-26b-a4b-4bit`. No model bytes were
deleted or rewritten by that rename.
