# open_ssh_tunnel.ps1
#
# Opens the two-lane SSH tunnel from the developer machine to mmmut-server so
# that the local AirBench Node can reach both vLLM containers through loopback.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\open_ssh_tunnel.ps1
#
# After this script starts, keep the window open.
# The AirBench Node (start_demo_node.ps1) reads:
#   E2B  base URL: http://127.0.0.1:18001  (forwarded from remote :8001)
#   12B  base URL: http://127.0.0.1:18002  (forwarded from remote :8002)
#
# Verify the tunnel is working:
#   curl http://127.0.0.1:18001/health
#   curl http://127.0.0.1:18002/health
#
# Requirements:
#   - SSH alias "mmmut-server" must be configured in ~/.ssh/config
#   - Private key must be configured there (never hardcoded here)

param(
    [string]$SshAlias = "mmmut-server",
    [int]$LocalE2B  = 18001,
    [int]$Remote8001 = 8001,
    [int]$LocalTwelveB = 18002,
    [int]$Remote8002 = 8002
)

$ErrorActionPreference = "Stop"

Write-Host "" 
Write-Host "Opening SSH tunnel to $SshAlias" -ForegroundColor Cyan
Write-Host "  127.0.0.1:$LocalE2B  --> remote 127.0.0.1:$Remote8001  (E2B  / Gemma 4 E2B)" -ForegroundColor DarkCyan
Write-Host "  127.0.0.1:$LocalTwelveB --> remote 127.0.0.1:$Remote8002  (12B  / Gemma 4 12B)" -ForegroundColor DarkCyan
Write-Host ""
Write-Host "Keep this window open. Press Ctrl+C to close the tunnel." -ForegroundColor Yellow
Write-Host ""

# Verify both local ports are free before opening the tunnel.
foreach ($port in @($LocalE2B, $LocalTwelveB)) {
    $existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing) {
        $owner = Get-Process -Id $existing.OwningProcess -ErrorAction SilentlyContinue
        $name = if ($owner) { $owner.ProcessName } else { "unknown" }
        Write-Host "WARNING: Port $port is already in use by PID $($existing.OwningProcess) ($name)." -ForegroundColor Yellow
        Write-Host "         If it is a previous tunnel, close that window first." -ForegroundColor Yellow
        Write-Host "         If it is something else, rerun with a different -LocalE2B/-LocalTwelveB value." -ForegroundColor Yellow
    }
}

ssh -N `
    -o ExitOnForwardFailure=yes `
    -o ServerAliveInterval=30 `
    -o ServerAliveCountMax=3 `
    "-L" "127.0.0.1:${LocalE2B}:127.0.0.1:${Remote8001}" `
    "-L" "127.0.0.1:${LocalTwelveB}:127.0.0.1:${Remote8002}" `
    $SshAlias
