#Requires -Version 5.1

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$InstallRoot = '',
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$CoreExe,
    [string]$PythonExe = '',
    [string]$V2rayNDir = '',
    [string]$SshHost = 'phai-lgx-dev',
    [string]$PrivateConfig = '',
    [ValidateSet('Logon', 'Boot')]
    [string]$StartupMode = 'Logon',
    [string]$OwnerHome = $env:USERPROFILE,
    [string]$ServiceSshConfig = '',
    [string[]]$MainAiSubscriptions = @(),
    [switch]$KeepAwakeOnAC,
    [switch]$Start,
    [switch]$SkipConnectionCheck,
    [switch]$Plan
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$AllManagedTasks = @(
    'FeituServerProxy',
    'PhaiReverseProxyTunnel',
    'ProxyQualityManager',
    'AiProxyFailover'
)
$BootManagedTasks = @(
    'FeituServerProxy',
    'PhaiReverseProxyTunnel',
    'ProxyQualityManager'
)

function Get-ManagedTasksForStartupMode {
    param([string]$Mode)
    if ($Mode -eq 'Boot') { return $BootManagedTasks }
    return $AllManagedTasks
}

function Resolve-FullPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$Base = (Get-Location).Path
    )
    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $Base $Path))
}

function ConvertTo-JsonFile {
    param(
        [Parameter(Mandatory = $true)]$InputObject,
        [Parameter(Mandatory = $true)][string]$Path
    )
    [System.IO.File]::WriteAllText($Path, ($InputObject | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Test-IsAdministrator {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-CurrentUserName {
    return [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
}

function Find-Python {
    param([string]$Requested)
    if ($Requested) {
        $candidate = Resolve-FullPath $Requested
        if (-not (Test-Path -LiteralPath $candidate)) {
            throw "PythonExe was provided but not found: $candidate"
        }
        return $candidate
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:ProgramFiles 'Python313\python.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    $commands = @('python.exe', 'python3.exe', 'py.exe')
    foreach ($command in $commands) {
        $found = Get-Command $command -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $found) { continue }
        if ($command -ieq 'py.exe') {
            $out = & $found.Source -3 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { return [string]$out }
        } else {
            return $found.Source
        }
    }
    throw 'Python was not found. Provide -PythonExe, preferably Python 3.13.'
}

function Get-ScriptRoot {
    if ($PSScriptRoot) { return $PSScriptRoot }
    if ($MyInvocation.MyCommand.Path) { return Split-Path -Parent $MyInvocation.MyCommand.Path }
    return (Get-Location).Path
}

function Find-TargetGuard {
    param([string]$ScriptRoot)
    $repoGuard = Resolve-FullPath '..\..\scripts\codex_target_guard.py' -Base $ScriptRoot
    $supportGuard = Join-Path $ScriptRoot 'support\codex_target_guard.py'
    if (Test-Path -LiteralPath $repoGuard) { return $repoGuard }
    if (Test-Path -LiteralPath $supportGuard) { return $supportGuard }
    throw "codex_target_guard.py was not found at $repoGuard or $supportGuard"
}

function Invoke-TargetGuard {
    param(
        [string]$Python,
        [string]$Guard,
        [string]$TargetProfileHome
    )
    $codexHome = Join-Path $TargetProfileHome '.codex'
    $ccSwitchDb = Join-Path $TargetProfileHome '.cc-switch\cc-switch.db'
    $args = @(
        $Guard,
        '--platform', 'win11',
        '--codex-home', $codexHome,
        '--cc-switch-db', $ccSwitchDb,
        '--path-only',
        '--skip-cc-switch-read-check',
        '--allow-missing-config',
        '--allow-missing-cc-switch',
        '--json'
    )
    $output = & $Python @args
    if ($LASTEXITCODE -ne 0) {
        throw "codex_target_guard.py failed before installer state writes."
    }
    return $output
}

function Resolve-SshPathValue {
    param(
        [string]$Value,
        [string]$OwnerHome
    )
    if (-not $Value) { return '' }
    $expanded = $Value
    if ($expanded.StartsWith('~/') -or $expanded.StartsWith('~\')) {
        $expanded = Join-Path $OwnerHome $expanded.Substring(2)
    }
    if ($expanded -match '^/mnt/([A-Za-z])/(.*)$') {
        $expanded = ($Matches[1].ToUpperInvariant() + ':\' + ($Matches[2] -replace '/', '\'))
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($expanded)
    return Resolve-FullPath $expanded -Base $OwnerHome
}

function Split-SshPathCandidates {
    param([string]$Value)
    if (-not $Value) { return @() }
    return @($Value -split '\s+(?=[A-Za-z]:[\\/])' | Where-Object { $_ })
}

function Resolve-SshAlias {
    param(
        [string]$HostAlias,
        [string]$OwnerHome,
        [string]$ReadyConfig
    )
    $sshExe = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
    if (-not (Test-Path -LiteralPath $sshExe)) {
        throw "ssh.exe was not found at $sshExe"
    }
    $args = @('-G')
    if ($ReadyConfig) {
        $args += @('-F', (Resolve-FullPath $ReadyConfig))
    }
    $args += @($HostAlias)
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $lines = & $sshExe @args 2>$null
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($LASTEXITCODE -ne 0 -or -not $lines) {
        throw "ssh -G failed for host alias: $HostAlias"
    }

    $values = @{}
    foreach ($line in $lines) {
        if ($line -notmatch '^([^ ]+)\s+(.*)$') { continue }
        $key = $Matches[1].ToLowerInvariant()
        $value = $Matches[2]
        if (-not $values.ContainsKey($key)) { $values[$key] = @() }
        $values[$key] += $value
    }

    $proxyJump = if ($values.ContainsKey('proxyjump')) { [string]$values['proxyjump'][0] } else { 'none' }
    $proxyCommand = if ($values.ContainsKey('proxycommand')) { [string]$values['proxycommand'][0] } else { 'none' }
    if ($proxyJump -and $proxyJump -ne 'none') {
        throw "ssh host $HostAlias resolves ProxyJump=$proxyJump. Automatic relay installation requires a direct SSH target; jump/command transport is not supported."
    }
    if ($proxyCommand -and $proxyCommand -ne 'none') {
        throw "ssh host $HostAlias resolves ProxyCommand. Automatic relay installation requires a direct SSH target; jump/command transport is not supported."
    }

    $identityFile = ''
    if ($values.ContainsKey('identityfile')) {
        foreach ($raw in $values['identityfile']) {
            foreach ($part in (Split-SshPathCandidates ([string]$raw))) {
                $candidate = Resolve-SshPathValue $part $OwnerHome
                if (Test-Path -LiteralPath $candidate) {
                    $identityFile = $candidate
                    break
                }
            }
            if ($identityFile) { break }
        }
    }
    if (-not $identityFile) {
        throw "No existing IdentityFile from ssh -G $HostAlias was found on disk."
    }

    $knownHosts = ''
    if ($values.ContainsKey('userknownhostsfile')) {
        foreach ($raw in $values['userknownhostsfile']) {
            foreach ($part in (Split-SshPathCandidates ([string]$raw))) {
                $candidate = Resolve-SshPathValue $part $OwnerHome
                if (Test-Path -LiteralPath $candidate) {
                    $knownHosts = $candidate
                    break
                }
            }
            if ($knownHosts) { break }
        }
    }
    if (-not $knownHosts) {
        throw "No existing UserKnownHostsFile from ssh -G $HostAlias was found on disk."
    }

    [pscustomobject]@{
        SshExe = $sshExe
        HostName = [string]$values['hostname'][0]
        User = [string]$values['user'][0]
        Port = [int]$values['port'][0]
        IdentityFile = $identityFile
        KnownHosts = $knownHosts
        ProxyJump = $proxyJump
        ProxyCommand = $proxyCommand
    }
}

function Write-ServiceSshConfig {
    param(
        [string]$Path,
        [string]$HostAlias,
        $Resolved,
        [string]$KnownHostsPath
    )
    function Quote-SshConfigValue([string]$Value) {
        if ($Value -match '[\s"#]') {
            return '"' + ($Value -replace '\\', '/' -replace '"', '\"') + '"'
        }
        return ($Value -replace '\\', '/')
    }
    $lines = @(
        "Host $HostAlias",
        "    HostName $($Resolved.HostName)",
        "    User $($Resolved.User)",
        "    Port $($Resolved.Port)",
        "    IdentityFile $(Quote-SshConfigValue $Resolved.IdentityFile)",
        "    UserKnownHostsFile $(Quote-SshConfigValue $KnownHostsPath)",
        '    IdentitiesOnly yes',
        '    PreferredAuthentications publickey',
        '    BatchMode yes',
        '    StrictHostKeyChecking yes'
    )
    $lines | Set-Content -LiteralPath $Path -Encoding ASCII
}

function Copy-PrivateConfig {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$SchemaPath,
        [string]$StateDir
    )
    $json = Get-Content -LiteralPath $Source -Raw -Encoding UTF8 | ConvertFrom-Json
    $schema = [ordered]@{}
    foreach ($property in $json.PSObject.Properties) {
        $schema[$property.Name] = $property.Value.GetType().Name
    }
    ConvertTo-JsonFile $schema $SchemaPath
    if ($json.PSObject.Properties.Name -contains 'experimental' -and
        $json.experimental.PSObject.Properties.Name -contains 'cache_file') {
        $cacheFile = $json.experimental.cache_file
        if (-not ($cacheFile.PSObject.Properties.Name -contains 'enabled')) {
            $cacheFile | Add-Member -NotePropertyName enabled -NotePropertyValue $true
        }
        if ($cacheFile.PSObject.Properties.Name -contains 'path') {
            $cacheFile.path = (Join-Path $StateDir 'server-cache.db')
        } else {
            $cacheFile | Add-Member -NotePropertyName path -NotePropertyValue (Join-Path $StateDir 'server-cache.db')
        }
    }
    ConvertTo-JsonFile $json $Destination
}

function Install-DashboardNodeLabels {
    param(
        [string]$PrivateConfigPath,
        [string]$RuntimeDir,
        [string]$StateDir
    )
    if (-not $PrivateConfigPath) { return }
    $labelsSource = Join-Path (Split-Path -Parent $PrivateConfigPath) 'node-labels.json'
    if (-not (Test-Path -LiteralPath $labelsSource)) { return }
    $labels = Get-Content -LiteralPath $labelsSource -Raw -Encoding UTF8 | ConvertFrom-Json
    $json = ($labels | ConvertTo-Json -Depth 20 -Compress).Replace('<', '\u003c')
    Copy-Item -LiteralPath $labelsSource -Destination (Join-Path $StateDir 'node-labels.json') -Force
    $dashboard = Join-Path $RuntimeDir 'v2rayn-dashboard.html'
    if (-not (Test-Path -LiteralPath $dashboard)) { return }
    $html = Get-Content -LiteralPath $dashboard -Raw -Encoding UTF8
    $needle = 'let nodeLabels = {};'
    if (-not $html.Contains($needle)) {
        throw "Dashboard node-label placeholder was not found: $needle"
    }
    $html.Replace($needle, "let nodeLabels = $json;") | Set-Content -LiteralPath $dashboard -Encoding UTF8
}

function Backup-ExistingState {
    param(
        [string]$InstallRoot,
        [string]$StateDir,
        [string[]]$TaskNames
    )
    $backupRoot = Join-Path $StateDir ('backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    foreach ($path in @((Join-Path $InstallRoot 'settings.json'), (Join-Path $StateDir 'server-config.json'))) {
        if (Test-Path -LiteralPath $path) {
            Copy-Item -LiteralPath $path -Destination (Join-Path $backupRoot (Split-Path -Leaf $path)) -Force
        }
    }
    $tasksDir = Join-Path $backupRoot 'tasks'
    New-Item -ItemType Directory -Force -Path $tasksDir | Out-Null
    $taskState = @()
    foreach ($taskName in $TaskNames) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if (-not $task) { continue }
        $xmlPath = Join-Path $tasksDir ($taskName + '.xml')
        Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath $xmlPath -Encoding UTF8
        $taskState += [pscustomobject]@{
            TaskName = $taskName
            State = $task.State.ToString()
            Xml = $xmlPath
        }
    }
    ConvertTo-JsonFile $taskState (Join-Path $backupRoot 'task-state.json')
    return [pscustomobject]@{ Root = $backupRoot; TaskState = $taskState }
}

function Restore-ExistingState {
    param(
        $Backup,
        [string]$InstallRoot,
        [string]$StateDir,
        [string[]]$TaskNames,
        [bool]$RestoreTasks = $false
    )
    foreach ($name in @('settings.json', 'server-config.json')) {
        $source = Join-Path $Backup.Root $name
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $dest = if ($name -eq 'settings.json') { Join-Path $InstallRoot $name } else { Join-Path $StateDir $name }
        Copy-Item -LiteralPath $source -Destination $dest -Force
    }
    if ($RestoreTasks) {
        foreach ($taskName in $TaskNames) {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        }
        foreach ($entry in $Backup.TaskState) {
            $xml = Get-Content -LiteralPath $entry.Xml -Raw -Encoding UTF8
            Register-ScheduledTask -TaskName $entry.TaskName -Xml $xml -Force | Out-Null
            if ($entry.State -eq 'Running') {
                Start-ScheduledTask -TaskName $entry.TaskName -ErrorAction SilentlyContinue
            }
        }
    }
}

function Set-RelayAcl {
    param(
        [string]$InstallRoot,
        [string]$RuntimeDir,
        [string]$StateDir,
        [string]$Owner,
        [string]$Mode
    )
    if ($Mode -eq 'Boot') {
        Invoke-NativeChecked icacls $InstallRoot /remove:g $Owner /T /C
        Invoke-NativeChecked icacls $InstallRoot /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' "${Owner}:(OI)(CI)RX"
        Invoke-NativeChecked icacls $RuntimeDir /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' "${Owner}:(OI)(CI)RX"
        Invoke-NativeChecked icacls (Join-Path $InstallRoot 'settings.json') /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' "${Owner}:R"
        $sshConfig = Join-Path $StateDir 'ssh_config'
        if (Test-Path -LiteralPath $sshConfig) {
            Invoke-NativeChecked icacls $sshConfig /inheritance:r /grant:r 'SYSTEM:F' 'Administrators:F' "${Owner}:R"
        }
        Invoke-NativeChecked icacls $StateDir /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' "${Owner}:(OI)(CI)R"
        Invoke-NativeChecked icacls $InstallRoot /setowner Administrators /T /C
    } else {
        Invoke-NativeChecked icacls $InstallRoot /inheritance:r /grant:r 'SYSTEM:(OI)(CI)F' 'Administrators:(OI)(CI)F' "${Owner}:(OI)(CI)F"
    }
}

function Copy-DirectoryContents {
    param(
        [string]$SourceDir,
        [string]$DestinationDir
    )
    if (-not (Test-Path -LiteralPath $SourceDir)) {
        throw "Source directory was not found: $SourceDir"
    }
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $DestinationDir -Recurse -Force
    }
}

function Install-BootVendors {
    param(
        [string]$InstallRoot,
        [string]$CoreExe,
        [string]$PythonExe
    )
    $vendorRoot = Join-Path $InstallRoot 'vendor'
    $coreDestDir = Join-Path $vendorRoot 'sing-box'
    $pythonDestDir = Join-Path $vendorRoot 'python'
    New-Item -ItemType Directory -Force -Path $coreDestDir, $pythonDestDir | Out-Null
    $coreDest = Join-Path $coreDestDir (Split-Path -Leaf $CoreExe)
    Copy-Item -LiteralPath $CoreExe -Destination $coreDest -Force
    $pythonRoot = Split-Path -Parent $PythonExe
    Copy-DirectoryContents -SourceDir $pythonRoot -DestinationDir $pythonDestDir
    $pythonDest = Join-Path $pythonDestDir (Split-Path -Leaf $PythonExe)
    if (-not (Test-Path -LiteralPath $pythonDest)) {
        throw "Vendored Python executable was not found after copy: $pythonDest"
    }
    [pscustomobject]@{
        CoreExe = $coreDest
        PythonExe = $pythonDest
    }
}

function Test-SingBoxConfig {
    param(
        [string]$Core,
        [string]$Config
    )
    if (-not (Test-Path -LiteralPath $Config)) {
        throw "server-config.json is required before task replacement: $Config"
    }
    & $Core check -c $Config
    if ($LASTEXITCODE -ne 0) {
        throw "sing-box config check failed before task replacement: $Config"
    }
}

function Set-KeepAwakeOnAcPower {
    $snapshot = [ordered]@{
        captured_at = (Get-Date).ToString('o')
        active_scheme = (& powercfg /getactivescheme)
        sleep_after = (& powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE)
        hibernate_after = (& powercfg /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE)
        lid_action = (& powercfg /qh SCHEME_CURRENT SUB_BUTTONS | Select-String -Pattern 'Lid close action|Current AC Power Setting Index|Current DC Power Setting Index' -Context 0,0 | ForEach-Object { $_.Line })
    }
    powercfg /change standby-timeout-ac 0 | Out-Null
    powercfg /change hibernate-timeout-ac 0 | Out-Null
    powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0 | Out-Null
    powercfg /setactive SCHEME_CURRENT | Out-Null
    return $snapshot
}

function New-TaskActionFor {
    param(
        [string]$TaskName,
        [string]$RuntimeDir,
        [string]$SettingsPath,
        [string]$Python
    )
    $backgroundPython = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $backgroundPython)) { $backgroundPython = $Python }
    $winPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    switch ($TaskName) {
        'FeituServerProxy' {
            return New-ScheduledTaskAction -Execute $winPowerShell -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -SettingsPath "{1}"' -f (Join-Path $RuntimeDir 'run-server-proxy.ps1'), $SettingsPath)
        }
        'PhaiReverseProxyTunnel' {
            return New-ScheduledTaskAction -Execute $winPowerShell -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -SettingsPath "{1}"' -f (Join-Path $RuntimeDir 'phai-reverse-proxy.ps1'), $SettingsPath)
        }
        'ProxyQualityManager' {
            return New-ScheduledTaskAction -Execute $backgroundPython -Argument ('"{0}" --settings "{1}"' -f (Join-Path $RuntimeDir 'quality-manager.py'), $SettingsPath)
        }
        'AiProxyFailover' {
            return New-ScheduledTaskAction -Execute $backgroundPython -Argument ('"{0}" --settings "{1}"' -f (Join-Path $RuntimeDir 'ai-fallback.py'), $SettingsPath)
        }
        default {
            throw "Unknown managed task: $TaskName"
        }
    }
}

function Register-RelayTasks {
    param(
        [string[]]$TaskNames,
        [string]$StartupMode,
        [string]$RuntimeDir,
        [string]$SettingsPath,
        [string]$Python,
        [string]$Owner
    )
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
    foreach ($taskName in $TaskNames) {
        $action = New-TaskActionFor $taskName $RuntimeDir $SettingsPath $Python
        $useBoot = $StartupMode -eq 'Boot'
        if ($useBoot) {
            $trigger = New-ScheduledTaskTrigger -AtStartup
            $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        } else {
            $trigger = New-ScheduledTaskTrigger -AtLogOn -User $Owner
            $principal = New-ScheduledTaskPrincipal -UserId $Owner -LogonType Interactive -RunLevel Limited
        }
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    }
}

function Test-ServiceSshConnection {
    param(
        [string]$SshConfig,
        [string]$SshHost,
        [string]$SshExe
    )
    & $SshExe -F $SshConfig -o BatchMode=yes -o RequestTTY=no -o ConnectTimeout=15 -T $SshHost 'true'
    if ($LASTEXITCODE -ne 0) {
        throw "SSH BatchMode check failed with generated config: $SshConfig"
    }
}

function Install-ControlFiles {
    param([string]$ScriptRoot, [string]$InstallRoot)
    foreach ($name in @('control.ps1', 'relay.cmd')) {
        $source = Join-Path $ScriptRoot $name
        if (-not (Test-Path -LiteralPath $source)) { throw "Required control entry point missing: $name" }
        Copy-Item -LiteralPath $source -Destination (Join-Path $InstallRoot $name) -Force
    }
}

if (-not $InstallRoot) {
    $InstallRoot = if ($StartupMode -eq 'Boot') { Join-Path $env:ProgramFiles 'Win11ProxyRelay' } else { Join-Path $env:LOCALAPPDATA 'Win11ProxyRelay' }
}
$scriptRoot = Get-ScriptRoot
$runtimeSource = Join-Path $scriptRoot 'runtime'
$installRootFull = Resolve-FullPath $InstallRoot
$runtimeDest = Join-Path $installRootFull 'runtime'
$stateDir = Join-Path $installRootFull 'state'
$settingsPath = Join-Path $installRootFull 'settings.json'
$ownerHomeFull = Resolve-FullPath $OwnerHome
$coreExeFull = Resolve-FullPath $CoreExe
$v2raynDirFull = if ($V2rayNDir) { Resolve-FullPath $V2rayNDir } else { Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $coreExeFull)) }
$owner = Get-CurrentUserName

if (-not (Test-Path -LiteralPath $runtimeSource)) {
    throw "runtime source directory was not found: $runtimeSource"
}
if (-not (Test-Path -LiteralPath $coreExeFull)) {
    throw "CoreExe was not found: $coreExeFull"
}
if (-not (Test-Path -LiteralPath $ownerHomeFull)) {
    throw "OwnerHome was not found: $ownerHomeFull"
}

$pythonFull = Find-Python $PythonExe
$targetGuard = Find-TargetGuard $scriptRoot
$sshResolved = Resolve-SshAlias -HostAlias $SshHost -OwnerHome $ownerHomeFull -ReadyConfig $ServiceSshConfig
$activeManagedTasks = @(Get-ManagedTasksForStartupMode $StartupMode)

$planObject = [pscustomobject]@{
    install_root = $installRootFull
    runtime_source = $runtimeSource
    runtime_dest = $runtimeDest
    settings_path = $settingsPath
    state_dir = $stateDir
    startup_mode = $StartupMode
    boot_requires_admin = ($StartupMode -eq 'Boot')
    will_start_after_install = [bool]$Start
    keep_awake_on_ac = [bool]$KeepAwakeOnAC
    target_guard = $targetGuard
    tasks = $activeManagedTasks
    boot_system_tasks = if ($StartupMode -eq 'Boot') { $activeManagedTasks } else { @() }
    logon_tasks = if ($StartupMode -eq 'Boot') { @() } else { $activeManagedTasks }
    untouched_legacy_tasks = if ($StartupMode -eq 'Boot') { @('AiProxyFailover') } else { @() }
    ssh_host = $SshHost
    ssh_hostname = $sshResolved.HostName
    ssh_user = $sshResolved.User
    ssh_port = $sshResolved.Port
    ssh_identity_file = $sshResolved.IdentityFile
    ssh_known_hosts_source = $sshResolved.KnownHosts
    main_ai_subscriptions = @($MainAiSubscriptions)
}

if ($Plan) {
    $planObject | ConvertTo-Json -Depth 8
    return
}

if ($StartupMode -eq 'Boot' -and -not (Test-IsAdministrator)) {
    throw 'StartupMode Boot requires an elevated PowerShell session. No user password is stored; rerun as Administrator.'
}

if ($PSCmdlet.ShouldProcess($installRootFull, 'Install Win11 proxy relay')) {
    Invoke-TargetGuard -Python $pythonFull -Guard $targetGuard -TargetProfileHome $ownerHomeFull | Out-Null

    $backup = $null
    $tasksTouched = $false
    try {
        if (Test-Path -LiteralPath $settingsPath) {
            throw "InstallRoot already contains settings.json; use a fresh versioned InstallRoot instead of in-place update: $installRootFull"
        }
        New-Item -ItemType Directory -Force -Path $installRootFull, $runtimeDest, $stateDir | Out-Null
        $backup = Backup-ExistingState -InstallRoot $installRootFull -StateDir $stateDir -TaskNames $activeManagedTasks

        Get-ChildItem -LiteralPath $runtimeSource -File | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $runtimeDest $_.Name) -Force
        }

        if ($StartupMode -eq 'Boot') {
            $vendors = Install-BootVendors -InstallRoot $installRootFull -CoreExe $coreExeFull -PythonExe $pythonFull
            $coreExeFull = $vendors.CoreExe
            $pythonFull = $vendors.PythonExe
        }

        $knownHostsDest = Join-Path $stateDir 'known_hosts'
        Copy-Item -LiteralPath $sshResolved.KnownHosts -Destination $knownHostsDest -Force
        $sshConfigDest = Join-Path $stateDir 'ssh_config'
        Write-ServiceSshConfig -Path $sshConfigDest -HostAlias $SshHost -Resolved $sshResolved -KnownHostsPath $knownHostsDest

        $settings = [ordered]@{
            v2rayn_dir = $v2raynDirFull
            core_exe = $coreExeFull
            ssh_host = $SshHost
            ssh_config = $sshConfigDest
            ssh_identity_file = $sshResolved.IdentityFile
            ssh_known_hosts = $knownHostsDest
            local_proxy_port = 17897
            remote_proxy_port = 17890
            controller_port = 17903
            main_controller_ports = @(7903, 7902)
            main_ai_subscriptions = @($MainAiSubscriptions)
            state_dir = $stateDir
            owner_home = $ownerHomeFull
            python_exe = $pythonFull
            startup_mode = $StartupMode
            ai_primary_port = 17911
            ai_fallback_port = 17912
            ai_measure_port = 17913
            feitu_measure_port = 17914
        }
        ConvertTo-JsonFile $settings $settingsPath

        if ($PrivateConfig) {
            $privateConfigFull = Resolve-FullPath $PrivateConfig
            if (-not (Test-Path -LiteralPath $privateConfigFull)) {
                throw "PrivateConfig was not found: $privateConfigFull"
            }
            Copy-PrivateConfig -Source $privateConfigFull -Destination (Join-Path $stateDir 'server-config.json') -SchemaPath (Join-Path $stateDir 'source-private-config-schema.json') -StateDir $stateDir
            Install-DashboardNodeLabels -PrivateConfigPath $privateConfigFull -RuntimeDir $runtimeDest -StateDir $stateDir
        }

        Test-SingBoxConfig -Core $coreExeFull -Config (Join-Path $stateDir 'server-config.json')

        $powerSnapshot = $null
        if ($KeepAwakeOnAC) {
            $powerSnapshot = Set-KeepAwakeOnAcPower
            ConvertTo-JsonFile $powerSnapshot (Join-Path $stateDir 'powercfg-before.json')
        }

        Install-ControlFiles -ScriptRoot $scriptRoot -InstallRoot $installRootFull
        Set-RelayAcl -InstallRoot $installRootFull -RuntimeDir $runtimeDest -StateDir $stateDir -Owner $owner -Mode $StartupMode

        if (-not $SkipConnectionCheck) {
            Test-ServiceSshConnection -SshConfig $sshConfigDest -SshHost $SshHost -SshExe $sshResolved.SshExe
        }

        $tasksTouched = $true
        foreach ($taskName in $activeManagedTasks) {
            Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        }
        Register-RelayTasks -TaskNames $activeManagedTasks -StartupMode $StartupMode -RuntimeDir $runtimeDest -SettingsPath $settingsPath -Python $pythonFull -Owner $owner

        if ($Start) {
            foreach ($taskName in $activeManagedTasks) {
                Start-ScheduledTask -TaskName $taskName
            }
        }

        [pscustomobject]@{
            installed = $true
            install_root = $installRootFull
            settings = $settingsPath
            state_dir = $stateDir
            startup_mode = $StartupMode
            backup = $backup.Root
            started = [bool]$Start
            untouched_legacy_tasks = if ($StartupMode -eq 'Boot') { @('AiProxyFailover') } else { @() }
        } | ConvertTo-Json -Depth 8
    } catch {
        if ($backup) {
            Restore-ExistingState -Backup $backup -InstallRoot $installRootFull -StateDir $stateDir -TaskNames $activeManagedTasks -RestoreTasks $tasksTouched
        }
        throw
    }
}
