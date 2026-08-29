param(
  [string]$OutputDirectory = ".\backups",
  [string]$ComposeFile = "docker-compose.prod.yml",
  [string]$EnvFile = ".env.production",
  [string]$ProjectName = ""
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) {
  throw "Compose file does not exist: $ComposeFile"
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$composeArgs = [System.Collections.Generic.List[string]]::new()
$composeArgs.Add("compose")
if ($ProjectName) { $composeArgs.Add("--project-name"); $composeArgs.Add($ProjectName) }
if (Test-Path -LiteralPath $EnvFile -PathType Leaf) { $composeArgs.Add("--env-file"); $composeArgs.Add($EnvFile) }
$composeArgs.Add("-f"); $composeArgs.Add($ComposeFile)

function Invoke-Compose {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & docker @composeArgs @Arguments
  if ($LASTEXITCODE -ne 0) { throw "docker compose failed with exit code $LASTEXITCODE" }
}

function Invoke-Docker {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & docker @Arguments
  if ($LASTEXITCODE -ne 0) { throw "docker failed with exit code $LASTEXITCODE" }
}

function Get-Sha256 {
  param([Parameter(Mandatory = $true)][string]$Path)
  $algorithm = [System.Security.Cryptography.SHA256]::Create()
  $stream = [System.IO.File]::OpenRead($Path)
  try {
    return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
  }
  finally {
    $stream.Dispose()
    $algorithm.Dispose()
  }
}

function Get-PostgresSettings {
  $environmentOutput = & docker @composeArgs exec -T postgres env
  $environmentExitCode = $LASTEXITCODE
  if ($environmentExitCode -ne 0) { throw "Could not read PostgreSQL connection settings" }
  $postgresUserLine = @($environmentOutput | Where-Object { $_ -like "POSTGRES_USER=*" } | Select-Object -First 1)
  $postgresDatabaseLine = @($environmentOutput | Where-Object { $_ -like "POSTGRES_DB=*" } | Select-Object -First 1)
  if (-not $postgresUserLine -or -not $postgresDatabaseLine) { throw "PostgreSQL container does not expose POSTGRES_USER and POSTGRES_DB" }
  return [pscustomobject]@{
    User = ([string]$postgresUserLine).Substring("POSTGRES_USER=".Length)
    Database = ([string]$postgresDatabaseLine).Substring("POSTGRES_DB=".Length)
  }
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$bundleName = "practiceflow-backup-$stamp"
$stagingDirectory = Join-Path $resolvedOutput ".${bundleName}.incomplete"
$bundleDirectory = Join-Path $resolvedOutput $bundleName
$databaseFile = "database.dump"
$storageFile = "backend-storage.tar.gz"
$manifestFile = "manifest.json"
$databaseContainerPath = "/tmp/$databaseFile"
$helperContainerId = $null
$backendWasRunning = $false
$completed = $false

if ((Test-Path -LiteralPath $stagingDirectory) -or (Test-Path -LiteralPath $bundleDirectory)) {
  throw "Backup destination already exists: $bundleDirectory"
}
New-Item -ItemType Directory -Path $stagingDirectory | Out-Null

try {
  $backendIdOutput = & docker @composeArgs ps -q backend
  $backendPsExitCode = $LASTEXITCODE
  $backendIdRaw = @($backendIdOutput) | Select-Object -First 1
  $backendId = if ($null -eq $backendIdRaw) { "" } else { ([string]$backendIdRaw).Trim() }
  if ($backendPsExitCode -ne 0) { throw "docker compose ps failed with exit code $backendPsExitCode" }
  if ($backendId) {
    $runningOutput = & docker inspect -f '{{.State.Running}}' $backendId
    $runningExitCode = $LASTEXITCODE
    $runningRaw = @($runningOutput) | Select-Object -First 1
    $running = if ($null -eq $runningRaw) { "" } else { ([string]$runningRaw).Trim() }
    if ($runningExitCode -ne 0) { throw "docker inspect failed with exit code $runningExitCode" }
    if ($running -eq "true") {
      $backendWasRunning = $true
      Write-Output "Stopping backend briefly to create a consistent database + file-storage snapshot..."
      Invoke-Compose stop backend
    }
  }

  Write-Output "Creating PostgreSQL dump..."
  $postgresSettings = Get-PostgresSettings
  Invoke-Compose exec -T postgres pg_dump "--username=$($postgresSettings.User)" "--dbname=$($postgresSettings.Database)" --format=custom --compress=9 "--file=$databaseContainerPath"
  Invoke-Compose cp "postgres:$databaseContainerPath" (Join-Path $stagingDirectory $databaseFile)

  $databasePath = Join-Path $stagingDirectory $databaseFile
  if ((Get-Item -LiteralPath $databasePath).Length -le 0) { throw "Database backup is empty: $databasePath" }

  Write-Output "Archiving persistent backend storage..."
  $helperContainerIdOutput = & docker @composeArgs run -d --no-deps --entrypoint sh backend -c "sleep 300"
  $helperContainerExitCode = $LASTEXITCODE
  $helperContainerIdRaw = @($helperContainerIdOutput) | Select-Object -First 1
  $helperContainerId = if ($null -eq $helperContainerIdRaw) { "" } else { ([string]$helperContainerIdRaw).Trim() }
  if ($helperContainerExitCode -ne 0 -or -not $helperContainerId) { throw "Could not start temporary backup helper container" }
  Invoke-Docker exec $helperContainerId sh -eu -c "tar -C /app/storage_data --numeric-owner -czf /tmp/$storageFile ."
  Invoke-Docker cp "${helperContainerId}:/tmp/$storageFile" (Join-Path $stagingDirectory $storageFile)

  $storagePath = Join-Path $stagingDirectory $storageFile
  if ((Get-Item -LiteralPath $storagePath).Length -le 0) { throw "Storage backup is empty: $storagePath" }

  $databaseItem = Get-Item -LiteralPath $databasePath
  $storageItem = Get-Item -LiteralPath $storagePath
  $manifest = [ordered]@{
    format_version = 1
    created_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    consistency = "backend service was stopped while PostgreSQL and backend_storage artifacts were captured"
    artifacts = @(
      [ordered]@{ name = $databaseFile; sha256 = Get-Sha256 $databasePath; size_bytes = $databaseItem.Length },
      [ordered]@{ name = $storageFile; sha256 = Get-Sha256 $storagePath; size_bytes = $storageItem.Length }
    )
  }
  $manifestPath = Join-Path $stagingDirectory $manifestFile
  [System.IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 5), [System.Text.UTF8Encoding]::new($false))
  $manifestHash = Get-Sha256 $manifestPath
  [System.IO.File]::WriteAllText((Join-Path $stagingDirectory "manifest.sha256"), "$manifestHash  $manifestFile`n", [System.Text.UTF8Encoding]::new($false))

  Move-Item -LiteralPath $stagingDirectory -Destination $bundleDirectory
  $completed = $true
  Write-Output "Complete backup bundle written to $bundleDirectory"
}
finally {
  if ($helperContainerId) {
    & docker rm -f $helperContainerId | Out-Null
  }
  if ($backendWasRunning) {
    try { Invoke-Compose up --detach backend | Out-Null }
    catch { Write-Warning "Backup succeeded but backend restart failed; start it manually. $($_.Exception.Message)" }
  }
  if (-not $completed -and (Test-Path -LiteralPath $stagingDirectory)) {
    Write-Warning "Backup did not complete. Diagnostic artifacts were preserved in $stagingDirectory"
  }
}
