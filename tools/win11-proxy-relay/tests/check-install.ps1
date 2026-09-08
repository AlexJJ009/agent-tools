#Requires -Version 5.1
# Exercise serialization helpers without registering tasks or reading private config.
$ErrorActionPreference='Stop'
$installer=Join-Path (Split-Path $PSScriptRoot -Parent) 'install.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($installer,[ref]$tokens,[ref]$errors)
if($errors){throw ($errors -join '; ')}
$functions=$ast.FindAll({param($a) $a -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)
if ('Install-ControlFiles' -notin $functions.Name){throw 'Control installer function missing'}
$functions | Where-Object {$_.Name -eq 'ConvertTo-JsonFile'} | ForEach-Object {Invoke-Expression $_.Extent.Text}
$guard=$functions | Where-Object {$_.Name -eq 'Invoke-TargetGuard'}
if($guard.Body.ParamBlock.Parameters.Name.VariablePath.UserPath -contains 'Home'){throw 'Reserved PowerShell HOME parameter'}
$testPath=Join-Path ([IO.Path]::GetTempPath()) ([IO.Path]::GetRandomFileName())
try {
    ConvertTo-JsonFile @{test='payload';number=7} $testPath
    $bytes=[IO.File]::ReadAllBytes($testPath)
    if($bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191){throw 'JSON BOM would break sing-box'}
    $value=Get-Content $testPath -Raw | ConvertFrom-Json
    if($value.test -ne 'payload' -or $value.number -ne 7){throw 'JSON roundtrip failed'}
    Write-Output 'Installer helper checks passed'
} finally {Remove-Item $testPath -ErrorAction SilentlyContinue}
