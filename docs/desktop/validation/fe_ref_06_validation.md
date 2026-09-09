# FE-REF-06 local validation preflight

This record covers the executable local slice of #111. It keeps the visual and
accessibility contract close to the frontend source without claiming that a
development build is the same as packaged desktop evidence.

## What the preflight checks

`npm run check:ui` reads `apps/desktop/validation/ui-baseline.json` and verifies:

- both Obsidian Signal and Ledger Paper theme selectors exist;
- high-contrast, focus-visible, and reduced-motion contracts remain present;
- the launchpad, disconnected home, empty task, plan review, live trace,
  question, proof inspector, and artifact-failure surfaces remain represented;
- authored frontend source does not introduce direct network APIs, external
  URLs, or browser telemetry surfaces;
- the HTML and CSS source contain no remote fonts, images, styles, or scripts;
- an existing production `dist` directory contains no remote HTML or CSS
  resource references;
- the Tauri local-resource policy still includes self-only defaults and a
  denied default connection path.
- the authored TSX tree gives every button an explicit type, gives native form
  controls an accessible name, and gives dialogs a modal and naming contract.
- the Live Task Workspace exposes explicit preserved, retry, and next-action
  guidance for its Node synchronization states. This is a presentation
  contract and does not replace packaged recovery or screen-reader evidence.

The accessibility portion uses the installed TypeScript parser rather than a
regular-expression scan. It checks the authored JSX structure without
executing uploaded content, starting a browser, or making a network request.

The Live Task Workspace also exposes a concise atomic status announcement for
Node-authoritative task status, phase, and cursor changes. Packaged keyboard,
screen-reader, and visual-baseline behavior still requires the desktop
validation environment described below.

The manifest is a semantic baseline. It deliberately does not pretend to be a
pixel screenshot baseline or a packaged accessibility audit. Pixel baselines,
keyboard-only packaged flow, WebDriver execution, and independent network
capture remain required in #111 and the FE-VAL issues.

## Run

From `apps/desktop/`:

```text
npm run check:ui
npm run check:accessibility
npm run check:egress
npm run check:tauri-config
npm test -- --run
```

The preflight uses only repository files and local build output. It creates no
network client and does not read uploaded or organization-sensitive documents.
