# AirBench acceptance package

This directory separates repository-owned checks from target-host evidence. It
is intentionally blocked until real measurements, local model qualification,
independent network observation, rendered-artifact checks, and human review
are attached. Deterministic fixtures and unit tests are not promoted to live
qualification by this package.

Run the local audit with `python scripts/acceptance_audit.py --allow-incomplete`.
Without `--allow-incomplete`, it returns a non-zero status while any release
gate is unresolved. It never fills a measurement or signature.
