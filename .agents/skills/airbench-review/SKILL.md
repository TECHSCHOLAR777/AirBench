---
name: airbench-review
description: Review an AirBench diff against its issue, architecture documents, security invariants, tests, and operational evidence before merge or push.
metadata:
  short-description: Perform specification and architecture review
---

# AirBench review

Review from a fixed diff base. Run separate passes:

1. Specification: does the diff implement the assigned issue and acceptance criteria?
2. Architecture: does it preserve ownership, contracts, provenance, ledger, routing, intake, and security rules?
3. Testing: do tests cover normal, failure, restart, and boundary behavior?
4. Operations: are logs, resources, timeouts, recovery, and offline deployment addressed?

Report findings by severity. Block completion for security, data-loss, authority, provenance, ledger, contract, or acceptance failures. Do not approve based only on tests passing.

