# AirBench Project Startup Guide

This guide starts AirBench from a fresh repository checkout. It is written
with repository-relative paths so it works regardless of where the repository
is cloned.

AirBench has two runtime paths:

```text
Local validation:
Tauri desktop -> local Python Node -> local fixtures

Remote model demonstration:
Tauri desktop -> local AirBench Node -> SSH tunnel -> AIMS vLLM endpoints
```

The desktop application must connect only to the AirBench Node. It must never
connect directly to a model endpoint.

## 1. Prerequisites

Install or provision the following before starting:

- Git
- Python 3.11 or newer
- Node.js and npm
- Rust and Cargo
- Tauri prerequisites for the target operating system
- Microsoft WebView2 on Windows
- SSH and, when required by the organization, Cloudflare Access
- An approved `aimslab` SSH alias for the remote model path
- Approved AIMS credentials supplied through the organization's secure channel

Do not commit passwords, bearer tokens, private keys, model weights, local
SQLite files, or confidential input documents.

## 2. Open the repository

### PowerShell

```powershell
$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo "pyproject.toml"))) {
    throw "Run this command from the AirBench repository root."
}

Set-Location $repo
```

If starting from another directory:

```powershell
Set-Location "<path-to-your-AirBench-checkout>"
$repo = (Get-Location).Path
```

### Bash

```bash
cd /path/to/your/AirBench
repo="$PWD"
test -f "$repo/pyproject.toml"
```

## 3. Synchronize the checkout

Review local work before pulling. Do not use a hard reset or broad cleanup.

```powershell
git status --short --branch
git fetch origin
git pull --ff-only origin main
git log -1 --oneline --decorate
```

Use the branch required by your team instead of `main` when appropriate.

## 4. Create the Python environment

### Windows PowerShell

```powershell
if (-not (Test-Path ".venv-deep\Scripts\python.exe")) {
    py -3 -m venv .venv-deep
}

$python = (Resolve-Path ".venv-deep\Scripts\python.exe").Path
$env:PATH = (Resolve-Path ".venv-deep\Scripts").Path + ";" + $env:PATH

& $python -m pip install --upgrade pip
& $python -m pip install -e ".[test,deliverables,vector,embedding]"
```

### Bash

```bash
if [ ! -x .venv-deep/bin/python ]; then
  python3 -m venv .venv-deep
fi

source .venv-deep/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test,deliverables,vector,embedding]'
```

## 5. Install desktop dependencies

```powershell
Set-Location (Join-Path $repo "apps\desktop")
if (-not (Test-Path "node_modules")) {
    npm ci
}
```

For Bash:

```bash
cd "$repo/apps/desktop"
[ -d node_modules ] || npm ci
```

## 6. Run local validation first

These checks do not require the remote AIMS model endpoints.

From `apps/desktop`:

```powershell
$env:AIRBENCH_PYTHON = (Resolve-Path "$repo\.venv-deep\Scripts\python.exe").Path

npm run check:ui
npm run check:accessibility
npm run check:egress
npm run check:tauri-config
npm test -- --run
npx tsc -b --pretty false
npm run build
```

Expected results are successful checks, passing frontend tests, a successful
TypeScript build, and a production frontend build.

## 7. Local Python Node validation

The validation scripts use `AIRBENCH_PYTHON` when it is set. This prevents an
incomplete system Python installation from being selected accidentally.

From `apps/desktop`:

```powershell
$env:AIRBENCH_PYTHON = (Resolve-Path "$repo\.venv-deep\Scripts\python.exe").Path

npm run validate:node
npm run validate:python-node
```

These commands start disposable local services and clean their temporary
state. They do not prove qualified model serving, packaged installation,
independent no-egress monitoring, or native Linux sandbox acceptance.

## 8. Prepare the remote AIMS model path

Skip this section when only running local validation.

The remote model path requires an approved SSH alias named `aimslab`:

```powershell
ssh -G aimslab
ssh aimslab "uname -m && nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader"
```

Record any hardware differences. Do not silently reuse a different hardware
profile.

## 9. Start the SSH tunnel

Open a separate terminal and run from the repository root:

```powershell
Set-Location $repo

powershell.exe -ExecutionPolicy Bypass `
  -File ".\scripts\open_ssh_tunnel.ps1"
```

Keep this terminal open. The standard forwards are:

```text
127.0.0.1:18001 -> AIMS 127.0.0.1:8001 -> airbench-qwen25-vl-7b
127.0.0.1:18002 -> AIMS 127.0.0.1:8002 -> airbench-qwen3-8b
```

Verify the forwards from another terminal:

```powershell
Invoke-WebRequest "http://127.0.0.1:18001/health"
Invoke-WebRequest "http://127.0.0.1:18002/health"
Invoke-WebRequest "http://127.0.0.1:18001/v1/models"
Invoke-WebRequest "http://127.0.0.1:18002/v1/models"
```

## 10. Start the AirBench Node

Use an approved bearer token from the secure organizational credential
process. The value below is only a local demonstration example.

```powershell
Set-Location $repo
$env:PATH = (Resolve-Path ".venv-deep\Scripts").Path + ";" + $env:PATH

$env:AIRBENCH_BEARER_TOKEN = "<approved-node-bearer-token>"

powershell.exe -ExecutionPolicy Bypass `
  -File ".\scripts\start_demo_node.ps1" `
  -Token $env:AIRBENCH_BEARER_TOKEN `
  -Subject "operator.validation" `
  -Retrieval `
  -AllowCandidateQualification
```

