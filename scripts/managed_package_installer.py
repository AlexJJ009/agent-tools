#!/usr/bin/env python3
"""Minimal descriptor-driven managed package installer shared by Unix and Win11."""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import stat
import subprocess
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class InstallerError(RuntimeError):
    pass


REQUIRED = {
    "schema_version", "name", "runtime", "codex_targets", "claude_targets",
    "plugin_registration", "launcher", "legacy_policy",
}


def load_descriptor(path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(f"invalid descriptor {path}: {exc}") from exc
    missing = REQUIRED - set(data)
    if missing:
        raise InstallerError(f"descriptor missing fields: {', '.join(sorted(missing))}")
    if data["schema_version"] != 1:
        raise InstallerError("unsupported descriptor schema_version")
    version = data.get("version")
    if not version:
        version_path = repo_root / data.get("version_file", "")
        if not version_path.is_file():
            raise InstallerError(f"missing version source: {version_path}")
        version = version_path.read_text(encoding="utf-8").strip()
    if not version:
        raise InstallerError("package version is empty")
    data["resolved_version"] = version
    data.setdefault("shared_targets", [])
    for group in ("codex_targets", "claude_targets", "shared_targets"):
        if not isinstance(data[group], list):
            raise InstallerError(f"{group} must be a list")
        for target in data[group]:
            if set(target) != {"source", "destination"}:
                raise InstallerError(f"invalid target in {group}")
    return data


def target_records(descriptor: dict[str, Any], repo_root: Path, home: Path) -> list[tuple[str, Path, Path]]:
    version = descriptor["resolved_version"]
    pairs: list[tuple[str, Path, Path]] = []
    for group in ("claude_targets", "codex_targets", "shared_targets"):
        for target in descriptor[group]:
            src = repo_root / target["source"]
            dst = home / target["destination"].format(version=version)
            pairs.append((group.removesuffix("_targets"), src, dst))
    return pairs


def target_pairs(descriptor: dict[str, Any], repo_root: Path, home: Path) -> list[tuple[Path, Path]]:
    return [(source, target) for _, source, target in target_records(descriptor, repo_root, home)]


def marker_for(source: Path, target: Path) -> Path:
    return target / ".agent-tools-managed" if source.is_dir() else Path(str(target) + ".agent-tools-managed")


def backup_name(target: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return target.with_name(f"{target.name}.backup-{stamp}")


def copy_managed(source: Path, target: Path, *, dry_run: bool = False) -> Path | None:
    if not source.exists():
        raise InstallerError(f"missing source for copy: {source}")
    marker = marker_for(source, target)
    backup: Path | None = None
    if dry_run:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if marker.is_file():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
            if marker.exists() and marker != target / ".agent-tools-managed":
                marker.unlink()
        else:
            backup = backup_name(target)
            target.replace(backup)
    if source.is_dir():
        shutil.copytree(source, target)
        marker = target / ".agent-tools-managed"
    else:
        shutil.copy2(source, target)
    marker.write_text("managed by agent-tools managed_package_installer.py\n", encoding="utf-8")
    return backup


def update_marketplace(home: Path, descriptor: dict[str, Any]) -> None:
    path = home / ".agents" / "plugins" / "marketplace.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            shutil.copy2(path, Path(str(path) + ".invalid-backup"))
            data = {}
    data.setdefault("name", "personal")
    data.setdefault("interface", {}).setdefault("displayName", "Personal")
    registration = descriptor["plugin_registration"]
    plugins = [p for p in data.get("plugins", []) if p.get("name") != registration["name"]]
    plugins.append({
        "name": registration["name"],
        "source": {"source": "local", "path": registration["path"]},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": registration["category"],
    })
    data["plugins"] = plugins
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)


def runtime_paths(descriptor: dict[str, Any], home: Path, platform: str) -> tuple[Path, Path, Path]:
    package = descriptor["name"]
    runtime_home = home / ".local" / "share" / package / "runtime"
    if platform == "win11":
        executable = runtime_home / ".venv" / "Scripts" / f'{descriptor["runtime"]["entrypoint"]}.exe'
        launcher = home / ".local" / "bin" / descriptor["launcher"]["windows_name"]
    else:
        executable = runtime_home / ".venv" / "bin" / descriptor["runtime"]["entrypoint"]
        launcher = home / ".local" / "bin" / descriptor["launcher"]["name"]
    return runtime_home, executable, launcher


def install_runtime(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str, uv: str) -> None:
    runtime_source = repo_root / descriptor["runtime"]["source"]
    if not (runtime_source / "pyproject.toml").is_file():
        raise InstallerError(f"missing runtime package: {runtime_source}")
    runtime_home, executable, launcher = runtime_paths(descriptor, home, platform)
    runtime_home.mkdir(parents=True, exist_ok=True)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([uv, "venv", "--clear", "--python", "3.12", str(runtime_home / ".venv")], check=True)
    python = runtime_home / ".venv" / ("Scripts/python.exe" if platform == "win11" else "bin/python")
    subprocess.run([uv, "pip", "install", "--python", str(python), str(runtime_source)], check=True)
    if platform == "win11":
        launcher.write_text(f'@echo off\r\n"{executable}" %*\r\n', encoding="ascii")
    else:
        launcher.write_text(f'#!/usr/bin/env bash\nexec "{executable}" "$@"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def compare_tree(source: Path, target: Path) -> bool:
    if source.is_file():
        return target.is_file() and filecmp.cmp(source, target, shallow=False)
    if not target.is_dir():
        return False
    ignored = {".agent-tools-managed", "migrated-command-skills", "__pycache__"}
    left = {p.relative_to(source) for p in source.rglob("*") if not ignored.intersection(p.parts) and p.is_file()}
    right = {p.relative_to(target) for p in target.rglob("*") if not ignored.intersection(p.parts) and p.is_file()}
    return left == right and all(filecmp.cmp(source / rel, target / rel, shallow=False) for rel in left)


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    ignored = {".agent-tools-managed", "migrated-command-skills", "__pycache__"}
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file() and not ignored.intersection(p.parts)]
    for file in sorted(files, key=lambda item: str(item.relative_to(path) if path.is_dir() else item.name)):
        relative = str(file.relative_to(path)) if path.is_dir() else file.name
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_manifest(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str) -> Path:
    runtime_home, _, launcher = runtime_paths(descriptor, home, platform)
    records = []
    for client, _, target in target_records(descriptor, repo_root, home):
        records.append({"client": client, "path": str(target), "sha256": fingerprint(target)})
    manifest = {
        "schema_version": 1,
        "package": descriptor["name"],
        "version": descriptor["resolved_version"],
        "platform": platform,
        "home": str(home.resolve()),
        "launcher": str(launcher),
        "targets": records,
    }
    path = runtime_home.parent / "install-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return path


def drift_report(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str) -> list[str]:
    drift = [str(dst) for src, dst in target_pairs(descriptor, repo_root, home) if not compare_tree(src, dst)]
    runtime_home, _, launcher = runtime_paths(descriptor, home, platform)
    module = descriptor["runtime"]["module"]
    source_cli = repo_root / descriptor["runtime"]["source"] / "src" / module / "cli.py"
    glob = "Lib/site-packages" if platform == "win11" else "lib/python*/site-packages"
    installed = list((runtime_home / ".venv").glob(f"{glob}/{module}/cli.py"))
    if not installed or not filecmp.cmp(source_cli, installed[0], shallow=False):
        drift.append(str(runtime_home))
    if not launcher.is_file():
        drift.append(str(launcher))
    return drift


def install(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str, uv: str, skip_runtime: bool) -> None:
    for source, target in target_pairs(descriptor, repo_root, home):
        copy_managed(source, target)
    update_marketplace(home, descriptor)
    if not skip_runtime:
        install_runtime(descriptor, repo_root, home, platform, uv)
        write_manifest(descriptor, repo_root, home, platform)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "pairs", "install", "check"])
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--platform", choices=["unix", "win11"], default="unix")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--skip-runtime", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        descriptor = load_descriptor(args.descriptor, args.repo_root)
        if args.command == "pairs":
            for source, target in target_pairs(descriptor, args.repo_root, args.home):
                print(f"{source}\t{target}")
        elif args.command == "install":
            install(descriptor, args.repo_root, args.home, args.platform, args.uv, args.skip_runtime)
        elif args.command == "check":
            drift = drift_report(descriptor, args.repo_root, args.home, args.platform)
            if drift:
                for path in drift:
                    print(f"DRIFT: {path}")
                return 1
            print(f'{descriptor["name"]} managed copies: in sync')
        else:
            print(json.dumps({"name": descriptor["name"], "version": descriptor["resolved_version"]}, sort_keys=True))
        return 0
    except (InstallerError, OSError, subprocess.SubprocessError) as exc:
        print(f"MANAGED_PACKAGE_INSTALLER=RED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
