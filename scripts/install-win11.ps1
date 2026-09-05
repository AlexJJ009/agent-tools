param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath,
  [string]$UserHome = $env:USERPROFILE,
  [string]$CodexHome = (Join-Path $env:USERPROFILE ".codex"),
  [string]$CcSwitchDb = (Join-Path $env:USERPROFILE ".cc-switch\cc-switch.db"),
  [switch]$NoCodexManualRemoteConnect,
  [string]$ManualRemoteConnectScript = "C:\AppsExternal\automation\_diagnostics\restart-codex-manual-remote.ps1",
  [switch]$NoCodexConfig,
  [switch]$NoCodexSqliteLogGuard,
  [switch]$DisableCodexSqliteLogGuard,
  [switch]$CodexSqliteLogGuardVacuum,
  [switch]$NoCodexProviderBucketMigration,
  [switch]$DryRunCodexProviderBucketMigration,
  [switch]$AllowRunningCodexProviderBucketMigration,
  [switch]$NoKillRunningCodexProviderBucketMigration
)

$ErrorActionPreference = "Stop"

function Get-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return $python.Source
  }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return $py.Source
  }

  throw "Python was not found on PATH. Install Python or run from a shell where python is available."
}

function Invoke-AgentToolsPython {
  param(
    [Parameter(Mandatory = $true)][string]$Script,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ScriptArgs
  )

  if (-not (Test-Path -LiteralPath $Script)) {
    throw "missing Python helper: $Script"
  }
  $resolvedScript = (Resolve-Path -LiteralPath $Script).ProviderPath

  $python = Get-PythonCommand
  if ((Split-Path -Leaf $python) -ieq "py.exe") {
    & $python -3 $resolvedScript @ScriptArgs
  } else {
    & $python $resolvedScript @ScriptArgs
  }
  if ($LASTEXITCODE -ne 0) {
    throw "Python helper failed ($LASTEXITCODE): $resolvedScript"
  }
}

function Assert-CodexTargetGuard {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetCodexHome,
    [Parameter(Mandatory = $true)][string]$TargetCcSwitchDb
  )

  $script = Join-Path $RepoRoot "scripts\codex_target_guard.py"
  Invoke-AgentToolsPython $script `
    --platform win11 `
    --codex-home $TargetCodexHome `
    --cc-switch-db $TargetCcSwitchDb `
    --expected-user $env:USERNAME `
    --path-only `
    --allow-missing-config `
    --allow-missing-cc-switch `
    --skip-cc-switch-read-check
}

function Copy-Managed {
  param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target
  )

  if (-not (Test-Path -LiteralPath $Source)) {
    throw "missing source for copy: $Source"
  }

  $parent = Split-Path -Parent $Target
  New-Item -ItemType Directory -Force -Path $parent | Out-Null

  if ((Get-Item -LiteralPath $Source).PSIsContainer) {
    $marker = Join-Path $Target ".agent-tools-managed"
    if (Test-Path -LiteralPath $Target) {
      if (Test-Path -LiteralPath $marker) {
        Remove-Item -LiteralPath $Target -Recurse -Force
      } else {
        $backup = "$Target.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Move-Item -LiteralPath $Target -Destination $backup
        Write-Host "Backed up existing managed target: $backup"
      }
    }
    Copy-Item -LiteralPath $Source -Destination $Target -Recurse
    Set-Content -LiteralPath (Join-Path $Target ".agent-tools-managed") -Value "managed by agent-tools install-win11.ps1"
  } else {
    $marker = "$Target.agent-tools-managed"
    if (Test-Path -LiteralPath $Target) {
      if (Test-Path -LiteralPath $marker) {
        Remove-Item -LiteralPath $Target -Force
        Remove-Item -LiteralPath $marker -Force
      } else {
        $backup = "$Target.backup-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Move-Item -LiteralPath $Target -Destination $backup
        Write-Host "Backed up existing managed target: $backup"
      }
    }
    Copy-Item -LiteralPath $Source -Destination $Target
    Set-Content -LiteralPath $marker -Value "managed by agent-tools install-win11.ps1"
  }
}

