param(
  [Parameter(Mandatory = $true)][string]$RecipePath,
  [Parameter(Mandatory = $true)][string]$DetectionReport,
  [Parameter(Mandatory = $true)][string]$SnapshotManifest,
  [Parameter(Mandatory = $true)][string]$ConfigHealthReport,
  [Parameter(Mandatory = $true)][string]$OutputReport
)

$ErrorActionPreference = "Stop"

function Read-Json([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
    throw "Required evidence file is missing: $Path"
  }
  return Get-Content -Raw -Encoding UTF8 -LiteralPath $Path | ConvertFrom-Json
}

if (@(Get-Process ChatGPT,Codex -ErrorAction SilentlyContinue).Count -gt 0) {
  throw "Close all ChatGPT/Codex windows normally before repair. This script never stops them."
}

$recipeFull = [IO.Path]::GetFullPath($RecipePath)
$releaseRoot = [IO.Path]::GetFullPath((Split-Path -Parent $recipeFull))
$recipe = Read-Json $recipeFull
$detect = Read-Json ([IO.Path]::GetFullPath($DetectionReport))
$snapshot = Read-Json ([IO.Path]::GetFullPath($SnapshotManifest))
$health = Read-Json ([IO.Path]::GetFullPath($ConfigHealthReport))

if ($recipe.status -notin @("candidate", "verified")) {
  throw "Release status is invalid."
}
if ($detect.packageVersion -ne $recipe.application.packageVersion -or
    $detect.sourceAsarSha256 -ne $recipe.application.sourceAsarSha256) {
  throw "Detection evidence does not match the exact release identity."
}
if ($snapshot.schemaVersion -lt 3 -or -not $snapshot.entries -or -not $snapshot.semantics) {
  throw "A complete closed-App snapshot manifest is required."
}

$package = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
if (-not $package -or $package.Version.ToString() -ne $recipe.application.packageVersion) {
  throw "The currently installed Store package does not match the exact release."
}
$sourceAsar = Join-Path $package.InstallLocation "app\resources\app.asar"
if (-not (Test-Path -LiteralPath $sourceAsar -PathType Leaf) -or
    (Get-FileHash -LiteralPath $sourceAsar -Algorithm SHA256).Hash -ne $recipe.application.sourceAsarSha256) {
  throw "The current Store source ASAR does not match the exact release."
}

$dependency = $health.externalDependencies.model_catalog_json
if (-not $dependency -or $dependency.exists) {
  throw "This repair is limited to a currently missing model_catalog_json dependency."
}
$snapshotDependency = $snapshot.semantics.config.externalDependencies.model_catalog_json
if (-not $snapshotDependency -or $snapshotDependency.exists -or
    $snapshotDependency.configuredPath -ne $dependency.configuredPath) {
  throw "Snapshot and config-health dependency evidence do not match."
}

$artifacts = @($recipe.patcher.artifacts | Where-Object {
  $_.configKey -eq "model_catalog_json" -and $_.requiredWhileConfigured
})
if ($artifacts.Count -ne 1) {
  throw "The exact release must declare one required model_catalog_json artifact."
}
$artifact = $artifacts[0]
if (-not $artifact.targetPath) {
  throw "The release artifact lacks an exact targetPath."
}

$artifactSource = [IO.Path]::GetFullPath((Join-Path $releaseRoot $artifact.path))
$releasePrefix = $releaseRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if (-not $artifactSource.StartsWith($releasePrefix, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Release artifact escapes its release directory."
}
if (-not (Test-Path -LiteralPath $artifactSource -PathType Leaf)) {
  throw "Release artifact is missing."
}
if ((Get-FileHash -LiteralPath $artifactSource -Algorithm SHA256).Hash -ne $artifact.sha256) {
  throw "Release artifact hash does not match the recipe."
}

$target = [IO.Path]::GetFullPath([string]$dependency.configuredPath)
$declaredTarget = [IO.Path]::GetFullPath([string]$artifact.targetPath)
if (-not $target.Equals($declaredTarget, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Configured dependency does not match the exact release targetPath."
}
if (Test-Path -LiteralPath $target) {
  throw "Refusing to overwrite an existing dependency; diagnose invalid content separately."
}
$targetParent = Split-Path -Parent $target
if (-not (Test-Path -LiteralPath $targetParent -PathType Container)) {
  throw "Refusing to create a missing target directory."
}

[IO.File]::Copy($artifactSource, $target, $false)
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $artifact.sha256) {
  throw "Restored dependency hash verification failed."
}
$catalog = Get-Content -Raw -Encoding UTF8 -LiteralPath $target | ConvertFrom-Json
if (-not $catalog.models -or @($catalog.models).Count -eq 0) {
  throw "Restored model catalog is invalid."
}

$result = [ordered]@{
  ok = $true
  action = "restore-model-catalog-only"
  releaseId = $recipe.releaseId
  releaseStatus = $recipe.status
  activationAllowed = $false
  packageVersion = $detect.packageVersion
  sourceAsarSha256 = $detect.sourceAsarSha256
  targetPath = $target
  artifactSha256 = $artifact.sha256
  modelCount = @($catalog.models).Count
  snapshotManifestSha256 = (Get-FileHash -LiteralPath $SnapshotManifest -Algorithm SHA256).Hash
  configChanged = $false
}
$result | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -LiteralPath $OutputReport
$result
