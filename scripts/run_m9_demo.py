"""Run the deterministic local M9 inspection-report demonstration.

This command uses the same File Intake Layer, local vision seam, retrieval
service, verification, artifact renderer, and ledger path as the backend. It
uses a deterministic fixture vision adapter so it is suitable for offline CI;
target-host model qualification remains a separate acceptance gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from airbench.intake.vision import LocalVisionAdapter, VisionResult
from airbench.m9 import RefineryPack, RefineryVerticalSlice
from contracts import EventLedger, HardwareProfile


def _fixture_vision() -> LocalVisionAdapter:
    def extract(request):
        return VisionResult(
            extraction_id=f"extraction-{request.page_id}", task_id=request.task_id,
            intake_id=request.intake_id, revision_id=request.revision_id,
            page_id=request.page_id, source_ref=request.source_ref,
            text="F-01: P-101: high: seal leakage observed\nF-02: P-102: critical: vibration above limit",
            confidence=0.91, extraction_method="offline_fixture_vision",
            adapter_id="airbench.vision.fixture", adapter_version="1.0",
            model_target_id="target.fixture.vision",
            qualification_reference="qualification.fixture.vision",
            clearance=request.clearance, taint=request.taint,
            content_hash=request.content_hash,
        )

    return LocalVisionAdapter(
        adapter_id="airbench.vision.fixture", adapter_version="1.0",
        model_target_id="target.fixture.vision",
        qualification_reference="qualification.fixture.vision",
        extractor=extract,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-key", required=True, help="deployment-provided pack verification key")
    parser.add_argument(
        "--pack-root", type=Path, default=ROOT / "packs" / "refinery_psu_v0",
        help="signed domain-pack directory (defaults to the repository pack)",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "acceptance" / "traces" / "m9-demo")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pack_root = args.pack_root.resolve()
    pack_key = args.pack_key.encode("utf-8")
    signature = RefineryPack.sign(pack_root, pack_key)
    pack = RefineryPack.load(pack_root, pack_key, signature)
    report_path = args.output_dir / "inspection-report.png"
    Image.new("RGB", (32, 32), "white").save(report_path, format="PNG")
    manual_path = args.output_dir / "maintenance-sop.txt"
    manual_path.write_text("seal leakage requires isolation and inspection\nvibration above limit requires review", encoding="utf-8")
    ledger = EventLedger()
    hardware = HardwareProfile(
        profile_id="hardware.m9.fixture-96gb", gpu_model="fixture-gpu", gpu_count=1,
        vram_bytes=96 * 1024**3, driver_version="fixture-driver",
        accelerator_runtime="fixture-runtime", cpu_model="fixture-cpu", cpu_cores=16,
        ram_bytes=128 * 1024**3, storage_bytes=1 * 1024**4, scratch_bytes=512 * 1024**3,
        model_context_tokens=32768, kv_cache_bytes=8 * 1024**3, safe_parallel_slots=2,
        egress_policy="no_egress", measurement_hash="a" * 64,
        supported_execution_modes=("parallel", "serial_virtual_team"),
        network_check_id="fixture.no-egress", sandbox_runtime="fixture-sandbox",
    )
    runs = []
    for label, slots, modes in (("serial", 1, ("serial_virtual_team",)), ("parallel", 2, ("parallel", "serial_virtual_team"))):
        result = RefineryVerticalSlice(pack, ledger, artifact_dir=args.output_dir).run_from_file(
            task_id=f"task.m9.demo.{label}", report_path=report_path,
            manual_paths={"local:maintenance-sop": manual_path},
            safe_parallel_slots=slots, supported_modes=modes,
            hardware_profile=(hardware if label == "parallel" else HardwareProfile.from_dict({**hardware.to_dict(), "safe_parallel_slots": 1, "supported_execution_modes": ["serial_virtual_team"]})),
            vision_adapter=_fixture_vision(),
        )
        runs.append({
            "task_id": result.task_id, "outcome": result.outcome,
            "review_status": result.review_status, "execution_mode": result.execution_mode,
            "finding_count": len(result.findings), "computed_values": dict(result.computed_values),
            "manual_refs": list(result.manual_refs),
            "artifact": result.artifact.__dict__ if hasattr(result.artifact, "__dict__") else {
                "artifact_id": result.artifact.artifact_id, "content_hash": result.artifact.content_hash,
                "structural": result.artifact.structural, "visual": result.artifact.visual,
                "generator_version": result.artifact.generator_version,
            },
        })
    ledger_path = args.output_dir / "ledger.jsonl"
    ledger.verify_chain()
    ledger_path.write_text("".join(json.dumps(event.to_dict(), sort_keys=True) + "\n" for event in ledger.events), encoding="utf-8")
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pack_id": pack.manifest["pack_id"], "pack_signature": signature,
        "ledger_head_hash": ledger.head_hash, "ledger_event_count": len(ledger.events),
        "runs": runs,
    }
    (args.output_dir / "pack-signature.json").write_text(json.dumps({
        "pack_id": pack.manifest["pack_id"],
        "pack_version": pack.manifest["pack_version"],
        "algorithm": "HMAC-SHA256",
        "detached": True,
        "signature": signature,
    }, indent=2, sort_keys=True), encoding="utf-8")
    (args.output_dir / "run-summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
