"""Run a development-only AirBench pipeline against Gemini models."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import sys
from pathlib import Path

from contracts import (
    BackendContent, BackendMessage, Clearance, ContractStatus, EventLedger,
    ModelCallRequest, ModelRegistry, ModelRouter, ModelTarget,
    Orchestrator, TeamPlan,
)
from devtools.gemini_adapter import GeminiApiAdapter


def request(model: str, index: int, query: str, *, modality: str) -> ModelCallRequest:
    return ModelCallRequest.from_dict({
        "request_id": f"request.gemini.e2e.{index}", "task_id": f"task.gemini.e2e.{index}",
        "team_id": f"team.gemini.e2e.{index}", "worker_id": f"worker.gemini.e2e.{index}",
        "task_kind": "inspection_review", "modality": modality, "required_capability": "reasoning",
        "evidence_summary": ["evidence.gemini.e2e"], "clearance": "internal",
        "action_risk": "inspection_review", "resource_budget": {"context_tokens": 4096},
        "attempt": 1, "idempotency_key": f"idem.gemini.e2e.{index}", "timeout_ms": 120000,
        "role": "reasoning", "resource_lease_id": f"lease.gemini.e2e.{index}",
    })


def target(model: str) -> ModelTarget:
    digest = hashlib.sha256(model.encode()).hexdigest()
    return ModelTarget.from_dict({
        "target_id": f"gemini-test-{model}", "repository": "external/gemini-test",
        "artifact_digest": digest, "artifact_path": "gemini-test-descriptor.json",
        "quantization": "fp16", "tokenizer_digest": "b" * 64,
        "chat_template_digest": "c" * 64, "runtime_version": "gemini-api-v1beta",
        "backend": "custom", "capabilities": ["reasoning"], "roles": ["reasoning"],
        "modalities": ["text", "image", "document"], "risk_classes": ["inspection_review"],
        "allowed_clearances": ["internal"], "pack_refs": ["pack.refinery.v0"],
        "hardware_profile_refs": ["hw.gemini-test"], "context_limit": 100000,
        "image_token_limit": 0, "tool_call_parser": "gemini-native",
        "structured_output_modes": ["json_object", "json_schema"],
        "license_id": "google-gemini-api-test-only", "local_storage_hash": digest,
        "qualification_certificate": f"test-only.gemini.{model}",
        "qualification_expires_at": "2030-01-01T00:00:00Z", "qualification_signature": "d" * 64,
        "role_qualifications": [["reasoning", f"test-only.gemini.{model}"]],
        "adapter_id": "airbench.gemini-test", "adapter_version": "0.1",
        "streaming": True, "cancellation": True,
    })


def run_one(model: str, index: int, query: str, *, stream: bool, attachments: tuple[BackendContent, ...] = ()) -> tuple[dict, int]:
    ledger = EventLedger()
    task_id = f"task.gemini.e2e.{index}"
    orchestrator = Orchestrator(ledger)
    orchestrator.create_task(
        principal_id="principal.gemini.e2e", clearance=Clearance.internal,
        request=query, domain_pack_ref="pack.refinery.v0", risk_class="inspection_review",
        autonomy_ceiling="review_required", permitted_worker_capabilities=("reasoning",),
        verification_criteria=("source_check",), resource_budget={"max_concurrency": 1},
        task_id=task_id,
    )
    orchestrator.authorize(task_id, authorization_ref=f"auth.gemini.e2e.{index}")
    orchestrator.commit_plan(TeamPlan(
        team_id=f"team.gemini.e2e.{index}", task_id=task_id,
        assignments=(f"assignment.gemini.e2e.{index}",), dependency_graph={}, concurrency_ceiling=1,
        required_verification=True, completion_criteria=("source_check",),
        plan_version_hash=f"plan.gemini.e2e.{index}", policy_version_hash="policy.gemini.e2e",
        status=ContractStatus.proposed,
    ))
    adapter = GeminiApiAdapter(model, ledger=ledger)
    modality = "image" if any(part.kind == "image" for part in attachments) else ("document" if attachments else "text")
    call = request(model, index, query, modality=modality)
    router = ModelRouter(
        ModelRegistry("registry.gemini.test", "1.0", (target(model),), "e" * 64, "2030-01-01T00:00:00Z"),
        {adapter.adapter_id: adapter}, policy_version_hash="policy.gemini.e2e",
        resource_admission=lambda _target, _request: "admitted",
    )
    execution = orchestrator.execute_model_call(
        call, router=router, pack_ref="pack.refinery.v0", hardware_profile_ref="hw.gemini-test",
        messages=(BackendMessage("user", (BackendContent("text", text=query), *attachments)),), stream=stream,
    )
    if execution.response is None:
        raise RuntimeError(execution.route.decision.reason)
    if stream:
        output = "".join(chunk.text for chunk in execution.response)
    else:
        output = execution.response.output
    return {"model": model, "status": "passed", "response": output, "route": execution.route.decision.to_dict()}, len(ledger.events)


def choose_models(adapter: GeminiApiAdapter, requested: str) -> list[str]:
    models = [item.strip() for item in requested.split(",") if item.strip()]
    if models != ["auto"]:
        return models
    return [name for name in adapter.available_models() if name.startswith("gemini-") and not any(tag in name for tag in ("tts", "embedding", "computer-use"))][:5]


def load_attachment(path_text: str) -> BackendContent:
    path = Path(path_text).resolve()
    if not path.is_file():
        raise ValueError(f"attachment is not a file: {path}")
    raw = path.read_bytes()
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    kind = "image" if mime_type.startswith("image/") else "document"
    encoded = base64.b64encode(raw).decode("ascii")
    return BackendContent(kind=kind, media_ref=f"data:{mime_type};base64,{encoded}", media_type=mime_type, content_hash=hashlib.sha256(raw).hexdigest())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=os.getenv("AIRBENCH_GEMINI_MODELS", "auto"))
    parser.add_argument("--query", default="Reply with exactly: AirBench Gemini pipeline OK")
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--interactive", action="store_true", help="read queries until exit")
    parser.add_argument("--attachment", action="append", default=[], help="local image or PDF to send as governed test input")
    args = parser.parse_args()
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is required; no request was sent.", file=sys.stderr)
        return 2
    models = choose_models(GeminiApiAdapter("model-discovery"), args.models)
    if not models:
        print("No Gemini text-generation models were returned for this API key.", file=sys.stderr)
        return 3
    attachments = tuple(load_attachment(item) for item in args.attachment)
    queries = [args.query]
    if args.interactive:
        print("AirBench Gemini dev console. Type 'exit' to stop.")
        queries = []
        while True:
            query = input("airbench> ").strip()
            if query.lower() in {"exit", "quit"}:
                break
            if query:
                queries.append(query)
    for query_index, query in enumerate(queries, 1):
        for model_index, model in enumerate(models, 1):
            try:
                result, event_count = run_one(model, model_index + (query_index - 1) * len(models), query, stream=args.stream, attachments=attachments)
                print(json.dumps({"test_only": True, "query": query, "ledger_events": event_count, **result}, indent=2, default=str))
            except Exception as exc:
                print(json.dumps({"test_only": True, "query": query, "model": model, "status": "failed", "error": str(exc)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
