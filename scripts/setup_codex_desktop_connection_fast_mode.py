#!/usr/bin/env python3
"""Prepare Codex Desktop so Connections can preserve Fast service tier.

This wrapper builds on `patch_codex_desktop_connection_fast_mode.py`.

On Win11 from WSL it creates a writable copy of the Microsoft Store Codex app,
patches that copy, and writes launchers that start the patched executable with
an isolated user-data-dir.

On macOS it patches the installed Codex.app resources in place after creating
the app.asar backup handled by the lower-level patcher.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import patch_codex_desktop_connection_fast_mode as bundle_patch


DEFAULT_WIN_DEST = r"%LOCALAPPDATA%\OpenAI\CodexDesktopPatched\app"
DEFAULT_WIN_PROFILE = r"C:\Users\Public\CodexPatchedProfile"
DEFAULT_WIN_SHORTCUT_NAME = "Codex Fast Connections"
PROVIDER_OVERRIDE_VERSION_FLOOR = (26, 616)


def run(cmd: list[str], *, dry_run: bool = False) -> subprocess.CompletedProcess[str] | None:
    print("+ " + " ".join(cmd))
    if dry_run:
        return None
    return subprocess.run(cmd, check=True, text=True)


def powershell() -> Path:
    candidates = [
        Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"),
        Path("powershell.exe"),
    ]
    for candidate in candidates:
        if candidate.exists() or str(candidate) == "powershell.exe":
            return candidate
    raise SystemExit("PowerShell was not found. Run Win11 setup from WSL or Windows.")


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def run_ps(script: str, *, dry_run: bool = False) -> str:
    cmd = [str(powershell()), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    print("+ powershell -NoProfile -ExecutionPolicy Bypass -Command <script>")
    if dry_run:
        print(script)
        return ""
    result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr)
    return result.stdout.strip()


def win_to_wsl_path(path: str) -> Path:
    if platform.system() == "Windows":
        return Path(path)
    normalized = path.strip().replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        return Path("/mnt") / drive / normalized[3:]
    return Path(normalized)


def discover_win_store_app() -> str:
    script = (
        "$p=(Get-AppxPackage *Codex* | Sort-Object Version -Descending | "
        "Select-Object -First 1).InstallLocation; "
        "if (-not $p) { throw 'Codex Microsoft Store package not found' }; "
        "$app=Join-Path $p 'app'; "
        "if (-not (Test-Path $app)) { throw \"Codex Store app directory not found: $app\" }; "
        "Write-Output $app"
    )
    return run_ps(script)


def expand_win_path(path: str) -> str:
    script = (
        "$raw="
        + ps_quote(path)
        + "; "
        "$expanded=[Environment]::ExpandEnvironmentVariables($raw); "
        "$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($expanded)"
    )
    return run_ps(script)


def detect_win_store_version(source: str) -> str:
    script = f"""
$src = {ps_quote(source)}
$pkg = Get-AppxPackage *Codex* | Where-Object {{ $_.InstallLocation -and $src.StartsWith($_.InstallLocation) }} | Sort-Object Version -Descending | Select-Object -First 1
if ($pkg) {{
  Write-Output $pkg.Version
}}
"""
    return run_ps(script).strip()


def parse_version(value: str) -> tuple[int, ...]:
    parts = []
    for part in value.split("."):
        if not part.isdigit():
            break
        parts.append(int(part))
    return tuple(parts)


def argparse_help_value(value: str) -> str:
    return value.replace("%", "%%")


def repair_route_for_version(version: str) -> tuple[str, str]:
    parsed = parse_version(version)
    if len(parsed) >= 2 and parsed[:2] >= PROVIDER_OVERRIDE_VERSION_FLOOR:
        return (
            "provider_override_required",
            "Codex Desktop 26.616+ did not reliably forward service_tier from the bundle/config path; use scoped NewAPI param_override plus runtime log verification.",
        )
    if parsed:
        return (
            "legacy_bundle_patch",
            "Older Codex Desktop builds use the bundle patch route to preserve explicit serviceTier for Connections.",
        )
    return (
        "unknown_version_bundle_patch",
        "Codex Desktop version was not detected; run the bundle patch as best effort and verify provider logs.",
    )


def metadata_json(
    *,
    source: str,
    dest: str,
    profile: str,
    source_version: str,
    repair_route: str,
    repair_note: str,
    bundle_patch_status: str,
    shortcut_scope: str,
    shortcut_name: str,
) -> str:
    payload = {
        "source": source,
        "dest": dest,
        "user_data_dir": profile,
        "source_store_version": source_version or None,
        "repair_route": repair_route,
        "repair_note": repair_note,
        "bundle_patch_status": bundle_patch_status,
        "shortcut_scope": shortcut_scope,
        "shortcut_name": shortcut_name,
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def copy_win_app(source: str, dest: str, *, dry_run: bool) -> None:
    script = f"""
