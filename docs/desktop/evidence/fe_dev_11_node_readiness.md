# FE-DEV-11: Node Connection Proof

## Status

Local frontend source slice for the existing approved Node handshake. It improves the operator-facing Node and settings screen without adding a Node API, a model-routing path, or an administrative policy action.

## Operator outcome

An operator can understand what an AirBench Node is, which internal Node connection is currently trusted, and which parts of the operational picture the desktop does not yet know.

An AirBench Node is the organization-run control plane that owns task coordination, model routing, tools, File Intake, verification, artifacts, clearance, and the audit ledger. The desktop is a presentation and typed-command surface for that Node. It is not a direct model client or a second source of authority.

## Authoritative inputs

The screen accepts only existing values from the Rust-owned trusted handshake and the native-approved profile catalog:

- approved profile label and transport kind;
- Node identity and protocol version;
- authenticated subject and clearance context;
- active domain-pack reference;
- verified, unknown, or blocked sovereignty result; and
- handshake ledger reference.

Endpoint URLs, certificate pins, credential references, and secrets never cross into the webview and are not rendered.

## Visible states

1. **Approved Node connection verified** shows the existing handshake proof fields only when the approved profile is present, policy-approved, and matches the profile ID and Node identity returned by the handshake. It explains that the Node, not the desktop, still controls consequential work.
2. **Checking approved Node**, **Reconnection required**, **Connection proof needs attention**, **Node connection blocked**, and **No approved Node connection** show no retained handshake fields. They fail closed for task authority.
3. **Operational status is not supplied** is distinct from a healthy Node. Hardware and capacity, sandbox health, qualified capability catalog, and router decision history stay visibly unknown until a versioned Node projection exists.
4. **Routing authority stays with the Node** explains why a raw model picker is not exposed. A future preference can appear only after the Node supplies a clearance-filtered qualified catalog and keeps final routing authority.

## Boundary and security rules

- The React view is display-only. It does not call a model endpoint, an arbitrary URL, or a Python route.
- The Rust shell remains the only desktop transport boundary.
- The UI does not infer GPU health, qualification, routing, or sovereignty from a connected profile.
- A `verified` response is not displayed as trusted proof when the approved profile is missing, unapproved, or mismatched with the returned profile ID or Node identity.
- No new consequential command or ledger event is created by this slice. The existing handshake ledger reference is rendered only after a verified connection.
- The core UI remains sector-neutral. The domain-pack reference is an opaque Node-supplied identifier, not field logic in React.

## Tests

`apps/desktop/src/platform/node/nodeReadiness.test.ts` covers:

- a verified connection and its allowed handshake fields;
- absence of endpoint, certificate, credential, GPU-ready, or qualified-model claims;
- reconnect behavior that hides retained identity and ledger fields; and
- incomplete trust behavior that does not claim readiness.
- missing and mismatched approved-profile inputs that hide trusted identity and ledger fields.

Full frontend build, generated-contract, no-egress, Tauri configuration, and Rust-shell tests remain required before integration evidence is recorded.
