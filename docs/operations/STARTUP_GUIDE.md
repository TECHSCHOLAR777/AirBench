# AirBench Startup Guide

This document outlines the standard procedure to start the AirBench Core Node and the Desktop UI for local development and demonstration.

## 0. Connect to the Remote GPU (If using a remote server)

If you are using remote GPU servers to serve the models (e.g. `workstation-04`), you must forward their model serving ports to your local machine so the AirBench Node can connect to them.

Open a PowerShell terminal and run the SSH loopback forward:

```powershell
# Forward both model ports from workstation-04 to your local machine.
# Keep this terminal open while the Node is running.
ssh -N -L 18001:127.0.0.1:18001 -L 18002:127.0.0.1:18002 user@workstation-04
```

## 1. Start the AirBench Node (Backend)

The backend Node requires specific environment variables to establish its operational identity, clearance level, and available models. 

Open a PowerShell terminal in the repository root and run:

```powershell
# Core Node authorization and identity
$env:AIRBENCH_NODE_IDENTITY       = "node.demo.local"
$env:AIRBENCH_BEARER_TOKEN        = "dev-token-123"
$env:AIRBENCH_DOMAIN_PACK_REF     = "refinery-psu-v0"
$env:AIRBENCH_CLEARANCE           = "internal"
$env:AIRBENCH_SUBJECT             = "demo.operator"
$env:AIRBENCH_POLICY_VERSION_HASH = "policy-v0.1"

# Enable Model Serving and point to your Tunneled GPU models
$env:AIRBENCH_MODEL_SERVING_PORT = "18000"
$env:AIRBENCH_LOCAL_MODELS       = "airbench-gemma-4-e2b,airbench-gemma-4-12b"

# Launch the node
python -m airbench.node.server --host 127.0.0.1 --port 8000
```

The server will begin listening on port 8000. Keep this terminal open.

## 2. Start the AirBench Desktop App (Frontend)

The desktop application requires an approved Node profile to successfully handshake with the backend. We use the `approved-node-profiles.json` which contains the trusted identity footprint of the node we just started.

Open a **new** PowerShell terminal and navigate to `apps/desktop`.

```powershell
cd apps/desktop

# Create the AppData folder for the desktop app
New-Item -Path "$env:APPDATA\org.airbench.desktop" -ItemType Directory -Force

# Copy the trusted profile to the AppData folder so the UI can discover it
Copy-Item ..\..\approved-node-profiles.json "$env:APPDATA\org.airbench.desktop\approved-node-profiles.json" -Force

# Launch the Tauri Desktop App in development mode
npm run tauri dev
```

The desktop UI will open and automatically use the trusted profile to perform a secure handshake with the Node running on port 8000.
