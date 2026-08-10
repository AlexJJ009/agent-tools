param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")),
  [string]$Distro = "Ubuntu",
  [int]$IntervalMinutes = 30,
  [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$taskName = "Codex Patch Safety Monitor"
if ($Uninstall) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task: $taskName"
  exit 0
}

$guard = Join-Path $RepoRoot "skills\codex-win11-patch-safety\scripts\codex_state_guard.py"
if (-not (Test-Path $guard)) { throw "Guard script not found: $guard" }
$wslGuard = (& wsl.exe -d $Distro -- wslpath -a $guard).Trim()
$windowsHome = $env:USERPROFILE
$wslHome = (& wsl.exe -d $Distro -- wslpath -a $windowsHome).Trim()
$reportDir = Join-Path $env:LOCALAPPDATA "OpenAI\CodexPatchGuard"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$wslReportDir = (& wsl.exe -d $Distro -- wslpath -a $reportDir).Trim()
$patchedRoot = Join-Path $env:USERPROFILE "Downloads\Report\CodexPatched"
$wslPatchedRoot = (& wsl.exe -d $Distro -- wslpath -a $patchedRoot).Trim()
$checkpointRoot = Join-Path $env:USERPROFILE ".codex\_codexpatched_backups\scheduled-critical"
$wslCheckpointRoot = (& wsl.exe -d $Distro -- wslpath -a $checkpointRoot).Trim()

$command = @"
set -eu
python3 '$wslGuard' detect --patched-root '$wslPatchedRoot' > '$wslReportDir/update-status.json.tmp'
mv '$wslReportDir/update-status.json.tmp' '$wslReportDir/update-status.json'
python3 '$wslGuard' config-health --user-home '$wslHome' > '$wslReportDir/config-health.json.tmp' || true
mv '$wslReportDir/config-health.json.tmp' '$wslReportDir/config-health.json'
python3 '$wslGuard' audit-cc-switch --user-home '$wslHome' > '$wslReportDir/cc-switch-audit.json.tmp' || true
mv '$wslReportDir/cc-switch-audit.json.tmp' '$wslReportDir/cc-switch-audit.json'
python3 '$wslGuard' checkpoint --user-home '$wslHome' --backup-root '$wslCheckpointRoot' > '$wslReportDir/checkpoint-status.json.tmp'
mv '$wslReportDir/checkpoint-status.json.tmp' '$wslReportDir/checkpoint-status.json'
"@
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($command))
$argument = "-d $Distro -- bash -lc `"echo $encoded | base64 -d | bash`""
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument $argument
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
  -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "Read-only Codex App update, config dependency, and cc-switch safety audit. Never patches or deletes profiles." `
  -Force | Out-Null
Write-Host "Installed scheduled task: $taskName"
Write-Host "Reports: $reportDir"
