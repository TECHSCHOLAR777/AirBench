"""CLI entry point: ``python -m airbench.qualify``.

Runs a model over a fixture set and writes a candidate certificate YAML.

Without ``--responses`` the harness runs a labelled reference self-test that
echoes each prompt; it proves the harness works and must not be read as a real
model qualification.  Supply ``--responses`` (a JSON map of fixture id to model
response) for an operator-measured run, and ``--signing-key-path`` to sign the
resulting certificate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

import yaml

from .harness import QualificationError, QualificationHarness, load_cases
from .reporter import build_certificate
from .signer import sign_certificate


def _reference_complete(prompt: str) -> str:
    return prompt


def _responses_complete(responses: Mapping[str, str], cases) -> callable:
    def complete(prompt: str) -> str:
        for case in cases:
            if case.prompt == prompt:
                return responses.get(case.fixture_id, "")
        return ""

    return complete


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="airbench.qualify", description="Run an offline model qualification fixture set.")
    parser.add_argument("--target", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--responses", default=None, help="JSON map of fixture id to model response")
    parser.add_argument("--signing-key-path", default=None)
    parser.add_argument("--hardware-profile-id", default="unmeasured")
    parser.add_argument("--runtime-version", default="unmeasured")
    parser.add_argument("--adapter-id", default="airbench.qualify")
    parser.add_argument("--duration-days", type=int, default=90)
    args = parser.parse_args(argv)

    try:
        cases = load_cases(args.fixtures)
    except QualificationError as exc:
        parser.error(str(exc))
        return 2

    if args.responses:
        try:
            responses = json.loads(Path(args.responses).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            parser.error(f"responses file is not valid JSON: {exc}")
            return 2
        complete = _responses_complete(responses, cases)
        source = "operator_measured"
    else:
        complete = _reference_complete
        source = "reference_self_test"

    run = QualificationHarness(complete, model_id=args.target).run(
        target_id=args.target, role=args.role, cases=cases, qualification_source=source,
    )
    certificate = build_certificate(
        run, hardware_profile_id=args.hardware_profile_id, runtime_version=args.runtime_version,
        adapter_id=args.adapter_id, duration_days=args.duration_days,
    )
    if args.signing_key_path:
        key = Path(args.signing_key_path).read_bytes()
        if len(key) != 32:
            parser.error("the signing key must be 32 bytes")
            return 2
        certificate = sign_certificate(certificate, key)

    output = Path(args.output) if args.output else Path(f"{args.target}.{args.role}.qualification.yaml")
    output.write_text(yaml.safe_dump(certificate, sort_keys=True), encoding="utf-8")
    print(f"Wrote qualification certificate to {output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
