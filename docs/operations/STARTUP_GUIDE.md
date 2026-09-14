# AirBench Operator Startup Guide (Two-Endpoint Demo)

This guide documents how to start the AirBench Node with the controlled two-endpoint demonstration roster (E2B and 12B). It walks through generating the local signing key, opening the SSH tunnel, running the preflight checks, and verifying that the Node admits both lanes.

## 1. Generate the local signing key

AirBench refuses to load unsigned model targets. To run the demo, you must have a local signing key at `.airbench_signing_key` in the repository root. This key is used to sign the demo roster so the Node trusts it.

Run the idempotent setup script to create the key:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_demo_signing_key.ps1
```

> [!CAUTION]
> This key is 32 cryptographically random bytes and is excluded by `.gitignore`. **Never commit it.**

## 2. Generate actual hashes for the model targets

The handoff model roster initially contains `PENDING:` placeholders for the artifact, tokenizer, and chat template hashes. You must hash the downloaded model files in your store.

Run the hashing script:

```powershell
# E.g., if models are in C:\airbench-models
$env:AIRBENCH_MODEL_STORE = "C:\airbench-models"
python scripts\airbench_hash.py --target airbench-gemma-4-e2b --target airbench-gemma-4-12b
```

## 3. Build the signed demo roster

Once the hashes are measured and written to the `models/roster/v0/model_roster.yaml` file (replacing the `PENDING` placeholders), generate the demo-specific roster. This script extracts the two demo targets, promotes them to candidate status, and signs the manifest.

```powershell
python scripts\airbench_demo_roster.py
```

This creates the signed file at `models/roster/demo/two_endpoint_roster.yaml`.

## 4. Open the SSH tunnel

The Node connects to the remote GPU workstation using loopback HTTP endpoints on ports `18001` and `18002`.

Open a **dedicated PowerShell window** and run the tunnel wrapper script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\open_ssh_tunnel.ps1
```

> [!IMPORTANT]
> Keep this window open for the duration of the demo. Closing it kills the tunnel.

## 5. Run the model preflight

Before starting the Node, prove that both lanes are actually up, that they match the expected model ID, and that the tunnel works. The start script does this for you automatically, but you can also run it directly:

```powershell
python scripts\model_endpoint_preflight.py `
  --roster models\roster\demo\two_endpoint_roster.yaml `
  --signing-key .airbench_signing_key
```

If it fails, verify the tunnel and the status of the vLLM containers on the remote machine.

## 6. Start the AirBench Node

In a new window, start the Node. By default, it runs in "Resume" mode to keep your existing ledger and corpus state.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1
```

If you want a totally fresh demo (wipes local database, ledger, intakes, and chroma), pass `-Mode Fresh`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_demo_node.ps1 -Mode Fresh
```

Wait until the console outputs `Starting AirBench Node ...` (after it finishes hashing the models).

## 7. Verify endpoints

Open another terminal and verify the Node has successfully mounted both endpoints:

```powershell
$env:AIRBENCH_BEARER_TOKEN="dev-token-123"
curl -H "Authorization: Bearer dev-token-123" http://127.0.0.1:8765/api/v1/node/model-serving
```

You should see `"configured": true` and `"status": "ready"` with both the E2B and 12B endpoints listed in the response payload.
