# start_demo_node.ps1 - start the AirBench Node for the two-endpoint demo.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1
#
# Assumes the SSH tunnel is already open:
#   ssh -NT -o ExitOnForwardFailure=yes -L 127.0.0.1:18001:127.0.0.1:8001 -L 127.0.0.1:18002:127.0.0.1:8002 aimslab
param(
    [string]$Token = $env:AIRBENCH_BEARER_TOKEN,
    [string]$Port = "8765",
    [string]$ModelEndpointsJson = $env:AIRBENCH_MODEL_ENDPOINTS_JSON,
    [string]$Subject = "demo.operator",
    [string]$DomainPackRef = "refinery-psu-v0",
    [string]$CorpusZip = "",
    [ValidateSet("Fresh", "Resume")]
    [string]$Mode = "Resume",   # Fresh: delete local demo state so old tasks/stores cannot leak into a new demo
    [switch]$PrepareCorpus,
    [switch]$Retrieval,   # off by default: loading BGE adds ~1 min and several GB RAM
    [switch]$NoExecution, # debugging only: disable Node-owned execution + deliverables
    [switch]$AllowDegradedLane,  # debugging only: start the Node even when a model lane is down
    [switch]$AllowCandidateQualification  # explicit controlled-demo opt-in; never production default
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$py = if (Test-Path "$repo\.venv-deep\Scripts\python.exe") { "$repo\.venv-deep\Scripts\python.exe" } else { "python" }

if ([string]::IsNullOrWhiteSpace($Token)) {
    Write-Error "A bearer token is required. Set AIRBENCH_BEARER_TOKEN or pass -Token explicitly."
}
if ([string]::IsNullOrWhiteSpace($ModelEndpointsJson)) {
    $ModelEndpointsJson = '[{"endpoint_id":"endpoint-vision","target_id":"airbench-qwen25-vl-7b","base_url":"http://127.0.0.1:18001","served_model_name":"airbench-qwen25-vl-7b"},{"endpoint_id":"endpoint-reasoning","target_id":"airbench-qwen3-8b","base_url":"http://127.0.0.1:18002","served_model_name":"airbench-qwen3-8b"}]'
}

# Phase 0: one Node per port. Refuse to compete with a live listener and print
# the owning process so the operator can stop it deliberately.
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $ownerName = if ($owner) { $owner.ProcessName } else { "unknown" }
    Write-Error "Port $Port is already owned by PID $($listener.OwningProcess) ($ownerName). Stop it first (Stop-Process -Id $($listener.OwningProcess)) or choose another port."
}

# Phase 0: FreshDemo deletes local demo state so a new demo cannot see old
# tasks, intakes, artifacts, or projections. ResumeDemo keeps everything.
if ($Mode -eq "Fresh") {
    $statePaths = @(
        "$repo\.airbench-node-ledger.sqlite", "$repo\.airbench-node-ledger.sqlite-wal", "$repo\.airbench-node-ledger.sqlite-shm",
        "$repo\.airbench-intake", "$repo\.airbench-artifacts", "$repo\.airbench-chroma",
        "$repo\.airbench-world-model.db", "$repo\.airbench-decisions.db",
        "$repo\.airbench-corpus\01_knowledge_base_ingestion", "$repo\retrieval-index.json",
        "$repo\.airbench-workspaces"
    )
    foreach ($path in $statePaths) {
        if (Test-Path $path) {
            Remove-Item -Recurse -Force $path
            Write-Host "FreshDemo removed: $path" -ForegroundColor DarkGray
        }
    }
    Write-Host "FreshDemo: local demo state cleared." -ForegroundColor Cyan
} else {
    Write-Host "ResumeDemo: existing ledger and stores are kept." -ForegroundColor Cyan
}

if (-not (Test-Path "$repo\models\roster\aimslab\qwen_vllm_roster.yaml")) {
    Write-Error "Signed Qwen roster missing. Run: python scripts\airbench_qwen_aimslab_records.py"
}
if (-not (Test-Path "$repo\.airbench_signing_key")) {
    Write-Host "Signing key missing. Auto-generating..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File "$repo\scripts\setup_demo_signing_key.ps1"
}
& $py "$repo\scripts\airbench_qwen_aimslab_records.py" --key "$repo\.airbench_signing_key"
if ($LASTEXITCODE -ne 0) { Write-Error "Qwen roster/attestation generation failed." }

