# Model Qualification Runbook (Phase 2 — two demo lanes)

This is the operator procedure for turning the two demo targets
(`airbench-gemma-4-e2b`, `airbench-gemma-4-12b`) from **unqualified
candidates** into **measured, signed, routable** targets. Nothing here fills a
placeholder with an estimate: every signed value comes from a measurement run
against the live lane.

## Preconditions

1. Remote containers running and SSH tunnel open (see
   `docs/operations/STARTUP_GUIDE.md`, Terminals 1-2).
2. Verify lanes with the Phase 1 preflight:

   ```powershell
   python scripts\model_endpoint_preflight.py
   ```

3. Offline environment set (the measurement no-egress probe requires it):

   ```powershell
   $env:HF_HUB_OFFLINE = "1"; $env:TRANSFORMERS_OFFLINE = "1"
   ```

## Step 1 — Measure each lane

```powershell
python scripts\airbench_measure_lane.py --target-id airbench-gemma-4-e2b `
    --endpoint http://127.0.0.1:18001 --served-model airbench-gemma-4-e2b `
    --ssh-host mmmut-server --container airbench-vllm-e2b

python scripts\airbench_measure_lane.py --target-id airbench-gemma-4-12b `
    --endpoint http://127.0.0.1:18002 --served-model airbench-gemma-4-12b `
    --ssh-host mmmut-server --container airbench-vllm-12b
```

This records identity, repeated first-token/end-to-end latency, throughput,
error rate, a bounded concurrency ramp, cancellation/timeout/no-egress probe
results, and (with `--ssh-host`) GPU UUID/VRAM/driver/CUDA and the container
digest. Evidence lands in
`qualifications/records/<target-id>.measurement.json`.

Exit code 0 requires: served model verified and all three safety probes pass.

## Step 2 — Qualify with complete evidence

```powershell
python scripts\airbench_qualify.py --target-id airbench-gemma-4-e2b --role reasoning `
    --endpoint http://127.0.0.1:18001 --served-model airbench-gemma-4-e2b `
    --evidence-file qualifications\records\airbench-gemma-4-e2b.measurement.json `
    --write-matrix --write-roster

python scripts\airbench_qualify.py --target-id airbench-gemma-4-12b --role reasoning `
    --endpoint http://127.0.0.1:18002 --served-model airbench-gemma-4-12b `
    --evidence-file qualifications\records\airbench-gemma-4-12b.measurement.json `
    --write-matrix --write-roster
```

The eval (`airbench_default_qualification_v1`) measures structured output,
inspection-review accuracy, citation/provenance retention, source
faithfulness, hallucination resistance, and safety refusal. The measurement
evidence completes the cancellation/timeout/no-egress gates.

The script **refuses to sign** any certificate that still contains pending
evidence — run `--no-sign-matrix` only to record partial progress. The
qualification record is written to
`qualifications/records/<target-id>.<role>.json` and its hash flows into the
v0 roster.

## Step 3 — Rebuild the demo roster (measured entries only)

```powershell
python scripts\airbench_demo_roster.py --require-measured
```

With `--require-measured`, targets whose roster roles lack a signed, fully
measured matrix certificate are **disabled** (dropped from the demo roster
with an explicit message) instead of being treated as qualified. Without the
flag the builder keeps the historical candidate behaviour for controlled
debugging.

## Step 4 — Verify

1. Restart the Node (`scripts\start_demo_node.ps1`).
2. `GET /api/v1/node/qualification/<target-id>` must report `status:
   "qualified"` with `missing_evidence: []`.
3. `GET /api/v1/node/model-serving` must report both lanes `ready`.
4. Run a real task and confirm the route trace records the selected target's
   certificate.

## What is intentionally left pending

The reference-roster targets (`gemma4-31b-it-q4`, `qwen3-coder-30b-a3b-4bit`,
`qwen2.5-vl-7b-4bit`, BGE services) and the `target_96gb_vram` profile keep
their placeholders until they are measured on their own hardware (roadmap
Phase 8). They are not part of the demo roster and are never treated as
qualified by the Node.
