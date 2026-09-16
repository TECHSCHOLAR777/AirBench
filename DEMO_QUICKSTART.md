# AirBench Demo — Quick Start Guide

## What you'll see
- **Real backend**: SSH tunnel + actual Node process with genuine logs
- **Fake frontend**: Assistant chat screen returning hardcoded answers from the corpus (or live Gemini fallback)
- **Proof of connection**: Node identity/protocol/clearance shown in the sidebar

---

## PowerShell Commands — Copy & Paste

Open **4 PowerShell windows** and run these in order:

### Window 1: SSH Tunnel to the inference host
```powershell
cd C:\Users\ALG\Downloads\SIH2026\AirBench-Deep
powershell -ExecutionPolicy Bypass -File scripts\open_ssh_tunnel.ps1
```
**Expected output:**
```
Opening SSH tunnel to aimslab
  127.0.0.1:18001  --> remote 127.0.0.1:8001  (Qwen2.5-VL)
  127.0.0.1:18002 --> remote 127.0.0.1:8002  (Qwen3-8B)

Keep this window open. Press Ctrl+C to close the tunnel.
```
**Leave this running** ← don't close it

---

### Window 2: Start the real AirBench Node
```powershell
cd C:\Users\ALG\Downloads\SIH2026\AirBench-Deep
$env:AIRBENCH_BEARER_TOKEN = "your-token-here"
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 -Token $env:AIRBENCH_BEARER_TOKEN
```
**Replace `your-token-here`** with your actual bearer token if you have one.

**Expected output (after ~30 sec):**
```
Node listening on http://127.0.0.1:8765
node.started ledger event recorded
```
**Leave this running** ← this is the real backend

---

### Window 3: Start the Tauri desktop app
```powershell
cd C:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop
npm run tauri:dev
```
**Expected output:**
```
  VITE v7.0.0  ready in 1234 ms

  ➜  Local:   http://127.0.0.1:1420/
  ➜  press h to show help
```
A native window opens with the AirBench app.

---

## In the App — Step-by-Step

### Step 1: Connect the real Node
1. Click **Node and settings** in left nav
2. Click **Connect** on "Local Demonstration Node"
3. **Watch Window 2** (the Node terminal) — you'll see:
   ```
   handshake request received from desktop
   protocol check passed
   ```
4. Click **Home** to go back

Now the **Assistant** screen's sidebar shows real Node identity/protocol/clearance.

---

### Step 2: Open the Assistant screen
Click **Assistant** in the left nav.

You should see:
- Left sidebar with genuine Node connection info (from step 1)
- Chat area with "What do you want AirBench to complete?"
- An attach button + text input + "Ask AirBench" button

---

### Step 3: Type a hardcoded prompt (guaranteed match)
Copy-paste **exactly**:
```
Read the Unit 4 inspection report and list the findings that need management review.
```

**Click "Ask AirBench"**

**You'll see:**
- Animated trace: "File Intake validated" → "Qualification checked" → "Auto route selected" → "Verification" → "Delivery"
- Then the hardcoded answer appears:
  ```
  Finding F-01 — High priority. Surface corrosion visible at P-101...
  Finding F-02 — Medium priority. Valve tag near V-101 is partially obscured...
  Finding F-03 — Medium priority. Insulation condition near E-201...
  ```

This is **fake** (client-side hardcoded), but:
- The Node connection in the sidebar is **real** (from your SSH + Node backend)
- The staged "pipeline" trace is cosmetic
- The actual answer came from `apps/desktop/public/demo-fixtures/text/findings-management-review.md`

---

### Step 4: Try uploading an image (hardcoded P&ID)
1. Click the **attachment** button (📎)
2. Browse to: `C:\Users\ALG\Downloads\SIH2026\AirBench-Deep\apps\desktop\public\demo-fixtures\sample_inputs\`
3. Select: `pid-sd-001-feed-transfer-train.png`
4. Type (optional): `Identify equipment tags in this P&ID`
5. **Click "Ask AirBench"**

**You'll see:**
- Same animated trace
- Then the annotated overlay image (with boxes and confidence scores) + a tag table

This is **fake** (hardcoded overlay from the corpus), but shows how the demo works visually.

---

### Step 5: Test live Gemini fallback
Type something **not in the hardcoded list**, e.g.:
```
Summarize the risks of confined space entry in three bullet points.
```

**Click "Ask AirBench"**

**You'll see:**
- Animated trace
- Then a **real, live Gemini response** (varies each time)
- Proves the fallback is working

---

## All Hardcoded Prompts (for reference)

Type any of these **exactly** to hit a fixture instead of Gemini:

| Prompt | Returns |
|---|---|
| `Read the Unit 4 inspection report and list the findings that need management review.` | F-01/F-02/F-03 findings table |
| `Which procedure governs the evidence required before a Unit 4 review note is drafted?` | The Unit 4 Maintenance Review Procedure |
| `What is downstream of P-101, and which route component has an ambiguous tag?` | P-101 → V-101 → E-201 route |
| `Calculate the total finding count, high-priority count, medium-priority count, and low-confidence count.` | 3 total / 1 high / 2 medium / 1 low |
| `Compare the current findings with the prior approval note. What review pattern is consistent?` | Comparison to AN-SD-007 |
| `Prepare a review-ready Word approval note with cited findings, totals, and human-review status.` | Full draft management review note |
| `What evidence would be missing if the source P&ID cannot be processed by the drawing adapter?` | Evidence gap explanation |

Upload image with filename containing: `pid-sd-001` or `feed-transfer` → gets PID-SD-001 overlay + tag review
Upload image with filename containing: `pid-sd-003` or `booster` or `tk-301` → gets PID-SD-003 overlay + route review

---

## Troubleshooting

**"Node path not verified" in sidebar**
→ You skipped Window 2 or it crashed. Restart it, then go to Node settings and click Connect again.

**"No Gemini API key configured" when typing off-script prompt**
→ Check `apps\desktop\.env.local` exists and has the key. Restart the Tauri app (Window 3) after editing it.

**"Cannot reach the approved Node" or SSH connection fails**
→ Make sure Window 1 (SSH tunnel) is still running. Restart it if it exited.

**Image upload doesn't attach**
→ Use the browser file picker in `npm run dev` (skip Tauri) if native file handling is blocked.

---

## Full Logs Paths

- **SSH tunnel**: Terminal 1
- **Node startup & handshake logs**: Terminal 2
- **Frontend app logs**: Terminal 3 (Vite) + browser console
- **Fixture loads**: Browser DevTools → Network tab → demo-fixtures/*.json

---

## One-Liner to Stop Everything
```powershell
# Press Ctrl+C in each of the 4 PowerShell windows (or close the Tauri native window)
```

Then close the SSH tunnel last (Ctrl+C in Window 1).
