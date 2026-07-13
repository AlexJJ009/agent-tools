param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$UserHome = $env:USERPROFILE,
  [switch]$NoGoalPlan,
  [switch]$NoCodexManualRemoteConnect,
  [string]$ManualRemoteConnectScript = "C:\AppsExternal\automation\_diagnostics\restart-codex-manual-remote.ps1"
)

$ErrorActionPreference = "Stop"

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
        Write-Host "Backed up existing goal-plan target: $backup"
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
        Write-Host "Backed up existing goal-plan target: $backup"
      }
    }
    Copy-Item -LiteralPath $Source -Destination $Target
    Set-Content -LiteralPath $marker -Value "managed by agent-tools install-win11.ps1"
  }
}

function Install-PersonalMarketplace {
  param([Parameter(Mandatory = $true)][string]$TargetHome)

  $marketplace = Join-Path $TargetHome ".agents\plugins\marketplace.json"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $marketplace) | Out-Null

  $plugins = @()
  if (Test-Path -LiteralPath $marketplace) {
    try {
      $raw = Get-Content -LiteralPath $marketplace -Raw
      if ($raw.Trim()) {
        $existing = $raw | ConvertFrom-Json
        if ($existing.plugins) {
          foreach ($plugin in @($existing.plugins)) {
            if ($plugin.name -ne "goal-plan") {
              $plugins += $plugin
            }
          }
        }
      }
    } catch {
      Copy-Item -LiteralPath $marketplace -Destination "$marketplace.invalid-backup" -Force
    }
  }

  $plugins += [ordered]@{
    name = "goal-plan"
    source = [ordered]@{
      source = "local"
      path = ".\plugins\goal-plan"
    }
    policy = [ordered]@{
      installation = "AVAILABLE"
      authentication = "ON_INSTALL"
    }
    category = "Developer Tools"
  }

  $data = [ordered]@{
    name = "personal"
    interface = [ordered]@{ displayName = "Personal" }
    plugins = $plugins
  }

  $data | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $marketplace -Encoding UTF8
}

function Install-GoalPlan {
  param(
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [Parameter(Mandatory = $true)][string]$TargetHome
  )

  $sourceRoot = Join-Path $RepoRoot "goal_plan"
  if (-not (Test-Path -LiteralPath $sourceRoot)) {
    throw "goal-plan tools not installed: missing $sourceRoot"
  }

  Copy-Managed (Join-Path $sourceRoot "claude\skills\goal-plan") (Join-Path $TargetHome ".claude\skills\goal-plan")
  Copy-Managed (Join-Path $sourceRoot "claude\commands\goal-plan.md") (Join-Path $TargetHome ".claude\commands\goal-plan.md")
  Copy-Managed (Join-Path $sourceRoot "claude\agents\goal-plan-reviewer.md") (Join-Path $TargetHome ".claude\agents\goal-plan-reviewer.md")

  Copy-Managed (Join-Path $sourceRoot "codex\skills\goal-plan") (Join-Path $TargetHome ".codex\skills\goal-plan")
  Copy-Managed (Join-Path $sourceRoot "codex\plugins\goal-plan") (Join-Path $TargetHome "plugins\goal-plan")
  Copy-Managed (Join-Path $sourceRoot "codex\plugins\goal-plan") (Join-Path $TargetHome ".codex\plugins\cache\personal\goal-plan\0.2.0")
  Copy-Managed (Join-Path $sourceRoot "codex\plugins\goal-plan\commands\goal-plan.md") (Join-Path $TargetHome ".codex\prompts\goal-plan.md")
  Install-PersonalMarketplace -TargetHome $TargetHome

  $uv = Get-Command uv -ErrorAction SilentlyContinue
  if (-not $uv) {
    throw "goal-plan runtime requires uv on PATH; install uv and rerun install-win11.ps1"
  }
  $runtimeSource = Join-Path $sourceRoot "runtime"
  $runtimeHome = Join-Path $TargetHome ".local\share\goal-plan\runtime"
  $runtimeBin = Join-Path $TargetHome ".local\bin"
  New-Item -ItemType Directory -Force -Path $runtimeHome, $runtimeBin | Out-Null
  & $uv.Source venv --clear --python 3.12 (Join-Path $runtimeHome ".venv") | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "failed to create goal-plan uv environment" }
  & $uv.Source pip install --python (Join-Path $runtimeHome ".venv\Scripts\python.exe") $runtimeSource | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "failed to install goal-plan runtime" }
  $launcher = @"
@echo off
"$runtimeHome\.venv\Scripts\goal-plan-runtime.exe" %*
"@
  Set-Content -LiteralPath (Join-Path $runtimeBin "goal-plan-runtime.cmd") -Value $launcher -Encoding ASCII

  Write-Host "goal-plan installed for Win11 user: $TargetHome"
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

if (-not $NoGoalPlan) {
  Install-GoalPlan -RepoRoot $Root -TargetHome $UserHome
} else {
  Write-Host "goal-plan tools not installed (-NoGoalPlan)."
}

if (-not $NoCodexManualRemoteConnect) {
  Install-CodexManualRemoteConnect -RepoRoot $Root -TargetHome $UserHome -TargetScript $ManualRemoteConnectScript
} else {
  Write-Host "Codex manual remote-connect helper not installed (-NoCodexManualRemoteConnect)."
}
