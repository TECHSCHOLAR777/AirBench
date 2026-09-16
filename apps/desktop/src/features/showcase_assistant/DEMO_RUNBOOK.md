# Running the demo (Assistant screen)

This is the operator runbook for a live demo. It reuses the existing,
unmodified SSH + Node workflow so the backend logs are real, and adds one
new "Assistant" screen to the desktop app for the chat itself. All
hardcoded content is grounded in `AirBench_Refinery_Demo_Corpus/` (Unit 4
synthetic refinery case file).

## 1. Start the real backend (unchanged)

From the repo root, exactly as before:

```powershell
# Terminal 1 — SSH tunnel to the real inference host
powershell -ExecutionPolicy Bypass -File scripts\open_ssh_tunnel.ps1

# Terminal 2 — the real AirBench Node, once the tunnel is up
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 -Token <your bearer token>
```

Leave both windows open. This is the genuine Node process — it will log
real startup/handshake/task activity the whole time, independent of
whatever the Assistant screen shows.

If you're just testing the Assistant screen itself and don't need the
Node-identity sidebar to show live values yet, you can skip this step —
the screen still works, it just shows "Node path not verified".

## 2. Gemini fallback key

Already configured in `apps/desktop/.env.local` (gitignored, not committed).
It's used only for prompts that don't match a hardcoded fixture below. To
add more keys for round-robin, edit that file — comma-separated:

```
VITE_GEMINI_API_KEYS=key_one,key_two,key_three
```

## 3. Start the desktop app

```powershell
cd apps\desktop
npm run tauri:dev
```

(Or `npm run dev` for just the web view in a browser at
`http://127.0.0.1:1420` if you don't need the native shell for this check —
file attach still works via the browser's file picker.)

## 4. What to test and exact prompts to type

Go to **Assistant** in the left nav. Type each prompt below **exactly as
shown** (or anything containing the bolded phrase) — each is guaranteed to
hit a hardcoded fixture instead of a live model call, so the answer is
always the same in every rehearsal:

| Type this prompt | You should see |
|---|---|
| `Read the Unit 4 inspection report and **list the findings** that need management review.` | F-01 (high, corrosion, P-101), F-02 (medium, low-confidence V-101 tag), F-03 (medium, E-201 insulation) |
| `**Which procedure governs** the evidence required before a Unit 4 review note is drafted?` | Summary of the Unit 4 Maintenance Review Procedure (acceptance rule, escalation, deliverable requirement) |
| `What is **downstream of P-101**, and which route component has an ambiguous tag?` | P-101 → V-101 → E-201, with the V-101 tag flagged low-confidence |
| `**Calculate the total finding count**, high-priority count, medium-priority count, and low-confidence count.` | 3 total / 1 high / 2 medium / 1 low-confidence, as a table |
| `Compare the current findings with the **prior approval note**. What review pattern is consistent?` | Comparison against AN-SD-007 |
| `**Prepare a review-ready** Word approval note with cited findings, totals, and human-review status.` | The full draft management review note (the flagship "generated document" answer) |
| `What evidence would be missing if the source P&ID **cannot be processed** by the drawing adapter?` | The evidence-gap explanation |

For the two image prompts, click the attach button and upload one of the
pre-supplied real P&IDs from
`apps/desktop/public/demo-fixtures/sample_inputs/`:

| Upload this file | Type (optional) | You should see |
|---|---|---|
| `sample_inputs/pid-sd-001-feed-transfer-train.png` | *(text optional, e.g. "Identify equipment and instrument tags in this P&ID")* | The real reference-reconstruction overlay image (tags boxed and confidence-scored) + a tag table |
| `sample_inputs/pid-sd-003-booster-pump-train.png` | *(optional, e.g. "Trace the route from TK-301 through the booster train")* | The real overlay for the booster train + the traced route |

**To test the live Gemini fallback** (not a fixture), type something that
doesn't match any phrase above, e.g. `Summarize the risks of confined space
entry in three bullet points.` — this should return a real, freshly
generated Gemini answer each time (varies slightly on rerun), confirming
the round-robin key is live. If it fails, check `apps/desktop/.env.local`
has a valid key and the app was restarted after editing it (Vite only
reads `.env.local` at startup).

## 5. Confirming the backend logs are real (separate from the chat)

1. Go to **Node and settings** → connect the approved local Node profile.
   Watch the Node's own terminal window (from step 1) — you'll see the
   real handshake request land in its logs.
2. Return to **Assistant** — the left sidebar now shows the genuine Node
   identity/protocol/clearance/ledger ref from that handshake. None of the
   chat answers above depend on this connection; it's shown purely so the
   backend's real activity is visible alongside the chat.

## Adding more hardcoded Q&A before a demo

Drop files into `apps/desktop/public/demo-fixtures/text/` or `.../images/`
and add a matching entry to `apps/desktop/public/demo-fixtures/manifest.json`
(see that folder's README for the full trigger format). No rebuild needed
in dev mode — just reload the app window.
