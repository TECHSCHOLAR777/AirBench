# FE-VAL-5 evidence record

Status: static and startup runtime no-egress controls are implemented. Complete packaged network-monitor evidence remains open until the Tauri WebDriver scenario exercises every reachable first-release path.

## Current controls

- Production CSP uses `default-src 'self'` and `connect-src 'none'`. The webview cannot call the Node directly; the only network client is the Rust-owned Tauri transport.
- Tauri capabilities expose only the current core capability set. No updater, analytics, remote font, crash reporter, or external resource is configured.
- `npm run check:egress` scans source for fetch, WebSocket, XMLHttpRequest, external URLs, and CSS imports.
- `npm run check:tauri-config` checks the offline installer, updater disablement, loopback development origin, and CSP.
- `npm run check:runtime-egress` launches the packaged release executable and samples established connections for the application process tree. It records process names and executable paths, fails on a non-loopback connection, and writes a JSON report under `frontend/artifacts/`.
- Rust transport rejects unapproved profiles, external loopback targets, non-HTTPS internal profiles, endpoint credentials, query or fragment data, wrong certificate pins, and identity mismatches.

## Runtime result on the development host

Run: `AirBenchRuntimeEgress-20260906-101326-4880c598f061410e8d2ac68060fcc5b1`

Result: failed as intended. The packaged application's `msedgewebview2.exe` descendant opened established non-loopback IPv6 connections to remote port 443 during startup. This means the CSP and source scan are not sufficient proof of sovereignty on this host. FE-VAL-5 remains open until the desktop shell applies an enforceable WebView2 or host firewall policy and the packet capture is repeated. The observed traffic was not treated as AirBench Node traffic.

The failure is retained as release evidence. It must not be hidden by filtering WebView2 descendants or by declaring a shared system WebView2 process unrelated to the application.

## Remaining acceptance evidence

- run the packaged application with OS firewall and packet capture enabled;
- attempt external navigation through document links, preview content, typed command input, remote fonts, scripts, source maps, update checks, and crash-report paths under WebDriver;
- show that the only successful network path during an approved task is the internal AirBench Node;
- retain firewall deny logs and the exact packaged application hash.