# Phase 1 model endpoint preflight: prove both tunnelled lanes are healthy and
# serve the exact roster model names before the Node starts. A degraded lane
# must be an explicit operator decision (-AllowDegradedLane), never a surprise
# discovered deep inside task execution.
if (-not $AllowDegradedLane) {
    Write-Host "Running model endpoint preflight (tunnel + served model IDs)..." -ForegroundColor Cyan
    & $py "$repo\scripts\model_endpoint_preflight.py" --roster "$repo\models\roster\aimslab\qwen_vllm_roster.yaml" --attestation "$repo\models\attestations\aimslab_qwen_vllm.yaml" --signing-key "$repo\.airbench_signing_key" --attestation-signing-key "$repo\.airbench_signing_key"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Model endpoint preflight failed. Start the remote vLLM containers and the SSH tunnel (see docs/operations/STARTUP_GUIDE.md), or pass -AllowDegradedLane to start degraded."
    }
} else {
    Write-Host "Model endpoint preflight skipped (-AllowDegradedLane): the Node will start with possibly degraded lanes." -ForegroundColor Yellow
}

$env:PYTHONPATH                  = "src"
$env:AIRBENCH_NODE_IDENTITY      = "node.demo.local"
$env:AIRBENCH_BEARER_TOKEN       = $Token
$env:AIRBENCH_DOMAIN_PACK_REF    = $DomainPackRef
$env:AIRBENCH_CLEARANCE          = "internal"
$env:AIRBENCH_SUBJECT            = $Subject
# The demo operator is the human reviewer required by the signed pack's
# inspection-review execution policy. Set this explicitly so an inherited
# empty/stale shell variable cannot make approval fail after ledger recording.
$env:AIRBENCH_OPERATOR_ROLES     = "human_reviewer"
$env:AIRBENCH_HOST               = "127.0.0.1"
$env:AIRBENCH_PORT               = $Port
$env:AIRBENCH_POLICY_VERSION_HASH = "policy-v0.1"
# Keep the command/evidence ledger durable across Node restarts.  The File
# Intake store is persistent too, so an in-memory ledger would make a valid
# prior intake look like orphaned evidence after every demo restart.
$env:AIRBENCH_LEDGER_PATH        = "$repo\.airbench-node-ledger.sqlite"
$env:AIRBENCH_SIGNING_KEY_PATH   = "$repo\.airbench_signing_key"

$env:AIRBENCH_MODEL_SERVING_ENABLED  = "1"
$env:AIRBENCH_MODEL_ROSTER_PATH      = "$repo\models\roster\aimslab\qwen_vllm_roster.yaml"
$env:AIRBENCH_MODEL_DEPLOYMENT_ATTESTATION_PATH = "$repo\models\attestations\aimslab_qwen_vllm.yaml"
$env:AIRBENCH_MODEL_ATTESTATION_SIGNING_KEY_PATH = "$repo\.airbench_signing_key"
$env:AIRBENCH_MODEL_SIGNING_KEY      = ""
$env:AIRBENCH_MODEL_SIGNING_KEY_PATH = "$repo\.airbench_signing_key"
$env:AIRBENCH_MODEL_ENDPOINTS_JSON   = $ModelEndpointsJson
if ($AllowCandidateQualification) { $env:AIRBENCH_MODEL_ALLOW_CANDIDATE_QUALIFICATION = "1" }
else { Remove-Item Env:AIRBENCH_MODEL_ALLOW_CANDIDATE_QUALIFICATION -ErrorAction SilentlyContinue }
$env:HF_HUB_OFFLINE                  = "1"
$env:TRANSFORMERS_OFFLINE            = "1"

$env:AIRBENCH_TASK_PLANNER_ENABLED   = "1"
$env:AIRBENCH_HARDWARE_PROFILE_PATH  = "$repo\profiles\hardware\aimslab_titan_rtx_24gb.yaml"
$env:AIRBENCH_HARDWARE_PROFILE       = "$repo\profiles\hardware\aimslab_titan_rtx_24gb.yaml"

