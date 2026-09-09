# AirBench frontend validation fixtures

These fixtures are synthetic and run only on the local validation workstation. They are not a replacement for the Python AirBench Node.

`node_fixture.py` exposes the minimum authenticated handshake used by the Tauri transport. The HTTPS fixture uses a local self-signed certificate. The certificate is trusted only through the explicit approved profile and is additionally checked by its SHA-256 leaf pin.

The fixture never prints bearer tokens or private keys. Generated certificates, profiles, logs, and temporary files belong in a temporary directory and must not be committed.

The Rust credential-store example uses the Windows Credential Manager through the `keyring` crate. The desktop webview receives only a credential reference, never the secret.

`validate-node-transport.ps1` builds into a disposable `CARGO_TARGET_DIR` under
its temporary run directory. This is intentional: Cargo dependency artifacts
can retain absolute paths from before the repository moved from
`frontend/src-tauri` to `apps/desktop/src-tauri`, including generated Tauri
permission files. The validation must not depend on, repair, or delete the
existing debug cache.
