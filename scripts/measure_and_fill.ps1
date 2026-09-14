<#
.SYNOPSIS
  One-time AirBench measurement + qualification filler.

.DESCRIPTION
  Connects to the GPU host over SSH (via cloudflared), measures the hardware
  profile on the box, pulls it back into this repo, then qualifies the two Gemma
  lanes through the SSH tunnel and re-signs the demo roster.

  The GPU host uses password authentication, so run this in an interactive
  PowerShell window. SSH connection multiplexing means you type the password
  once and every ssh/scp afterwards reuses the connection.

.PARAMETER RemoteRepo
  Absolute path of the AirBench-Deep checkout on the GPU host, e.g.
  /home/workstation-04/AirBench-Deep

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\measure_and_fill.ps1 `
      -RemoteRepo /home/workstation-04/AirBench-Deep
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$RemoteRepo,
  [string]$SshHost = "mmmut-server",
  [string]$ContainerImage = "vllm/vllm-openai:v0.28.0-ubuntu2404",
  [string]$Python = "",
  [string]$Profile = "profiles/hardware/workstation_04.json",
  [switch]$SkipTunnel,
  [switch]$SkipQualify,
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Python) { $Python = Join-Path $RepoRoot ".venv-deep\Scripts\python.exe" }

$controlPath = Join-Path $env:TEMP "airbench-ssh-%r@%h:%p"
$SshOpts = @(
  "-o", "ControlMaster=auto",
  "-o", "ControlPath=$controlPath",
  "-o", "ControlPersist=15m",
  "-o", "ConnectTimeout=20"
)
function Assert { param([bool]$Condition, [string]$Message) if (-not $Condition) { throw $Message } }
function Invoke-Ssh { param([string]$Command) & ssh @SshOpts $SshHost $Command }
function Copy-FromRemote { param([string]$RemotePath, [string]$LocalPath) & scp @SshOpts ("{0}:{1}" -f $SshHost, $RemotePath) $LocalPath }

Write-Host "== AirBench measure & fill ==" -ForegroundColor Cyan
Assert ([bool](Get-Command ssh -ErrorAction SilentlyContinue)) "ssh not found"
Assert ([bool](Get-Command cloudflared -ErrorAction SilentlyContinue)) "cloudflared not on PATH (copy it into a PATH directory such as %LOCALAPPDATA%\Microsoft\WindowsApps)"
Assert (Test-Path $Python) "Python venv not found: $Python"

# 1. Tunnel (single password prompt, reused for every later ssh/scp).
if (-not $SkipTunnel) {
  Write-Host "Opening SSH tunnel in a new window - enter the SSH password there..." -ForegroundColor Yellow
  $tunnelCmd = "ssh -N -o ControlMaster=master -o ControlPath=`"$controlPath`" -o ControlPersist=15m " +
               "-L 127.0.0.1:18001:127.0.0.1:8001 -L 127.0.0.1:18002:127.0.0.1:8002 $SshHost"
  Start-Process powershell -ArgumentList @("-NoExit", "-Command", $tunnelCmd) | Out-Null
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:18001/v1/models" -TimeoutSec 5 | Out-Null; $ready = $true; break } catch {}
  }
  Assert $ready "The tunnel did not serve 127.0.0.1:18001 within 60s."
}

# 2. Verify both model lanes.
foreach ($port in 18001, 18002) {
  $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/v1/models" -TimeoutSec 10
  Write-Host ("model lane {0}: HTTP {1}" -f $port, $r.StatusCode) -ForegroundColor Green
}

# 3. Measure hardware on the GPU host (one ssh connection).
Write-Host "Measuring hardware on the GPU host..." -ForegroundColor Cyan
$forceArg = if ($Force) { " --force" } else { "" }
$remote = Invoke-Ssh "cd '$RemoteRepo' && python3 scripts/airbench_hardware_profile.py --profile $Profile --write$forceArg && echo ---PROFILE--- && cat $Profile"
$remote | Out-Host
Assert ($remote -match "---PROFILE---") "Remote hardware measurement failed (see output above)."

# 4. Bring the measured profile back into this repo.
Copy-FromRemote "$RemoteRepo/$Profile" (Join-Path $RepoRoot $Profile)
Write-Host "Updated $Profile in this repo." -ForegroundColor Green

# 5. Qualify Gemma lanes and re-sign the roster.
if (-not $SkipQualify) {
  $digest = (Invoke-Ssh "docker inspect --format '{{index .RepoDigests 0}}' $ContainerImage" | Select-Object -Last 1).Trim()
  Write-Host "vLLM container digest: $digest" -ForegroundColor Cyan

  $lanes = @(
    @{ target = "airbench-gemma-4-e2b"; role = "reasoning";   endpoint = "http://127.0.0.1:18001"; served = "airbench-gemma-4-e2b" },
    @{ target = "airbench-gemma-4-12b"; role = "reasoning";   endpoint = "http://127.0.0.1:18002"; served = "airbench-gemma-4-12b" },
    @{ target = "airbench-gemma-4-12b"; role = "lead_worker"; endpoint = "http://127.0.0.1:18002"; served = "airbench-gemma-4-12b" }
  )
  foreach ($lane in $lanes) {
    Write-Host ("Qualifying {0} / {1} ..." -f $lane.target, $lane.role) -ForegroundColor Cyan
    & $Python (Join-Path $RepoRoot "scripts\airbench_qualify.py") `
      --target-id $lane.target --role $lane.role --endpoint $lane.endpoint --served-model $lane.served `
      --write-roster --write-matrix --container-digest $digest
    Assert ($LASTEXITCODE -eq 0) ("Qualification failed for {0}/{1}" -f $lane.target, $lane.role)
  }

  Write-Host "Re-signing the demo roster..." -ForegroundColor Cyan
  & $Python (Join-Path $RepoRoot "scripts\airbench_demo_roster.py")
  Assert ($LASTEXITCODE -eq 0) "Demo roster build failed."

  Write-Host "Qualifying BGE retrieval..." -ForegroundColor Cyan
  & $Python (Join-Path $RepoRoot "scripts\airbench_retrieval_demo.py") --model-store (Join-Path $RepoRoot "airbench-models") --qualify --write-roster
}

Write-Host ""
Write-Host "Done. Final manual checks:" -ForegroundColor Yellow
Write-Host "  * $Profile has no PENDING / aaaa... values"
Write-Host "  * models\roster\v0\model_roster.yaml Gemma roles have real certificate_id + qualification_hash"
Write-Host "  * qualifications\model_qualification_matrix.yaml Gemma certs have no REPLACE_WITH_MEASURED"
Write-Host "  * restart the Node so it reloads the re-signed roster (scripts\start_demo_node.ps1)"
