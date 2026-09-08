param(
  [string]$UserHome = $env:USERPROFILE,
  [string]$StatePath,
  [string]$LogDir = "C:\AppsExternal\automation\_diagnostics\codex-app-lag-20260702",
  [switch]$NoStopProcesses,
  [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

if (-not $StatePath) {
  $StatePath = Join-Path $UserHome ".codex\.codex-global-state.json"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$logPath = Join-Path $LogDir "restart-codex-manual-remote.log"

function Write-Log {
  param([string]$Message)
  $line = "$(Get-Date -Format o) $Message"
  Add-Content -Encoding UTF8 -Path $logPath -Value $line
}

function Get-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($python) {
    return @($python.Source)
  }

  $py = Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($py) {
    return @($py.Source, "-3")
  }

  throw "Python was not found on PATH; cannot safely edit Codex global state JSON."
}

function Invoke-PythonStdin {
  param([Parameter(Mandatory = $true)][string]$Code)

  $cmd = @(Get-PythonCommand)
  $exe = $cmd[0]
  $args = @()
  if ($cmd.Count -gt 1) {
    $args += $cmd[1..($cmd.Count - 1)]
  }
  $args += "-"

  $Code | & $exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "python state update failed with exit code $LASTEXITCODE"
  }
}

function Find-CodexLaunchPath {
  $codexProcess = Get-Process -Name Codex -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*OpenAI.Codex_*" -or $_.Path -like "*OpenAI\CodexDesktopPatched*" } |
    Select-Object -First 1

  if ($codexProcess -and $codexProcess.Path) {
    return $codexProcess.Path
  }

  $patched = Join-Path $env:LOCALAPPDATA "OpenAI\CodexDesktopPatched\app\Codex.exe"
  if (Test-Path -LiteralPath $patched) {
    return $patched
  }

  $candidate = Get-ChildItem "C:\Program Files\WindowsApps" -Filter "OpenAI.Codex_*_x64__2p2nqsd0c76g0" -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
  if ($candidate) {
    return (Join-Path $candidate.FullName "app\Codex.exe")
  }

  return $null
}

function Get-CodexRelatedProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -in @("Codex.exe", "codex.exe", "node_repl.exe") -or
      ($_.Name -eq "ssh.exe" -and $_.CommandLine -match "codex app-server proxy|command -v codex")
    }
}

function Get-CodexRemoteProxyProcesses {
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -eq "ssh.exe" -and $_.CommandLine -match "codex app-server proxy|command -v codex"
    }
}

