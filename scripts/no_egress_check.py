"""First-scope no-egress observation.

Lists the host's established TCP connections and records any non-loopback
remote endpoint as evidence.  Independently attested continuous observation is
deferred (``docs/future/future_full_fledged_must_have.md`` P0-2); this records
the first-scope local check required by the sovereignty document.

Usage:
    python scripts/no_egress_check.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from airbench.node.no_egress import NoEgressError, observe_no_egress  # noqa: E402


def main() -> int:
    try:
        report = observe_no_egress()
    except NoEgressError as exc:
        print(f"no-egress observation failed: {exc}", file=sys.stderr)
        return 3
    payload = {**report.to_dict(), "scope": "first_scope_local"}
    output = Path(__file__).resolve().parents[1] / "acceptance" / "no_egress_first_scope.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"written to {output}")
    return 0 if report.clean else 2


if __name__ == "__main__":
    raise SystemExit(main())
