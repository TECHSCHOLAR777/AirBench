$ErrorActionPreference = "Stop"

$validationRoot = Split-Path -Parent $PSScriptRoot
$tauriRoot = Join-Path $validationRoot "src-tauri"
$repoRoot = Split-Path -Parent $validationRoot
$runRoot = Join-Path ([IO.Path]::GetTempPath()) ("AirBenchPythonNodeValidation-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N"))
$null = New-Item -ItemType Directory -Path $runRoot -Force
# Use a disposable Cargo target so real Python Node validation cannot reuse
# generated Tauri permissions or absolute dependency paths from the old
# frontend/src-tauri location after the repository refactor.
$env:CARGO_TARGET_DIR = Join-Path $runRoot "cargo-target"
$python = (Get-Command python).Source
$cargo = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
if (-not (Test-Path -LiteralPath $cargo)) { throw "Rust cargo was not found at the expected installation path." }

function Get-FreePort {
  $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
  $listener.Start()
  $port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
  $listener.Stop()
  return $port
}

function Wait-Port([int]$port, [Diagnostics.Process]$process) {
  for ($attempt = 0; $attempt -lt 100; $attempt++) {
    if ($process.HasExited) { throw "The Python Node exited before port $port became ready." }
    $client = [Net.Sockets.TcpClient]::new()
    try {
      $client.Connect("127.0.0.1", $port)
      $client.Dispose()
      return
    } catch {
      $client.Dispose()
      Start-Sleep -Milliseconds 100
    }
  }
  throw "The Python Node port $port did not become ready."
}

function Write-Json([string]$path, [hashtable]$value) {
  [IO.File]::WriteAllText($path, ($value | ConvertTo-Json -Depth 12), [Text.UTF8Encoding]::new($false))
}

function Invoke-Probe([string]$profilePath, [string[]]$arguments) {
  $output = & $cargo run --quiet --manifest-path (Join-Path $tauriRoot "Cargo.toml") --example node_transport_probe -- $profilePath @arguments 2>&1
  $code = $LASTEXITCODE
  $line = ($output | Where-Object { $_ -match '^\s*\{' } | Select-Object -Last 1)
  $payload = if ($line) { $line | ConvertFrom-Json } else { [pscustomobject]@{ error = ($output -join " ") } }
  return [pscustomobject]@{ code = $code; payload = $payload }
}

