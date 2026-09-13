"""Drive the governed two-endpoint demo through the AirBench Node API.

Runs the documented command chain against a running Node and a live (or
tunnelled) vLLM:

  create -> authorize (Node plans + admits) -> plan ready -> approve
         -> model-call -> route-trace

Uses only the standard library.  No secrets are stored; the bearer token is
read from AIRBENCH_BEARER_TOKEN or passed on the command line.

Usage:
    python scripts/run_two_endpoint_demo.py
    python scripts/run_two_endpoint_demo.py --base-url http://127.0.0.1:8765 \
        --token demo-token --subject demo.operator --hardware-profile-ref workstation-04
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - operator-provided loopback URL
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} for {method} {url}\n{detail}") from exc


def _command(command_id: str, idempotency: str, command_type: str, arguments: dict,
             *, task_id: str | None, expected_sequence: int | None, subject: str, client_version: str) -> dict:
    return {
        "command_id": command_id, "task_id": task_id, "actor": subject,
        "expected_sequence": expected_sequence, "idempotency_key": idempotency,
        "client_version": client_version, "command_type": command_type, "arguments": arguments,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.environ.get("AIRBENCH_NODE_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--token", default=os.environ.get("AIRBENCH_BEARER_TOKEN", "demo-token"))
    parser.add_argument("--subject", default=os.environ.get("AIRBENCH_SUBJECT", "demo.operator"))
    parser.add_argument("--domain-pack-ref", default=os.environ.get("AIRBENCH_DOMAIN_PACK_REF", "refinery-psu-v0"))
    parser.add_argument("--hardware-profile-ref", default="workstation-04")
    parser.add_argument("--protocol-version", default="0.1")
    args = parser.parse_args(argv)
    base = args.base_url.rstrip("/")

    def get(path: str) -> dict:
        return _request("GET", base + path, args.token)

    def post(path: str, body: dict) -> dict:
        return _request("POST", base + path, args.token, body)

    def task_sequence(task_id: str) -> int:
        return int(get(f"/api/v1/tasks/{task_id}/events")["next_sequence"])

    print("== Node model serving ==")
    print(json.dumps(get("/api/v1/node/model-serving"), indent=2))

    body = _command(
        "command.demo.create", "idem.demo.create", "task.create",
        {
            "principal_id": args.subject, "clearance": "internal",
            "request": "Summarise the pump inspection finding.", "risk_class": "inspection_review",
            "autonomy_ceiling": "review_required", "allowed_evidence_scope": ["inspection-report"],
            "permitted_worker_capabilities": ["reasoning"], "permitted_tools": [],
            "output_contract": "text", "verification_criteria": ["source_check"],
            "resource_budget": {"max_concurrency": 1},
        },
        task_id=None, expected_sequence=None, subject=args.subject, client_version=args.protocol_version,
    )
    created = post("/api/v1/tasks", body)
    task_id = created["task"]["task_id"]
    print(f"\ncreated task: {task_id}")

    print("\n== authorize (Node plans + admits) ==")
    authorize = _command(
        "command.demo.authorize", "idem.demo.authorize", "task.authorize", {"authorization_ref": "auth.demo"},
        task_id=task_id, expected_sequence=task_sequence(task_id), subject=args.subject,
        client_version=args.protocol_version,
    )
    print(json.dumps(post(f"/api/v1/tasks/{task_id}/authorize", authorize), indent=2))

    print("\n== plan ==")
    plan = get(f"/api/v1/tasks/{task_id}/plan")
    print(f"plan_state={plan['plan_state']} execution_mode={plan.get('execution_mode')}")

    print("\n== approve ==")
    approve = _command(
        "command.demo.approve", "idem.demo.approve", "task.approve_plan", {"approval_ref": "approval.demo"},
        task_id=task_id, expected_sequence=task_sequence(task_id), subject=args.subject,
        client_version=args.protocol_version,
    )
    print(json.dumps(post(f"/api/v1/tasks/{task_id}/approve", approve), indent=2))

    print("\n== model call (two-lane routing) ==")
    model_call = _command(
        "command.demo.call", "idem.demo.call", "model.call",
        {
            "hardware_profile_ref": args.hardware_profile_ref,
            "request": {
                "request_id": "request.demo.call", "task_id": task_id, "team_id": "team.demo",
                "worker_id": "worker.demo", "task_kind": "inspection_review", "modality": "text",
                "required_capability": "reasoning", "evidence_summary": ["evidence.demo"],
                "clearance": "internal", "action_risk": "inspection_review",
                "resource_budget": {"context_tokens": 512}, "attempt": 1,
                "idempotency_key": "idem.demo.request", "timeout_ms": 180000,
                "role": "reasoning", "resource_lease_id": "lease.demo",
            },
            "messages": [{"role": "user", "content": [{"kind": "text", "text": "Reply with exactly AIRBENCH_OK."}]}],
            "output": {"mode": "text"},
        },
        task_id=task_id, expected_sequence=task_sequence(task_id), subject=args.subject,
        client_version=args.protocol_version,
    )
    result = post(f"/api/v1/tasks/{task_id}/model-call", model_call)
    if "model" not in result:
        print(json.dumps(result, indent=2))
        return 0
    model = result["model"]
    print(f"selected_target={model['selected_target']} status={model['status']}")
    print(f"output={model['output']!r}")
    print(f"endpoint_id={model['provenance'].get('endpoint_id')} response_hash={model['provenance'].get('response_hash','')[:16]}...")

    print("\n== route trace ==")
    trace = get(f"/api/v1/tasks/{task_id}/route-trace")
    for entry in trace.get("entries", []):
        print(f"  seq={entry.get('sequence')} {entry.get('eventType')} target={entry.get('selected_target')}")
    print("\nDemo chain complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
