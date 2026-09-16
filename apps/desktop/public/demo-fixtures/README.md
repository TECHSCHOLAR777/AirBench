# Demo fixtures for the Assistant screen

This folder is fetched **at runtime** by `src/features/showcase_assistant`
(not bundled at build time) — drop files here and reload the app to pick
them up.

All hardcoded content here is grounded in the real
`AirBench_Refinery_Demo_Corpus` (Unit 4 synthetic refinery case file): the
inspection report, the maintenance SOP, the equipment register, the prior
approval note, and two of the five P&IDs. Nothing here is invented from
scratch — it's the corpus's own findings, procedure text, and reference
reconstruction overlays, pre-written as answers.

## How matching works

- **Text prompts**: `manifest.json` → `text_triggers[]`. If the operator's
  typed request contains one of a trigger's `match` substrings
  (case-insensitive), the assistant returns `output_file` verbatim instead
  of calling Gemini.
- **Image / P&ID uploads**: `manifest.json` → `image_triggers[]`. If the
  **uploaded file's name** contains one of a trigger's `match_filename`
  substrings, the assistant returns `output_image` (shown inline) and
  `output_text` instead of calling Gemini vision.
- If nothing matches, the request goes live to Gemini (round-robin across
  the keys in `VITE_GEMINI_API_KEYS`, see `apps/desktop/.env.local`).

## Wired triggers

| # | Type | Type prompt containing… | Returns |
|---|---|---|---|
| 1 | text | "findings that need management review" / "list the findings" | `text/findings-management-review.md` — F-01/F-02/F-03 from the inspection report |
| 2 | text | "which procedure governs" / "evidence required" | `text/governing-procedure.md` — the Unit 4 Maintenance Review Procedure |
| 3 | text | "downstream of P-101" / "ambiguous tag" | `text/downstream-route.md` — P-101 → V-101 → E-201, with the V-101 tag ambiguity |
| 4 | text | "total finding count" / "calculate the total" | `text/finding-totals.md` — 3 findings, 1 high, 2 medium, 1 low-confidence |
| 5 | text | "prior approval note" / "review pattern" | `text/prior-note-comparison.md` — comparison against AN-SD-007 |
| 6 | text | "approval note" / "review-ready" | `text/approval-note-draft.md` — the full draft management review note |
| 7 | text | "cannot be processed" / "drawing adapter" | `text/missing-pid-evidence.md` — what evidence would be missing |
| 8 | image | filename contains `pid-sd-001` / `pid_sd_001` / `feed-transfer` | `images/pid-sd-001-tag-review-output.png` + `text/pid-sd-001-review.md` |
| 9 | image | filename contains `pid-sd-003` / `pid_sd_003` / `booster` / `tk-301` | `images/pid-sd-003-route-review-output.png` + `text/pid-sd-003-review.md` |

The exact prompt wording for each is in
`apps/desktop/src/features/showcase_assistant/DEMO_RUNBOOK.md`, along with
the two sample P&IDs to upload (already copied into `sample_inputs/` with
filenames that trigger the match).

## To add your own hardcoded outputs

1. Put your canned answer as a `.md`/`.txt` file under `text/`, or your
   canned output image under `images/`.
2. Add an entry to `manifest.json` pointing at it, with the trigger phrases
   (for text) or filename fragments (for image uploads) that should match.
3. Reload the desktop app (no rebuild needed in dev mode).