$src = {ps_quote(source)}
$dst = {ps_quote(dest)}
if (-not (Test-Path $src)) {{ throw "Source Codex app not found: $src" }}
New-Item -ItemType Directory -Force -Path $dst | Out-Null
# Mirror the current Store package on every run. This intentionally removes
# stale patched artifacts from older Codex versions before patching again.
robocopy $src $dst /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
$code = $LASTEXITCODE
if ($code -gt 7) {{ throw "robocopy failed with exit code $code" }}
Write-Output $dst
"""
    run_ps(script, dry_run=dry_run)


def write_win_launchers(
    dest: str,
    profile: str,
    shortcut_scope: str,
    shortcut_name: str,
    setup_metadata: str,
    *,
    dry_run: bool,
) -> None:
    dest_path = PureWindowsPath(dest)
    root_path = dest_path.parent
    ps1 = str(root_path / "Start-Codex-Fast-Connections.ps1")
    cmd = str(root_path / "Start-Codex-Fast-Connections.cmd")
    exe = str(dest_path / "Codex.exe")
    resources_codex = str(dest_path / "resources" / "codex.exe")
    metadata = str(root_path / "codex-fast-connections.json")

    script = f"""
$exe = {ps_quote(exe)}
$profile = {ps_quote(profile)}
$ps1 = {ps_quote(ps1)}
$cmd = {ps_quote(cmd)}
$codexCli = {ps_quote(resources_codex)}
$metadata = {ps_quote(metadata)}
$shortcutScope = {ps_quote(shortcut_scope)}
$shortcutName = {ps_quote(shortcut_name)}
$setupMetadata = {ps_quote(setup_metadata)}
New-Item -ItemType Directory -Force -Path (Split-Path $ps1) | Out-Null
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$ps1Text = @'
$ErrorActionPreference = "Stop"
$exe = "{exe}"
$userDataDir = "{profile}"
if (-not (Test-Path $exe)) {{ throw "Patched Codex.exe not found: $exe" }}
New-Item -ItemType Directory -Force -Path $userDataDir | Out-Null
Get-Process -Name Codex,codex -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$args = @("--user-data-dir=`"$userDataDir`"", "--no-first-run")
Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory (Split-Path $exe)
'@
Set-Content -Path $ps1 -Value $ps1Text -Encoding UTF8
$cmdText = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File ""$ps1""`r`n"
Set-Content -Path $cmd -Value $cmdText -Encoding ASCII
$metadataObject = $setupMetadata | ConvertFrom-Json
$metadataObject | Add-Member -NotePropertyName generated_at -NotePropertyValue (Get-Date).ToString("o") -Force
$metadataObject | Add-Member -NotePropertyName exe -NotePropertyValue $exe -Force
$metadataObject | Add-Member -NotePropertyName launcher_ps1 -NotePropertyValue $ps1 -Force
$metadataObject | Add-Member -NotePropertyName launcher_cmd -NotePropertyValue $cmd -Force
$metadataObject | Add-Member -NotePropertyName bundled_codex -NotePropertyValue $codexCli -Force
$metadataObject | ConvertTo-Json -Depth 4 | Set-Content -Path $metadata -Encoding UTF8
Write-Output "Launcher written: $ps1"
Write-Output "Launcher written: $cmd"
Write-Output "Metadata written: $metadata"
if (Test-Path $codexCli) {{ Write-Output "Bundled app-server CLI: $codexCli" }}

function Ensure-CodexShortcut {{
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Target,
    [Parameter(Mandatory=$true)][string]$WorkingDirectory,
    [Parameter(Mandatory=$true)][string]$Icon
  )
  $shell = New-Object -ComObject WScript.Shell
  $needsWrite = $true
  if (Test-Path $Path) {{
    $existing = $shell.CreateShortcut($Path)
    $needsWrite = (
      $existing.TargetPath -ne $Target -or
      $existing.WorkingDirectory -ne $WorkingDirectory -or
      $existing.IconLocation -ne $Icon
    )
  }}
  if ($needsWrite) {{
    New-Item -ItemType Directory -Force -Path (Split-Path $Path) | Out-Null
    $shortcut = $shell.CreateShortcut($Path)
    $shortcut.TargetPath = $Target
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = $Icon
    $shortcut.Description = "Launch patched Codex Desktop for Fast Mode Connections"
    $shortcut.Save()
    Write-Output "Shortcut updated: $Path"
  }} else {{
    Write-Output "Shortcut already current: $Path"
  }}
}}

if ($shortcutScope -ne "none") {{
  $shortcutTargets = @()
  if ($shortcutScope -eq "desktop" -or $shortcutScope -eq "both") {{
    $shortcutTargets += (Join-Path ([Environment]::GetFolderPath("Desktop")) "$shortcutName.lnk")
  }}
  if ($shortcutScope -eq "start-menu" -or $shortcutScope -eq "both") {{
    $shortcutTargets += (Join-Path ([Environment]::GetFolderPath("Programs")) "$shortcutName.lnk")
  }}
  foreach ($shortcutPath in $shortcutTargets) {{
    Ensure-CodexShortcut -Path $shortcutPath -Target $cmd -WorkingDirectory (Split-Path $cmd) -Icon "$exe,0"
  }}
}}
"""
    run_ps(script, dry_run=dry_run)


def setup_win11(args: argparse.Namespace) -> int:
    source = args.source or discover_win_store_app()
    dest = args.dest or expand_win_path(DEFAULT_WIN_DEST)
    profile = args.profile or DEFAULT_WIN_PROFILE
    source_version = detect_win_store_version(source)
    repair_route, repair_note = repair_route_for_version(source_version)

    print(f"Win11 Codex source: {source}")
    print(f"Win11 Codex Store version: {source_version or 'unknown'}")
    print(f"Fast repair route: {repair_route}")
    print(f"Fast repair note: {repair_note}")
    print(f"Writable patched copy: {dest}")
    print(f"User data dir: {profile}")

    copy_win_app(source, dest, dry_run=args.dry_run)
    asar = win_to_wsl_path(str(PureWindowsPath(dest) / "resources" / "app.asar"))
    bundle_patch_status = "skipped: dry-run"
    if args.dry_run:
        print(f"Would patch copied asar: {asar}")
    else:
        try:
            patches = bundle_patch.patch_asar(asar, asar.with_name("app.connection-fast-patched.asar"), dry_run=False)
        except SystemExit as exc:
            if repair_route != "provider_override_required":
                raise
            bundle_patch_status = (
                "skipped: bundle pattern changed for 26.616+; scoped provider override remains required "
                f"({exc})"
            )
            print(f"WARNING: {bundle_patch_status}", file=sys.stderr)
        else:
            if repair_route == "provider_override_required":
                bundle_patch_status = (
                    f"best-effort: applied {patches} bundle patch(es), but 26.616+ still requires scoped provider override"
                )
            else:
                bundle_patch_status = f"applied: {patches} bundle patch(es)"
            backup = asar.with_name("app.asar.connection-fast-backup")
            if not backup.exists():
                shutil.copy2(asar, backup)
                print(f"Backup written: {backup}")
            shutil.copy2(asar.with_name("app.connection-fast-patched.asar"), asar)
            print(f"Patched copied app.asar in place: {asar}")
    print(f"Bundle patch status: {bundle_patch_status}")

    setup_metadata = metadata_json(
        source=source,
        dest=dest,
        profile=profile,
        source_version=source_version,
        repair_route=repair_route,
        repair_note=repair_note,
        bundle_patch_status=bundle_patch_status,
        shortcut_scope=args.shortcut_scope,
        shortcut_name=args.shortcut_name,
    )

    write_win_launchers(
        dest,
        profile,
        args.shortcut_scope,
        args.shortcut_name,
        setup_metadata,
        dry_run=args.dry_run,
    )

    if args.launch:
        launcher = str(PureWindowsPath(dest).parent / "Start-Codex-Fast-Connections.ps1")
        run_ps(f"& {ps_quote(launcher)}", dry_run=args.dry_run)

    return 0


def setup_macos(args: argparse.Namespace) -> int:
    asar = Path(args.asar or "/Applications/Codex.app/Contents/Resources/app.asar")
    print(f"macOS Codex app.asar: {asar}")
    if args.dry_run:
        bundle_patch.patch_asar(asar, asar.with_name("app.connection-fast-patched.asar"), dry_run=True)
        return 0
    bundle_patch.patch_asar(asar, asar.with_name("app.connection-fast-patched.asar"), dry_run=False)
    backup = asar.with_name("app.asar.connection-fast-backup")
    if not backup.exists():
        shutil.copy2(asar, backup)
        print(f"Backup written: {backup}")
    shutil.copy2(asar.with_name("app.connection-fast-patched.asar"), asar)
    print(f"Patched in place: {asar}")

    if args.launch:
        run(["open", "-a", "Codex"], dry_run=args.dry_run)
    return 0


def infer_platform() -> str:
    if Path("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe").exists():
        return "win11"
    if platform.system() == "Darwin":
        return "macos"
    raise SystemExit("Could not infer platform. Pass --platform win11 or --platform macos.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up Codex Desktop so WSL/SSH Connections can preserve Fast service tier."
    )
    parser.add_argument("--platform", choices=["auto", "win11", "macos"], default="auto")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--launch", action="store_true", help="Launch Codex Desktop after setup.")
    parser.add_argument("--source", help="Win11 Codex app source directory. Defaults to the Store package.")
    parser.add_argument("--dest", help=f"Win11 writable app copy. Default: {argparse_help_value(DEFAULT_WIN_DEST)}")
    parser.add_argument("--profile", help=f"Win11 user-data-dir. Default: {DEFAULT_WIN_PROFILE}")
    parser.add_argument(
        "--shortcut-scope",
        choices=["none", "desktop", "start-menu", "both"],
        default="both",
        help="Win11 shortcut locations. Default: both.",
    )
    parser.add_argument(
        "--shortcut-name",
        default=DEFAULT_WIN_SHORTCUT_NAME,
        help=f"Win11 shortcut name. Default: {DEFAULT_WIN_SHORTCUT_NAME!r}.",
    )
    parser.add_argument("--asar", help="macOS app.asar path. Defaults to /Applications/Codex.app/...")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = infer_platform() if args.platform == "auto" else args.platform
    if target == "win11":
        return setup_win11(args)
    if target == "macos":
        return setup_macos(args)
    raise SystemExit(f"Unsupported platform: {target}")


if __name__ == "__main__":
    raise SystemExit(main())
