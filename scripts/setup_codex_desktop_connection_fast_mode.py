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
import platform
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import patch_codex_desktop_connection_fast_mode as bundle_patch


DEFAULT_WIN_DEST = r"%LOCALAPPDATA%\OpenAI\CodexDesktopPatched\app"
DEFAULT_WIN_PROFILE = r"C:\Users\Public\CodexPatchedProfile"


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


def copy_win_app(source: str, dest: str, *, dry_run: bool) -> None:
    script = f"""
$src = {ps_quote(source)}
$dst = {ps_quote(dest)}
if (-not (Test-Path $src)) {{ throw "Source Codex app not found: $src" }}
New-Item -ItemType Directory -Force -Path $dst | Out-Null
robocopy $src $dst /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
$code = $LASTEXITCODE
if ($code -gt 7) {{ throw "robocopy failed with exit code $code" }}
Write-Output $dst
"""
    run_ps(script, dry_run=dry_run)


def write_win_launchers(dest: str, profile: str, *, dry_run: bool) -> None:
    dest_path = PureWindowsPath(dest)
    root_path = dest_path.parent
    ps1 = str(root_path / "Start-Codex-Fast-Connections.ps1")
    cmd = str(root_path / "Start-Codex-Fast-Connections.cmd")
    exe = str(dest_path / "Codex.exe")
    resources_codex = str(dest_path / "resources" / "codex.exe")

    script = f"""
$exe = {ps_quote(exe)}
$profile = {ps_quote(profile)}
$ps1 = {ps_quote(ps1)}
$cmd = {ps_quote(cmd)}
$codexCli = {ps_quote(resources_codex)}
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
Write-Output "Launcher written: $ps1"
Write-Output "Launcher written: $cmd"
if (Test-Path $codexCli) {{ Write-Output "Bundled app-server CLI: $codexCli" }}
"""
    run_ps(script, dry_run=dry_run)


def setup_win11(args: argparse.Namespace) -> int:
    source = args.source or discover_win_store_app()
    dest = args.dest or expand_win_path(DEFAULT_WIN_DEST)
    profile = args.profile or DEFAULT_WIN_PROFILE

    print(f"Win11 Codex source: {source}")
    print(f"Writable patched copy: {dest}")
    print(f"User data dir: {profile}")

    copy_win_app(source, dest, dry_run=args.dry_run)
    asar = win_to_wsl_path(str(PureWindowsPath(dest) / "resources" / "app.asar"))
    if args.dry_run:
        print(f"Would patch copied asar: {asar}")
    else:
        bundle_patch.patch_asar(asar, asar.with_name("app.connection-fast-patched.asar"), dry_run=False)
        backup = asar.with_name("app.asar.connection-fast-backup")
        if not backup.exists():
            shutil.copy2(asar, backup)
            print(f"Backup written: {backup}")
        shutil.copy2(asar.with_name("app.connection-fast-patched.asar"), asar)
        print(f"Patched copied app.asar in place: {asar}")

    write_win_launchers(dest, profile, dry_run=args.dry_run)

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
    parser.add_argument("--dest", help=f"Win11 writable app copy. Default: {DEFAULT_WIN_DEST}")
    parser.add_argument("--profile", help=f"Win11 user-data-dir. Default: {DEFAULT_WIN_PROFILE}")
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
