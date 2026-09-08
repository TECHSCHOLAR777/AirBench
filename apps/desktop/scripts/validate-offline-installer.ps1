param(
    [switch]$RequireCleanOfflineImage
)

$ErrorActionPreference = "Stop"

$scriptRoot = (Resolve-Path $PSScriptRoot).Path
$frontendRoot = (Resolve-Path (Join-Path $scriptRoot "..")).Path
$installerPath = Join-Path $frontendRoot "src-tauri\target\release\bundle\nsis\AirBench_0.1.0_x64-setup.exe"
$artifactDirectory = Join-Path $frontendRoot "artifacts"
$runId = "AirBenchInstallerSmoke-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N")
$reportPath = Join-Path $artifactDirectory "$runId.json"
$installRoot = Join-Path $env:TEMP ("AirBenchValidation-" + $runId)
$failures = [System.Collections.Generic.List[string]]::new()
$networkObservations = [System.Collections.Generic.List[object]]::new()
$startupObservations = [System.Collections.Generic.List[object]]::new()
$installerProcess = $null
$applicationProcess = $null

function Get-ProcessTreeIds([int]$rootProcessId) {
    $allIds = [System.Collections.Generic.HashSet[int]]::new()
    $pending = [System.Collections.Generic.Queue[int]]::new()
    $snapshot = @(Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId, Name -ErrorAction SilentlyContinue)
    $root = $snapshot | Where-Object { [int]$_.ProcessId -eq $rootProcessId } | Select-Object -First 1
    $allowedNames = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    if ($null -ne $root) { $null = $allowedNames.Add([string]$root.Name) }
    $null = $allowedNames.Add("msedgewebview2.exe")
    $childrenByParent = @{}
    foreach ($process in $snapshot) {
        if (-not $allowedNames.Contains([string]$process.Name)) { continue }
        $parentId = [int]$process.ParentProcessId
        if (-not $childrenByParent.ContainsKey($parentId)) { $childrenByParent[$parentId] = [System.Collections.Generic.List[int]]::new() }
        $childrenByParent[$parentId].Add([int]$process.ProcessId)
    }
    $pending.Enqueue($rootProcessId)
    while ($pending.Count -gt 0) {
        $currentId = $pending.Dequeue()
        if (-not $allIds.Add($currentId)) { continue }
        foreach ($childId in @($childrenByParent[[int]$currentId])) { $pending.Enqueue([int]$childId) }
    }
    return @($allIds)
}

function Get-ObservedConnections([array]$processIds, [string]$phase) {
    $observed = [System.Collections.Generic.List[object]]::new()
    $processIdSet = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($processId in $processIds) { $null = $processIdSet.Add([int]$processId) }
    $connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object { $processIdSet.Contains([int]$_.OwningProcess) -and $_.RemotePort -ne 0 })
    foreach ($connection in $connections) {
            $observed.Add([pscustomobject]@{
                phase = $phase
                processId = $connection.OwningProcess
                remoteAddress = $connection.RemoteAddress
                remotePort = $connection.RemotePort
                observedAt = (Get-Date).ToString("o")
            })
    }
    return @($observed)
}

function Get-NetworkEnvironment {
    $adapters = @()
    try {
        $adapters = @(Get-NetAdapter -ErrorAction Stop | Select-Object Name, Status, LinkSpeed)
    } catch {
        $adapters = @([pscustomobject]@{ error = $_.Exception.Message })
    }
    $proxy = "unavailable"
    try { $proxy = (netsh winhttp show proxy 2>&1 | Out-String).Trim() } catch { $proxy = $_.Exception.Message }
    return [ordered]@{
        capturedAt = (Get-Date).ToString("o")
        adapters = $adapters
        winHttpProxy = $proxy
    }
}

