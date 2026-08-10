param(
  [Parameter(Mandatory = $true)][string]$CodexExe,
  [Parameter(Mandatory = $true)][string]$MarketplaceRoot,
  [string]$ReportPath = ""
)

$ErrorActionPreference = "Stop"
$marketplaceName = "openai-curated-remote-local"
$CodexExe = [System.IO.Path]::GetFullPath($CodexExe)
$MarketplaceRoot = [System.IO.Path]::GetFullPath($MarketplaceRoot)

if (-not (Test-Path -LiteralPath $CodexExe -PathType Leaf)) {
  throw "Native codex.exe was not found at the requested copied-App path."
}
if (-not (Test-Path -LiteralPath $MarketplaceRoot -PathType Container)) {
  throw "Plugin marketplace root was not found."
}
if ($MarketplaceRoot -match '^(?:/mnt/|\\\\wsl)') {
  throw "Marketplace registration requires a native Windows path, not a WSL path."
}

$manifestPath = Join-Path $MarketplaceRoot ".agents\plugins\marketplace.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
  throw "Marketplace root does not contain .agents\plugins\marketplace.json."
}
$manifest = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.name -ne $marketplaceName) {
  throw "Marketplace name does not match the guarded local marketplace name."
}

$removeStatus = "not-present-or-removed"
try {
  & $CodexExe plugin marketplace remove $marketplaceName --json *> $null
} catch {
  $removeStatus = "remove-returned-nonzero"
}

$addRaw = & $CodexExe plugin marketplace add $MarketplaceRoot --json
if ($LASTEXITCODE -ne 0) { throw "Native marketplace add failed." }
$add = $addRaw | ConvertFrom-Json
if ($add.marketplaceName -ne $marketplaceName) {
  throw "Native marketplace add returned a different marketplace name."
}

$listRaw = & $CodexExe plugin list --marketplace $marketplaceName --available --json
if ($LASTEXITCODE -ne 0) { throw "Native plugin list verification failed." }
$list = $listRaw | ConvertFrom-Json
$items = @($list.installed) + @($list.available)
$names = @($items | ForEach-Object { $_.name } | Where-Object { $_ } | Sort-Object -Unique)

$required = [ordered]@{}
foreach ($name in @("github", "figma")) {
  $required[$name] = $names -contains $name
  if (-not $required[$name]) { throw "Required locally bundled plugin is missing: $name" }
}

$report = [ordered]@{
  ok = $true
  marketplaceName = $marketplaceName
  marketplaceRoot = $MarketplaceRoot
  registrationPathKind = "windows-native"
  removeStatus = $removeStatus
  installedCount = @($list.installed).Count
  availableCount = @($list.available).Count
  uniquePluginCount = $names.Count
  requiredPresent = $required
  externalOAuthStillRequired = $true
}
$json = $report | ConvertTo-Json -Depth 5
if ($ReportPath) {
  $ReportPath = [System.IO.Path]::GetFullPath($ReportPath)
  [System.IO.File]::WriteAllText($ReportPath, $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
}
$json
