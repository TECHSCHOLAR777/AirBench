$ErrorActionPreference = "Stop"

$executable = Join-Path $PSScriptRoot "..\src-tauri\target\release\airbench-desktop.exe"
$executable = [IO.Path]::GetFullPath($executable)
if (-not (Test-Path -LiteralPath $executable)) { throw "Release executable not found. Run npm run tauri:build first." }

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

$runId = "AirBenchRuntimeEgress-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N")
$artifactDir = Join-Path $PSScriptRoot "..\artifacts"
$null = New-Item -ItemType Directory -Path $artifactDir -Force
$reportPath = Join-Path $artifactDir "$runId.json"
$process = Start-Process -FilePath $executable -WindowStyle Hidden -PassThru
$observations = [Collections.Generic.List[object]]::new()
try {
  for ($sample = 0; $sample -lt 20; $sample++) {
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
} finally {
  $finalSnapshot = @(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name,ExecutablePath -ErrorAction SilentlyContinue)
  $finalProcesses = @(Get-DescendantProcesses $process.Id $finalSnapshot)
  foreach ($descendant in $finalProcesses | Sort-Object { $_.ProcessId -eq $process.Id }) {
    Stop-Process -Id ([int]$descendant.ProcessId) -Force -ErrorAction SilentlyContinue
  }
}

$allConnections = @($observations | ForEach-Object established_connections)
$externalConnections = @($allConnections | Where-Object { $_.remote_address -notin @("127.0.0.1", "::1", "0.0.0.0", "::") })
$report = [ordered]@{
  status = if ($externalConnections.Count -eq 0) { "passed" } else { "failed" }
  executable = $executable
  run_id = $runId
  samples = $observations
  external_established_connections = $externalConnections
  limitation = "Startup-only host evidence. Node transport allowlisting and external navigation attempts require the packaged WebDriver scenario."
}
[IO.File]::WriteAllText($reportPath, ($report | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
Write-Output ($report | ConvertTo-Json -Depth 8)
if ($externalConnections.Count -gt 0) { exit 2 }
