param(
  [Parameter(Mandatory = $true)][string]$BackupDirectory,
  [switch]$ConfirmEmptyTarget,
  [string]$ComposeFile = "docker-compose.prod.yml",
  [string]$EnvFile = ".env.production",
  [string]$ProjectName = ""
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmEmptyTarget) {
  throw "Restore is blocked. Pass -ConfirmEmptyTarget only after creating an empty target database and backend_storage volume."
}
if (-not (Test-Path -LiteralPath $ComposeFile -PathType Leaf)) { throw "Compose file does not exist: $ComposeFile" }

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

$resolvedBackup = [System.IO.Path]::GetFullPath($BackupDirectory)
$manifestPath = Join-Path $resolvedBackup "manifest.json"
$manifestChecksumPath = Join-Path $resolvedBackup "manifest.sha256"
$databasePath = Join-Path $resolvedBackup "database.dump"
$storagePath = Join-Path $resolvedBackup "backend-storage.tar.gz"
foreach ($path in @($manifestPath, $manifestChecksumPath, $databasePath, $storagePath)) {
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Backup bundle is incomplete: missing $path" }
}

$manifestChecksumParts = ((Get-Content -Raw -LiteralPath $manifestChecksumPath).Trim() -split '\s+')
if ($manifestChecksumParts.Count -lt 2 -or $manifestChecksumParts[1] -ne "manifest.json") {
  throw "Invalid manifest.sha256 format"
}
$actualManifestHash = Get-Sha256 $manifestPath
if ($actualManifestHash -ne $manifestChecksumParts[0].ToLowerInvariant()) {
  throw "Checksum mismatch for manifest.json"
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.format_version -ne 1) { throw "Unsupported backup manifest format" }
foreach ($name in @("database.dump", "backend-storage.tar.gz")) {
  $artifact = @($manifest.artifacts | Where-Object { $_.name -eq $name }) | Select-Object -First 1
  if ($null -eq $artifact) { throw "Manifest does not describe $name" }
  $path = Join-Path $resolvedBackup $name
  $hash = Get-Sha256 $path
  if ($hash -ne $artifact.sha256 -or (Get-Item -LiteralPath $path).Length -ne [int64]$artifact.size_bytes) {
    throw "Checksum or size mismatch for $name"
  }
}

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

$postgresIdOutput = & docker @composeArgs ps -q postgres
$postgresPsExitCode = $LASTEXITCODE
$postgresIdRaw = @($postgresIdOutput) | Select-Object -First 1
$postgresId = if ($null -eq $postgresIdRaw) { "" } else { ([string]$postgresIdRaw).Trim() }
if ($postgresPsExitCode -ne 0 -or -not $postgresId) { throw "Target postgres service is not running. Start only the clean postgres target first." }
$postgresRunningOutput = & docker inspect -f '{{.State.Running}}' $postgresId
$postgresRunningExitCode = $LASTEXITCODE
$postgresRunningRaw = @($postgresRunningOutput) | Select-Object -First 1
$postgresRunning = if ($null -eq $postgresRunningRaw) { "" } else { ([string]$postgresRunningRaw).Trim() }
if ($postgresRunningExitCode -ne 0 -or $postgresRunning -ne "true") { throw "Target postgres service is not running. Start only the clean postgres target first." }

$postgresSettings = Get-PostgresSettings
$emptyDatabaseCheckSql = 'SELECT/**/count(*)/**/FROM/**/pg_catalog.pg_tables/**/WHERE/**/schemaname=$$public$$;'
$tableCountOutput = Invoke-Compose exec -T postgres psql "--username=$($postgresSettings.User)" "--dbname=$($postgresSettings.Database)" --tuples-only --no-align "--command=$emptyDatabaseCheckSql"
$tableCountRaw = @($tableCountOutput) | Select-Object -First 1
$tableCount = if ($null -eq $tableCountRaw) { "" } else { ([string]$tableCountRaw).Trim() }
if ($tableCount -ne "0") { throw "Refusing restore: target database contains $tableCount public tables and is not empty." }

$helperContainerId = $null
$backendWasRunning = $false
try {
  $backendIdOutput = & docker @composeArgs ps -q backend
  $backendPsExitCode = $LASTEXITCODE
  $backendIdRaw = @($backendIdOutput) | Select-Object -First 1
  $backendId = if ($null -eq $backendIdRaw) { "" } else { ([string]$backendIdRaw).Trim() }
  if ($backendPsExitCode -ne 0) { throw "docker compose ps failed with exit code $backendPsExitCode" }
  if ($backendId) {
    $backendRunningOutput = & docker inspect -f '{{.State.Running}}' $backendId
    $backendRunningExitCode = $LASTEXITCODE
    $backendRunningRaw = @($backendRunningOutput) | Select-Object -First 1
    $backendRunning = if ($null -eq $backendRunningRaw) { "" } else { ([string]$backendRunningRaw).Trim() }
    if ($backendRunningExitCode -ne 0) { throw "docker inspect failed with exit code $backendRunningExitCode" }
    if ($backendRunning -eq "true") {
      $backendWasRunning = $true
      Write-Output "Stopping backend before restore..."
      Invoke-Compose stop backend
    }
  }

  $helperContainerIdOutput = & docker @composeArgs run -d --no-deps --entrypoint sh backend -c "sleep 300"
  $helperContainerExitCode = $LASTEXITCODE
  $helperContainerIdRaw = @($helperContainerIdOutput) | Select-Object -First 1
  $helperContainerId = if ($null -eq $helperContainerIdRaw) { "" } else { ([string]$helperContainerIdRaw).Trim() }
  if ($helperContainerExitCode -ne 0 -or -not $helperContainerId) { throw "Could not start temporary restore helper container" }
  $storageEntriesOutput = & docker exec $helperContainerId find /app/storage_data -mindepth 1 -print -quit
  $storageEntriesExitCode = $LASTEXITCODE
  if ($storageEntriesExitCode -ne 0 -or @($storageEntriesOutput).Count -ne 0) { throw "Refusing restore: target backend_storage is not empty." }

  Invoke-Docker cp $storagePath "${helperContainerId}:/tmp/backend-storage.tar.gz"
  Invoke-Docker exec $helperContainerId tar -tzf /tmp/backend-storage.tar.gz

  Write-Output "Restoring persistent backend storage..."
  Invoke-Docker exec $helperContainerId tar -C /app/storage_data --numeric-owner -xzf /tmp/backend-storage.tar.gz

  Write-Output "Restoring PostgreSQL database..."
  Invoke-Compose cp $databasePath "postgres:/tmp/database.dump"
  Invoke-Compose exec -T postgres pg_restore "--username=$($postgresSettings.User)" "--dbname=$($postgresSettings.Database)" --clean --if-exists --no-owner --exit-on-error /tmp/database.dump
  Invoke-Compose exec -T postgres rm -f -- /tmp/database.dump
  Write-Output "Restore completed. Start backend only after the target storage and database checks have both succeeded."
}
finally {
  if ($helperContainerId) { & docker rm -f $helperContainerId | Out-Null }
  if ($backendWasRunning) {
    try { Invoke-Compose up --detach backend | Out-Null }
    catch { Write-Warning "Restore completed but backend restart failed; start it manually. $($_.Exception.Message)" }
  }
}
