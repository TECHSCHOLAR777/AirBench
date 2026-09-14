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

```powershell
# Run from the root of the repository
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 `
  -Retrieval `
  -ModelStore "C:\airbench-models" `
  -Token "dev-token-123" `
  -Subject "demo.operator"
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
