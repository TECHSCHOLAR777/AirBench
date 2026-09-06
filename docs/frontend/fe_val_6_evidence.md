# FE-VAL-6 evidence record

Status: WebDriver harness implemented. Packaged desktop execution is not yet a pass claim.

## Harness boundary

- WebdriverIO uses the official `@wdio/tauri-service` embedded provider by default. Set `AIRBENCH_WDIO_DRIVER=external` to exercise the external `tauri-driver` path.
- The Rust `tauri-plugin-wdio` and `tauri-plugin-wdio-webdriver` crates are declared so Tauri can resolve their ACL schemas. Plugin registration and the `wdio` capability remain feature and test-overlay gated, so the production binary does not expose the test commands.
- The production Tauri configuration explicitly references only the `main-window` capability. The test overlay adds the `wdio` capability and enables `withGlobalTauri`.
- The frontend statically imports the WebDriver plugin as required by the official plugin setup. Vite aliases that import to an empty module in production, so production builds do not register or bundle the WebDriver plugin path.
- The WebDriver build uses a test-only invoke bridge. It checks the WDIO mock registry before the normal Tauri core surface because the Windows WebView2 global Tauri core object can reject the plugin's property interception. The production bridge remains the normal `@tauri-apps/api/core` implementation.
- The desktop suite covers visible shell rendering, IPC mocking for native file selection, trusted settings navigation, Tauri execute access, a retained frontend log marker, and a separate multiremote configuration for two local app instances.

## Commands

From `frontend/`:

```text
npm run build:webdriver
npm run tauri:build:webdriver
npm run test:desktop
npm run test:desktop:multiremote
```

The test binary is deliberately built with the `wdio` feature and is never the production release binary.

The clean embedded Windows run passed all four shell checks. This includes IPC mocking, which initially failed because the WDIO guest plugin could not redefine the WebView2 Tauri core property. The external `tauri-driver` 2.0.6 run with Microsoft Edge WebDriver 152.0.4191.66 also passed all four checks. The retained WDIO log contains the frontend marker emitted through the Tauri log path. The external multiremote run passed its two-instance addressability assertion. The WDIO service still emits non-fatal cleanup warnings when it tries to restore mocks after the WebDriver session has already been deleted, so those warnings remain part of the harness evidence and should be removed or accepted explicitly before a release gate.

## Remaining acceptance evidence

- Build and run the harness on the supported clean Windows image.
- Retain the embedded and external WDIO reports, the per-run frontend log, IPC mock call evidence, and multiremote output as CI artifacts.
- Remove or isolate the non-fatal WDIO mock cleanup warning so a release run has a clean teardown signal.
- Add the scanned-document upload, safe preview, artifact download, reconnect, and blocked-navigation flows after the corresponding UI commands exist.
- Repeat the no-egress monitor with the test binary under the enforced host policy. The WebDriver test must not be used to hide WebView2 runtime traffic.
