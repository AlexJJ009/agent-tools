#Requires -Version 5.1
[CmdletBinding()]
param(
    [string]$SettingsPath = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'settings.ps1')
$settings = Get-ProxyRelaySettings -SettingsPath $SettingsPath
$core = $settings.CoreExe
$config = Join-Path $settings.StateDir 'server-config.json'
$log = Join-Path $settings.StateDir 'server-supervisor.log'
$listen = '127.0.0.1:{0}' -f $settings.LocalProxyPort
New-Item -ItemType Directory -Force -Path $settings.StateDir | Out-Null
Set-Location $PSScriptRoot
. (Join-Path $PSScriptRoot 'enter-supervised-job.ps1') -Name 'FeituServerProxy'
function Write-Log([string]$Message) {
    if ((Test-Path $log) -and (Get-Item $log).Length -gt 1048576) {
        Move-Item $log "$log.1" -Force
    }
    Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) $Message"
}
$delay = 3
while ($true) {
    $started = Get-Date
    Write-Log "Starting dedicated server proxy on $listen"
    # Native stderr is log data; Windows PowerShell must not treat it as a fatal exception.
    $ErrorActionPreference = 'Continue'
    & $core run -c $config 2>&1 | ForEach-Object { Write-Log "$_" }
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if (((Get-Date) - $started).TotalSeconds -ge 60) { $delay = 3 }
    Write-Log "Core exited $code; retry in $delay seconds"
    Start-Sleep -Seconds $delay
    $delay = [Math]::Min(60, $delay * 2)
}