$port = Get-FreePort
$serverLog = Join-Path $runRoot "python-node.stderr.log"
$serverScript = Join-Path $PSScriptRoot "python_node_server.py"
$server = $null
$credentialSet = $false
try {
  $serverArguments = '"{0}" --port {1} --token python-node-token --node-identity python-node-validation --subject validation-user' -f $serverScript, $port
  $server = Start-Process -FilePath $python -ArgumentList $serverArguments -WindowStyle Hidden -RedirectStandardOutput ([IO.Path]::ChangeExtension($serverLog, ".stdout.log")) -RedirectStandardError $serverLog -PassThru
  Wait-Port $port $server

  "python-node-token" | & $cargo run --quiet --manifest-path (Join-Path $tauriRoot "Cargo.toml") --example credential_store -- set-stdin validation-user | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Could not seed the OS credential store." }
  $credentialSet = $true

  $profilePath = Join-Path $runRoot "python-node-profile.json"
  Write-Json $profilePath ([ordered]@{
    profile_id = "python-node-profile"
    endpoint = "http://127.0.0.1:$port"
    transport = "loopback"
    node_identity = "python-node-validation"
    protocol_version = "0.1"
    clearance_context = "restricted"
    certificate_pin_sha256 = $null
    trusted_ca_pem = $null
    credential_ref = "validation-user"
    approved_by_policy = $true
  })

  $createPath = Join-Path $runRoot "create.json"
  Write-Json $createPath ([ordered]@{
    schema_version = "1.0"
    compatibility_id = "airbench-core-contracts"
    command_id = "command.create.live"
    task_id = $null
    actor = "validation-user"
    expected_sequence = $null
    idempotency_key = "idempotency.create.live"
    client_version = "0.1"
    command_type = "task.create"
    arguments = [ordered]@{
      principal_id = "validation-user"
      clearance = "internal"
      request = "Validate the real Python Node boundary"
      domain_pack_ref = "validation-pack.v0"
      risk_class = "low"
      autonomy_ceiling = "review_required"
      allowed_evidence_scope = @("validation")
      permitted_worker_capabilities = @("reasoning")
      permitted_tools = @()
      output_contract = "text"
      verification_criteria = @("ledger-reference")
      resource_budget = @{ max_concurrency = 1; max_steps = 2 }
    }
  })

  $handshake = Invoke-Probe $profilePath @()
  if ($handshake.code -ne 0 -or $handshake.payload.protocol_compatibility_id -ne "airbench-node-protocol") { throw "The Rust transport did not accept the real Python Node handshake." }

  $created = Invoke-Probe $profilePath @("create", $createPath)
  if ($created.code -ne 0 -or $created.payload.command.outcome -ne "accepted") { throw "The Rust transport could not create a task through the Python Node." }
  $taskId = [string]$created.payload.snapshot.taskId
  if ([string]::IsNullOrWhiteSpace($taskId) -or $created.payload.snapshot.compatibilityId -ne "airbench-node-protocol") { throw "The Python Node create response did not contain the typed snapshot envelope." }

  $snapshot = Invoke-Probe $profilePath @("snapshot", $taskId)
  if ($snapshot.code -ne 0 -or $snapshot.payload.taskId -ne $taskId -or $snapshot.payload.compatibilityId -ne "airbench-node-protocol") { throw "The Rust transport could not re-fetch the Python Node snapshot." }

  $plan = Invoke-Probe $profilePath @("plan", $taskId)
  if ($plan.code -ne 0 -or $plan.payload.task_id -ne $taskId -or $plan.payload.plan_state -ne "not_ready" -or $plan.payload.task_sequence -ne $snapshot.payload.asOfSequence -or $plan.payload.execution_mode -ne "not_selected" -or $plan.payload.failure_code -ne "plan_not_ready" -or [string]::IsNullOrWhiteSpace($plan.payload.failure_reason) -or $plan.payload.required_verification -ne $true) {
    throw "The Python Node plan projection did not preserve the safe not-ready state: $($plan.payload | ConvertTo-Json -Compress)"
  }

  $events = Invoke-Probe $profilePath @("events", $taskId, "0")
  if ($events.code -ne 0 -or $events.payload.schema_version -ne "1.0" -or $events.payload.compatibility_id -ne "airbench-core-contracts" -or $events.payload.events.Count -lt 1) { throw "The Python Node event batch did not satisfy the typed batch contract." }
  if ($events.payload.events[0].compatibilityId -ne "airbench-node-protocol") { throw "The Python Node event did not preserve the Node wire envelope." }

  $routeTrace = Invoke-Probe $profilePath @("route-trace", $taskId)
  if ($routeTrace.code -ne 0 -or $routeTrace.payload.taskId -ne $taskId -or $routeTrace.payload.nodeIdentity -ne "python-node-validation" -or $routeTrace.payload.protocolVersion -ne "0.1" -or $routeTrace.payload.clearanceContext -ne "restricted" -or $routeTrace.payload.compatibilityId -ne "airbench-node-protocol") { throw "The Rust transport could not validate the Python Node route-trace projection." }

  $authorizePath = Join-Path $runRoot "authorize.json"
  Write-Json $authorizePath ([ordered]@{
    schema_version = "1.0"
    compatibility_id = "airbench-core-contracts"
    command_id = "command.authorize.live"
    task_id = $taskId
    actor = "validation-user"
    expected_sequence = [int]$snapshot.payload.asOfSequence
    idempotency_key = "idempotency.authorize.live"
    client_version = "0.1"
    command_type = "task.authorize"
    arguments = @{ authorization_ref = "validation-authorization" }
  })
  $authorized = Invoke-Probe $profilePath @("command", $authorizePath)
  $authorizedRetry = Invoke-Probe $profilePath @("command", $authorizePath)
  if ($authorized.code -ne 0 -or $authorizedRetry.code -ne 0 -or $authorized.payload.outcome -ne "accepted" -or $authorized.payload.ledger_event_ref -ne $authorizedRetry.payload.ledger_event_ref) { throw "The Python Node command retry did not preserve its ledger identity." }

  $eventsAfterAuthorization = Invoke-Probe $profilePath @("events", $taskId, "0")
  if ($eventsAfterAuthorization.code -ne 0 -or $eventsAfterAuthorization.payload.events.Count -lt 2) { throw "The Python Node did not expose the post-authorization event stream." }
  $replayedAuthorization = Invoke-Probe $profilePath @("events", $taskId, [string]$snapshot.payload.asOfSequence)
  if ($replayedAuthorization.code -ne 0 -or $replayedAuthorization.payload.events.Count -ne 1 -or $replayedAuthorization.payload.events[0].sequence -ne ([int]$snapshot.payload.asOfSequence + 1) -or $replayedAuthorization.payload.events[0].ledgerEventRef -ne $authorized.payload.ledger_event_ref) {
    throw "The Python Node replay did not return the authoritative post-authorization event from the prior cursor."
  }

  [ordered]@{
    status = "passed"
    node = "real Python NodeApiService"
    task_id = $taskId
    checks = @("handshake-negotiation", "create-snapshot", "plan-projection-not-ready", "event-batch", "route-trace", "command-idempotency", "ledger-reference", "event-replay")
    log = $serverLog
  } | ConvertTo-Json -Depth 8
} finally {
  if ($credentialSet) { & $cargo run --quiet --manifest-path (Join-Path $tauriRoot "Cargo.toml") --example credential_store -- delete validation-user | Out-Null }
  if ($null -ne $server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
}
