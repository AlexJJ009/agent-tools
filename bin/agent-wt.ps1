$ErrorActionPreference = "Stop"

$repoCore = Join-Path (Split-Path -Parent $PSScriptRoot) "skills/manage-worktrees/scripts/agent_wt.py"
$installedCore = $null
if ($env:USERPROFILE) {
  $installedCore = Join-Path $env:USERPROFILE ".agents/skills/manage-worktrees/scripts/agent_wt.py"
}

if ($installedCore -and (Test-Path -LiteralPath $installedCore)) {
  $core = $installedCore
} elseif (Test-Path -LiteralPath $repoCore) {
  $core = $repoCore
} else {
  throw "agent-wt Python core was not found in the installed Skill or repository"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
  & $python.Source $core @args
  exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
  & $py.Source -3 $core @args
  exit $LASTEXITCODE
}

throw "Python 3 was not found on PATH (checked python and py launchers)"
