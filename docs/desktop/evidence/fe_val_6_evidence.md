# FE-VAL-6 evidence record

Status: WebDriver harness implemented. The Windows desktop command now selects the working external `tauri-driver` provider by default, while the embedded provider remains an explicit diagnostic option.

## Harness boundary

- WebdriverIO uses the external `tauri-driver` provider by default on Windows because the embedded provider failed to spawn on this host. Set `AIRBENCH_WDIO_DRIVER=embedded` to exercise the embedded provider explicitly, or set `AIRBENCH_WDIO_DRIVER=external` explicitly for a portable run.
- The Rust `tauri-plugin-wdio` and `tauri-plugin-wdio-webdriver` crates are declared so Tauri can resolve their ACL schemas. Plugin registration and the `wdio` capability remain feature and test-overlay gated, so the production binary does not expose the test commands.
- The production Tauri configuration explicitly references only the `main-window` capability. The test overlay adds the `wdio` capability and enables `withGlobalTauri`.
- The frontend statically imports the WebDriver plugin as required by the official plugin setup. Vite aliases that import to an empty module in production, so production builds do not register or bundle the WebDriver plugin path.
- The WebDriver build uses a test-only invoke bridge. It checks the WDIO mock registry before the normal Tauri core surface because the Windows WebView2 global Tauri core object can reject the plugin's property interception. The production bridge remains the normal `@tauri-apps/api/core` implementation.
- The desktop suite covers visible shell rendering, IPC mocking for native file selection, trusted settings navigation, Tauri execute access, a retained frontend log marker, and an approved-profile intake preview path. A separate multiremote configuration exists for two local app instances. Driver installation and downloads are disabled by default so running the harness cannot silently add network traffic.

## Commands

From `apps/desktop/`:

```text
npm run check:webdriver
npm run build:webdriver
npm run tauri:build:webdriver
npm run test:desktop
npm run test:desktop:multiremote
```

The test binary is deliberately built with the `wdio` feature and is never the production release binary.

Latest retained Windows run: `apps/desktop/logs/wdio-2026-09-08T18-29-06-616Z.log`. The self-built webdriver binary passed 6/6 shell checks, including approved-profile connection and safe intake preview. The same non-fatal WDIO mock-cleanup warning remains after session teardown.

The retained 2026-09-08 run with Microsoft Edge WebDriver 152.0.4191.66 passed all six shell checks, including approved profile connection and safe intake preview. The retained WDIO log contains the frontend marker emitted through the Tauri log path. The retained multiremote run passed its two-instance addressability assertion. Those are provisioned-driver results, not proof that this host can run offline today. The WDIO service still emits a non-fatal cleanup warning when it tries to restore mocks after the WebDriver session has already been deleted, so that warning remains part of the harness evidence and should be removed or accepted explicitly before a release gate.

On 2026-09-09, a fresh Windows run reached the external provider but could not resolve `msedgedriver.microsoft.com` because no matching local Edge driver was provisioned. It did not reach application assertions. The new preflight prevents this missing-prerequisite case from triggering a download or rebuilding the Tauri binary first.

The standalone desktop command now performs a local WebDriver preflight before the expensive webdriver build. On Windows, the default external provider requires `tauri-driver` and a matching local `msedgedriver.exe`; the preflight fails before compilation if either is unavailable. The reproducible sequence is:

```text
npm run check:webdriver
npm run build:webdriver
npm run tauri:build:webdriver
npm run test:desktop
npm run test:desktop:multiremote
```

The embedded provider may be selected with `AIRBENCH_WDIO_DRIVER=embedded` when the test binary has the embedded plugin enabled. A deliberately connected test host may set `AIRBENCH_ALLOW_DRIVER_DOWNLOAD=1`, but that run is not offline or no-egress evidence. `TAURI_DRIVER_PATH` may point to an approved local `tauri-driver` binary.

## Remaining acceptance evidence

- Build and run the harness on the supported clean Windows image.
- Retain the embedded and external WDIO reports, the per-run frontend log, IPC mock call evidence, and multiremote output as CI artifacts.
- Remove or isolate the non-fatal WDIO mock cleanup warning so a release run has a clean teardown signal.
- Add artifact download, reconnect, and blocked-navigation flows after the corresponding UI commands exist. The scanned-document upload and safe-preview path is now covered by the six-test packaged smoke run.
- Repeat the no-egress monitor with the test binary under the enforced host policy. The WebDriver test must not be used to hide WebView2 runtime traffic.
