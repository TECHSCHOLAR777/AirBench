# FE-VAL-1 evidence record

Status: implementation in progress. No pass claim is made until the packaged Windows installer has been run on a clean offline image.

## Decision

AirBench uses Tauri 2 with the Windows `offlineInstaller` WebView2 mode. The shipped installer must carry the WebView2 offline installer so installation does not need the internet. The fixed-version runtime remains a later deployment decision because it increases package size and requires a separately pinned runtime artifact.

The first shell also uses a production CSP with `connect-src 'none'`. FE-VAL-2 may replace this with a narrowly allowlisted AirBench Node transport only after the trust and endpoint contract is implemented.

## Current implementation

- `frontend/src-tauri/tauri.conf.json` selects `offlineInstaller`, disables updater artifacts, and denies all connections.
- `frontend/src-tauri/capabilities/default.json` grants only the core default capability set.
- `frontend/src/` contains no fetch, WebSocket, XMLHttpRequest, external URL, remote font, analytics, or update code.
- The initial screen reports that no Node is connected and does not invent tasks or sovereignty verification.
- `frontend/scripts/check-no-egress.mjs` scans frontend source.
- `frontend/scripts/check-tauri-config.mjs` checks the FE-VAL-1 packaging and CSP decisions.
- `frontend/scripts/create-resource-manifest.mjs` records a SHA-256 manifest for the built local assets.
- `frontend/scripts/check-runtime-egress.ps1` can run an unprivileged observation pass or an explicitly elevated, temporary WebView2 firewall-enforcement pass. The latter is the required host evidence path; it does not silently treat an unprivileged observation as a sovereignty proof.
- The native Windows executable has built successfully with Tauri 2.11.5 and Rust 1.98.1. The current executable hash is recorded in the native build evidence below.

## Commands

From `frontend/`:

```text
npm install
npm run check:egress
npm run check:tauri-config
npm run test
npm run build
npm run create:manifest
npm run tauri:build
```

## Required offline evidence before closing #64

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
- Native executable: `frontend/src-tauri/target/release/airbench-desktop.exe`
- Native executable size: 14,422,016 bytes
- Native executable SHA-256: `C506232878D227DFCDA95E418149EE5A6F50CCE0291A4216EB28E5BA00AEDAC9`
- Offline NSIS installer: `frontend/src-tauri/target/release/bundle/nsis/AirBench_0.1.0_x64-setup.exe`
- Offline NSIS installer size: 265,618,968 bytes
- Offline NSIS installer SHA-256: `90C1B0F185E8E399A32BB7D26E20861D104C3F15131C9DEAE4745D592B7FC79F`
- Installer status: built successfully with the WebView2 offline package embedded; clean offline image evidence remains pending.

## Runtime egress evidence

The unprivileged observation run `AirBenchRuntimeEgress-20260906-172216-8eba51b349f644cf8bbc5c43ed2d8b6a` failed as intended. WebView2 descendants established remote IPv6 connections to `2603:1046:c04:140d::2:443`. Adding QUIC disablement and host-resolver rules did not remove this traffic. The result is retained as a release blocker, not filtered out.

The explicitly requested enforcement run `AirBenchRuntimeEgress-20260906-172315-514704d7d908458c8ebb21bd30d9c1ac` returned `blocked_not_administrator`. The current account is not elevated, so no firewall rule was installed and no pass claim is possible. A clean-image run from an elevated validation session remains required.

## Host installer smoke run

Command: `npm run validate:installer`

- Run: `20260906-101534`
- Installer SHA-256: `11853741B8ACB519548AAAE8E17AA0B411A31618239A066515D9FEE62CE1D97A`
- Exit code: `0`
- Installed executable: present in the isolated temp install directory
- Established connections observed from the installer process tree: none
- Limitation: this machine was not a clean Windows image with all network interfaces disabled, so this is supporting evidence only. The clean offline image run remains required before closing FE-VAL-1.

## Source

The packaging decision follows the official Tauri Windows installer guidance. The default WebView2 bootstrapper is not acceptable for AirBench because it can require internet access. The offline installer mode is the required first validation target.