function Install-CodexPatchSafetySkill {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetHome
  )

  $source = Join-Path $RepoRoot "skills\codex-win11-patch-safety"
  if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md"))) {
    throw "Codex patch safety skill missing: $source"
  }
  Copy-Managed $source (Join-Path $TargetHome ".codex\skills\codex-win11-patch-safety")
  Write-Host "Installed Codex Win11 patch safety skill."
}

function Install-CodexManualRemoteConnect {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetHome,
    [Parameter(Mandatory = $true)][string]$TargetScript
  )

  $source = Join-Path $RepoRoot "scripts\restart-codex-manual-remote.ps1"
  if (-not (Test-Path -LiteralPath $source)) {
    throw "Codex manual remote-connect script missing: $source"
  }

  Copy-Managed $source $TargetScript

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $TargetScript `
    -UserHome $TargetHome `
    -NoStopProcesses `
    -NoRestart
  if ($LASTEXITCODE -ne 0) {
    throw "Codex manual remote-connect state install failed with exit code $LASTEXITCODE"
  }

  Write-Host "Codex remote auto-connect disabled for Win11 user: $TargetHome"
  Write-Host "Codex manual remote-connect helper installed: $TargetScript"
}

function Install-CodexWin11SubscriptionConfig {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetCodexHome,
    [Parameter(Mandatory = $true)][string]$TargetCcSwitchDb
  )

  $script = Join-Path $RepoRoot "scripts\configure_codex_win11_subscription.py"
  Invoke-AgentToolsPython $script `
    --codex-home $TargetCodexHome `
    --cc-switch-db $TargetCcSwitchDb
}

function Install-CodexSqliteLogGuard {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetCodexHome
  )

  $script = Join-Path $RepoRoot "scripts\configure_codex_sqlite_log_guard.py"
  $mode = "enable"
  if ($DisableCodexSqliteLogGuard) {
    $mode = "disable"
  }

  $args = @("--mode", $mode, "--codex-home", $TargetCodexHome)
  if ($CodexSqliteLogGuardVacuum) {
    $args += "--vacuum"
  }
  Invoke-AgentToolsPython $script @args
}

function Invoke-CodexProviderBucketMigration {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetCodexHome,
    [Parameter(Mandatory = $true)][string]$TargetCcSwitchDb
  )

  $script = Join-Path $RepoRoot "migrate_codex_provider_bucket.py"
  $args = @(
    "--target", "custom",
    "--codex-dir", $TargetCodexHome,
    "--cc-switch-db", $TargetCcSwitchDb,
    "--all-non-target-providers",
    "--repair-resume-index",
    "--skip-cc-switch"
  )

  if (-not $DryRunCodexProviderBucketMigration) {
    $args += @("--apply", "--yes")
    if ($AllowRunningCodexProviderBucketMigration) {
      $args += "--allow-running-codex"
    } elseif (-not $NoKillRunningCodexProviderBucketMigration) {
      $args += "--kill-running-codex"
    }
  }

  Invoke-AgentToolsPython $script @args
}

Assert-CodexTargetGuard -RepoRoot $Root -TargetCodexHome $CodexHome -TargetCcSwitchDb $CcSwitchDb

Install-CodexPatchSafetySkill -RepoRoot $Root -TargetHome $UserHome

if (-not $NoCodexManualRemoteConnect) {
  Install-CodexManualRemoteConnect -RepoRoot $Root -TargetHome $UserHome -TargetScript $ManualRemoteConnectScript
} else {
  Write-Host "Codex manual remote-connect helper not installed (-NoCodexManualRemoteConnect)."
}

if (-not $NoCodexConfig) {
  Install-CodexWin11SubscriptionConfig -RepoRoot $Root -TargetCodexHome $CodexHome -TargetCcSwitchDb $CcSwitchDb
} else {
  Write-Host "Win11 Codex subscription config not changed (-NoCodexConfig)."
}

if (-not $NoCodexSqliteLogGuard) {
  Install-CodexSqliteLogGuard -RepoRoot $Root -TargetCodexHome $CodexHome
} else {
  Write-Host "Codex SQLite log guard not changed (-NoCodexSqliteLogGuard)."
}

if (-not $NoCodexProviderBucketMigration) {
  Invoke-CodexProviderBucketMigration -RepoRoot $Root -TargetCodexHome $CodexHome -TargetCcSwitchDb $CcSwitchDb
} else {
  Write-Host "Codex provider bucket migration not run (-NoCodexProviderBucketMigration)."
}
