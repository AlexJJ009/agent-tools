param(
  [string]$Root = (Join-Path $env:USERPROFILE "Downloads\Report\CodexPatched"),
  [Parameter(Mandatory = $true)][string]$SnapshotManifest,
  [switch]$RegisterPlugins
)

$ErrorActionPreference = "Stop"
$expectedVersion = "26.721.4979.0"
$expectedSourceAsar = "44884F86D619A12C3C0AF1B8C65945005BDA4379775B03270674C666226FF4B7"
$expectedModelCatalog = "6D6C694360AD6ADAF91B4D72B32014AFCE4C8C8322A304CD01ADE377CC00D5F6"
$wslNode = "/home/alex_mercer/.local/share/fnm/fnm exec --using 24.14.0 -- node"
$wslNpx = "/home/alex_mercer/.local/share/fnm/fnm exec --using 24.14.0 -- npx"

function Quote-Bash([string]$Value) {
  return "'" + ($Value -replace "'", "'\''") + "'"
}

function To-WslPath([string]$WindowsPath) {
  $result = & wsl.exe wslpath -a $WindowsPath
  if ($LASTEXITCODE -ne 0) { throw "wslpath failed for a guarded patch path." }
  return $result.Trim()
}

function Get-ConfiguredModelCatalogPath {
  $configPath = Join-Path $env:USERPROFILE ".codex\config.toml"
  $configText = Get-Content -Raw -Encoding UTF8 -LiteralPath $configPath
  $match = [regex]::Match($configText, '(?m)^\s*model_catalog_json\s*=\s*"(?<value>(?:\\.|[^"\\])*)"\s*$')
  if (-not $match.Success) { return $null }
  return ('"' + $match.Groups['value'].Value + '"' | ConvertFrom-Json)
}

function Assert-ModelCatalog([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Configured model_catalog_json dependency is missing: $Path"
  }
  if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $expectedModelCatalog) {
    throw "Configured model catalog does not match the hash-bound release artifact: $Path"
  }
  $catalog = Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
  if (-not $catalog.models -or @($catalog.models).Count -eq 0) {
    throw "Configured model catalog has no models: $Path"
  }
}

function Repair-ReleaseModelCatalogDependency {
  $configured = Get-ConfiguredModelCatalogPath
  if (-not $configured) { return }
  $releaseTarget = Join-Path $Root "model-catalog.json"
  if (-not (Test-Path -LiteralPath $configured -PathType Leaf)) {
    if ([IO.Path]::GetFullPath($configured) -ne [IO.Path]::GetFullPath($releaseTarget)) {
      throw "Refusing to repair a missing model catalog outside this release root: $configured"
    }
    $artifactCandidates = @(
      (Join-Path $Root "model-catalog-candidate-runtime.json"),
      (Join-Path $PSScriptRoot "model-catalog.json"),
      (Join-Path $env:USERPROFILE ".codex\skills\codex-win11-patch-safety\releases\26.721.4979.0\model-catalog.json")
    )
    $artifact = $null
    foreach ($candidate in $artifactCandidates) {
      if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and
          (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash -eq $expectedModelCatalog) {
        Assert-ModelCatalog $candidate
        $artifact = $candidate
        break
      }
    }
    if (-not $artifact) {
      throw "The exact hash-bound release model catalog artifact is unavailable."
    }
    Copy-Item -LiteralPath $artifact -Destination $releaseTarget
  }
  Assert-ModelCatalog $configured
}

if (@(Get-Process ChatGPT,Codex -ErrorAction SilentlyContinue).Count -gt 0) {
  throw "Close all ChatGPT/Codex windows normally before rebuilding. This script never stops them."
}
if (-not (Test-Path -LiteralPath $SnapshotManifest -PathType Leaf)) {
  throw "A closed-App snapshot manifest is required."
}
Repair-ReleaseModelCatalogDependency
$recipe = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $Root "recipe.json") | ConvertFrom-Json
if ($recipe.status -ne "candidate" -and $recipe.status -ne "verified") {
  throw "The local release recipe status is invalid."
}

