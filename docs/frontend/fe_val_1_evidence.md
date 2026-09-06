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
- The first native Windows executable has built successfully with Tauri 2.11.5 and Rust 1.98.1. Its current SHA-256 is `AFDD2B673D01D1351941458456A14FFA0686879C1C101C3F0611F2140B063EFE`.

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
- Native executable SHA-256: `AFDD2B673D01D1351941458456A14FFA0686879C1C101C3F0611F2140B063EFE`
- Installer status: built successfully with the WebView2 offline package embedded; clean offline image evidence remains pending.

## Host installer smoke run

Command: `npm run validate:installer`

- Run: `20260906-072213`
- Exit code: `0`
- Installed executable: present in the isolated temp install directory
- Established connections observed from the installer process tree: none
- Limitation: this machine was not a clean Windows image with all network interfaces disabled, so this is supporting evidence only. The clean offline image run remains required before closing FE-VAL-1.

## Source

The packaging decision follows the official Tauri Windows installer guidance. The default WebView2 bootstrapper is not acceptable for AirBench because it can require internet access. The offline installer mode is the required first validation target.
