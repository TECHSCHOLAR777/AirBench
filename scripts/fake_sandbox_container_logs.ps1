# fake_sandbox_container_logs.ps1
#
# Streams the fake "container" boot/session log used for the Sandbox demo
# (see apps\desktop\src\features\sandbox\sandboxContainer.ts for the source
# of truth on the message text — keep this in sync with that file). This is
# NOT a real container: it prints staged log lines to look like one running
# in a second terminal window next to the app, the same way open_ssh_tunnel.ps1
# and start_demo_node.ps1 give the demo real-looking terminal chatter.
#
# The Python code the Sandbox screen runs is real (local subprocess) — only
# this surrounding narrative is fake.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\fake_sandbox_container_logs.ps1

$ErrorActionPreference = "Stop"

function Write-Line([string]$Text, [string]$Color = "Green") {
    Write-Host $Text -ForegroundColor $Color
    Start-Sleep -Milliseconds (Get-Random -Minimum 250 -Maximum 650)
}

$containerId = "sbx-" + -join ((48..57 + 97..102) | Get-Random -Count 12 | ForEach-Object { [char]$_ })
$cursor = "0x" + -join ((48..57 + 97..102) | Get-Random -Count 8 | ForEach-Object { [char]$_ })

Write-Host ""
Write-Host "CLI SESSION // TTY1" -ForegroundColor White
Write-Host ""
Write-Line "STATUS: IDLE | CURSOR: $cursor | LISTEN: ipc:///tmp/airbench.sock" DarkGreen
Write-Line "[DAEMON] Sovereign handshake verified. Local crypto engine initialized: Ed25519-SHA512."
Write-Line "[ENCLAVE] Zero unauthorized mutations detected in workspace journal since genesis block 0x0000."
Write-Host ""
Write-Host "Press Ctrl+C to close this session." -ForegroundColor Yellow
Write-Host ""

while ($true) {
    Write-Line "[DAEMON] Requesting worker lease from pool (2/4 idle)..." DarkGreen
    Write-Line "[DAEMON] Container $containerId scheduled from image airbench/sandbox-runtime:py3.11-slim."
    Write-Line "[ENCLAVE] Mounting ephemeral workspace, network egress disabled." DarkGreen
    Write-Line "[DAEMON] stdout/stderr pipes attached over ipc:///tmp/airbench.sock."
    Write-Line "[DAEMON] Executing script.py inside $containerId..."
    Start-Sleep -Seconds (Get-Random -Minimum 3 -Maximum 8)
    Write-Line "[DAEMON] Process exited with code 0." DarkGreen
    Write-Host ""
    Start-Sleep -Seconds (Get-Random -Minimum 4 -Maximum 10)
}
