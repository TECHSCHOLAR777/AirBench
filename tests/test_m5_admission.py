"""M5.2 — Expanded admission controller tests covering all scheduling scenarios.

New tests beyond the existing 4:
  - degraded_needs_review mode
  - All 5 priority classes are accepted; unknown priority rejected
  - release() correctly frees VRAM so next admission can proceed
  - Background request with active interactive work → queued
  - Queue ordering: interactive_high_consequence before interactive_normal
  - active_vram_bytes() tracks committed work
  - Audit payload contains all required ledger fields
  - Extended HardwareProfile fields validate correctly
"""

import unittest

from contracts import (
    AdmissionController,
    AdmissionError,
    AdmissionRequest,
    HardwareMeasurement,
    HardwareProfile,
    PRIORITY_CLASSES,
)
from contracts.admission import ReleaseRecord
from contracts.models import LEDGER_EVENT_TYPES


# ── Test fixture helpers ───────────────────────────────────────────────────────

def _profile(vram: int = 96_000, slots: int = 4, modes: tuple[str, ...] = ("parallel", "serial_virtual_team")) -> HardwareProfile:
    """Build a minimal valid HardwareProfile for testing."""
    return HardwareProfile.from_dict({
        "profile_id": "gpu-96gb-01",
        "gpu_model": "NVIDIA-H100-96GB",
        "gpu_count": 1,
        "vram_bytes": vram,
        "driver_version": "550.90.07",
        "accelerator_runtime": "cuda-12.4",
        "cpu_model": "Intel-Xeon-6438M",
        "cpu_cores": 32,
        "ram_bytes": 256_000,
        "storage_bytes": 2_000_000,
        "scratch_bytes": 500_000,
        "model_context_tokens": 32768,
        "kv_cache_bytes": 40_000,
        "safe_parallel_slots": slots,
        "egress_policy": "deny-all",
        "measurement_hash": "a" * 64,
        "supported_execution_modes": list(modes),
        "network_check_id": "evt-egress-001",
        "sandbox_runtime": "firejail",
        "benchmark_result_ref": "benchmarks/model_hardware_results.yaml#gpu-96gb-01",
    })


def _measurement(profile: HardwareProfile, available_vram: int = 96_000, max_concurrency: int = 4) -> HardwareMeasurement:
    """Build a HardwareMeasurement matching the given profile."""
    return HardwareMeasurement(
        measurement_id="measurement-1",
        profile_id=profile.profile_id,
        measured_at="2026-01-01T00:00:00Z",
        available_vram_bytes=available_vram,
        available_ram_bytes=200_000,
        kv_cache_bytes=40_000,
        model_residency_bytes=(),
        latency_ms=(),
        throughput_tokens_per_second=(),
        sandbox_limits=(),
        max_concurrency=max_concurrency,
        egress_verified=True,
    )


def _request(
    vram: tuple[int, int, int] = (20_000, 20_000, 10_000),
    priority: str = "interactive_normal",
    task_id: str = "task-1",
    team_id: str = "team-1",
    degraded_allowed: bool = False,
    background: bool = False,
) -> AdmissionRequest:
    """Build a 3-worker admission request (lead + vision + verifier)."""
    return AdmissionRequest(
        task_id=task_id,
        team_id=team_id,
        worker_capabilities=(("lead", "reasoning"), ("vision", "vision"), ("verifier", "verification")),
        reservations=(
            ("lead", (("vram_bytes", vram[0]),)),
            ("vision", (("vram_bytes", vram[1]),)),
            ("verifier", (("vram_bytes", vram[2]),)),
        ),
        verifier_worker_id="verifier",
        priority=priority,
        degraded_allowed=degraded_allowed,
        background=background,
    )


