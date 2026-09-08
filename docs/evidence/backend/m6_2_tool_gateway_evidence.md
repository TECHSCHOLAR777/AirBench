# M6.2 Tool Gateway evidence

This document records the completed core Tool Gateway slice for GitHub issue
#39.

## Implemented

`airbench.tool_gateway.ToolGateway` admits only a typed `ToolAction` and a
signed `CapabilityScope`. The scope binds the action to its task, team worker,
tool set, path roots, risk classes, maximum clearance, timeout, expiry, and
policy version. The gateway verifies the HMAC signature and all of those
limits before returning a `ToolAuthorization`.

Registered `ToolDefinition` values provide the capability name, risk classes,
input schema, required arguments, and output schema. The gateway rejects
unknown tools, scope expansion, path traversal or out-of-scope paths,
clearance escalation, excessive timeouts, missing arguments, schema mismatches,
expired or tampered scopes, non-clean taint, and raw prompt-shaped fields.

The gateway writes `tool.requested` followed by either `tool.authorized` or
`tool.denied`. The sandbox accepts the authorization and writes only its
`tool.result`, so the integrated path produces one auditable request,
authorization, and result trace rather than duplicate events. The event
payloads contain hashes and policy metadata, not raw code or prompts.

## Tests

`tests/test_m62_tool_gateway.py` covers:

- one Gateway authorization followed by sandbox execution with no duplicate
  request or authorization events;
- path, risk, clearance, signature, and expiry denials;
- raw prompt rejection and non-clean taint rejection;
- mandatory output schema validation;
- immutable scope identity and policy binding.

Evidence commands:

```text
python -m pytest -q tests/test_m62_tool_gateway.py tests/test_m61_sandbox.py
python -m pytest -q
python -m compileall -q airbench contracts tests
git diff --check
```

Observed result: 9 focused tests passed and 61 repository tests passed.

## Boundary and remaining work

The Gateway is the policy and capability boundary. It does not claim to be an
OS sandbox, firewall, namespace, container, or no-egress proof. M6.1 remains
open until the deployment supplies verified hard isolation. The Gateway also
does not execute tools or receive model prompts. The authorized executor owns
the tool-specific runtime and result evidence.
