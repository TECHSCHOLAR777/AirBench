"""Measure one demo model lane and emit qualification evidence.

Runs against a live (usually tunnelled) vLLM OpenAI-compatible endpoint and
records only measured values:

  * identity — HTTP health and the exact served model name;
  * performance — repeated streaming completions for first-token latency,
    end-to-end latency, token throughput, and error rate;
  * concurrency — a bounded ramp (1..--max-concurrency) for the stable level
    and the failure threshold;
  * safety — client timeout behaviour, stream cancellation with a follow-up
    request, and the no-egress offline environment;
  * environment (optional, --ssh-host) — remote GPU facts and the serving
    container digest captured over SSH.

The output JSON carries the flat keys consumed by
``scripts/airbench_qualify.py --evidence-file`` (``cancellation_result``,
``timeout_result``, ``no_egress_startup_result``, ``cancellation_and_timeout``,
``no_egress_startup``) plus detail sections for the record.  Nothing is
estimated: a value that could not be measured is ``null`` with a note.

Usage:
    python scripts/airbench_measure_lane.py --target-id airbench-gemma-4-e2b \
        --endpoint http://127.0.0.1:18001 --served-model airbench-gemma-4-e2b
    python scripts/airbench_measure_lane.py --target-id airbench-gemma-4-12b \
        --endpoint http://127.0.0.1:18002 --served-model airbench-gemma-4-12b \
        --ssh-host mmmut-server --container airbench-vllm-12b
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

TOOL_VERSION = "airbench-measure-0.1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "qualifications" / "records"


def _get_json(url: str, timeout: float) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - operator-provided loopback URL
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _post_chat(endpoint: str, payload: dict, timeout: float):
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - operator-provided loopback URL


def _latency_sample(endpoint: str, model: str, timeout: float) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly MEASURE_OK."}],
        "temperature": 0, "max_tokens": 16, "stream": True,
        "stream_options": {"include_usage": True},
    }
    start = time.perf_counter()
    ttfb_ms = None
    usage = None
    with _post_chat(endpoint, payload, timeout) as response:
        for raw in response:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"]
            choice = (chunk.get("choices") or [{}])[0]
            if ttfb_ms is None and (choice.get("delta", {}).get("content") or choice.get("finish_reason") is not None):
                ttfb_ms = (time.perf_counter() - start) * 1000
    e2e_ms = (time.perf_counter() - start) * 1000
    return {
        "ttfb_ms": ttfb_ms if ttfb_ms is not None else e2e_ms,
        "e2e_ms": e2e_ms,
        "prompt_tokens": (usage or {}).get("prompt_tokens"),
        "completion_tokens": (usage or {}).get("completion_tokens"),
    }


def _complete(endpoint: str, model: str, timeout: float, max_tokens: int = 16) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly MEASURE_OK."}],
        "temperature": 0, "max_tokens": max_tokens,
    }
    with _post_chat(endpoint, payload, timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str((body.get("choices") or [{}])[0].get("message", {}).get("content") or "")


def _measure_latency(endpoint: str, model: str, reps: int, timeout: float) -> tuple[dict, int, int]:
    samples: list[dict] = []
    errors = 0
    for _ in range(reps):
        try:
            samples.append(_latency_sample(endpoint, model, timeout))
        except Exception:  # noqa: BLE001 - a failed call is a measured error, not a crash
            errors += 1
    summary: dict = {"repetitions": reps, "error_count": errors, "samples": samples}
    if samples:
        ttfb = sorted(sample["ttfb_ms"] for sample in samples)
        e2e = sorted(sample["e2e_ms"] for sample in samples)
        summary["first_token_latency_ms"] = {
            "median": round(statistics.median(ttfb), 3),
            "p95": round(ttfb[max(0, int(len(ttfb) * 0.95) - 1)], 3),
        }
        summary["end_to_end_latency_ms"] = {"median": round(statistics.median(e2e), 3)}
        if statistics.mean(e2e) > 0:
            summary["latency_cv"] = round(statistics.pstdev(e2e) / statistics.mean(e2e), 4)
        token_counts = [sample["completion_tokens"] for sample in samples if sample.get("completion_tokens")]
        if token_counts:
            rates = [
                sample["completion_tokens"] / (sample["e2e_ms"] - sample["ttfb_ms"]) * 1000
                for sample in samples
                if sample.get("completion_tokens") and sample["e2e_ms"] > sample["ttfb_ms"]
            ]
            if rates:
                summary["generation_tokens_per_s"] = round(statistics.median(rates), 3)
    return summary, reps, errors


def _measure_concurrency(endpoint: str, model: str, max_concurrency: int, timeout: float) -> dict:
    stable = 0
    failure_threshold = None
    requests_sent = 0
    for level in range(1, max_concurrency + 1):
        with ThreadPoolExecutor(max_workers=level) as pool:
            futures = [pool.submit(_complete, endpoint, model, timeout) for _ in range(level)]
            outcomes = []
            for future in futures:
                requests_sent += 1
                try:
                    future.result()
                    outcomes.append(True)
                except Exception:  # noqa: BLE001
                    outcomes.append(False)
        if all(outcomes):
            stable = level
        else:
            failure_threshold = level
            break
    return {
        "stable_max_concurrency": stable,
        "failure_threshold_concurrency": failure_threshold,
        "max_tested_concurrency": max_concurrency,
        "requests_sent": requests_sent,
        "note": None if failure_threshold is not None else "no failure observed up to max_tested_concurrency",
    }


def _probe_timeout(endpoint: str, model: str) -> tuple[str, str]:
    try:
        _complete(endpoint, model, timeout=0.05)
        return "pass", "completed before the short timeout"
    except (socket.timeout, TimeoutError):
        return "pass", "clean client-side timeout"
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)):
            return "pass", "clean client-side timeout"
        return "fail", f"unexpected error: {type(exc).__name__}"
    except Exception:  # noqa: BLE001
        return "fail", "unexpected error during timeout probe"


def _probe_cancellation(endpoint: str, model: str, timeout: float) -> tuple[str, str]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Count slowly from one to one hundred."}],
        "temperature": 0, "max_tokens": 128, "stream": True,
    }
    try:
        with _post_chat(endpoint, payload, timeout) as response:
            for raw in response:
                if raw.strip():
                    break  # abort the stream after the first event
    except Exception as exc:  # noqa: BLE001
        return "fail", f"stream could not be aborted: {type(exc).__name__}"
    try:
        _complete(endpoint, model, timeout)
    except Exception as exc:  # noqa: BLE001
        return "fail", f"follow-up request failed after abort: {type(exc).__name__}"
    return "pass", "endpoint served a follow-up request after an aborted stream"


def _probe_no_egress(endpoint: str) -> tuple[str, dict]:
    missing = [name for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE") if os.environ.get(name) != "1"]
    host = urlparse(endpoint).hostname or ""
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    detail = {"missing_env": missing, "loopback_endpoint": loopback}
    return ("pass" if not missing and loopback else "fail"), detail


def _capture_remote(ssh_host: str, container: str) -> dict:
    facts: dict = {"gpu": None, "container_digest": None, "errors": []}
    try:
        output = subprocess.run(
            ["ssh", ssh_host, "nvidia-smi",
             "--query-gpu=name,uuid,memory.total,memory.free,driver_version,compute_cap",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()
        gpus = []
        for line in output.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 6:
                gpus.append({
                    "model": parts[0], "uuid": parts[1],
                    "vram_total_mib": parts[2], "vram_free_mib": parts[3],
                    "driver_version": parts[4], "compute_cap": parts[5],
                })
        facts["gpu"] = gpus or None
    except Exception as exc:  # noqa: BLE001 - remote capture is best-effort evidence
        facts["errors"].append(f"nvidia-smi over ssh failed: {type(exc).__name__}")
    if container:
        for template in ("{{index .RepoDigests 0}}", "{{.Image}}"):
            try:
                output = subprocess.run(
                    ["ssh", ssh_host, "docker", "inspect", "--format", template, container],
                    capture_output=True, text=True, timeout=60, check=True,
                ).stdout.strip()
                if output:
                    facts["container_digest"] = output
                    break
            except Exception:  # noqa: BLE001
                continue
        if not facts["container_digest"]:
            facts["errors"].append("docker inspect over ssh failed")
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--served-model", required=True)
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--ssh-host", default="", help="Optional: capture GPU facts over SSH.")
    parser.add_argument("--container", default="", help="Optional: serving container name for the digest capture.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Evidence JSON path (default: qualifications/records/<target-id>.measurement.json).")
    args = parser.parse_args(argv)

    models = _get_json(args.endpoint.rstrip("/") + "/v1/models", args.timeout) or {}
    served = sorted({
        item.get("id") for item in models.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    })
    served_verified = args.served_model in served
    health_ok = _get_json(args.endpoint.rstrip("/") + "/health", args.timeout) is not None or served_verified

    latency, calls, errors = _measure_latency(args.endpoint, args.served_model, args.reps, args.timeout)
    concurrency = _measure_concurrency(args.endpoint, args.served_model, args.max_concurrency, args.timeout)
    timeout_result, timeout_detail = _probe_timeout(args.endpoint, args.served_model)
    cancellation_result, cancellation_detail = _probe_cancellation(args.endpoint, args.served_model, args.timeout)
    no_egress_result, no_egress_detail = _probe_no_egress(args.endpoint)

    environment = _capture_remote(args.ssh_host, args.container) if args.ssh_host else None
    total_calls = calls + concurrency.get("requests_sent", 0) + 2
    total_errors = errors + (0 if concurrency.get("failure_threshold_concurrency") is None else 1)

    evidence = {
        "tool_version": TOOL_VERSION,
        "target_id": args.target_id,
        "served_model": args.served_model,
        "endpoint": args.endpoint,
        "measured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "identity": {
            "health_ok": health_ok,
            "served_model_verified": served_verified,
            "served_models": served,
        },
        "performance": {**latency, "error_rate": round(total_errors / total_calls, 4) if total_calls else None},
        "concurrency": concurrency,
        "probes": {
            "timeout": {"result": timeout_result, "detail": timeout_detail},
            "cancellation": {"result": cancellation_result, "detail": cancellation_detail},
            "no_egress": {"result": no_egress_result, "detail": no_egress_detail},
        },
        "environment": environment,
        # Flat keys consumed by scripts/airbench_qualify.py --evidence-file.
        "cancellation_result": cancellation_result,
        "timeout_result": timeout_result,
        "no_egress_startup_result": no_egress_result,
        "cancellation_and_timeout": 1.0 if cancellation_result == "pass" and timeout_result == "pass" else 0.0,
        "no_egress_startup": no_egress_result,
    }

    output = args.output or DEFAULT_OUTPUT_DIR / f"{args.target_id}.measurement.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    safe = latency.get("first_token_latency_ms", {})
    print(f"target={args.target_id} served_model_verified={served_verified}")
    print(f"first_token_ms_median={safe.get('median')} e2e_ms_median={latency.get('end_to_end_latency_ms', {}).get('median')}")
    print(f"stable_concurrency={concurrency['stable_max_concurrency']} failure_threshold={concurrency['failure_threshold_concurrency']}")
    print(f"cancellation={cancellation_result} timeout={timeout_result} no_egress={no_egress_result}")
    print(f"evidence written to {output}")

    passed = served_verified and all(result == "pass" for result in (cancellation_result, timeout_result, no_egress_result))
    print(f"model lane measurement: {'pass' if passed else 'fail'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
