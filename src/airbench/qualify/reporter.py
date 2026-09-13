"""Build certificate documents from a completed qualification run."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .harness import QualificationRun


def _now_iso(now: datetime | None) -> str:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_certificate(
    run: QualificationRun,
    *,
    hardware_profile_id: str,
    runtime_version: str,
    adapter_id: str = "airbench.qualify",
    duration_days: int = 90,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Produce a certificate YAML document for one completed run.

    ``status`` reflects the measured pass rate: a run at or above 0.8 is
    ``ready_for_review``; below that it is ``unqualified``.  A certificate is
    never treated as qualification until an operator signs it.
    """
    if duration_days < 1:
        raise ValueError("duration_days must be positive")
    current = now or datetime.now(timezone.utc)
    pass_rate = run.pass_rates.get("fixture_pass_rate", 0.0)
    return {
        "certificate_id": f"cert-{run.target_id}-{run.role}-v0",
        "target_id": run.target_id,
        "worker_role": run.role,
        "hardware_profile_id": hardware_profile_id,
        "runtime_version": runtime_version,
        "adapter_id": adapter_id,
        "qualification_source": run.qualification_source,
        "fixture_set_hash": run.fixture_set_hash,
        "benchmark_scores": run.benchmark_scores,
        "pass_rates": run.pass_rates,
        "status": "ready_for_review" if pass_rate >= 0.8 else "unqualified",
        "qualified_at": _now_iso(current),
        "expires_at": _now_iso(current + timedelta(days=duration_days)),
        "signature": None,
    }


__all__ = ["build_certificate"]