$package = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
if (-not $package -or $package.Version.ToString() -ne $expectedVersion) {
  throw "The installed Store build is not the exact release captured by this patcher. Probe a new candidate instead."
}
$sourceApp = Join-Path $package.InstallLocation "app"
$sourceAsar = Join-Path $sourceApp "resources\app.asar"
$sourceHash = (Get-FileHash -LiteralPath $sourceAsar -Algorithm SHA256).Hash
if ($sourceHash -ne $expectedSourceAsar) {
  throw "The Store app.asar hash differs from the exact release recipe."
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stagingRoot = Join-Path $Root "staging-$stamp"
$stagingApp = Join-Path $stagingRoot "app"
$work = Join-Path $stagingRoot "app-unpacked"
$packed = Join-Path $stagingRoot "app.asar"
if (Test-Path -LiteralPath $stagingRoot) { throw "Unique staging path already exists." }
New-Item -ItemType Directory -Path $stagingRoot | Out-Null
Copy-Item -LiteralPath $sourceApp -Destination $stagingApp -Recurse

$stagingAsar = Join-Path $stagingApp "resources\app.asar"
$extractCommand = "$wslNpx --yes @electron/asar@3.4.1 extract " + (Quote-Bash (To-WslPath $stagingAsar)) + " " + (Quote-Bash (To-WslPath $work))
& wsl.exe bash -lc $extractCommand
if ($LASTEXITCODE -ne 0) { throw "ASAR extraction failed." }

$patcher = Join-Path $Root "patch-codex-webview.mjs"
$patchCommand = "$wslNode " + (Quote-Bash (To-WslPath $patcher)) + " " + (Quote-Bash (To-WslPath $work))
$patchReport = & wsl.exe bash -lc $patchCommand
if ($LASTEXITCODE -ne 0) { throw "Feature-signature patch failed." }
$patchReportPath = Join-Path $stagingRoot "patch-report.json"
[System.IO.File]::WriteAllText($patchReportPath, ($patchReport -join [Environment]::NewLine) + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
$parsedPatch = Get-Content -Raw -Encoding UTF8 -LiteralPath $patchReportPath | ConvertFrom-Json
foreach ($relative in @($parsedPatch.patched)) {
  $js = Join-Path $work $relative
  $checkCommand = "$wslNode --check " + (Quote-Bash (To-WslPath $js))
  & wsl.exe bash -lc $checkCommand
  if ($LASTEXITCODE -ne 0) { throw "node --check failed for a modified asset." }
}
if (Get-ChildItem -LiteralPath $work -Recurse -File | Where-Object Name -Match '\.(original|bak|backup|tmp)$') {
  throw "A temporary or backup file would enter app.asar."
}

$packCommand = "$wslNpx --yes @electron/asar@3.4.1 pack " + (Quote-Bash (To-WslPath $work)) + " " + (Quote-Bash (To-WslPath $packed))
& wsl.exe bash -lc $packCommand
if ($LASTEXITCODE -ne 0) { throw "ASAR repack failed." }
Copy-Item -LiteralPath $packed -Destination $stagingAsar -Force
if ((Get-FileHash $packed -Algorithm SHA256).Hash -ne (Get-FileHash $stagingAsar -Algorithm SHA256).Hash) {
  throw "Packed/runtime ASAR hash mismatch."
}
$patchedHash = (Get-FileHash $stagingAsar -Algorithm SHA256).Hash

$activeApp = Join-Path $Root "app"
$previousApp = Join-Path $Root "app.previous-$stamp"
if (Test-Path -LiteralPath $activeApp) { Move-Item -LiteralPath $activeApp -Destination $previousApp }
Move-Item -LiteralPath $stagingApp -Destination $activeApp
Repair-ReleaseModelCatalogDependency

$target = Join-Path $activeApp "ChatGPT.exe"
$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @(
  (Join-Path $Root "Codex Patched.lnk"),
  (Join-Path $Root "Codex Fast Connections.lnk"),
  (Join-Path $env:USERPROFILE "Desktop\Codex Fast Connections.lnk")
)) {
  $shortcut = $shell.CreateShortcut($shortcutPath)
  $shortcut.TargetPath = $target
  $shortcut.Arguments = ""
  $shortcut.WorkingDirectory = $activeApp
  $shortcut.IconLocation = "$target,0"
  $shortcut.Save()
}

if ($RegisterPlugins) {
  & (Join-Path $Root "register-plugin-marketplace.ps1") -CodexExe (Join-Path $activeApp "resources\codex.exe") -MarketplaceRoot (Join-Path $Root "plugin-marketplace") -ReportPath (Join-Path $Root "plugin-verification.json") | Out-Null
}

$guard = Join-Path $Root "codex_state_guard.py"
$verifyReport = Join-Path $Root "prelaunch-state-verification.json"
$guardCommand = "python3 " + (Quote-Bash (To-WslPath $guard)) + " verify --user-home " + (Quote-Bash (To-WslPath $env:USERPROFILE)) + " --baseline " + (Quote-Bash (To-WslPath $SnapshotManifest)) + " --output " + (Quote-Bash (To-WslPath $verifyReport))
if ($RegisterPlugins) {
  $binding = "openai-curated-remote-local=" + (Join-Path $Root "plugin-marketplace")
  $guardCommand += " --allow-marketplace-root " + (Quote-Bash $binding)
}
& wsl.exe bash -lc $guardCommand
if ($LASTEXITCODE -ne 0) { throw "Protected-state verification failed. The previous app remains at $previousApp." }

[pscustomobject]@{
  ok = $true
  packageVersion = $expectedVersion
  sourceAsarSha256 = $sourceHash
  patchedAsarSha256 = $patchedHash
  previousApp = $previousApp
  shortcutTarget = $target
  launched = $false
} | ConvertTo-Json -Depth 3
