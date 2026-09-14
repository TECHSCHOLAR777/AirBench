"""AirBench Node preflight — report what owns the demo port and Node readiness.

Phase 0 of the end-to-end roadmap: startup must prove its dependencies instead
of assuming them.  This script answers, before/while starting a Node:

  * who owns the local port (another Node, a foreign process, or nobody);
  * if a Node answers: its identity, protocol, ledger head, model-serving
    lane states, and hardware profile from the unauthenticated readiness
    endpoints;
  * the store paths a demo would use.

Read-only. Exits 0 when the port is free (ready to start a Node) or a healthy
Node is running; 1 when the port is owned by a foreign process or a running
Node reports degraded lanes; 2 when a running Node fails its readiness probe.

Usage:
    python scripts/node_preflight.py            # default port 8765
    python scripts/node_preflight.py --port 8765 --json
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _get_json(url: str, timeout: float) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - loopback probe
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # A degraded Node still answers its readiness route with 503; its
        # body is the readiness report, so parse instead of misclassifying
        # the listener as foreign.
        try:
            return json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError):
            return None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _port_state(port: int, timeout: float) -> dict:
    probe = _get_json(f"http://127.0.0.1:{port}/api/v1/node/readiness", timeout)
    if probe is not None:
        return {"owner": "airbench-node", "node_readiness": probe}
    # Nothing answered the readiness route: is anything listening at all?
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            return {"owner": "unknown-listener", "node_readiness": None}
    return {"owner": "free", "node_readiness": None}


def _owner_pid_windows(port: int) -> int | None:
    try:
        import subprocess  # noqa: S404 - read-only netstat query

        output = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=15,
        ).stdout
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].endswith(f":{port}"):
                return int(parts[4])
    except (OSError, ValueError):
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    state = _port_state(args.port, args.timeout)
    report: dict = {
        "port": args.port,
        "owner": state["owner"],
        "owner_pid": _owner_pid_windows(args.port) if state["owner"] != "free" else None,
        "node_readiness": state["node_readiness"],
        "stores": {
            "ledger": str(REPO_ROOT / ".airbench-node-ledger.sqlite"),
            "intake_root": str(REPO_ROOT / ".airbench-intake"),
            "artifact_root": str(REPO_ROOT / ".airbench-artifacts"),
            "world_model": str(REPO_ROOT / ".airbench-world-model.db"),
            "decisions": str(REPO_ROOT / ".airbench-decisions.db"),
        },
    }

    if state["owner"] == "airbench-node":
        serving = _get_json(f"http://127.0.0.1:{args.port}/api/v1/node/model-serving", args.timeout)
        report["model_serving"] = serving
        degraded = serving is None or serving.get("status") != "ready"
    else:
        report["model_serving"] = None
        degraded = False

    if state["owner"] == "free":
        status, code = "port_free", 0
    elif state["owner"] == "airbench-node":
        status = "node_ready" if not degraded else "node_degraded"
        code = 0 if not degraded else 1
    elif state["owner"] == "unknown-listener":
        status, code = "port_owned_by_foreign_process", 1
    else:  # pragma: no cover - readiness route answered but reported failure
        status, code = "node_unhealthy", 2
    report["status"] = status

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"port {args.port}: {status} (owner={report['owner']}, pid={report['owner_pid']})")
        if state["node_readiness"] is not None:
            print(f"  node readiness: {json.dumps(state['node_readiness'], sort_keys=True)[:300]}")
        if report.get("model_serving"):
            for endpoint in report["model_serving"].get("endpoints", []):
                print(f"  lane {endpoint.get('target_id')}: {endpoint.get('reason', endpoint.get('readiness'))}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
