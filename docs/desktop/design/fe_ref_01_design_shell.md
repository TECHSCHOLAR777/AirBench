# FE-REF-01 Design Shell Evidence

Issue: [#107](https://github.com/TECHSCHOLAR777/AirBench/issues/107)  
Parent: [#105](https://github.com/TECHSCHOLAR777/AirBench/issues/105)

## Outcome

Establish a professional, offline-safe desktop shell before rebuilding task-specific controls. The shell must make AirBench feel active and trustworthy without simulating work or leaking model reasoning.

## Implemented surface

- `Obsidian Signal` is the default dark theme.
- `Ledger Paper` is the warm beige and orange alternative.
- Both themes use the same semantic colors for verified, active, attention, failed, and stopped state.
- The desktop shell uses restrained translucent navigation, top-bar, and elevated task surfaces over a local ambient background. The visual treatment is hierarchy only and does not claim that a task is active, verified, or sovereign.
- The Launchpad outcome field rests at three lines. Longer requests scroll inside the native textarea instead of stretching the task canvas. Its focused border and glow are presentation-only focus feedback.
- The left rail, Node status, sovereignty control, display control, task canvas, previews, plan review, task workspace, and Node settings use one token foundation.
- Static local SVG icons replace letter placeholders in the navigation and shell.
- A local Display menu offers theme, comfortable or compact density, and high contrast.
- A local workspace command menu is available from the top bar and with `Ctrl/Cmd + K`. It contains only navigation and presentation commands: New task, Current task when a Node projection exists, Node and settings, and Display preferences.
- `Ctrl/Cmd + N` returns to a fresh outcome brief and restores focus to the composer. The command menu traps focus while open, restores focus on close, supports search and arrow-key entry, and never emits a Node command.
- Selecting Tasks without an authoritative task projection shows an honest empty state. It explains the required Node-issued task ID, event cursor, and ledger reference instead of rendering invented activity or a false task count.
- Presentation preferences are stored only in the local desktop webview profile. They do not alter Node state, task payloads, policy, routing, evidence, or ledger records.
- The current type stack uses local operating-system fonts only. It contains no remote `@import`, CDN, font URL, image URL, analytics, or tracking asset.

## Architectural boundary

This work changes only the React presentation layer. The Node remains authoritative for connection trust, sovereignty evidence, task state, plan, model routing, tool policy, file intake, provenance, verification, approvals, calculations, and ledger records.

The Node-path control is derived from the existing typed connection state. It does not claim a verified route while disconnected. The desktop UI still renders task events supplied by the Node and does not expose raw model chain-of-thought.

## Accessibility behavior

- semantic HTML buttons, fields, and fieldsets;
- visible focus rings;
- 44 px consequential controls;
- text and icon reinforcement for status;
- reduced-motion behavior;
- forced-colors support;
- responsive desktop shell collapse without changing task authority.

## Verification completed

On 2026-09-07:

- `npm test -- --run`: 63 tests passed.
- `npm run build`: passed with generated typed contracts and local resource manifest.
- `npm run check:contracts`: passed.
- `npm run check:egress`: passed, reporting no network-capable APIs or external resource URLs in frontend source.
- `npm run check:tauri-config`: passed.
- `git diff --check`: passed.
- `npm run tauri:build:webdriver`: passed, rebuilding the dedicated desktop test binary with the `wdio` feature.
- `npm run test:desktop`: did not reach the application DOM. The embedded WDIO direct-evaluation endpoint returned HTTP 404 before the first shell assertion. The reproducible failure is recorded in the packaged release gate [#124](https://github.com/TECHSCHOLAR777/AirBench/issues/124#issuecomment-5563772756).

## Remaining gate

This is a source and local-build implementation slice. `npm run tauri:dev` has compiled and launched the local `target/debug/airbench-desktop.exe` shell against the current bundle. Full visual baselines for both themes, a desktop accessibility run, and packaged Tauri WebDriver evidence remain in [#111](https://github.com/TECHSCHOLAR777/AirBench/issues/111). A local browser render can inspect presentation but is not packaged desktop evidence.
