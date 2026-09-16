# Showcase assistant (demo mode)

This feature is a self-contained chat screen ("Assistant" in the sidebar)
for live demos. It exists to answer text / image / hybrid prompts instantly
and reliably even when the real Node pipeline (planning, qualification,
execution, verification) isn't the thing being shown in that moment.

## What is real vs. faked

**Real:**
- The Node connection in the left rail (`connection`, `nodeConnected`,
  `profile` props passed in from `App.tsx`) is the actual, already-existing
  Node handshake — same `NodeConnectionController` used by the rest of the
  app. Connect a Node from **Node and settings** first (which still goes
  through the real SSH tunnel to `aimslab` + `start_demo_node.ps1`, see
  `AIMSLAB_VLLM_ENDPOINT_HANDOFF.md` and `scripts/open_ssh_tunnel.ps1` /
  `scripts/start_demo_node.ps1` at the repo root) and this screen will show
  the genuine Node identity, protocol, clearance, and ledger ref. That Node
  keeps producing its normal server-side logs the whole time — this screen
  just doesn't route the chat content through it.
- The roster names shown (`airbench-qwen25-vl-7b`, `airbench-qwen3-8b`) are
  the real deployed model IDs from the handoff doc, used only for visual
  accuracy.

**Faked, entirely client-side:**
- `pipelineTheater.ts` — the staged "Intake validated / Qualification
  checked / Auto route selected / Verification / Delivery" trace is a timed
  UI reveal. It does not call the Node's real task/plan/route-trace API.
- The actual answer content comes from one of two places, in order:
  1. `fixtures.ts` — a hardcoded match against
     `public/demo-fixtures/manifest.json`. See that folder's README for the
     exact trigger format and how to add your own canned outputs.
  2. `geminiRouter.ts` — if nothing matches, a live call to the Gemini API
     using round-robin keys from `VITE_GEMINI_API_KEYS` (see
     `apps/desktop/.env.example`). This is a real model call, but it is
     **Gemini**, not the AirBench Node's qualified vLLM lane — it's a
     fallback so unscripted questions still get a plausible answer.

## Why it's isolated here

Nothing in `platform/node/*` or `features/tasks/*` was changed. This screen
imports the existing `NodeConnectionView` / `ApprovedNodeProfileReference`
types only to *display* the real connection state — it never calls
`createTask`, `sendTaskCommand`, or any other Node command. That keeps the
real task/ledger/verification code paths (and their tests) completely
untouched.
