#Requires -Version 5.1

<#
.SYNOPSIS
  Supervise the Windows v2rayN local proxy reverse SSH tunnel to phai-lgx-dev.

.DESCRIPTION
  Default chain after activation:
    phai-lgx-dev 127.0.0.1:17890 -> Windows 127.0.0.1:17897

  The script does not change SSH config. It only launches ssh.exe with explicit
  per-process options and restarts with bounded backoff when ssh exits.
#>

[CmdletBinding()]
param(
    [string]$SettingsPath = '',
    [string]$SshHost = '',
    [int]$RemotePort = 0,
    [int]$LocalPort = 0,
    [string]$LocalHost = '127.0.0.1',
    [string]$RemoteBind = '127.0.0.1',
    [string]$SshExe = "$env:WINDIR\System32\OpenSSH\ssh.exe",
    [string]$SshConfig = '',
    [string]$IdentityFile = '',
    [string]$UserKnownHostsFile = '',
    [string]$LogFile = '',
    [int]$MaxLogBytes = 1048576,
    [int]$MaxBackoffSeconds = 60,
    [int]$HealthyResetSeconds = 60
)

$ErrorActionPreference = 'Continue'
$ScriptRoot = if ($PSScriptRoot) { $PSScriptRoot }
              elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
              else { (Get-Location).Path }
if (Test-Path -LiteralPath (Join-Path $ScriptRoot 'settings.ps1')) {
    . (Join-Path $ScriptRoot 'settings.ps1')
    $settings = Get-ProxyRelaySettings -SettingsPath $SettingsPath
    if (-not $SshHost) { $SshHost = $settings.SshHost }
    if ($RemotePort -le 0) { $RemotePort = $settings.RemoteProxyPort }
    if ($LocalPort -le 0) { $LocalPort = $settings.LocalProxyPort }
    if (-not $SshConfig) { $SshConfig = $settings.SshConfig }
    if (-not $IdentityFile) { $IdentityFile = $settings.SshIdentityFile }
    if (-not $UserKnownHostsFile) { $UserKnownHostsFile = $settings.SshKnownHosts }
    if (-not $LogFile) {
        New-Item -ItemType Directory -Force -Path $settings.StateDir | Out-Null
        $LogFile = Join-Path $settings.StateDir 'phai-reverse-proxy.log'
    }
}
if (-not $SshHost) { $SshHost = 'phai-lgx-dev' }
if ($RemotePort -le 0) { $RemotePort = 17890 }
if ($LocalPort -le 0) { $LocalPort = 17897 }
if (-not $LogFile) {
    $LogFile = Join-Path $ScriptRoot 'phai-reverse-proxy.log'
}
. (Join-Path $ScriptRoot 'enter-supervised-job.ps1') -Name 'PhaiReverseProxyTunnel'
$ErrorActionPreference = 'Continue'

function Rotate-Log {
    if (-not (Test-Path $LogFile)) { return }
    try {
        $item = Get-Item -LiteralPath $LogFile -ErrorAction Stop
        if ($item.Length -lt $MaxLogBytes) { return }
        $old = "$LogFile.1"
        if (Test-Path $old) { Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue }
        Move-Item -LiteralPath $LogFile -Destination $old -Force -ErrorAction Stop
    } catch {}
}

function Log {
    param([string]$Message)
    Rotate-Log
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    try { $line | Out-File -FilePath $LogFile -Append -Encoding utf8 } catch {}
}

function Test-LocalPort {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($LocalHost, $LocalPort, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(1500, $false)
        if ($ok) { $client.EndConnect($iar) }
        $client.Close()
        return $ok
    } catch {
        return $false
    }
}

$mutexName = 'Global\PhaiReverseProxyTunnel.Mutex'
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$hasMutex = $false
try {
    $hasMutex = $mutex.WaitOne(0, $false)
} catch {
    $mutexName = 'Local\PhaiReverseProxyTunnel.Mutex'
    $mutex = New-Object System.Threading.Mutex($false, $mutexName)
    $hasMutex = $mutex.WaitOne(0, $false)
}
if (-not $hasMutex) {
    Log "another supervisor instance is already running; exiting"
    exit 0
}

if (-not (Test-Path -LiteralPath $SshExe)) {
    Log "fatal: ssh.exe not found at $SshExe"
    exit 127
}

Log "supervisor started pid=$PID host=$SshHost remote=$RemoteBind`:$RemotePort local=$LocalHost`:$LocalPort"
$backoff = 3

while ($true) {
    if (-not (Test-LocalPort)) {
        Log "local target $LocalHost`:$LocalPort is not accepting TCP; retrying in ${backoff}s"
        Start-Sleep -Seconds $backoff
        $backoff = [Math]::Min([Math]::Max($backoff * 2, 3), $MaxBackoffSeconds)
        continue
    }

    $remoteForward = "$RemoteBind`:$RemotePort`:$LocalHost`:$LocalPort"
    $args = @(
        '-N',
        '-T',
        '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'ConnectTimeout=15',
        '-o', 'ConnectionAttempts=3',
        '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=6',
        '-o', 'TCPKeepAlive=yes',
        '-o', 'IPQoS=none'
    )
    if ($SshConfig) { $args += @('-F', $SshConfig) }
    if ($IdentityFile) { $args += @('-o', "IdentityFile=$IdentityFile") }
    if ($UserKnownHostsFile) { $args += @('-o', "UserKnownHostsFile=$UserKnownHostsFile") }
    $args += @('-R', $remoteForward, $SshHost)

    Log "starting ssh remote-forward $remoteForward via $SshHost"
    $startedAt = Get-Date
    & $SshExe @args 2>&1 | ForEach-Object { Log "ssh: $_" }
    $code = $LASTEXITCODE
    $duration = [int]((Get-Date) - $startedAt).TotalSeconds
    Log "ssh exited code=$code; restarting in ${backoff}s"
    Start-Sleep -Seconds $backoff
    if ($duration -ge $HealthyResetSeconds) {
        $backoff = 3
    } else {
        $backoff = [Math]::Min([Math]::Max($backoff * 2, 3), $MaxBackoffSeconds)
    }
}
