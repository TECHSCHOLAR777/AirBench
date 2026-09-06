# M5.3 Backend Adapter Contract

`contracts.backend` is the provider-neutral seam between the router/orchestrator
and a model server. A vLLM, NIM, local custom server, or future remote adapter
translates into these types; provider response objects must not cross this
boundary.

## Call lifecycle

1. The orchestrator supplies a validated `ModelCallRequest` and the router
   supplies the selected target identity and artifact digest.
2. `BackendRequest` carries typed messages, governed media references, tools,
   structured-output requirements, and the stream preference.
3. The adapter checks health, readiness, declared capability, and resource
   limits before execution.
4. The adapter returns `BackendResponse` or a typed `BackendCallError`.
5. Successful responses carry `ResponseProvenance`; model output remains
   untrusted until orchestration and verification accept it.

`FakeBackend` is the deterministic reference implementation for contract,
failure, timeout, cancellation, streaming, resource, capability, and ledger
tests. It does not require a model runtime or network service.

## Required behavior

- Structured output, tools, and modalities are rejected when unsupported.
- Health and readiness are separate states.
- Timeout, cancellation, unavailable, not-ready, capability, and resource
  failures have explicit error codes and retry guidance.
- Media is referenced by a governed URI and SHA-256 digest; raw binary data is
  not silently accepted by the contract.
- Ledger events contain request/response hashes, target/backend identity,
  artifact digest, clearance, and usage, never full prompts or responses.
- `model.call.started`, `model.call.completed`, and `model.call.failed` are
  emitted when a ledger is supplied.

Hardware measurement, model residency, queue admission, and local vLLM/NIM
implementations remain owned by M5.2 and M5.4. Remote endpoint behavior is
owned by the endpoint issue and must still conform to this contract.