# Domain pack (signed), world model, decision history, intake, and qualification.
$env:AIRBENCH_INTAKE_ROOT            = "$repo\.airbench-intake"
$env:AIRBENCH_ARTIFACT_ROOT          = "$repo\.airbench-artifacts"
$env:AIRBENCH_PACK_DIR               = "$repo\packs\refinery_psu_v0"
$env:AIRBENCH_PACK_SIGNING_KEY       = ""
$env:AIRBENCH_PACK_SIGNING_KEY_PATH  = "$repo\.airbench_signing_key"
$env:AIRBENCH_WORLD_MODEL_BACKEND    = "sqlite"
$env:AIRBENCH_WORLD_MODEL_PATH       = "$repo\.airbench-world-model.db"
$env:AIRBENCH_DECISION_STORE_PATH    = "$repo\.airbench-decisions.db"
$env:AIRBENCH_QUALIFICATION_MATRIX   = "$repo\qualifications\model_qualification_matrix.yaml"

# Bulk knowledge ingestion + durable vector store (Chroma).
$corpusRoot = "$repo\.airbench-corpus"
$env:AIRBENCH_KNOWLEDGE_INGEST_ROOT  = "$corpusRoot\01_knowledge_base_ingestion"
$env:AIRBENCH_KNOWLEDGE_CATALOG_PATH  = "$corpusRoot\document_catalog.yaml"
$env:AIRBENCH_VECTOR_STORE           = "chroma"
$env:AIRBENCH_VECTOR_STORE_PATH      = "$repo\.airbench-chroma"
if (-not (Test-Path $corpusRoot)) {
    New-Item -ItemType Directory -Path $corpusRoot | Out-Null
}
if (-not (Test-Path $env:AIRBENCH_KNOWLEDGE_INGEST_ROOT)) {
    New-Item -ItemType Directory -Path $env:AIRBENCH_KNOWLEDGE_INGEST_ROOT | Out-Null
    Write-Host "Created knowledge corpus directory: $env:AIRBENCH_KNOWLEDGE_INGEST_ROOT (drop approved documents here to ingest)." -ForegroundColor Yellow
}
if ($PrepareCorpus) {
    if (-not $CorpusZip) {
        throw "-PrepareCorpus requires -CorpusZip pointing to the approved local corpus ZIP."
    }
    & $py "$repo\scripts\prepare_refinery_demo_corpus.py" $CorpusZip --destination $corpusRoot --force
    if ($LASTEXITCODE -ne 0) { throw "Corpus preparation failed." }
}

$env:USE_TF                 = "0"
$env:TRANSFORMERS_NO_TF     = "1"
$env:KMP_DUPLICATE_LIB_OK   = "TRUE"

if ($Retrieval) {
    $env:AIRBENCH_RETRIEVAL_ENABLED     = "1"
    $env:AIRBENCH_RETRIEVAL_INDEX_PATH  = "$repo\retrieval-index.json"
    $env:AIRBENCH_EMBEDDING_DIR         = "bge-m3"
    $env:AIRBENCH_RERANKER_DIR          = "bge-reranker-v2-m3"
    # BGE lives in the repo model store; the remote vLLM models are not local artifacts.
    $env:AIRBENCH_RETRIEVAL_MODEL_STORE = "$repo\airbench-models"
} else {
    $env:AIRBENCH_RETRIEVAL_ENABLED = "0"
}

# Node-owned execution is ON by default so that approving an admissible plan
# actually runs the Node-approved work (model routing, verification, and a
# rendered DOCX/XLSX/PPTX deliverable). Use -NoExecution only to debug transport
# without executing tasks.
if ($NoExecution) {
    $env:AIRBENCH_TASK_EXECUTION_ENABLED = "0"
    Write-Host "Task execution disabled (-NoExecution): approved plans will not run." -ForegroundColor Yellow
} else {
    $env:AIRBENCH_TASK_EXECUTION_ENABLED    = "1"
    $env:AIRBENCH_DELIVERABLE_TEMPLATE_PATH = "$repo\packs\refinery_psu_v0\deliverable_templates.yaml"
    # The draft/render step is the reversible prepare action; release stays human-gated.
    $env:AIRBENCH_EXECUTION_ACTION_KIND     = "prepare_approval_note"
    Write-Host "Task execution enabled: approving a plan runs the Node work and renders the deliverable." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Starting AirBench Node on http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "The Node verifies the signed remote deployment records at startup: wait until you see" -ForegroundColor Yellow
Write-Host "'Starting AirBench Node ...' before running the curl checks. Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""
& $py -m airbench.node.server
