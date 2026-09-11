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

The test binary is deliberately built with the `wdio` feature and is never the production release binary. The runner builds it with `--debug --no-bundle`, so these checks are native Tauri binary evidence, not installer or packaged release evidence.

The current Windows run on 2026-09-10 used Microsoft Edge WebDriver 152.0.4191.66 and passed all 6 shell checks. The route covered approved-profile connection, native file selection through IPC mocking, scanned-file intake, Node-shaped task creation, explicit plan approval, live workspace projection, artifact review, and controlled download. The test now withholds the artifact event until the approval command is sent, so the fixture preserves the Node authorization boundary.

The current multiremote run on 2026-09-10 passed its two-instance addressability assertion with two local WebView2 instances. Both runs used `AIRBENCH_ALLOW_DRIVER_DOWNLOAD=1` because a matching driver was not provisioned locally. They are therefore not offline or no-egress evidence. The WDIO service still emits a non-fatal mock-cleanup warning after the WebDriver session has already been deleted; it is visible in the run output and remains a release-harness cleanup item.

The desktop runner places Cargo output and WebDriver logs under one disposable temporary run directory. The frontend log-capture assertion runs before cleanup, and the runner removes only that temporary directory. It does not reuse or delete the repository's existing Cargo debug cache, and it does not leave a new WebDriver log in the working tree.

On 2026-09-09, a fresh Windows run reached the external provider but could not resolve `msedgedriver.microsoft.com` because no matching local Edge driver was provisioned. It did not reach application assertions. The new preflight prevents this missing-prerequisite case from triggering a download or rebuilding the Tauri binary first.

The standalone desktop command now performs a local WebDriver preflight before the expensive webdriver build. On Windows, the default external provider requires `tauri-driver` and a matching local `msedgedriver.exe`; the preflight fails before compilation if either is unavailable. The reproducible offline-safe sequence is:

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
- Reconnect, blocked-navigation, and additional denied-action flows still need to be exercised in the release configuration. Scanned-document upload, safe preview, explicit plan approval, artifact review, and controlled download are covered by the current six-test native shell run using IPC fixtures.
- Repeat the no-egress monitor with the test binary under the enforced host policy. The WebDriver test must not be used to hide WebView2 runtime traffic.
