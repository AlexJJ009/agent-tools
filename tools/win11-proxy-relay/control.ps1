#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('Menu','Start','Stop','Restart','Status','Doctor','Dashboard')]
    [string]$Action = 'Menu'
)
$ErrorActionPreference = 'Stop'
$settingsPath = Join-Path $PSScriptRoot 'settings.json'
if (-not (Test-Path $settingsPath)) { throw 'Run install.ps1 first; settings.json is missing.' }
. (Join-Path $PSScriptRoot 'runtime\settings.ps1')
$s = Get-ProxyRelaySettings -SettingsPath $settingsPath
$raw = Get-Content $settingsPath -Raw | ConvertFrom-Json
$names = @('FeituServerProxy','PhaiReverseProxyTunnel','ProxyQualityManager')
if ($raw.startup_mode -eq 'Logon') { $names += 'AiProxyFailover' }
if ($Action -eq 'Menu') {
    Write-Host 'Proxy Relay: 1 Status | 2 Start | 3 Stop | 4 Restart | 5 Doctor | 6 Dashboard'
    $choice = Read-Host 'Choose'
    $Action = switch ($choice) { '1' {'Status'} '2' {'Start'} '3' {'Stop'} '4' {'Restart'} '5' {'Doctor'} '6' {'Dashboard'} default {'Status'} }
}
if ($Action -in @('Start','Stop','Restart')) {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if ($raw.startup_mode -eq 'Boot' -and -not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        $child = Start-Process "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"{0}"' -f $PSCommandPath),'-Action',$Action)
        exit $child.ExitCode
    }
    if ($Action -in @('Stop','Restart')) {
        $reverse = @($names); [array]::Reverse($reverse)
        foreach ($name in $reverse) { Stop-ScheduledTask -TaskName $name }
        Start-Sleep -Seconds 3
    }
    if ($Action -in @('Start','Restart')) {
        foreach ($name in $names) { Start-ScheduledTask -TaskName $name }
        Start-Sleep -Seconds 3
    }
    $Action = 'Status'
}
if ($Action -eq 'Status') {
    Write-Host "Startup mode: $($raw.startup_mode). Running does not imply HTTPS is healthy; use Doctor."
    foreach ($name in $names) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            [pscustomobject]@{Task=$name; State=$task.State; Account=$task.Principal.UserId; Trigger=($task.Triggers.CimClass.CimClassName -join ',')} | Format-List
        } else { Write-Host "MISSING: $name" }
    }
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in @($s.LocalProxyPort,$s.ControllerPort) } | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table
    exit 0
}
if ($Action -eq 'Doctor') {
    Write-Host 'Laptop HTTPS payload checks (no retries):'
    & $raw.python_exe (Join-Path $PSScriptRoot 'runtime\probe.py') --proxy "http://127.0.0.1:$($s.LocalProxyPort)"
    $localCode = $LASTEXITCODE
    Write-Host 'PHAI reverse tunnel HTTPS payload checks (requires python3 on server):'
    $sshArgs = @('-F',$s.SshConfig,'-o','BatchMode=yes','-o','RequestTTY=no','-o','ConnectTimeout=10','-T',$s.SshHost,"python3 - --proxy http://127.0.0.1:$($s.RemoteProxyPort)")
    Get-Content (Join-Path $PSScriptRoot 'runtime\probe.py') -Raw | & "$env:WINDIR\System32\OpenSSH\ssh.exe" @sshArgs
    $remoteCode = $LASTEXITCODE
    if ($localCode -ne 0 -or $remoteCode -ne 0) { exit 1 }
    exit 0
}
if ($Action -eq 'Dashboard') {
    Start-Process (Join-Path $PSScriptRoot 'runtime\v2rayn-dashboard.html')
}
