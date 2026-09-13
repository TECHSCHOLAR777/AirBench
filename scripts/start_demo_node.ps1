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
    [switch]$Retrieval   # off by default: loading BGE adds ~1 min and several GB RAM
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
$env:AIRBENCH_HOST               = "127.0.0.1"
$env:AIRBENCH_PORT               = $Port
$env:AIRBENCH_POLICY_VERSION_HASH = "policy-v0.1"

$env:AIRBENCH_MODEL_SERVING_ENABLED  = "1"
$env:AIRBENCH_MODEL_ROSTER_PATH      = "$repo\models\roster\demo\two_endpoint_roster.yaml"
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
$env:AIRBENCH_PACK_SIGNING_KEY_PATH  = "$repo\.airbench_signing_key"
$env:AIRBENCH_WORLD_MODEL_BACKEND    = "sqlite"
$env:AIRBENCH_WORLD_MODEL_PATH       = "$repo\.airbench-world-model.db"
$env:AIRBENCH_DECISION_STORE_PATH    = "$repo\.airbench-decisions.db"
$env:AIRBENCH_QUALIFICATION_MATRIX   = "$repo\qualifications\model_qualification_matrix.yaml"

# Bulk knowledge ingestion + durable vector store (Chroma).
$env:AIRBENCH_KNOWLEDGE_INGEST_ROOT  = "$repo\.airbench-corpus"
$env:AIRBENCH_VECTOR_STORE           = "chroma"
$env:AIRBENCH_VECTOR_STORE_PATH      = "$repo\.airbench-chroma"
if (-not (Test-Path $env:AIRBENCH_KNOWLEDGE_INGEST_ROOT)) {
    New-Item -ItemType Directory -Path $env:AIRBENCH_KNOWLEDGE_INGEST_ROOT | Out-Null
    Write-Host "Created knowledge corpus directory: $env:AIRBENCH_KNOWLEDGE_INGEST_ROOT (drop documents here to ingest)." -ForegroundColor Yellow
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

Write-Host ""
Write-Host "Starting AirBench Node on http://127.0.0.1:$Port" -ForegroundColor Cyan
Write-Host "The Node re-hashes the signed model files at startup: wait ~35s until you see" -ForegroundColor Yellow
Write-Host "'Starting AirBench Node ...' before running the curl checks. Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""
& $py -m airbench.node.server
