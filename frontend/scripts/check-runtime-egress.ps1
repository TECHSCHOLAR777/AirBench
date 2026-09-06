[CmdletBinding()]
param(
  [switch]$EnforceFirewall,
  [switch]$RequireFirewall,
  [int]$Samples = 20
)

$ErrorActionPreference = "Stop"

$executable = Join-Path $PSScriptRoot "..\src-tauri\target\release\airbench-desktop.exe"
$executable = [IO.Path]::GetFullPath($executable)
if (-not (Test-Path -LiteralPath $executable)) { throw "Release executable not found. Run npm run tauri:build first." }
if ($Samples -lt 5 -or $Samples -gt 120) { throw "Samples must be between 5 and 120." }

function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-DescendantProcesses([int]$rootPid, [array]$snapshot) {
  $ids = [Collections.Generic.HashSet[int]]::new()
  $null = $ids.Add($rootPid)
  $processes = @{}
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($process in $snapshot) {
      if ($process.ParentProcessId -and $ids.Contains([int]$process.ParentProcessId) -and $ids.Add([int]$process.ProcessId)) {
        $processes[[int]$process.ProcessId] = $process
        $changed = $true
      }
    }
  }
  $root = $snapshot | Where-Object { [int]$_.ProcessId -eq $rootPid } | Select-Object -First 1
  if ($root) { $processes[$rootPid] = $root }
  return @($processes.Values)
}

function Get-WebView2Executables {
  $roots = @()
  if ($env:ProgramFiles) { $roots += Join-Path $env:ProgramFiles "Microsoft\EdgeWebView\Application" }
  if (${env:ProgramFiles(x86)}) { $roots += Join-Path ${env:ProgramFiles(x86)} "Microsoft\EdgeWebView\Application" }
  $paths = foreach ($root in $roots) {
    if (Test-Path -LiteralPath $root) {
      Get-ChildItem -LiteralPath $root -Filter "msedgewebview2.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
    }
  }
  return @($paths | Sort-Object -Unique)
}

function Get-ProfileSnapshot {
  @(Get-NetFirewallProfile -ErrorAction Stop | Select-Object Name, LogBlocked, LogFileName, LogMaxSizeKilobytes)
}

$runId = "AirBenchRuntimeEgress-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N")
$artifactDir = Join-Path $PSScriptRoot "..\artifacts"
$null = New-Item -ItemType Directory -Path $artifactDir -Force
$reportPath = Join-Path $artifactDir "$runId.json"
$firewallLog = Join-Path $artifactDir "$runId-firewall.log"
$observations = [Collections.Generic.List[object]]::new()
$firewallRuleNames = [Collections.Generic.List[string]]::new()
$previousFirewallProfiles = @()
$firewallState = "not_requested"
$firewallPaths = @(Get-WebView2Executables)
$firewallBlockedLines = @()
$process = $null
$failure = $null

if ($EnforceFirewall) {
  if (-not (Test-IsAdministrator)) {
    $firewallState = "blocked_not_administrator"
    $failure = "Firewall enforcement requires an elevated PowerShell session."
  } elseif ($firewallPaths.Count -eq 0) {
    $firewallState = "blocked_runtime_not_found"
    $failure = "No installed WebView2 runtime executable was found to scope the outbound deny rule."
  } else {
    try {
      $previousFirewallProfiles = @(Get-ProfileSnapshot)
      $profileNames = @($previousFirewallProfiles | ForEach-Object Name)
      Set-NetFirewallProfile -Name $profileNames -LogBlocked True -LogFileName $firewallLog -LogMaxSizeKilobytes 32768
      $pathIndex = 0
      foreach ($path in $firewallPaths) {
        $ruleName = "AirBench Validation WebView2 $runId $pathIndex"
        New-NetFirewallRule -DisplayName $ruleName -Direction Outbound -Action Block -Program $path -Profile Any -Description "Temporary AirBench FE-VAL-5 WebView2 deny rule." | Out-Null
        $firewallRuleNames.Add($ruleName)
        $pathIndex++
      }
      $firewallState = "enforced"
    } catch {
      $firewallState = "enforcement_failed"
      $failure = "Could not install the temporary WebView2 firewall policy: $($_.Exception.Message)"
    }
  }
}

