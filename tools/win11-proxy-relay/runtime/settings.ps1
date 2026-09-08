#Requires -Version 5.1

function Get-ProxyRelaySettings {
    [CmdletBinding()]
    param(
        [string]$SettingsPath = ''
    )

    $runtimeRoot = if ($PSScriptRoot) { $PSScriptRoot }
                   elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
                   else { (Get-Location).Path }
    $installRoot = Split-Path -Parent $runtimeRoot
    if (-not $SettingsPath) {
        $SettingsPath = Join-Path $installRoot 'settings.json'
    }

    $data = @{}
    if (Test-Path -LiteralPath $SettingsPath) {
        $json = Get-Content -LiteralPath $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($property in $json.PSObject.Properties) {
            $data[$property.Name] = $property.Value
        }
    }

    function Get-SettingValue([string]$Name, $Default) {
        if ($data.ContainsKey($Name) -and $null -ne $data[$Name] -and "$($data[$Name])" -ne '') {
            return $data[$Name]
        }
        return $Default
    }

    function Resolve-PortablePath([string]$Value) {
        if ([System.IO.Path]::IsPathRooted($Value)) {
            return $Value
        }
        return [System.IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $SettingsPath) $Value))
    }

    $v2raynDir = Resolve-PortablePath ([string](Get-SettingValue 'v2rayn_dir' (Join-Path $installRoot 'v2rayN-windows-64')))
    $coreExe = [string](Get-SettingValue 'core_exe' '')
    if ($coreExe) {
        $coreExe = Resolve-PortablePath $coreExe
    } else {
        $coreExe = Join-Path $v2raynDir 'bin\sing_box\sing-box.exe'
    }
    $stateDir = Resolve-PortablePath ([string](Get-SettingValue 'state_dir' (Join-Path $installRoot 'state')))
    $ownerHome = [string](Get-SettingValue 'owner_home' '')
    $sshConfig = [string](Get-SettingValue 'ssh_config' '')
    $sshIdentityFile = [string](Get-SettingValue 'ssh_identity_file' '')
    $sshKnownHosts = [string](Get-SettingValue 'ssh_known_hosts' '')
    if ($ownerHome) { $ownerHome = Resolve-PortablePath $ownerHome }
    if ($sshConfig) { $sshConfig = Resolve-PortablePath $sshConfig }
    if ($sshIdentityFile) { $sshIdentityFile = Resolve-PortablePath $sshIdentityFile }
    if ($sshKnownHosts) { $sshKnownHosts = Resolve-PortablePath $sshKnownHosts }

    [pscustomobject]@{
        SettingsPath = $SettingsPath
        RuntimeRoot = $runtimeRoot
        InstallRoot = $installRoot
        V2rayNDir = $v2raynDir
        CoreExe = $coreExe
        SshHost = [string](Get-SettingValue 'ssh_host' 'phai-lgx-dev')
        LocalProxyPort = [int](Get-SettingValue 'local_proxy_port' 17897)
        RemoteProxyPort = [int](Get-SettingValue 'remote_proxy_port' 17890)
        ControllerPort = [int](Get-SettingValue 'controller_port' 17903)
        StateDir = $stateDir
        OwnerHome = $ownerHome
        SshConfig = $sshConfig
        SshIdentityFile = $sshIdentityFile
        SshKnownHosts = $sshKnownHosts
        MainControllerPorts = @(Get-SettingValue 'main_controller_ports' @(7903, 7902) | ForEach-Object { [int]$_ })
        AiPrimaryPort = [int](Get-SettingValue 'ai_primary_port' 17911)
        AiFallbackPort = [int](Get-SettingValue 'ai_fallback_port' 17912)
        AiMeasurePort = [int](Get-SettingValue 'ai_measure_port' 17913)
        FeituMeasurePort = [int](Get-SettingValue 'feitu_measure_port' 17914)
    }
}
