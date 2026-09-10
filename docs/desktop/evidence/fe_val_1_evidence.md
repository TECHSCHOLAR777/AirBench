# FE-VAL-1 evidence record

Status: current-host smoke failed the no-egress gate. No pass claim is made until the packaged Windows installer has been run on a clean offline image with enforced host policy.

## Decision

AirBench uses Tauri 2 with the Windows `offlineInstaller` WebView2 mode. The shipped installer must carry the WebView2 offline installer so installation does not need the internet. The fixed-version runtime remains a later deployment decision because it increases package size and requires a separately pinned runtime artifact.

The first shell also uses a production CSP with `connect-src 'none'`. FE-VAL-2 may replace this with a narrowly allowlisted AirBench Node transport only after the trust and endpoint contract is implemented.

## Current implementation

- `apps/desktop/src-tauri/tauri.conf.json` selects `offlineInstaller`, disables updater artifacts, denies all page connections, and passes the DNS deny rule as one quoted WebView2 argument.
- `apps/desktop/src-tauri/capabilities/default.json` grants only the core default capability set.
- `apps/desktop/src/` contains no fetch, WebSocket, XMLHttpRequest, external URL, remote font, analytics, or update code.
- The initial screen reports that no Node is connected and does not invent tasks or sovereignty verification.
- `apps/desktop/scripts/check-no-egress.mjs` scans frontend source.
- `apps/desktop/scripts/check-tauri-config.mjs` checks the FE-VAL-1 packaging and CSP decisions.
- `apps/desktop/scripts/create-resource-manifest.mjs` records a SHA-256 manifest for the built local assets.
- `apps/desktop/scripts/check-runtime-egress.ps1` can run an unprivileged observation pass or an explicitly elevated, temporary WebView2 firewall-enforcement pass. The latter is the required host evidence path; it does not silently treat an unprivileged observation as a sovereignty proof.
- The native Windows executable has built successfully with Tauri 2.11.5 and Rust 1.98.1. The current executable hash is recorded in the native build evidence below.

## Commands

From `apps/desktop/`:

```text
npm install
npm run check:egress
npm run check:tauri-config
npm run test
npm run build
npm run create:manifest
npm run tauri:build
```

## Required offline evidence before closing the packaged release gate #124

- installer hash and application version;
- clean supported Windows image with network disabled;
- offline install transcript;
- startup screenshot and local resource manifest;
- process and network capture showing no external traffic;
- blocked startup result for missing or incompatible WebView2;
- exact Windows, WebView2, Node.js, npm, Rust, and Tauri CLI versions;
- remaining limitation, if the test machine cannot provide the approved WebView2 offline package.

## Native build evidence so far

- OS: Windows 10.0.26200 x86_64
- WebView2 available: 152.0.4191.66
- Rust: 1.98.1
- Cargo: 1.98.1
- Tauri Rust crate: 2.11.5
- Tauri API: 2.11.1
- Tauri CLI: 2.11.4
- Native executable: `apps/desktop/src-tauri/target/release/airbench-desktop.exe`
- Native executable size: 15,165,952 bytes
- Native executable SHA-256: `AC5DC5D356642079D37C9414DA6D11D6389FF23D4F49983E0265C52DE06F9DB3`
- Offline NSIS installer: `apps/desktop/src-tauri/target/release/bundle/nsis/AirBench_0.1.0_x64-setup.exe`
- Offline NSIS installer size: 265,869,972 bytes
- Offline NSIS installer SHA-256: `2E2B7EFE71D2A3B145C1092C529882C2E2F0805984D7B47832EA967ED8E42A4A`
- Installer status: built successfully with the WebView2 offline package embedded and installed successfully in the current-host smoke; clean offline image evidence and no-egress evidence remain pending.

## Runtime egress evidence

The unprivileged observation run `AirBenchRuntimeEgress-20260908-235051-f7a6ef92dea64c778f7aa4d7894abb7f` failed as intended. The release process command line now contains the complete quoted host-resolver rule, but the WebView2 browser process still established remote IPv6 connections to `2603:1046:c04:839::2:443`. The result is retained as a release blocker, not filtered out. The monitor now records the actual WebView2 command line so a stale or malformed release cannot pass based only on the source configuration.

This is a WebView2 runtime egress limitation, not an AirBench page request. Microsoft documents browser arguments as behavior controls, while the WebView2 project tracks disabling all outgoing traffic as an unresolved feature request. Therefore the enforceable production control is an elevated host network policy: deny WebView2 external egress and allow only the approved AirBench Node path at the host boundary. The current account is not an administrator, so that policy could not be installed during this run.

The explicitly requested enforcement run `AirBenchRuntimeEgress-20260908-232408-7b4ad526dd234856afbaa14b82cc5bf8` returned `blocked_not_administrator`. The current account is not elevated, so no firewall rule was installed and no pass claim is possible. A clean-image run from an elevated validation session remains required.

## Host installer smoke run

Command: `npm run validate:installer`

- Run: `AirBenchInstallerSmoke-20260908-235209-df3340264c644cc9b90fe1a3b45ee869`
- Installer SHA-256: `2E2B7EFE71D2A3B145C1092C529882C2E2F0805984D7B47832EA967ED8E42A4A`
- Exit code: `0`
- Installed executable: present in the isolated temp install directory
- Application started: yes
- Established non-loopback connection observed from a WebView2 descendant: `2603:1046:c04:839::2:443`
- Limitation: this machine was not a clean Windows image with all network interfaces disabled, and the runtime egress gate failed, so this is supporting install evidence only. The clean offline image run remains required before closing FE-VAL-1.

## Source

The packaging decision follows the official Tauri Windows installer guidance. The default WebView2 bootstrapper is not acceptable for AirBench because it can require internet access. The offline installer mode is the required first validation target.
