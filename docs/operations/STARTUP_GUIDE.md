# AirBench Startup Guide

This document outlines the standard 4-terminal procedure to start the AirBench Core Node and the Desktop UI for local development, assuming your models are served from a remote GPU.

## Terminal 1 — Remote GPU Server

Start the model-serving containers on your remote server (e.g., `mmmut-server`) and monitor the GPUs.

```bash
ssh mmmut-server
docker start airbench-vllm-e2b airbench-vllm-12b
watch -n 1 nvidia-smi
```

## Terminal 2 — Laptop SSH Tunnel

Forward the model serving ports from the remote server to your local machine. Leave this terminal open.

```powershell
ssh -N -L 127.0.0.1:18001:127.0.0.1:8001 -L 127.0.0.1:18002:127.0.0.1:8002 mmmut-server
```

## Terminal 3 — Laptop AirBench Node

From the root of the AirBench repository, start the backend Core Node using the provided startup script. Be sure to point `-ModelStore` to wherever you store your model hashes locally.

The startup script first runs the model endpoint preflight (`scripts/model_endpoint_preflight.py`): it verifies the signed roster, checks each tunnelled lane's HTTP health, and confirms the exact served model name matches the roster. The Node refuses to start when a lane is down unless you pass `-AllowDegradedLane` (debugging only — plan approval is then refused with `model_lane_not_ready` until the lane recovers).

You can also run the preflight on its own:

```powershell
python scripts\model_endpoint_preflight.py
```

```powershell
# Run from the root of the repository
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 `
  -Mode Fresh `               # Fresh: delete local demo state so old tasks cannot leak in (default: Resume)
  -Retrieval `
  -ModelStore "C:\airbench-models" `
  -Token "dev-token-123" `
  -Subject "demo.operator"
```

The script refuses to start when port 8765 is already owned by another
process (it prints the owning PID), runs the model endpoint preflight, and
prints a machine-readable `NODE_STARTUP_SUMMARY` line (stores, execution mode,
model serving, ledger head) plus a preflight report before the Node binds.
You can inspect the port/Node state at any time with:

```powershell
python scripts\node_preflight.py --json
```

## Terminal 4 — Laptop Desktop UI

Launch the frontend application. It will copy the approved node profile into its configuration folder and start the development server.

```powershell
# Navigate to the desktop app folder
cd apps\desktop

# Create the AppData folder for the desktop app
New-Item -Path "$env:APPDATA\org.airbench.desktop" -ItemType Directory -Force

# Copy the trusted profile to the AppData folder so the UI can discover it
Copy-Item `
  "..\..\approved-node-profiles.json" `
  "$env:APPDATA\org.airbench.desktop\approved-node-profiles.json" `
  -Force

# Launch the Tauri Desktop App in development mode
npm run tauri:dev
```
