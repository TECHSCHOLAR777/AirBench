# AIMSLAB Qwen Remote-GPU Setup

This runbook connects a local AirBench Node to the two already-running vLLM
services on `aimslab`. The inference host remains an inference server only;
the AirBench Node and desktop stay on the developer machine.

## Prerequisites

- Windows PowerShell, the repository virtual environment, and `cloudflared`.
- AIMSLAB SSH credentials supplied separately.
- The `aimslab` SSH alias configured in `%USERPROFILE%\.ssh\config`.
- The local `.airbench_signing_key` created by the repository setup.

Never commit `.airbench_signing_key`, SSH passwords, bearer tokens, or other credentials.

## Configure the SSH alias

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh"
notepad "$env:USERPROFILE\.ssh\config"
```

Add this block:

```sshconfig
Host aimslab
    HostName ssh.aimsdtu.in
    User aims-dtu
    PasswordAuthentication yes
    ProxyCommand cloudflared access ssh --hostname %h
```

Verify the alias:

```powershell
ssh -G aimslab
```

## Start the tunnel

Open a dedicated PowerShell window and keep it open:

```powershell
Set-Location "C:\Users\ALG\Downloads\SIH2026\AirBench-Deep"
powershell.exe -ExecutionPolicy Bypass -File ".\scripts\open_ssh_tunnel.ps1"
```

The forwards are:

```text
127.0.0.1:18001 -> aimslab:127.0.0.1:8001 -> airbench-qwen25-vl-7b
127.0.0.1:18002 -> aimslab:127.0.0.1:8002 -> airbench-qwen3-8b
```

## Verify the endpoints

In a second PowerShell window:

```powershell
Set-Location "C:\Users\ALG\Downloads\SIH2026\AirBench-Deep"
Invoke-WebRequest "http://127.0.0.1:18001/health"
Invoke-WebRequest "http://127.0.0.1:18002/health"

.\.venv-deep\Scripts\python.exe ".\scripts\model_endpoint_preflight.py" `
  --roster ".\models\roster\aimslab\qwen_vllm_roster.yaml" `
  --attestation ".\models\attestations\aimslab_qwen_vllm.yaml" `
  --signing-key ".\.airbench_signing_key" `
  --attestation-signing-key ".\.airbench_signing_key"
```

Continue only when the final line is `Model endpoint preflight: ready`.

## Start the local AirBench Node

In a third PowerShell window:

```powershell
Set-Location "C:\Users\ALG\Downloads\SIH2026\AirBench-Deep"
$env:AIRBENCH_BEARER_TOKEN = "airbench-local-demo-token"
powershell.exe -ExecutionPolicy Bypass -File ".\scripts\start_demo_node.ps1" `
  -AllowCandidateQualification
```

The Qwen roster is marked `candidate` until role-specific evaluation is
completed. The switch is required for this controlled demo and is not a
production qualification.

If port `8765` is already occupied, inspect the process before stopping it:

```powershell
Get-Process -Id <PID> | Format-List Id,ProcessName,Path,StartTime
Stop-Process -Id <PID>
```

Do not use `-AllowDegradedLane` for a real demo; it is only for diagnostics.

## Run the governed demo

In a fourth PowerShell window:

```powershell
Set-Location "C:\Users\ALG\Downloads\SIH2026\AirBench-Deep"
.\.venv-deep\Scripts\python.exe ".\scripts\run_two_endpoint_demo.py" `
  --token "airbench-local-demo-token" `
  --hardware-profile-ref "aimslab-titan-rtx-24gb"
```

The successful run must show Node model-serving status, task creation,
authorization, plan approval, model response, route trace, and ledger-backed
completion. The desktop calls the Node API only; it must never call vLLM
directly.

## Troubleshooting

- `unhealthy` on ports `18001` or `18002`: reopen the SSH tunnel and rerun
  preflight.
- `Port 8765 is already owned`: inspect the PID and stop only the intended
  AirBench process before restarting the Node.
- HTTP `500` during authorization: copy the traceback from the Node terminal;
  do not repeatedly create new tasks. Restart the Node after resolving the
  reported local configuration or state error.
- Candidate routing is rejected: use the explicit demo switch above.

## Production boundary

The signed attestation is a controlled remote-serving record with an expiry.
Production use still requires measured role qualification, supervised tunnel
recovery, key rotation, monitoring, and a production-grade host attestation.
