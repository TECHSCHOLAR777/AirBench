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
if [[ -n "${AIRBENCH_PACK_DIR:-}" ]]; then
    PACK_DIR="$AIRBENCH_PACK_DIR"
elif [[ -d "$APP_ROOT/packs/refinery_psu_v0" ]]; then
    PACK_DIR="$APP_ROOT/packs/refinery_psu_v0"
elif [[ -d "$APP_ROOT/refinery_psu_v0" ]]; then
    # The shared-node staging layout keeps the pack beside src/.
    PACK_DIR="$APP_ROOT/refinery_psu_v0"
else
    PACK_DIR="$APP_ROOT/packs/refinery_psu_v0"
fi
if [[ -n "${AIRBENCH_PYTHON_BIN:-}" ]]; then
    PYTHON_BIN="$AIRBENCH_PYTHON_BIN"
elif [[ -x "$APP_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$APP_ROOT/.venv/bin/python"
elif [[ -x "$NODE_ROOT/.venv/bin/python" ]]; then
    # Shared deployments may keep one environment beside app/ so the app
    # tree can be replaced without rebuilding the runtime environment.
    PYTHON_BIN="$NODE_ROOT/.venv/bin/python"
else
    PYTHON_BIN="python3"
fi

: "${AIRBENCH_BEARER_TOKEN:?Set AIRBENCH_BEARER_TOKEN without writing it to this script}"

for required in "$APP_ROOT/src" "$PACK_DIR" \
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
export AIRBENCH_PACK_DIR="$PACK_DIR"
export AIRBENCH_PACK_SIGNING_KEY_PATH="$AIRBENCH_SIGNING_KEY_PATH"
export AIRBENCH_INTAKE_ROOT="$STATE_ROOT/intake"
export AIRBENCH_ARTIFACT_ROOT="$STATE_ROOT/artifacts"
export AIRBENCH_WORLD_MODEL_BACKEND="sqlite"
export AIRBENCH_WORLD_MODEL_PATH="$STATE_ROOT/world-model.sqlite"
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
if [[ -n "${AIRBENCH_PACK_DIR:-}" ]]; then
    PACK_DIR="$AIRBENCH_PACK_DIR"
elif [[ -d "$APP_ROOT/packs/refinery_psu_v0" ]]; then
    PACK_DIR="$APP_ROOT/packs/refinery_psu_v0"
elif [[ -d "$APP_ROOT/refinery_psu_v0" ]]; then
    # The shared-node staging layout keeps the pack beside src/.
    PACK_DIR="$APP_ROOT/refinery_psu_v0"
else
    PACK_DIR="$APP_ROOT/packs/refinery_psu_v0"
fi
if [[ -n "${AIRBENCH_PYTHON_BIN:-}" ]]; then
    PYTHON_BIN="$AIRBENCH_PYTHON_BIN"
elif [[ -x "$APP_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$APP_ROOT/.venv/bin/python"
elif [[ -x "$NODE_ROOT/.venv/bin/python" ]]; then
    # Shared deployments may keep one environment beside app/ so the app
    # tree can be replaced without rebuilding the runtime environment.
    PYTHON_BIN="$NODE_ROOT/.venv/bin/python"
else
    PYTHON_BIN="python3"
fi

: "${AIRBENCH_BEARER_TOKEN:?Set AIRBENCH_BEARER_TOKEN without writing it to this script}"

for required in "$APP_ROOT/src" "$PACK_DIR" \
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
export AIRBENCH_PACK_DIR="$PACK_DIR"
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

export AIRBENCH_MODEL_SERVING_ENABLED="${AIRBENCH_MODEL_SERVING_ENABLED:-1}"
export AIRBENCH_MODEL_ROSTER_PATH="${AIRBENCH_MODEL_ROSTER_PATH:-$APP_ROOT/models/roster/aimslab/qwen_vllm_roster.yaml}"
if [ -z "${AIRBENCH_MODEL_ENDPOINTS_JSON:-}" ]; then
  export AIRBENCH_MODEL_ENDPOINTS_JSON='[{"endpoint_id":"endpoint-vision","target_id":"airbench-qwen25-vl-7b","base_url":"http://127.0.0.1:18001","served_model_name":"airbench-qwen25-vl-7b"},{"endpoint_id":"endpoint-reasoning","target_id":"airbench-qwen3-8b","base_url":"http://127.0.0.1:18002","served_model_name":"airbench-qwen3-8b"}]'
fi
export AIRBENCH_MODEL_DEPLOYMENT_ATTESTATION_PATH="${AIRBENCH_MODEL_DEPLOYMENT_ATTESTATION_PATH:-$APP_ROOT/models/attestations/aimslab_qwen_vllm.yaml}"
export AIRBENCH_MODEL_ATTESTATION_SIGNING_KEY_PATH="${AIRBENCH_MODEL_ATTESTATION_SIGNING_KEY_PATH:-$AIRBENCH_SIGNING_KEY_PATH}"
export AIRBENCH_MODEL_SIGNING_KEY_PATH="${AIRBENCH_MODEL_SIGNING_KEY_PATH:-$AIRBENCH_SIGNING_KEY_PATH}"
export AIRBENCH_POLICY_VERSION_HASH="${AIRBENCH_POLICY_VERSION_HASH:-policy-v0.1}"

export AIRBENCH_HARDWARE_PROFILE_PATH="${AIRBENCH_HARDWARE_PROFILE_PATH:-$APP_ROOT/profiles/hardware/aimslab_titan_rtx_24gb.yaml}"

export AIRBENCH_TASK_EXECUTION_ENABLED="${AIRBENCH_TASK_EXECUTION_ENABLED:-1}"
export AIRBENCH_DELIVERABLE_TEMPLATE_PATH="${AIRBENCH_DELIVERABLE_TEMPLATE_PATH:-$PACK_DIR/deliverable_templates.yaml}"
export AIRBENCH_WORKSPACE_ROOT="${AIRBENCH_WORKSPACE_ROOT:-$STATE_ROOT/workspaces}"
export AIRBENCH_EXECUTION_ACTION_KIND="${AIRBENCH_EXECUTION_ACTION_KIND:-prepare_approval_note}"

exec "$PYTHON_BIN" -m airbench.node.server
