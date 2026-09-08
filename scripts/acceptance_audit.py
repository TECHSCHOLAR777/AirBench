"""CLI entry point for the repository-owned offline acceptance audit."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from airbench.acceptance_audit import main

if __name__ == "__main__":
    raise SystemExit(main())
