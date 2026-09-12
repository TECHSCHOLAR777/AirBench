# Gemini API Test Console

**Type:** development-only integration test path  
**Branch:** `Deepanshu`  
**Purpose:** exercise the full AirBench provider-neutral pipeline with Gemini before local GPU / model server work is ready

> This is not a production feature and is not a claim that AirBench is sovereign, offline, or GPU-qualified. Gemini is an external provider. This path must be removed or kept behind a dev-only guard before any sovereign acceptance milestone.

---

## Why this exists

The AirBench contracts layer — task lifecycle, authorization, plan commit, deterministic routing, backend adapter boundary, ledger events, and response provenance — was implemented ahead of local model serving. This path lets you run a live query through every layer of that stack via Gemini, so bugs in the pipeline can be found before the local GPU / vLLM / NIM work begins.

Related issues: [#112](https://github.com/TECHSCHOLAR777/AirBench/issues/112) (closed, not planned for production), [#113](https://github.com/TECHSCHOLAR777/AirBench/issues/113), [#119](https://github.com/TECHSCHOLAR777/AirBench/issues/119), [#123](https://github.com/TECHSCHOLAR777/AirBench/issues/123).

---

## Files changed

### New files

| File | Purpose |
|------|---------|
| `src/contracts/adapters/gemini_adapter.py` | `GeminiApiAdapter` — implements the provider-neutral `BackendAdapter` contract for Gemini REST |
| `scripts/gemini_test_server.py` | FastAPI server — wraps the full AirBench pipeline, serves the browser console |
| `scripts/gemini_test_ui.html` | Premium dark-mode browser test console |
| `scripts/run_gemini_e2e.py` | CLI alternative — same pipeline as the server, runs from terminal |
| `tests/test_gemini_adapter.py` | 4 offline mocked tests for the adapter (no API key needed) |

### Modified files

| File | Change |
|------|--------|
| `src/contracts/adapters/__init__.py` | Added `GeminiApiAdapter` to the package exports |
| `src/contracts/__init__.py` | Added `GeminiApiAdapter` to the public contracts exports |
| `src/contracts/model/backend.py` | Extended `BackendContent.kind` enum to accept `"document"` (for PDF transport) |

---

## Full pipeline exercised

Every query through the test console travels this path — identical to what local models will use:

```
query
  → orchestrator.create_task
  → orchestrator.authorize
  → orchestrator.commit_plan
  → ModelRouter  (deterministic registry + qualification + health + admission)
  → GeminiApiAdapter.complete / .stream
  → Gemini REST API  (generateContent / streamGenerateContent)
  → BackendResponse / BackendChunk
  → orchestrator ledger  (8 events: task.created, authorized, plan.committed,
                           routing.decision, model.requested, model.call.started,
                           model.call.completed, model.responded)
  → response + provenance + usage returned to UI
```

---

## How to run (browser console)

```powershell
cd C:\Users\<you>\AirBench         # repository root
$env:PYTHONPATH = "src"
$env:GEMINI_API_KEY = "<your-key>" # from https://aistudio.google.com/apikey
python scripts/gemini_test_server.py
# Open http://127.0.0.1:8765 in your browser
```

Optional flags:

```powershell
python scripts/gemini_test_server.py --port 9000          # change port
python scripts/gemini_test_server.py --host 0.0.0.0       # expose on LAN
```

### CLI alternative (no browser needed)

```powershell
$env:PYTHONPATH = "src"
$env:GEMINI_API_KEY = "<your-key>"

# One-shot text query
python scripts/run_gemini_e2e.py --query "Explain the inspection workflow"

# Interactive terminal session
python scripts/run_gemini_e2e.py --interactive

# Streaming output
python scripts/run_gemini_e2e.py --interactive --stream

# Force a specific model
python scripts/run_gemini_e2e.py --models gemini-2.5-flash --query "Hello"

# Attach an image or PDF
python scripts/run_gemini_e2e.py --query "Analyse this" --attachment ./path/to/file.png
```

### Offline unit tests (no API key)

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_gemini_adapter.py" -v
# Ran 4 tests ... OK
```

---

## Server endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /` | GET | Serve `gemini_test_ui.html` |
| `GET /api/health` | GET | Server status, adapter health, API key presence |
| `GET /api/models` | GET | Auto-discover Gemini text-generation models |
| `POST /api/query` | POST | Full pipeline query — returns JSON with trace, ledger, provenance, usage |
| `POST /api/query/stream` | POST | Full pipeline query — SSE streaming |
| `POST /api/upload` | POST | Upload image or PDF (returns base64 data URI for attachment) |
| `GET /api/tests/run` | GET | Run the 4 offline unit tests and return output |

`POST /api/query` body:

```json
{
  "model": "gemini-2.5-flash",
  "query": "Your question here",
  "stream": false,
  "attachments": []
}
```

---

## What this proves ✅

| Component | Evidence |
|-----------|---------|
| Task creation + identity | Live — `task.created` ledger event |
| Authorization + clearance binding | Live — `task.authorized` event |
| Plan commit before model call | Live — `task.plan.committed` event |
| Deterministic `ModelRouter` selection | Live — `routing.decision` event |
| `BackendAdapter` health / readiness contract | Live — health check endpoint |
| Gemini text generation | Live — model response returned |
| Streaming normalization (`BackendChunk`) | Implemented — SSE endpoint |
| JSON structured output (`json_object` / `json_schema`) | Offline tests — test 2 |
| Multimodal image / PDF input (inline base64) | Implemented — upload + attach |
| Ledger events (`model.call.started`, `completed`, `failed`) | Live — 8 events per query |
| Response provenance + taint propagation | Live — provenance panel |
| Usage normalization (token counts) | Live — usage panel |
| Per-model failure isolation | Implemented — separate task per model |
| API key missing → fail-closed (`authentication_failed`) | Offline test — test 3 |
| Undeclared tool call → rejected | Adapter contract |

---

## What is NOT proven by this path ❌

These are open issues that require local model serving, real hardware, and sovereign operation:

| Open Work | Issue |
|-----------|-------|
| Local Gemma / Qwen model loading | [#123](https://github.com/TECHSCHOLAR777/AirBench/issues/123) |
| GPU memory, latency, throughput measurement | [#113](https://github.com/TECHSCHOLAR777/AirBench/issues/113) |
| Sovereign / no-egress operation | [#119](https://github.com/TECHSCHOLAR777/AirBench/issues/119) |
| Local vLLM / NIM adapter (`VllmAdapter` / `NimAdapter`) | Adapters exist, need real endpoint |
| BGE-M3 embeddings and local reranking | Local retrieval stack |
| OCR and vision adapters as deployed | Local deployment |
| Local model artifact signatures and qualification certificates | Qualification matrix |
| Desktop / Tauri UI (`apps/desktop/`) | Frontend workstream |
| Production approval, human review, deployment acceptance | Governance |

---

## Security and data handling

- The API key is read **only from `GEMINI_API_KEY`** at call time. It is never written to source code, logs, ledger payloads, response provenance, or error messages.
- All query results include `"test_only": true` in their JSON payload.
- A development-mode warning banner is always visible in the browser console.
- **Do not send** confidential production files, industrial documents, credentials, or real ledger data through the attachment upload path. This is an external data-egress test path.
- **Rotate the API key** after any session where the key was shared in a conversation or a shared terminal.

---

## Removing credentials after a session

```powershell
Remove-Item Env:GEMINI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:AIRBENCH_GEMINI_MODELS -ErrorAction SilentlyContinue
```