if ($RequireFirewall -and $firewallState -ne "enforced") {
  $report = [ordered]@{
    status = "blocked"
    run_id = $runId
    executable = $executable
    firewall_state = $firewallState
    firewall_paths = $firewallPaths
    error = $failure
    limitation = "Run from an elevated host validation session before treating no-egress evidence as a release gate."
  }
  [IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
  Write-Output ($report | ConvertTo-Json -Depth 8)
  exit 3
}

try {
  if ($failure) { throw $failure }
  $process = Start-Process -FilePath $executable -WindowStyle Hidden -PassThru
  for ($sample = 0; $sample -lt $Samples; $sample++) {
    $snapshot = @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,ExecutablePath -ErrorAction SilentlyContinue)
    $processes = @(Get-DescendantProcesses $process.Id $snapshot)
    $pids = @($processes | ForEach-Object { [int]$_.ProcessId })
    $processIndex = @{}
    foreach ($descendant in $processes) { $processIndex[[int]$descendant.ProcessId] = $descendant }
    $connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Where-Object { $pids -contains $_.OwningProcess } | ForEach-Object {
      $owner = $processIndex[[int]$_.OwningProcess]
      [ordered]@{
        local_address = $_.LocalAddress
        local_port = $_.LocalPort
        remote_address = $_.RemoteAddress
        remote_port = $_.RemotePort
        state = $_.State
        owning_process = $_.OwningProcess
        process_name = $owner.Name
        executable_path = $owner.ExecutablePath
      }
    })
    $observations.Add([ordered]@{
      sample = $sample
      process_ids = $pids
      processes = @($processes | ForEach-Object {
        [ordered]@{ process_id = $_.ProcessId; parent_process_id = $_.ParentProcessId; name = $_.Name; executable_path = $_.ExecutablePath }
      })
      established_connections = $connections
    })
    Start-Sleep -Milliseconds 250
    if ($process.HasExited -and $sample -gt 4) { break }
  }
} catch {
  $failure = $_.Exception.Message
} finally {
  if ($process) {
    $finalSnapshot = @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,ExecutablePath -ErrorAction SilentlyContinue)
    $finalProcesses = @(Get-DescendantProcesses $process.Id $finalSnapshot)
    foreach ($descendant in $finalProcesses | Sort-Object { $_.ProcessId -eq $process.Id }) {
      Stop-Process -Id ([int]$descendant.ProcessId) -Force -ErrorAction SilentlyContinue
    }
  }
  if ($firewallState -eq "enforced") {
    try {
      foreach ($ruleName in $firewallRuleNames) { Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue }
      foreach ($profile in $previousFirewallProfiles) {
        Set-NetFirewallProfile -Name $profile.Name -LogBlocked $profile.LogBlocked -LogFileName $profile.LogFileName -LogMaxSizeKilobytes $profile.LogMaxSizeKilobytes
      }
    } catch {
      if (-not $failure) { $failure = "The temporary firewall policy could not be fully restored: $($_.Exception.Message)" }
    }
  }
  if (Test-Path -LiteralPath $firewallLog) {
    $firewallBlockedLines = @(Get-Content -LiteralPath $firewallLog -ErrorAction SilentlyContinue | Where-Object { $_ -match " DROP " } | Select-Object -Last 200)
  }
}

$allConnections = @($observations | ForEach-Object established_connections)
$externalConnections = @($allConnections | Where-Object { $_.remote_address -notin @("127.0.0.1", "::1", "0.0.0.0", "::") })
$status = if ($failure) { "failed" } elseif ($firewallState -eq "enforced" -and $externalConnections.Count -eq 0) { "passed_with_host_firewall" } elseif ($externalConnections.Count -eq 0) { "host_smoke_passed_clean_image_required" } else { "failed" }
$report = [ordered]@{
  status = $status
  executable = $executable
  run_id = $runId
  firewall_state = $firewallState
  firewall_paths = $firewallPaths
  firewall_log = if (Test-Path -LiteralPath $firewallLog) { $firewallLog } else { $null }
  firewall_blocked_line_count = $firewallBlockedLines.Count
  firewall_blocked_lines = $firewallBlockedLines
  samples = $observations
  external_established_connections = $externalConnections
  error = $failure
  limitation = "Startup-only host evidence. Clean offline image, approved Node allowlist, and full WebDriver navigation/resource attempts remain separate gates."
}
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Write-Output ($report | ConvertTo-Json -Depth 8)
if ($status -eq "failed") { exit 2 }
if ($status -eq "blocked") { exit 3 }
