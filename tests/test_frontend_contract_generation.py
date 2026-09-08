import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_generated_frontend_contracts_match_python_authority():
    result = subprocess.run(
        [sys.executable, "scripts/generate_frontend_contracts.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_frontend_contracts_include_typed_node_boundary():
    generated = (ROOT / "frontend" / "src" / "generated" / "core_contracts.ts").read_text(encoding="utf-8")
    assert "NODE_PROTOCOL_COMPATIBILITY_ID = \"airbench-node-protocol\"" in generated
    assert "export interface NodeTaskSnapshot extends NodeWireContractEnvelope" in generated
    assert "export interface NodeTaskEvent extends NodeWireContractEnvelope" in generated
    assert "export interface NodeTaskEventBatch extends ContractEnvelope" in generated
    assert "export interface NodeEvidenceRef extends NodeWireContractEnvelope" in generated
