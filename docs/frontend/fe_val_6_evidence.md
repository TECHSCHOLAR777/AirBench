# FE-VAL-6 evidence record

Status: WebDriver harness implemented. Packaged desktop execution is not yet a pass claim.

## Harness boundary

- WebdriverIO uses the official `@wdio/tauri-service` embedded provider by default. Set `AIRBENCH_WDIO_DRIVER=external` to exercise the external `tauri-driver` path.
- The Rust `tauri-plugin-wdio` and `tauri-plugin-wdio-webdriver` crates are declared so Tauri can resolve their ACL schemas. Plugin registration and the `wdio` capability remain feature and test-overlay gated, so the production binary does not expose the test commands.
- The production Tauri configuration explicitly references only the `main-window` capability. The test overlay adds the `wdio` capability and enables `withGlobalTauri`.
- The frontend statically imports the WebDriver plugin as required by the official plugin setup. Vite aliases that import to an empty module in production, so production builds do not register or bundle the WebDriver plugin path.
- The desktop suite covers visible shell rendering, IPC mocking for native file selection, trusted settings navigation, Tauri execute access, frontend log capture, and a separate multiremote configuration for two local app instances.

## Commands

From `frontend/`:

```text
npm run build:webdriver
npm run tauri:build:webdriver
npm run test:desktop
npm run test:desktop:multiremote
```

The test binary is deliberately built with the `wdio` feature and is never the production release binary.

The current embedded run on Windows did not expose the direct-evaluation route: all four tests failed with HTTP 404 responses from the embedded provider and the shell was not available to the session. An external run was exercised with `tauri-driver` 2.0.6 and matching Microsoft Edge WebDriver 152.0.4191.66. It loaded the real shell and passed the renderer-only assertion, but IPC mocking, settings navigation, Tauri execute, and frontend log capture timed out on the Windows async execute seam. The multiremote run passed its two-instance addressability assertion through the external provider. These are diagnostic results, not full acceptance passes.

## Remaining acceptance evidence

- Build and run the harness on the supported clean Windows image.
- Capture backend logs, frontend logs, IPC mock calls, and multiremote output as retained artifacts.
- Resolve the embedded-provider 404 and the external Windows Tauri-side async execution timeout before claiming IPC mocks, Tauri execute, or log assertions. The basic external multiremote addressability check is passing, but it still needs the retained artifact and complete acceptance evidence.
- Add the scanned-document upload, safe preview, artifact download, reconnect, and blocked-navigation flows after the corresponding UI commands exist.
- Repeat the no-egress monitor with the test binary under the enforced host policy. The WebDriver test must not be used to hide WebView2 runtime traffic.
