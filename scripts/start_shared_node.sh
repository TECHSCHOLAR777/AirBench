#!/usr/bin/env bash
set -Eeuo pipefail

# Start the shared AirBench Node on the same Linux host as the local models.
# The Node remains loopback-bound by default; expose it only through the
# operator-approved internal HTTPS/authentication boundary.

NODE_ROOT="${AIRBENCH_NODE_ROOT:-/media/aims-dtu/e6f3d549-768f-4cd9-bdd7-fe600ab3bf81/airbench-serving/airbench-node}"
APP_ROOT="${AIRBENCH_APP_ROOT:-$NODE_ROOT/app}"
STATE_ROOT="${AIRBENCH_STATE_ROOT:-$NODE_ROOT/state}"
CORPUS_ROOT="${AIRBENCH_CORPUS_ROOT:-$NODE_ROOT/corpus}"
MODEL_STORE="${AIRBENCH_MODEL_STORE:-/media/aims-dtu/e6f3d549-768f-4cd9-bdd7-fe600ab3bf81/airbench-serving/models}"
PYTHON_BIN="${AIRBENCH_PYTHON_BIN:-$APP_ROOT/.venv/bin/python}"

: "${AIRBENCH_BEARER_TOKEN:?Set AIRBENCH_BEARER_TOKEN without writing it to this script}"

for required in "$APP_ROOT/src" "$APP_ROOT/packs/refinery_psu_v0" \
    "$CORPUS_ROOT/document_catalog.yaml" "$CORPUS_ROOT/01_knowledge_base_ingestion" \
    "$MODEL_STORE/bge-m3" "$MODEL_STORE/bge-reranker-v2-m3"; do
    if [[ ! -e "$required" ]]; then
        echo "Required shared-node asset is missing: $required" >&2
        exit 2
    fi
done

mkdir -p "$STATE_ROOT/intake" "$STATE_ROOT/artifacts" "$STATE_ROOT/chroma"

export PYTHONPATH="$APP_ROOT/src"
export AIRBENCH_NODE_IDENTITY="${AIRBENCH_NODE_IDENTITY:-node.aimslab.local}"
export AIRBENCH_DOMAIN_PACK_REF="${AIRBENCH_DOMAIN_PACK_REF:-refinery-psu-v0}"
export AIRBENCH_CLEARANCE="${AIRBENCH_CLEARANCE:-internal}"
export AIRBENCH_SUBJECT="${AIRBENCH_SUBJECT:-shared.operator}"
export AIRBENCH_OPERATOR_ROLES="${AIRBENCH_OPERATOR_ROLES:-human_reviewer}"
export AIRBENCH_HOST="${AIRBENCH_HOST:-127.0.0.1}"
export AIRBENCH_PORT="${AIRBENCH_PORT:-8765}"
export AIRBENCH_BEARER_TOKEN
export AIRBENCH_LEDGER_PATH="$STATE_ROOT/ledger.sqlite3"
export AIRBENCH_SIGNING_KEY_PATH="${AIRBENCH_SIGNING_KEY_PATH:-$APP_ROOT/.airbench_signing_key}"
export AIRBENCH_PACK_DIR="$APP_ROOT/packs/refinery_psu_v0"
export AIRBENCH_PACK_SIGNING_KEY_PATH="$AIRBENCH_SIGNING_KEY_PATH"
export AIRBENCH_INTAKE_ROOT="$STATE_ROOT/intake"
export AIRBENCH_ARTIFACT_ROOT="$STATE_ROOT/artifacts"
export AIRBENCH_WORLD_MODEL_BACKEND="sqlite"
export AIRBENCH_WORLD_MODEL_PATH="$STATE_ROOT/world-model.sqlite"
export AIRBENCH_DECISION_STORE_PATH="$STATE_ROOT/decisions.sqlite"
export AIRBENCH_KNOWLEDGE_INGEST_ROOT="$CORPUS_ROOT/01_knowledge_base_ingestion"
export AIRBENCH_KNOWLEDGE_CATALOG_PATH="$CORPUS_ROOT/document_catalog.yaml"
export AIRBENCH_RETRIEVAL_ENABLED="1"
export AIRBENCH_RETRIEVAL_MODEL_STORE="$MODEL_STORE"
export AIRBENCH_VECTOR_STORE="chroma"
export AIRBENCH_VECTOR_STORE_PATH="$STATE_ROOT/chroma"
export AIRBENCH_MODEL_STORE="$MODEL_STORE"
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"
export ANONYMIZED_TELEMETRY="False"
export CHROMA_TELEMETRY_ENABLED="False"

exec "$PYTHON_BIN" -m airbench.node.server
