"""AirBench Gemini development-only web test console server.

Starts a FastAPI server that wraps the full AirBench pipeline
(task → auth → plan → router → GeminiApiAdapter → ledger) and exposes
REST / SSE endpoints consumed by gemini_test_ui.html.

Usage (from repository root):
    $env:PYTHONPATH = "src"
    $env:GEMINI_API_KEY = "<your-key>"
    python scripts/gemini_test_server.py

The API key is read only from the environment variable GEMINI_API_KEY.
It is never written to logs, source code, or response payloads.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import os
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Ensure the src/ tree is importable regardless of how the server is launched.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Third-party / stdlib imports
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, UploadFile, File, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import (
        HTMLResponse, JSONResponse, StreamingResponse, FileResponse,
    )
    import uvicorn
except ImportError as exc:  # pragma: no cover
    print(f"[server] Missing dependency: {exc}. Run: pip install fastapi uvicorn httpx")
    raise

# ---------------------------------------------------------------------------
# AirBench contracts
# ---------------------------------------------------------------------------
from contracts import (
    BackendContent, BackendMessage, Clearance, ContractStatus,
    EventLedger, ModelCallRequest, ModelRegistry,
    ModelRouter, ModelTarget, Orchestrator, TeamPlan,
)
from devtools.gemini_adapter import GeminiApiAdapter

# ---------------------------------------------------------------------------
# Helpers (inlined from run_gemini_e2e.py so the server is self-contained)
# ---------------------------------------------------------------------------

_UI_FILE = Path(__file__).parent / "gemini_test_ui.html"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _make_request(model: str, index: int, query: str, modality: str) -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": f"request.gemini.web.{index}",
        "task_id": f"task.gemini.web.{index}",
        "team_id": f"team.gemini.web.{index}",
        "worker_id": f"worker.gemini.web.{index}",
        "task_kind": "inspection_review",
        "modality": modality,
        "required_capability": "reasoning",
        "evidence_summary": ["evidence.gemini.web"],
        "clearance": "internal",
        "action_risk": "inspection_review",
        "resource_budget": {"context_tokens": 4096},
        "attempt": 1,
        "idempotency_key": f"idem.gemini.web.{index}",
        "timeout_ms": 120000,
        "role": "reasoning",
        "resource_lease_id": f"lease.gemini.web.{index}",
    })


def _make_target(model: str) -> ModelTarget:
    digest = _sha256(model)
    return ModelTarget.from_dict({
        "target_id": f"gemini-web-{model}",
        "repository": "external/gemini-web",
        "artifact_digest": digest,
        "artifact_path": "gemini-web-descriptor.json",
        "quantization": "fp16",
        "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64,
        "runtime_version": "gemini-api-v1beta",
        "backend": "custom",
        "capabilities": ["reasoning"],
        "roles": ["reasoning"],
        "modalities": ["text", "image", "document"],
        "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"],
        "pack_refs": ["pack.refinery.v0"],
        "hardware_profile_refs": ["hw.gemini-web"],
        "context_limit": 100000,
        "image_token_limit": 0,
        "tool_call_parser": "gemini-native",
        "structured_output_modes": ["json_object", "json_schema"],
        "license_id": "google-gemini-api-test-only",
        "local_storage_hash": digest,
        "qualification_certificate": f"test-only.gemini.{model}",
        "qualification_expires_at": "2030-01-01T00:00:00Z",
        "qualification_signature": "d" * 64,
        "role_qualifications": [["reasoning", f"test-only.gemini.{model}"]],
        "adapter_id": "airbench.gemini-test",
        "adapter_version": "0.1",
        "streaming": True,
        "cancellation": True,
    })


def run_pipeline(
    model: str,
    index: int,
    query: str,
    *,
    stream: bool,
    attachments: tuple[BackendContent, ...] = (),
) -> dict[str, Any]:
    """Run the full AirBench pipeline for one query and return a rich trace dict."""
    trace_steps: list[dict[str, Any]] = []
    t0 = time.monotonic()

    def step(name: str, detail: dict[str, Any]) -> None:
        trace_steps.append({
            "step": name,
            "elapsed_ms": round((time.monotonic() - t0) * 1000),
            **detail,
        })

    # 1 — Create task
    ledger = EventLedger()
    task_id = f"task.gemini.web.{index}"
    orchestrator = Orchestrator(ledger)
    task = orchestrator.create_task(
        principal_id="principal.gemini.web",
        clearance=Clearance.internal,
        request=query,
        domain_pack_ref="pack.refinery.v0",
        risk_class="inspection_review",
        autonomy_ceiling="review_required",
        permitted_worker_capabilities=("reasoning",),
        verification_criteria=("source_check",),
        resource_budget={"max_concurrency": 1},
        task_id=task_id,
    )
    step("task.created", {"task_id": task_id, "state": "created"})

    # 2 — Authorize
    orchestrator.authorize(task_id, authorization_ref=f"auth.gemini.web.{index}")
    step("task.authorized", {"state": "authorized"})

    # 3 — Commit plan
    orchestrator.commit_plan(TeamPlan(
        team_id=f"team.gemini.web.{index}",
        task_id=task_id,
        assignments=(f"assignment.gemini.web.{index}",),
        dependency_graph={},
        concurrency_ceiling=1,
        required_verification=True,
        completion_criteria=("source_check",),
        plan_version_hash=f"plan.gemini.web.{index}",
        policy_version_hash="policy.gemini.web",
        status=ContractStatus.proposed,
    ))
    step("task.plan.committed", {"state": "planned"})

    # 4 — Build adapter + router
    adapter = GeminiApiAdapter(model, ledger=ledger)
    modality = (
        "image" if any(p.kind == "image" for p in attachments)
        else ("document" if attachments else "text")
    )
    call = _make_request(model, index, query, modality)
    router = ModelRouter(
        ModelRegistry(
            "registry.gemini.web", "1.0",
            ((_make_target(model)),), "e" * 64, "2030-01-01T00:00:00Z",
        ),
        {adapter.adapter_id: adapter},
        policy_version_hash="policy.gemini.web",
        resource_admission=lambda _t, _r: "admitted",
    )
    step("router.built", {"model": model, "adapter": adapter.adapter_id, "health": adapter.health().value})

    # 5 — Execute
    messages = (BackendMessage("user", (BackendContent("text", text=query), *attachments)),)
    t_call = time.monotonic()
    execution = orchestrator.execute_model_call(
        call, router=router,
        pack_ref="pack.refinery.v0",
        hardware_profile_ref="hw.gemini-web",
        messages=messages,
        stream=stream,
    )
    call_ms = round((time.monotonic() - t_call) * 1000)

    if execution.response is None:
        reason = execution.route.decision.reason if execution.route else "routing failed"
        raise RuntimeError(f"Model call not executed: {reason}")

    if stream:
        chunks = execution.response  # already a tuple from execute_model_call
        output = "".join(chunk.text for chunk in chunks)
        chunk_count = len(chunks)
    else:
        output = execution.response.output
        if isinstance(output, dict):
            output = json.dumps(output, indent=2)
        chunk_count = None

    step("model.call.completed", {
        "model": model,
        "stream": stream,
        "call_ms": call_ms,
        "chunk_count": chunk_count,
    })

    # 6 — Collect provenance
    route_dict = execution.route.decision.to_dict() if execution.route else {}
    prov_dict: dict[str, Any] = {}
    usage_dict: dict[str, Any] = {}
    if not stream and hasattr(execution.response, "provenance"):
        prov_dict = execution.response.provenance.to_dict()
        usage_dict = execution.response.usage.to_dict()

    # 7 — Collect ledger events
    events_out = []
    for ev in ledger.events:
        events_out.append({
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "task_id": ev.task_id,
            "actor_id": ev.actor_id,
            "sequence": ev.sequence,
            "occurred_at": ev.occurred_at,
        })

    total_ms = round((time.monotonic() - t0) * 1000)
    return {
        "status": "passed",
        "model": model,
        "query": query,
        "output": output if isinstance(output, str) else str(output),
        "stream": stream,
        "call_ms": call_ms,
        "total_ms": total_ms,
        "ledger_event_count": len(events_out),
        "ledger_events": events_out,
        "route": route_dict,
        "provenance": prov_dict,
        "usage": usage_dict,
        "pipeline_trace": trace_steps,
        "test_only": True,
    }


def _stream_pipeline(model: str, index: int, query: str) -> Iterator[str]:
    """SSE generator for streaming queries — yields pipeline SSE events."""
    try:
        result = run_pipeline(model, index, query, stream=True)
        # Send pipeline trace first
        for step in result["pipeline_trace"]:
            yield f"data: {json.dumps({'type': 'step', **step})}\n\n"
        # Send final result
        yield f"data: {json.dumps({'type': 'done', **result})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(title="AirBench Gemini Test Console", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_query_counter = 0


@app.get("/", response_class=HTMLResponse)
async def serve_ui() -> HTMLResponse:
    if _UI_FILE.exists():
        return HTMLResponse(_UI_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>gemini_test_ui.html not found alongside server</h1>", status_code=404)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    has_key = bool(os.environ.get("GEMINI_API_KEY"))
    adapter = GeminiApiAdapter("health-check")
    return {
        "server": "ok",
        "api_key_present": has_key,
        "adapter_health": adapter.health().value,
        "adapter_readiness": adapter.readiness().value,
        "test_only": True,
    }


@app.get("/api/models")
async def list_models() -> dict[str, Any]:
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set")
    adapter = GeminiApiAdapter("model-discovery")
    all_models = adapter.available_models()
    text_models = [
        name for name in all_models
        if name.startswith("gemini-")
        and not any(tag in name for tag in ("tts", "embedding", "computer-use"))
    ]
    return {
        "all": list(all_models),
        "text_models": text_models,
        "count": len(text_models),
    }


@app.post("/api/query")
async def query(request: Request) -> JSONResponse:
    global _query_counter
    body = await request.json()
    model = body.get("model", "gemini-2.5-flash")
    q = body.get("query", "").strip()
    stream_mode = bool(body.get("stream", False))
    attachments_raw: list[dict[str, Any]] = body.get("attachments", [])

    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set")

    _query_counter += 1
    index = _query_counter

    attachments = tuple(
        BackendContent(
            kind=a["kind"],
            media_ref=a["data_uri"],
            media_type=a["mime_type"],
            content_hash=a.get("hash", "a" * 64),
        )
        for a in attachments_raw
    )

    try:
        result = run_pipeline(model, index, q, stream=stream_mode, attachments=attachments)
        return JSONResponse(result)
    except Exception as exc:
        tb = traceback.format_exc()
        return JSONResponse(
            {"status": "failed", "model": model, "query": q, "error": str(exc), "traceback": tb, "test_only": True},
            status_code=500,
        )


@app.post("/api/query/stream")
async def query_stream(request: Request) -> StreamingResponse:
    global _query_counter
    body = await request.json()
    model = body.get("model", "gemini-2.5-flash")
    q = body.get("query", "").strip()

    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    if not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY not set")

    _query_counter += 1
    index = _query_counter

    return StreamingResponse(
        _stream_pipeline(model, index, q),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, Any]:
    raw = await file.read()
    mime_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    kind = "image" if mime_type.startswith("image/") else "document"
    encoded = base64.b64encode(raw).decode("ascii")
    file_hash = hashlib.sha256(raw).hexdigest()
    return {
        "filename": file.filename,
        "mime_type": mime_type,
        "kind": kind,
        "size_bytes": len(raw),
        "hash": file_hash,
        "data_uri": f"data:{mime_type};base64,{encoded}",
    }


@app.get("/api/tests/run")
async def run_tests() -> dict[str, Any]:
    """Run the offline unit tests (mock-based, no live API calls)."""
    test_file = _REPO_ROOT / "tests" / "test_gemini_adapter.py"
    if not test_file.exists():
        raise HTTPException(status_code=404, detail="test_gemini_adapter.py not found")

    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests",
         "-p", "test_gemini_adapter.py", "-v"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=env,
        timeout=60,
    )
    raw_output = result.stdout + result.stderr
    passed = result.returncode == 0
    lines = [l.strip() for l in raw_output.splitlines() if l.strip()]
    return {
        "passed": passed,
        "return_code": result.returncode,
        "output": raw_output,
        "summary": next((l for l in reversed(lines) if "Ran" in l or "OK" in l or "FAIL" in l), ""),
        "test_file": str(test_file),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AirBench Gemini test console server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        print("[WARNING] GEMINI_API_KEY is not set — live queries will be rejected.", flush=True)
    print(f"[AirBench] Gemini test console -> http://{args.host}:{args.port}", flush=True)
    uvicorn.run("gemini_test_server:app", host=args.host, port=args.port, reload=args.reload)
