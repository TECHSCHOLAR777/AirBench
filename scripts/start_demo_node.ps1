# start_demo_node.ps1 - start the AirBench Node for the two-endpoint demo.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 -ModelStore "C:\airbench-models"
#
# Assumes the SSH tunnel is already open:
#   ssh -N -L 127.0.0.1:18001:127.0.0.1:8001 -L 127.0.0.1:18002:127.0.0.1:8002 mmmut-server
param(
    [string]$ModelStore = "C:\airbench-models",
    [string]$Token = "dev-token-123",
    [string]$Port = "8765",
    [string]$Subject = "demo.operator",
    [string]$DomainPackRef = "refinery-psu-v0",
    [string]$CorpusZip = "",
    [switch]$PrepareCorpus,
    [switch]$Retrieval,   # off by default: loading BGE adds ~1 min and several GB RAM
    [switch]$NoExecution  # debugging only: disable Node-owned execution + deliverables
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$py = if (Test-Path "$repo\.venv-deep\Scripts\python.exe") { "$repo\.venv-deep\Scripts\python.exe" } else { "python" }

if (-not (Test-Path "$repo\models\roster\demo\two_endpoint_roster.yaml")) {
    Write-Error "Signed demo roster missing. Run: python scripts\airbench_demo_roster.py"
}
if (-not (Test-Path "$repo\.airbench_signing_key")) {
    Write-Error "Signing key missing at $repo\.airbench_signing_key"
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
$env:AIRBENCH_MODEL_ROSTER_PATH      = "$repo\models\roster\demo\two_endpoint_roster.yaml"
$env:AIRBENCH_MODEL_SIGNING_KEY      = ""
$env:AIRBENCH_MODEL_SIGNING_KEY_PATH = "$repo\.airbench_signing_key"
$env:AIRBENCH_MODEL_STORE            = $ModelStore
$env:AIRBENCH_MODEL_E2B_URL          = "http://127.0.0.1:18001"
$env:AIRBENCH_MODEL_12B_URL          = "http://127.0.0.1:18002"
$env:HF_HUB_OFFLINE                  = "1"
$env:TRANSFORMERS_OFFLINE            = "1"

$env:AIRBENCH_TASK_PLANNER_ENABLED   = "1"
$env:AIRBENCH_HARDWARE_PROFILE_PATH  = "$repo\profiles\hardware\workstation_04.json"
$env:AIRBENCH_HARDWARE_PROFILE       = "$repo\profiles\hardware\workstation_04.json"

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
    # BGE lives in the repo model store; the Gemmas may live elsewhere.
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
Write-Host "The Node re-hashes the signed model files at startup: wait ~35s until you see" -ForegroundColor Yellow
Write-Host "'Starting AirBench Node ...' before running the curl checks. Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""
& $py -m airbench.node.server
