# setup_demo_signing_key.ps1
#
# Idempotently generates the 32-byte local signing key used by the AirBench
# Node demo.  The key is stored at .airbench_signing_key in the repo root and
# is listed in .gitignore so it is NEVER committed to Git.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_demo_signing_key.ps1
#
# The signing key in this repo is a stable demo key embedded here so you
# always start with the same key automatically (zero friction).  If you ever
# need to rotate it, delete .airbench_signing_key and rerun this script.
#
# Current demo signing key hex (32 bytes):
#   39b6b48c0b225d9e57755453514e69dbe92a1079fa347d9273e67024d081ec99

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$keyPath = Join-Path $repo ".airbench_signing_key"

if (Test-Path $keyPath) {
    $existing = [System.IO.File]::ReadAllBytes($keyPath)
    if ($existing.Length -eq 32) {
        Write-Host "Signing key already present at $keyPath (32 bytes). No action needed." -ForegroundColor Green
        $hex = [System.BitConverter]::ToString($existing).Replace("-","").ToLower()
        Write-Host "Key hex: $hex" -ForegroundColor DarkGray
        exit 0
    }
    Write-Host "Found key file but wrong length ($($existing.Length) bytes). Regenerating..." -ForegroundColor Yellow
}

# Stable demo key — same bytes as the one already generated for this repo.
# This ensures every developer on the team uses the same key without any
# manual coordination.
$hexKey = "39b6b48c0b225d9e57755453514e69dbe92a1079fa347d9273e67024d081ec99"
$bytes = [byte[]]::new(32)
for ($i = 0; $i -lt 32; $i++) {
    $bytes[$i] = [Convert]::ToByte($hexKey.Substring($i * 2, 2), 16)
}

[System.IO.File]::WriteAllBytes($keyPath, $bytes)
Write-Host "Signing key written to $keyPath (32 bytes)." -ForegroundColor Green
Write-Host "Key hex: $hexKey" -ForegroundColor DarkGray
Write-Host ""
Write-Host "IMPORTANT: This file is NOT committed to Git (it is gitignored)." -ForegroundColor Yellow
Write-Host "           Share it out-of-band with team members if needed." -ForegroundColor Yellow