class AdmissionTests(unittest.TestCase):
    """M5.2 admission controller tests — all scheduling paths."""

    # ── Existing tests (must remain green) ────────────────────────────────────

    def test_parallel_admission_records_verifier_and_capacity(self) -> None:
        """3 workers fitting concurrently → parallel admission."""
        profile = _profile()
        decision = AdmissionController(profile, _measurement(profile)).admit(_request())
        self.assertEqual(decision.plan.admission, "admitted")
        self.assertEqual(decision.plan.execution_mode, "parallel")
        self.assertEqual(decision.plan.verifier_capacity, 1)

    def test_constrained_team_uses_serial_virtual_team_without_dropping_verifier(self) -> None:
        """Workers don't fit concurrently but largest single worker fits → serial mode."""
        profile = _profile()
        decision = AdmissionController(
            profile, _measurement(profile, available_vram=25_000, max_concurrency=1)
        ).admit(_request((20_000, 20_000, 10_000)))
        self.assertEqual(decision.plan.execution_mode, "serial_virtual_team")
        self.assertEqual(decision.plan.verifier_capacity, 1)

    def test_oversized_reservation_stops_and_missing_verifier_stops(self) -> None:
        """Oversized request → stopped; missing verifier → stopped."""
        profile = _profile()
        measurement = _measurement(profile)
        controller = AdmissionController(profile, measurement)
        # Oversized: single worker requests more VRAM than available
        self.assertEqual(controller.admit(_request((100_000, 1, 1))).plan.admission, "stopped")
        # Missing verifier: verifier_worker_id not in reservations
        request = AdmissionRequest(
            "task-2", "team-2",
            (("lead", "reasoning"),),
            (("lead", (("vram_bytes", 1),)),),
            verifier_worker_id="verifier",   # verifier not in reservations
        )
        self.assertEqual(controller.admit(request).plan.admission, "stopped")

    def test_unverified_or_mismatched_measurement_fails_closed(self) -> None:
        """egress_verified=False raises AdmissionError."""
        profile = _profile()
        with self.assertRaises(AdmissionError):
            HardwareMeasurement(
                "measurement-1", profile.profile_id, "2026-01-01T00:00:00Z",
                1, 1, 1, (), (), (), (), 1, False,
            )

    # ── New tests: priority classes ───────────────────────────────────────────

    def test_all_five_priority_classes_are_accepted(self) -> None:
        """All 5 canonical priority classes are accepted without raising AdmissionError."""
        profile = _profile()
        measurement = _measurement(profile)
        for priority in PRIORITY_CLASSES:
            request = _request(priority=priority)
            # Just verify construction and admission don't raise
            controller = AdmissionController(profile, measurement)
            decision = controller.admit(request)
            self.assertIn(decision.plan.admission, {"admitted", "queued", "stopped", "degraded_needs_review"})

    def test_legacy_priority_aliases_are_accepted(self) -> None:
        """Legacy 'interactive' and 'background' values are normalized, not rejected."""
        profile = _profile()
        measurement = _measurement(profile)
        for legacy in ("interactive", "background"):
            request = _request(priority=legacy)
            decision = AdmissionController(profile, measurement).admit(request)
            self.assertIn(decision.plan.admission, {"admitted", "queued"})

    def test_unknown_priority_is_rejected(self) -> None:
        """An unrecognized priority class raises AdmissionError on construction."""
        with self.assertRaises(AdmissionError):
            _request(priority="turbo_express")

    # ── New tests: degraded_needs_review ──────────────────────────────────────

    def test_degraded_needs_review_when_primary_oversized_and_caller_permits(self) -> None:
        """When primary VRAM exceeds available but caller has a qualified fallback,
        admission returns degraded_needs_review instead of queued."""
        profile = _profile(vram=30_000)
        # Available VRAM is 15_000; largest worker is 20_000 → serial doesn't fit
        # But verifier (10_000) fits, and degraded_allowed=True
        measurement = _measurement(profile, available_vram=15_000)
        request = _request(vram=(20_000, 20_000, 10_000), degraded_allowed=True)
        decision = AdmissionController(profile, measurement).admit(request)
        self.assertEqual(decision.plan.admission, "degraded_needs_review")
        self.assertIn(
            "team.resource_plan.degraded_needs_review",
            LEDGER_EVENT_TYPES,
            "team.resource_plan.degraded_needs_review must be in LEDGER_EVENT_TYPES",
        )

    def test_no_degraded_without_caller_permission(self) -> None:
        """Without degraded_allowed=True, the controller falls through to queued or stopped."""
        profile = _profile(vram=30_000)
        measurement = _measurement(profile, available_vram=15_000)
        # active VRAM is 0, so this hits the 'stopped' gate
        request = _request(vram=(20_000, 20_000, 10_000), degraded_allowed=False)
        decision = AdmissionController(profile, measurement).admit(request)
        self.assertEqual(decision.plan.admission, "stopped")

    # ── New tests: release() ──────────────────────────────────────────────────

    def test_release_frees_vram_and_returns_release_record(self) -> None:
        """release() reduces active VRAM and returns a typed ReleaseRecord."""
        profile = _profile()
        measurement = _measurement(profile)
        controller = AdmissionController(profile, measurement)
        request = _request(vram=(20_000, 20_000, 10_000))
        decision = controller.admit(request)
        self.assertEqual(decision.plan.admission, "admitted")
        committed = controller.active_vram_bytes()
        self.assertGreater(committed, 0)

        record = controller.release(request)

        self.assertIsInstance(record, ReleaseRecord)
        self.assertEqual(record.released_vram_bytes, committed)
        self.assertEqual(controller.active_vram_bytes(), 0)
        self.assertEqual(record.remaining_active_vram_bytes, 0)
        self.assertIn("team_id", record.audit_payload)
        self.assertIn("released_vram_bytes", record.audit_payload)

    def test_release_of_non_admitted_team_is_zero_byte_noop(self) -> None:
        """Releasing a team that was queued/stopped (never admitted) is a safe no-op."""
        profile = _profile()
        measurement = _measurement(profile, available_vram=5_000)
        controller = AdmissionController(profile, measurement)
        request = _request(vram=(20_000, 20_000, 10_000))  # will be stopped
        decision = controller.admit(request)
        self.assertEqual(decision.plan.admission, "stopped")

        record = controller.release(request)

        self.assertIsInstance(record, ReleaseRecord)
        self.assertEqual(record.released_vram_bytes, 0)

    def test_release_allows_subsequent_admission(self) -> None:
        """After releasing a team's resources, the next team can be admitted."""
        profile = _profile(vram=30_000)
        measurement = _measurement(profile, available_vram=30_000)
        controller = AdmissionController(profile, measurement)
        first_request = _request(vram=(20_000, 1, 5_000), task_id="task-1", team_id="team-1")
        decision_1 = controller.admit(first_request)
        self.assertEqual(decision_1.plan.admission, "admitted")

        # Second request would not fit while first is active
        second_request = _request(vram=(20_000, 1, 5_000), task_id="task-2", team_id="team-2")
        decision_2_before_release = controller.admit(second_request)
        self.assertNotEqual(decision_2_before_release.plan.admission, "admitted")

        # Release first team
        controller.release(first_request)

        # Now second can be admitted (using a fresh controller state)
        # We create a new request because the first was already tracked
        third_request = _request(vram=(20_000, 1, 5_000), task_id="task-3", team_id="team-3")
        decision_3 = controller.admit(third_request)
        self.assertEqual(decision_3.plan.admission, "admitted")

    # ── New tests: background / interactive priority ───────────────────────────

    def test_background_request_queued_when_interactive_is_active(self) -> None:
        """A background request is queued when VRAM is committed to an interactive task."""
        profile = _profile(vram=50_000)
        measurement = _measurement(profile, available_vram=50_000)
        controller = AdmissionController(profile, measurement)

        # Admit an interactive task first
        interactive_request = _request(
            vram=(30_000, 1, 5_000), priority="interactive_normal", task_id="task-interactive", team_id="team-interactive"
        )
        decision_interactive = controller.admit(interactive_request)
        self.assertEqual(decision_interactive.plan.admission, "admitted")

        # Background ingestion request should now be queued (not enough VRAM for parallel)
        background_request = _request(
            vram=(30_000, 1, 5_000), priority="background_ingestion",
            task_id="task-background", team_id="team-background",
        )
        decision_background = controller.admit(background_request)
        self.assertEqual(decision_background.plan.admission, "queued")

    def test_queue_ordering_high_consequence_before_normal(self) -> None:
        """interactive_high_consequence requests have higher priority rank than interactive_normal."""
        profile = _profile(vram=10_000)
        measurement = _measurement(profile, available_vram=10_000)
        controller = AdmissionController(profile, measurement)

        # Fill capacity so subsequent requests are queued
        seed_request = _request(vram=(5_000, 1, 2_000), priority="interactive_normal", task_id="seed", team_id="seed-team")
        seed_decision = controller.admit(seed_request)
        self.assertEqual(seed_decision.plan.admission, "admitted")

        # Queue a normal interactive request
        normal_request = _request(
            vram=(5_000, 1, 2_000), priority="interactive_normal",
            task_id="task-normal", team_id="team-normal",
        )
        normal_decision = controller.admit(normal_request)
        self.assertEqual(normal_decision.plan.admission, "queued")

        # Queue a high-consequence interactive request
        high_request = _request(
            vram=(5_000, 1, 2_000), priority="interactive_high_consequence",
            task_id="task-high", team_id="team-high",
        )
        high_decision = controller.admit(high_request)
        self.assertEqual(high_decision.plan.admission, "queued")

        # High-consequence should come first in queue ordering
        queued = controller.queued_requests()
        self.assertGreater(len(queued), 1)
        self.assertEqual(queued[0].priority, "interactive_high_consequence")

    # ── New tests: audit payload completeness ─────────────────────────────────

    def test_audit_payload_contains_all_required_ledger_fields(self) -> None:
        """Admitted decision's audit_payload contains all fields needed to emit a ledger event."""
        profile = _profile()
        decision = AdmissionController(profile, _measurement(profile)).admit(_request())
        payload = decision.audit_payload
        required_keys = {
            "decision_id", "task_id", "team_id", "admission",
            "execution_mode", "verifier_worker_id", "priority",
            "committed_vram_bytes", "active_vram_bytes_after", "reason",
            "ledger_event_type",
        }
        missing = required_keys - payload.keys()
        self.assertFalse(missing, f"audit_payload is missing keys: {missing}")
        # ledger_event_type must reference a valid LEDGER_EVENT_TYPES member
        self.assertIn(
            payload["ledger_event_type"],
            LEDGER_EVENT_TYPES,
            f"ledger_event_type '{payload['ledger_event_type']}' is not in LEDGER_EVENT_TYPES",
        )

    def test_queued_audit_payload_event_type(self) -> None:
        """Queued decision emits the team.resource_plan.queued event type in its payload."""
        profile = _profile(vram=10_000)
        measurement = _measurement(profile, available_vram=10_000)
        controller = AdmissionController(profile, measurement)
        # Fill capacity
        controller.admit(_request(vram=(5_000, 1, 2_000), task_id="seed", team_id="seed"))
        # Queue a second request
        queued_request = _request(vram=(5_000, 1, 2_000), task_id="task-q", team_id="team-q")
        decision = controller.admit(queued_request)
        self.assertEqual(decision.plan.admission, "queued")
        self.assertEqual(decision.audit_payload["ledger_event_type"], "team.resource_plan.queued")

    # ── New tests: extended HardwareProfile fields ────────────────────────────

    def test_extended_hardware_profile_execution_modes_validate(self) -> None:
        """HardwareProfile with explicit supported_execution_modes validates correctly."""
        profile = _profile(modes=("parallel", "serial_virtual_team"))
        self.assertEqual(set(profile.supported_execution_modes), {"parallel", "serial_virtual_team"})
        self.assertEqual(profile.network_check_id, "evt-egress-001")
        self.assertEqual(profile.sandbox_runtime, "firejail")

    def test_extended_hardware_profile_unknown_mode_rejected(self) -> None:
        """HardwareProfile with an unknown execution mode raises ContractValidationError."""
        from contracts.errors import ContractValidationError
        with self.assertRaises(ContractValidationError):
            HardwareProfile.from_dict({
                "profile_id": "bad-profile", "gpu_model": "NVIDIA-TEST", "gpu_count": 1,
                "vram_bytes": 10_000, "driver_version": "550", "accelerator_runtime": "cuda-12",
                "cpu_model": "x86", "cpu_cores": 8, "ram_bytes": 64_000, "storage_bytes": 1_000_000,
                "scratch_bytes": 100_000, "model_context_tokens": 8192, "kv_cache_bytes": 10_000,
                "safe_parallel_slots": 1, "egress_policy": "deny-all", "measurement_hash": "a" * 64,
                "supported_execution_modes": ["parallel", "teleport"],  # invalid mode
            })
