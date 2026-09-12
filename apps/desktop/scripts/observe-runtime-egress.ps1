[CmdletBinding()]
param(
  # Path to write the JSON observation report.
  [Parameter(Mandatory = $true)]
  [string]$ReportPath,

  # Process IDs to monitor. All descendants are included automatically.
  # If empty, observations record an empty process tree.
  [int[]]$MonitorPids = @(),

  # How often to sample, in milliseconds. Default is 2000 ms.
  [int]$IntervalMs = 2000,

  # Maximum run time in seconds before the observer exits on its own.
  # The caller is expected to kill this process when the run ends; this
  # is a safety ceiling only.
  [int]$MaxRuntimeSeconds = 600
)

$ErrorActionPreference = "Stop"

# Loopback and unrouted addresses that are never external egress.
$loopback = [Collections.Generic.HashSet[string]]::new(
  [string[]]@("127.0.0.1", "::1", "0.0.0.0", "::", "")
)

function Get-DescendantPids([int[]]$roots) {
  $snapshot = @(Get-CimInstance Win32_Process -Property ProcessId, ParentProcessId `
    -ErrorAction SilentlyContinue)
  $ids = [Collections.Generic.HashSet[int]]::new()
  foreach ($root in $roots) { $null = $ids.Add($root) }
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($process in $snapshot) {
      $ppid = [int]$process.ParentProcessId
      if ($ids.Contains($ppid) -and $ids.Add([int]$process.ProcessId)) {
        $changed = $true
      }
    }
  }
  return @($ids)
}

$observations = [Collections.Generic.List[object]]::new()
$externalConnections = [Collections.Generic.List[object]]::new()
$startedAt = Get-Date
$sampleIndex = 0

try {
  while ($true) {
    $elapsed = (Get-Date) - $startedAt
    if ($elapsed.TotalSeconds -ge $MaxRuntimeSeconds) { break }

    $allPids = if ($MonitorPids.Count -gt 0) {
      @(Get-DescendantPids $MonitorPids)
    } else { @() }

    $connections = @()
    if ($allPids.Count -gt 0) {
      $connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue `
        | Where-Object { $allPids -contains $_.OwningProcess } `
        | ForEach-Object {
          [ordered]@{
            local_address  = $_.LocalAddress
            local_port     = $_.LocalPort
            remote_address = $_.RemoteAddress
            remote_port    = $_.RemotePort
            owning_process = $_.OwningProcess
          }
        })
    }

    $external = @($connections | Where-Object { -not $loopback.Contains($_.remote_address) })
    foreach ($conn in $external) {
      $conn["observed_at"] = (Get-Date -Format "o")
      $conn["sample"] = $sampleIndex
      $externalConnections.Add($conn)
    }

    $observations.Add([ordered]@{
      sample              = $sampleIndex
      elapsed_seconds     = [math]::Round($elapsed.TotalSeconds, 2)
      monitored_pids      = $allPids
      established_count   = $connections.Count
      external_count      = $external.Count
    })

    $sampleIndex++
    Start-Sleep -Milliseconds $IntervalMs
  }
} catch {
  # Observer must not crash the parent run; write what we have.
  $observations.Add([ordered]@{
    sample        = $sampleIndex
    observer_error = $_.Exception.Message
  })
} finally {
  $status = if ($externalConnections.Count -eq 0) {
    "no_external_connections_observed"
  } else {
    "external_connections_observed"
  }

  $report = [ordered]@{
    status                    = $status
    started_at                = $startedAt.ToString("o")
    ended_at                  = (Get-Date -Format "o")
    total_samples             = $sampleIndex
    monitored_root_pids       = $MonitorPids
    external_connections      = @($externalConnections)
    external_connection_count = $externalConnections.Count
    observations              = @($observations)
    limitation                = (
      "Observer watches established TCP connections for the monitored process tree. " +
      "UDP, ICMP, and connections completed before the observer started are not captured. " +
      "A clean host firewall or independent network monitor is required for full no-egress acceptance."
    )
  }

  $encoded = $report | ConvertTo-Json -Depth 8 -Compress:$false
  [IO.File]::WriteAllText(
    $ReportPath,
    $encoded,
    [Text.UTF8Encoding]::new($false)
  )
}