function Stop-CodexTree {
  for ($attempt = 1; $attempt -le 10; $attempt++) {
    $targets = @(Get-CodexRelatedProcesses)
    foreach ($target in $targets) {
      Write-Log "stopping $($target.Name) pid=$($target.ProcessId) ppid=$($target.ParentProcessId)"
      Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Milliseconds 700
    $remaining = @(Get-CodexRelatedProcesses)
    if ($remaining.Count -eq 0) {
      Write-Log "all Codex-related processes stopped after attempt $attempt"
      return
    }
    Write-Log "still waiting for Codex processes after attempt $attempt count=$($remaining.Count)"
  }
}

function Stop-CodexRemoteProxyProcesses {
  for ($attempt = 1; $attempt -le 5; $attempt++) {
    $targets = @(Get-CodexRemoteProxyProcesses)
    foreach ($target in $targets) {
      Write-Log "stopping Codex remote proxy $($target.Name) pid=$($target.ProcessId) ppid=$($target.ParentProcessId)"
      Stop-Process -Id $target.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Milliseconds 700
    $remaining = @(Get-CodexRemoteProxyProcesses)
    if ($remaining.Count -eq 0) {
      Write-Log "all Codex remote proxy processes stopped after attempt $attempt"
      return
    }
    Write-Log "still waiting for Codex remote proxy processes after attempt $attempt count=$($remaining.Count)"
  }
}

function Disable-RemoteAutoConnect {
  if (-not (Test-Path -LiteralPath $StatePath)) {
    Write-Log "state file not found: $StatePath"
    return
  }

  $backupPath = "$StatePath.bak-disable-remote-autoconnect-$(Get-Date -Format yyyyMMdd-HHmmss)"
  Copy-Item -LiteralPath $StatePath -Destination $backupPath -Force
  Write-Log "backed up global state to $backupPath"

  $env:CODEX_GLOBAL_STATE_PATH = $StatePath
  $env:CODEX_GLOBAL_STATE_LOG_PATH = $logPath
  Invoke-PythonStdin @'
import json, os, pathlib

state_path = pathlib.Path(os.environ["CODEX_GLOBAL_STATE_PATH"])
log_path = pathlib.Path(os.environ["CODEX_GLOBAL_STATE_LOG_PATH"])

def log(message):
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")

raw = state_path.read_text(encoding="utf-8-sig")
state = json.loads(raw)

auto_key = "remote-connection-auto-connect-by-host-id"
selected_key = "selected-remote-host-id"

auto = state.get(auto_key)
if not isinstance(auto, dict):
    auto = {}
    state[auto_key] = auto

for host_id in sorted(auto):
    auto[host_id] = False
    log(f"python set manual connect: {host_id}=false")

if selected_key in state:
    state[selected_key] = None
    log("python cleared selected-remote-host-id")

state_path.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

verify = json.loads(state_path.read_text(encoding="utf-8-sig"))
bad = {k: v for k, v in (verify.get(auto_key) or {}).items() if v is not False}
if bad:
    raise SystemExit(f"auto-connect values still not false: {bad}")
log(f"python verified global state: all remote auto-connect values are false; selected={verify.get(selected_key)!r}")
'@

  Write-Log "saved global state with remote auto-connect disabled"
}

function Write-PostRestartState {
  if (-not (Test-Path -LiteralPath $StatePath)) {
    return
  }

  $env:CODEX_GLOBAL_STATE_PATH = $StatePath
  $env:CODEX_GLOBAL_STATE_LOG_PATH = $logPath
  Invoke-PythonStdin @'
import json, os, pathlib

state_path = pathlib.Path(os.environ["CODEX_GLOBAL_STATE_PATH"])
log_path = pathlib.Path(os.environ["CODEX_GLOBAL_STATE_LOG_PATH"])
state = json.loads(state_path.read_text(encoding="utf-8-sig"))
auto = state.get("remote-connection-auto-connect-by-host-id") or {}

with log_path.open("a", encoding="utf-8") as f:
    for host_id, value in sorted(auto.items()):
        f.write(f"post-restart setting: {host_id}={value}\n")
    f.write(f"post-restart selected-remote-host-id={state.get('selected-remote-host-id')!r}\n")
'@
}

function Assert-RemoteAutoConnectDisabled {
  if (-not (Test-Path -LiteralPath $StatePath)) {
    throw "state file not found: $StatePath"
  }

  $env:CODEX_GLOBAL_STATE_PATH = $StatePath
  $env:CODEX_GLOBAL_STATE_LOG_PATH = $logPath
  Invoke-PythonStdin @'
import json, os, pathlib

state_path = pathlib.Path(os.environ["CODEX_GLOBAL_STATE_PATH"])
log_path = pathlib.Path(os.environ["CODEX_GLOBAL_STATE_LOG_PATH"])
state = json.loads(state_path.read_text(encoding="utf-8-sig"))
auto = state.get("remote-connection-auto-connect-by-host-id") or {}
bad = {k: v for k, v in auto.items() if v is not False}
selected = state.get("selected-remote-host-id")

with log_path.open("a", encoding="utf-8") as f:
    f.write(f"assert remote auto-connect disabled: bad={bad} selected={selected!r}\n")

if bad:
    raise SystemExit(f"remote auto-connect values still enabled: {bad}")
'@
}

Write-Log "starting Codex manual remote-connect script"
Write-Log "state path: $StatePath"

$codexPath = Find-CodexLaunchPath
Write-Log "Codex launch path: $codexPath"

if (-not $NoStopProcesses) {
  Start-Sleep -Seconds 3
  Stop-CodexTree
  Start-Sleep -Seconds 2
} else {
  Write-Log "process stop skipped by -NoStopProcesses"
}

Disable-RemoteAutoConnect
Assert-RemoteAutoConnectDisabled

if (-not $NoRestart) {
  if ($codexPath -and (Test-Path -LiteralPath $codexPath)) {
    Start-Process -FilePath $codexPath
    Write-Log "restarted Codex App"
  } else {
    Write-Log "could not restart Codex App because launch path was missing"
  }

  Start-Sleep -Seconds 10
  # Codex Desktop may rewrite .codex-global-state.json while booting. Apply the
  # manual-connect preference again after startup and verify the final state.
  Disable-RemoteAutoConnect
  Stop-CodexRemoteProxyProcesses
  Assert-RemoteAutoConnectDisabled
  Write-PostRestartState
} else {
  Write-Log "restart skipped by -NoRestart"
}

Write-Log "script finished"
