$ErrorActionPreference = "Stop"

$installerPath = Join-Path $PSScriptRoot "..\src-tauri\target\release\bundle\nsis\AirBench_0.1.0_x64-setup.exe"
if (-not (Test-Path -LiteralPath $installerPath)) {
    throw "Installer not found: $installerPath"
}

$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$installRoot = Join-Path $env:TEMP ("AirBenchValidation-" + $runId)
$null = New-Item -ItemType Directory -Path $installRoot -Force
$hash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash
$start = Get-Date
$process = Start-Process -FilePath $installerPath -ArgumentList @("/S", "/D=$installRoot") -PassThru
$networkObservations = [System.Collections.Generic.List[object]]::new()
$installedExecutable = Join-Path $installRoot "airbench-desktop.exe"

function Get-ProcessTreeIds([int]$rootProcessId) {
    $allIds = [System.Collections.Generic.HashSet[int]]::new()
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $pending.Enqueue($rootProcessId)
    while ($pending.Count -gt 0) {
        $currentId = $pending.Dequeue()
        if (-not $allIds.Add($currentId)) { continue }
        $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $currentId" | Select-Object -ExpandProperty ProcessId)
        foreach ($childId in $children) { $pending.Enqueue([int]$childId) }
    }
    return @($allIds)
}

while (-not $process.HasExited) {
    $process.Refresh()
    $processIds = Get-ProcessTreeIds $process.Id
    foreach ($processId in $processIds) {
        $connections = @(Get-NetTCPConnection -OwningProcess $processId -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Established" -and $_.RemotePort -ne 0 })
        foreach ($connection in $connections) {
            $networkObservations.Add([pscustomobject]@{
                processId = $processId
                remoteAddress = $connection.RemoteAddress
                remotePort = $connection.RemotePort
                observedAt = (Get-Date).ToString("o")
            })
        }
    }
    Start-Sleep -Milliseconds 200
}

$process.Refresh()
$installDeadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $installDeadline) {
    if ((Test-Path -LiteralPath $installedExecutable) -and ((Get-Item -LiteralPath $installedExecutable).Length -gt 0)) {
        break
    }
    Start-Sleep -Milliseconds 250
}

$installedFile = Get-Item -LiteralPath $installedExecutable -ErrorAction SilentlyContinue
$artifactDirectory = Join-Path $PSScriptRoot "..\artifacts"
$null = New-Item -ItemType Directory -Path $artifactDirectory -Force
$reportPath = Join-Path $artifactDirectory ("AirBenchInstallerSmoke-" + $runId + "-" + $hash.Substring(0, 12) + ".json")
$result = [ordered]@{
    validation = "FE-VAL-1 installer smoke run"
    runId = $runId
    installer = (Resolve-Path -LiteralPath $installerPath).Path
    installerSha256 = $hash
    startedAt = $start.ToString("o")
    finishedAt = (Get-Date).ToString("o")
    exitCode = $process.ExitCode
    installRoot = $installRoot
    installedExecutableExists = $null -ne $installedFile -and $installedFile.Length -gt 0
    installedExecutableBytes = if ($null -ne $installedFile) { $installedFile.Length } else { 0 }
    observedEstablishedConnections = @($networkObservations | Sort-Object processId, remoteAddress, remotePort, observedAt -Unique)
    limitation = "This is a host smoke run, not the required clean offline Windows image proof."
}

$json = $result | ConvertTo-Json -Depth 8
$json | Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Output ("Installer smoke report: " + $reportPath)
Write-Output $json
