"""Generate the frontend TypeScript view of the Python Node contracts.

The Python contract classes are authoritative. The generated file is a wire
type dependency for the frontend and must not become a second handwritten
schema. Core contracts retain their Python snake-case representation; the
Node response contracts explicitly describe the camel-case desktop wire view.
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps" / "desktop" / "src" / "generated" / "core_contracts.ts"
CONTRACT_NAMES = (
    "TaskEnvelope",
    "TeamPlan",
    "TaskPlanReview",
    "WorkerAssignment",
    "WorkPacket",
    "WorkerResult",
    "HandoffSubmission",
    "JoinBarrier",
    "CompletionRecord",
    "StageSignals",
    "ModelCallRequest",
    "RoutingDecision",
    "TeamResourcePlan",
    "ResourceReservation",
    "ResourceLease",
    "HardwareProfile",
    "ToolAction",
    "FactEnvelope",
    "UntrustedEvidence",
    "LedgerEventEnvelope",
    "NodeCommandEnvelope",
    "NodeCommandResult",
    "NodeHandshake",
    "NodeProvenanceRef",
    "NodeEvidenceRef",
    "NodeFactRef",
    "NodeTaskSnapshot",
    "NodeTaskEvent",
    "NodeTaskEventBatch",
)

PLAIN_TYPE_NAMES = (
    "NodeLifecycleEventPayload",
    "NodeWorkerEventPayload",
    "NodeEvidenceEventPayload",
    "NodeVerificationEventPayload",
    "NodeApprovalEventPayload",
    "NodeArtifactEventPayload",
    "NodeSummaryEventPayload",
    "NodeUnknownEventPayload",
)

sys.path.insert(0, str(ROOT / "src"))
from contracts import models  # noqa: E402


def _ts_type(annotation: Any) -> str:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if annotation is Any:
        return "unknown"
    if origin in (Union, types.UnionType):
        return " | ".join(_ts_type(arg) for arg in args)
    if origin is Literal:
        return " | ".join(json.dumps(arg) for arg in args)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return f"Array<{_ts_type(args[0])}>"
        return f"[{', '.join(_ts_type(arg) for arg in args)}]"
    if origin is list:
        return f"Array<{_ts_type(args[0])}>" if args else "Array<unknown>"
    if origin is dict:
        return f"Record<string, {_ts_type(args[1])}>" if len(args) == 2 else "Record<string, unknown>"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation.__name__
    if isinstance(annotation, type) and (is_dataclass(annotation) or issubclass(annotation, models.Contract)):
        return annotation.__name__
    if annotation is str:
        return "string"
    if annotation is int or annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation is type(None):
        return "null"
    return "unknown"


def _is_optional(field: Any) -> bool:
    return field.default is not MISSING or field.default_factory is not MISSING


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _enum_block(enum: type[Enum]) -> str:
    values = " | ".join(json.dumps(member.value) for member in enum)
    return f"export type {enum.__name__} = {values};"


def _is_node_wire_contract(contract: type[Any]) -> bool:
    return isinstance(contract, type) and issubclass(contract, models.NodeWireContract)


def _is_node_payload(name: str) -> bool:
    return name in PLAIN_TYPE_NAMES


def generate() -> str:
    hints_by_class = {
        name: get_type_hints(getattr(models, name), vars(models), vars(models))
        for name in (*PLAIN_TYPE_NAMES, *CONTRACT_NAMES)
    }
    lines = [
        "// AUTO-GENERATED FILE. DO NOT EDIT.",
        "// Source of truth: src/contracts/models.py and its ledger event catalog.",
        "",
        f'export const CORE_CONTRACT_SCHEMA_VERSION = {json.dumps(models.SCHEMA_VERSION)} as const;',
        f'export const CORE_CONTRACT_COMPATIBILITY_ID = {json.dumps(models.COMPATIBILITY_ID)} as const;',
        f'export const NODE_PROTOCOL_VERSION = {json.dumps(models.NODE_PROTOCOL_VERSION)} as const;',
        f'export const NODE_PROTOCOL_COMPATIBILITY_ID = {json.dumps(models.NODE_PROTOCOL_COMPATIBILITY_ID)} as const;',
        "",
    ]
    for enum in (models.Clearance, models.Taint, models.ContractStatus, models.LeaseStatus, models.BarrierStatus, models.NodeTaskStatus):
        lines.append(_enum_block(enum))
    lines.extend([
        "",
        "export const LEDGER_EVENT_TYPES = [",
    ])
    lines.extend(f"  {json.dumps(event_type)}," for event_type in sorted(models.LEDGER_EVENT_TYPES))
    lines.extend([
        "] as const;",
        "export type LedgerEventType = typeof LEDGER_EVENT_TYPES[number];",
        "",
        "export interface ContractEnvelope {",
        "  schema_version: string;",
        "  compatibility_id: string;",
        "}",
        "",
        "export interface NodeWireContractEnvelope {",
        "  schemaVersion: string;",
        "  compatibilityId: string;",
        "}",
        "",
    ])
    for name in (*PLAIN_TYPE_NAMES, *CONTRACT_NAMES):
        contract = getattr(models, name)
        hints = hints_by_class[name]
        is_plain = name in PLAIN_TYPE_NAMES
        base = "" if is_plain else ("NodeWireContractEnvelope" if _is_node_wire_contract(contract) else "ContractEnvelope")
        extends = f" extends {base}" if base else ""
        lines.append(f"export interface {name}{extends} {{")
        for field in fields(contract):
            if not field.init:
                continue
            optional = "?" if _is_optional(field) else ""
            field_type = "LedgerEventType" if name == "LedgerEventEnvelope" and field.name == "event_type" else _ts_type(hints[field.name])
            field_name = _camel_case(field.name) if (_is_node_wire_contract(contract) or _is_node_payload(name)) else field.name
            lines.append(f"  {field_name}{optional}: {field_type};")
        lines.extend(["}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the generated file is stale")
    args = parser.parse_args()
    expected = generate()
    if args.check:
        try:
            actual = OUTPUT.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"Missing generated contract file: {OUTPUT}")
            return 1
        if actual != expected:
            print(f"Generated frontend contracts are stale: {OUTPUT}")
            return 1
        print(f"Frontend contracts are current: {OUTPUT}")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Generated {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
