"""Run a minimal real AirBench Python Node for cross-language validation.

This process is intentionally local-only and exists for validation. It uses
the real NodeApiService and Orchestrator, not the synthetic HTTP fixture.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402

from airbench.intake import FileIntakeLayer, LocalIntakeStore  # noqa: E402
from airbench.node.api import NodeApiConfig, NodeApiService, create_app  # noqa: E402
from airbench.node.intake_gateway import LocalNodeIntakeGateway  # noqa: E402
from contracts import Clearance, EventLedger, Orchestrator  # noqa: E402


def build_app(args: argparse.Namespace):
    ledger = EventLedger()
    orchestrator = Orchestrator(ledger)
    intake_store = LocalIntakeStore(args.intake_root)
    intake_layer = FileIntakeLayer(ledger, store=intake_store)
    intake_gateway = LocalNodeIntakeGateway(
        layer=intake_layer,
        store=intake_store,
        ledger=ledger,
        clearance_context=Clearance.restricted,
    )
    service = NodeApiService(
        orchestrator,
        NodeApiConfig(
            node_identity=args.node_identity,
            protocol_version="0.1",
            clearance_context=Clearance.restricted,
            authenticated_subject=args.subject,
            domain_pack_ref="validation-pack.v0",
            bearer_token=args.token,
            handshake_ledger_event_ref="ledger-validation-handshake",
            sovereignty_evidence_ref="evidence-validation-sovereignty",
            require_orchestrator_authorization=False,
        ),
        intake_gateway=intake_gateway,
    )
    return create_app(service)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--node-identity", default="python-node-validation")
    parser.add_argument("--subject", default="validation-user")
    parser.add_argument("--intake-root", required=True)
    args = parser.parse_args()
    uvicorn.run(build_app(args), host="127.0.0.1", port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