The Node should listen on `http://127.0.0.1:8765`.

`-AllowCandidateQualification` is a controlled development/demo switch. It
does not qualify a model or prove production readiness. Do not use
`-AllowDegradedLane` for a normal demonstration.

## 11. Verify the Node

In another terminal, set the same token in that PowerShell process:

```powershell
Set-Location $repo
$env:AIRBENCH_BEARER_TOKEN = "<approved-node-bearer-token>"

$headers = @{
    Authorization = "Bearer $env:AIRBENCH_BEARER_TOKEN"
}

Invoke-RestMethod "http://127.0.0.1:8765/api/v1/health" `
  -Headers $headers

Invoke-RestMethod "http://127.0.0.1:8765/api/v1/node/readiness" `
  -Headers $headers

Invoke-RestMethod "http://127.0.0.1:8765/api/v1/node/model-serving" `
  -Headers $headers

Invoke-RestMethod "http://127.0.0.1:8765/api/v1/knowledge/status" `
  -Headers $headers
```

The readiness response should be `ready`, and model-serving should report the
exact configured model IDs. A healthy endpoint is not the same as a qualified
model.

## 12. Provision the desktop Node profile

The desktop uses a native approved profile catalog. React must not be given a
free-form endpoint field.

```powershell
Set-Location $repo

$appConfig = Join-Path $env:APPDATA "org.airbench.desktop"
New-Item -ItemType Directory -Path $appConfig -Force | Out-Null

Copy-Item `
  (Join-Path $repo "approved-node-profiles.json") `
  (Join-Path $appConfig "approved-node-profiles.json") `
  -Force
```

Run the copy as the same Windows user who will launch the desktop. If the
profile was previously created by an administrator and is unreadable, repair
its ACL for the signed-in user before launching the app.

## 13. Provision the OS credential

Use AirBench's native helper so the keyring target and session scope match the
Rust desktop transport:

```powershell
Set-Location $repo

"<approved-node-bearer-token>" |
  cargo run --quiet `
    --manifest-path ".\apps\desktop\src-tauri\Cargo.toml" `
    --example credential_store -- set-stdin airbench-demo-node
```

Do not commit the token or place a production token in a script. This helper
stores it in the operating system credential store under the approved
`org.airbench.desktop` service and `airbench-demo-node` reference.

## 14. Start the Tauri desktop app

Open another terminal:

```powershell
Set-Location (Join-Path $repo "apps\desktop")
npm run tauri:dev
```

In the app:

1. Open Node settings.
2. Select the approved local Node profile.
3. Click **Connect**.
4. Confirm verified Node identity, protocol, clearance, and ledger reference.
5. Create a task and attach files through File Intake.
6. Review and approve the server-owned plan.
7. Watch the authoritative live work trace.
8. Review and download artifacts only through the Node-authorized path.

The desktop connects to the Node on port `8765`. It must not connect directly
to ports `18001` or `18002`.

## 15. End-to-end validation commands

From `apps/desktop`:

```powershell
npm run check:webdriver
npm run test:desktop:real-node
```

The real-node desktop test uses a disposable local Node and synthetic input.
It does not prove qualified AIMS serving, scanned-document quality, native
Linux sandbox isolation, independent no-egress monitoring, or packaged clean
machine acceptance.

For the two-endpoint Node demonstration, from the repository root:

```powershell
Set-Location $repo

python scripts/run_two_endpoint_demo.py `
  --base-url "http://127.0.0.1:8765" `
  --token $env:AIRBENCH_BEARER_TOKEN `
  --subject "operator.validation" `
  --hardware-profile-ref aimslab-titan-rtx-24gb
```

Record exact commands, commit, task ID, sequence range, artifact ID and hash,
ledger references, model identity, hardware, and any failures. Mark external
tests `blocked` when their required AIMS, GPU, Linux, human-review, or
network-monitor evidence is unavailable.

## 16. Shutdown

Stop in this order:

1. Close the Tauri desktop app.
2. Stop the AirBench Node with `Ctrl+C`.
3. Stop the SSH tunnel with `Ctrl+C`.

## 17. Troubleshooting

### The app shows `Blocked`

Check all of the following:

```powershell
Test-Path (Join-Path $env:APPDATA "org.airbench.desktop\approved-node-profiles.json")
cmdkey.exe /list:org.airbench.desktop
Invoke-RestMethod "http://127.0.0.1:8765/api/v1/node/readiness"
```

Then re-run the native credential helper and restart `npm run tauri:dev`.

### The handshake says authentication is required

The bearer token is missing from that PowerShell process. Set
`$env:AIRBENCH_BEARER_TOKEN` again in the same terminal, and ensure it exactly
matches the token used to start the Node.

### The model ports refuse connections

The SSH tunnel is not active, the remote vLLM service is not running, or the
SSH alias/credential is incorrect. Do not use degraded mode to claim a live
model result.

### Validation selects the wrong Python

Set the repository interpreter explicitly:

```powershell
$env:AIRBENCH_PYTHON = (Resolve-Path "$repo\.venv-deep\Scripts\python.exe").Path
```

Then rerun the validation command.

### A task or plan is blocked

This is an authoritative Node state, not a UI error to override locally.
Inspect the plan failure reason, ledger event, clearance, model qualification,
hardware admission, or verification state before retrying.