function Get-WebView2RuntimeObservation {
    $observations = [System.Collections.Generic.List[object]]::new()
    $registryPaths = @(
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
        "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    )
    foreach ($path in $registryPaths) {
        $item = Get-ItemProperty -LiteralPath $path -ErrorAction SilentlyContinue
        if ($null -ne $item) { $observations.Add([pscustomobject]@{ source = $path; version = $item.pv; name = $item.name }) }
    }
    $programRoots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Where-Object { $_ }
    foreach ($programRoot in $programRoots) {
        $pattern = Join-Path $programRoot "Microsoft\EdgeWebView\Application\*\msedgewebview2.exe"
        foreach ($file in @(Get-ChildItem -Path $pattern -File -ErrorAction SilentlyContinue)) {
            $observations.Add([pscustomobject]@{ source = $file.FullName; version = $file.VersionInfo.ProductVersion; name = $file.Name })
        }
    }
    return @($observations)
}

function Stop-ProcessTree([int]$rootProcessId) {
    foreach ($processId in (Get-ProcessTreeIds $rootProcessId | Sort-Object -Descending)) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Write-ValidationReport([hashtable]$report) {
    $null = New-Item -ItemType Directory -Path $artifactDirectory -Force
    ($report | ConvertTo-Json -Depth 10) | Set-Content -LiteralPath $reportPath -Encoding utf8
    Write-Output ("Installer validation report: " + $reportPath)
    Write-Output ($report | ConvertTo-Json -Depth 10)
}

$startedAt = Get-Date
$installerHash = $null
$installedExecutable = $null
$installedExecutableHash = $null
$installedVersion = $null
$manifestPath = Join-Path $frontendRoot "dist\resource-manifest.json"
$manifestHash = $null
$installerExitCode = $null
$applicationExitCode = $null
$applicationStarted = $false

try {
    if (-not (Test-Path -LiteralPath $installerPath)) { throw "Installer not found: $installerPath" }
    $installerHash = (Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash
    if (Test-Path -LiteralPath $manifestPath) { $manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash }
    else { $failures.Add("The production resource manifest is missing: $manifestPath") }

    $null = New-Item -ItemType Directory -Path $installRoot -Force
    $networkBefore = Get-NetworkEnvironment
    $installerProcess = Start-Process -FilePath $installerPath -ArgumentList @("/S", "/D=$installRoot") -PassThru
    $installerDeadline = (Get-Date).AddMinutes(2)
    while (-not $installerProcess.HasExited -and (Get-Date) -lt $installerDeadline) {
        $installerProcess.Refresh()
        $installerConnections = @(Get-ObservedConnections (Get-ProcessTreeIds $installerProcess.Id) "installer")
        if ($installerConnections.Count -gt 0) { $networkObservations.AddRange([object[]]$installerConnections) }
        Start-Sleep -Milliseconds 250
    }
    if (-not $installerProcess.HasExited) {
        $failures.Add("The installer did not exit within two minutes.")
        Stop-ProcessTree $installerProcess.Id
    } else {
        $installerProcess.Refresh()
        $installerExitCode = $installerProcess.ExitCode
        if ($installerExitCode -ne 0) { $failures.Add("The installer exited with code $installerExitCode.") }
    }

    $installedExecutables = @(Get-ChildItem -LiteralPath $installRoot -Filter "*.exe" -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notin @("uninstall.exe", "unins000.exe") })
    if ($installedExecutables.Count -ne 1) {
        $failures.Add("Expected exactly one installed application executable, found $($installedExecutables.Count).")
    } else {
        $installedExecutable = $installedExecutables[0]
        $installedExecutableHash = (Get-FileHash -LiteralPath $installedExecutable.FullName -Algorithm SHA256).Hash
        $installedVersion = $installedExecutable.VersionInfo.ProductVersion
        if ($installedExecutable.Length -le 0) { $failures.Add("Installed application executable is empty.") }
    }

    if ($null -ne $installedExecutable) {
        $applicationProcess = Start-Process -FilePath $installedExecutable.FullName -WorkingDirectory $installRoot -WindowStyle Hidden -PassThru
        $applicationStarted = $true
        for ($sample = 0; $sample -lt 32; $sample++) {
            $applicationProcess.Refresh()
            $processIds = Get-ProcessTreeIds $applicationProcess.Id
            $connections = @(Get-ObservedConnections $processIds "application-startup")
            if ($connections.Count -gt 0) { $networkObservations.AddRange([object[]]$connections) }
            $startupObservations.Add([ordered]@{
                sample = $sample
                processIds = $processIds
                processCount = $processIds.Count
                processExited = $applicationProcess.HasExited
                observedAt = (Get-Date).ToString("o")
            })
            if ($applicationProcess.HasExited -and $sample -ge 4) { break }
            Start-Sleep -Milliseconds 250
        }
        $applicationProcess.Refresh()
        if ($applicationProcess.HasExited) { $applicationExitCode = $applicationProcess.ExitCode }
        else { Stop-ProcessTree $applicationProcess.Id }
    }

    $externalConnections = @($networkObservations | Where-Object { $_.remoteAddress -notin @("127.0.0.1", "::1", "0.0.0.0", "::") })
    if ($externalConnections.Count -gt 0) { $failures.Add("The installer or application established non-loopback connections.") }
    $networkAfter = Get-NetworkEnvironment
    $runtimeObservation = @(Get-WebView2RuntimeObservation)
    if (-not $applicationStarted) { $failures.Add("The installed application was not started.") }

    $cleanOfflineEvidence = $env:AIRBENCH_CLEAN_OFFLINE_IMAGE -eq "1"
    $status = if ($failures.Count -gt 0) { "failed" } elseif ($cleanOfflineEvidence) { "passed" } else { "host_smoke_passed_clean_image_required" }
    $report = [ordered]@{
        validation = "FE-VAL-1 offline Tauri installer and startup"
        status = $status
        runId = $runId
        startedAt = $startedAt.ToString("o")
        finishedAt = (Get-Date).ToString("o")
        cleanOfflineImageEvidence = $cleanOfflineEvidence
        installer = (Resolve-Path -LiteralPath $installerPath).Path
        installerSha256 = $installerHash
        installerExitCode = $installerExitCode
        installRoot = $installRoot
        installedExecutable = if ($null -ne $installedExecutable) { $installedExecutable.FullName } else { $null }
        installedExecutableSha256 = $installedExecutableHash
        installedExecutableBytes = if ($null -ne $installedExecutable) { $installedExecutable.Length } else { 0 }
        installedProductVersion = $installedVersion
        applicationStarted = $applicationStarted
        applicationExitCode = $applicationExitCode
        resourceManifest = if (Test-Path -LiteralPath $manifestPath) { $manifestPath } else { $null }
        resourceManifestSha256 = $manifestHash
        webView2Runtime = $runtimeObservation
        networkBefore = $networkBefore
        networkAfter = $networkAfter
        startupProcessSamples = @($startupObservations)
        observedEstablishedConnections = @($networkObservations | Sort-Object phase, processId, remoteAddress, remotePort, observedAt -Unique)
        externalEstablishedConnections = @($externalConnections)
        failures = @($failures)
        limitation = if ($cleanOfflineEvidence) { "Clean offline image evidence was explicitly declared by AIRBENCH_CLEAN_OFFLINE_IMAGE=1." } else { "This host smoke run does not prove installation on a clean Windows image with adapters, DNS, and proxy disabled. Set AIRBENCH_CLEAN_OFFLINE_IMAGE=1 only inside that controlled environment." }
    }
    Write-ValidationReport $report
    if ($RequireCleanOfflineImage -and -not $cleanOfflineEvidence) { exit 3 }
    if ($failures.Count -gt 0) { exit 2 }
} catch {
    $failures.Add($_.Exception.Message)
    $report = [ordered]@{
        validation = "FE-VAL-1 offline Tauri installer and startup"
        status = "failed"
        runId = $runId
        startedAt = $startedAt.ToString("o")
        finishedAt = (Get-Date).ToString("o")
        failures = @($failures)
        observedEstablishedConnections = @($networkObservations)
    }
    Write-ValidationReport $report
    exit 2
} finally {
    if ($null -ne $applicationProcess -and -not $applicationProcess.HasExited) { Stop-ProcessTree $applicationProcess.Id }
    if ($null -ne $installerProcess -and -not $installerProcess.HasExited) { Stop-ProcessTree $installerProcess.Id }
}
