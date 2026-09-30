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


def managed_install_exists(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str) -> bool:
    for source, target in target_pairs(descriptor, repo_root, home):
        if marker_for(source, target).is_file():
            return True
    runtime_home, _, _ = runtime_paths(descriptor, home, platform)
    manifest = runtime_home.parent / "install-manifest.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return value.get("package") == descriptor["name"]


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


MANAGED_MARKER = "managed by agent-tools managed_package_installer.py\n"


def _safe_home_path(home: Path, path: Path) -> None:
    home = home.absolute()
    path = path.absolute()
    if path == home or not path.is_relative_to(home) or '..' in path.parts:
        raise InstallerError(f"discovery target escapes home: {path}")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise InstallerError(f"symlink in discovery path: {part}")
        if part == home:
            break


def discovery_targets(descriptor: dict[str, Any], repo_root: Path, home: Path) -> list[tuple[Path, Path]]:
    """Only declared client targets, including sibling versions of a cache target."""
    pairs = []
    for group in ('codex_targets', 'claude_targets'):
        for item in descriptor[group]:
            source = repo_root / item['source']
            destination = item['destination']
            target = home / destination.format(version=descriptor['resolved_version'])
            _safe_home_path(home, target)
            relative = Path(destination)
            if relative.parts[:2] in (('.codex', 'skills'), ('.claude', 'skills'), ('.claude', 'commands')):
                if target.parent.is_dir():
                    for backup in target.parent.glob(target.name + '.backup-*'):
                        _safe_home_path(home, backup)
                        discoverable = backup / 'SKILL.md' if source.is_dir() else backup
                        if discoverable.exists() or discoverable.is_symlink():
                            raise InstallerError(f'unmanaged discoverable backup must be resolved explicitly: {backup}')
            pairs.append((source, target))
            # Do not glob the profile: only this explicitly declared package cache.
            if '{version}' in destination:
                relative = Path(destination)
                if relative.name != '{version}' or relative.parts[:3] != ('.codex', 'plugins', 'cache'):
                    raise InstallerError('version expansion is only supported for declared plugin cache directories')
                if target.parent.is_dir():
                    for sibling in sorted(target.parent.iterdir()):
                        if sibling != target:
                            _safe_home_path(home, sibling)
                            pairs.append((source, sibling))
    retained = [home / '.local/share' / descriptor['name']]
    retained.extend(home / item['destination'].format(version=descriptor['resolved_version'])
                    for item in descriptor.get('shared_targets', []))
    unique = {}
    for source, target in pairs:
        if any(target.is_relative_to(path) or path.is_relative_to(target) for path in retained):
            raise InstallerError(f'discovery target overlaps retained runtime/shared storage: {target}')
        unique[str(target)] = (source, target)
    return list(unique.values())


def _marketplace_state(home: Path, descriptor: dict[str, Any]):
    path = home / '.agents/plugins/marketplace.json'
    _safe_home_path(home, path)
    if not path.exists():
        return path, None, []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(f'cannot inspect marketplace: {exc}') from exc
    if not isinstance(data, dict) or not isinstance(data.get('plugins', []), list):
        raise InstallerError('invalid personal marketplace shape')
    registration = descriptor['plugin_registration']
    matching = []
    for item in data.get('plugins', []):
        if not isinstance(item, dict):
            raise InstallerError('invalid personal marketplace plugin entry')
        if item.get('name') == registration['name']:
            if item.get('source') != {'source': 'local', 'path': registration['path']}:
                raise InstallerError('same-name marketplace entry has an unmanaged source')
            matching.append(item)
    return path, data, matching


def disabled_report(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str) -> list[str]:
    remaining = []
    for source, target in discovery_targets(descriptor, repo_root, home):
        marker = marker_for(source, target)
        if target.exists() or marker.exists():
            remaining.append(str(target))
    _, _, launcher = runtime_paths(descriptor, home, platform)
    _safe_home_path(home, launcher)
    if launcher.exists():
        remaining.append(str(launcher))
    path, _, matches = _marketplace_state(home, descriptor)
    if matches:
        remaining.append(str(path) + '#' + descriptor['plugin_registration']['name'])
    return remaining


def _disable_manifest(descriptor, home, platform):
    runtime_home, _, _ = runtime_paths(descriptor, home, platform)
    path = runtime_home.parent / 'install-manifest.json'
    _safe_home_path(home, path)
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(f'cannot inspect install manifest: {exc}') from exc
    if (manifest.get('package') != descriptor['name'] or manifest.get('home') != str(home.resolve())
            or manifest.get('platform') != platform):
        raise InstallerError('install manifest belongs to a different package or profile')
    return {item['path']: item['sha256'] for item in manifest.get('targets', [])}


def _verify_migrated_commands(target: Path) -> None:
    """Accept only Codex's exact generated wrapper of a verified command file."""
    if not target.is_dir():
        return
    for path in target.rglob('*'):
        relative = path.relative_to(target)
        if 'migrated-command-skills' not in relative.parts or not path.is_file():
            continue
        parts = relative.parts
        if (len(parts) != 4 or parts[:2] != ('.codex-plugin', 'migrated-command-skills')
                or parts[3] != 'SKILL.md' or not parts[2].startswith('source-command-')):
            raise InstallerError(f'unverified migrated discovery content: {path}')
        command_name = parts[2].removeprefix('source-command-')
        command = target / 'commands' / f'{command_name}.md'
        if not command.is_file():
            raise InstallerError(f'migrated skill has no verified command: {path}')
        text = command.read_text(encoding='utf-8')
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:
            raise InstallerError(f'unsupported command frontmatter: {command}')
        header, body = text[4:].split('\n---\n', 1)
        descriptions = [line[len('description: '):] for line in header.splitlines() if line.startswith('description: ')]
        if len(descriptions) != 1:
            raise InstallerError(f'unsupported command description: {command}')
        name = f'source-command-{command_name}'
        expected = (f'---\nname: {json.dumps(name, ensure_ascii=False)}\n'
                    f'description: {json.dumps(descriptions[0], ensure_ascii=False)}\n---\n\n'
                    f'# {name}\n\n'
                    f'Use this skill when the user asks to run the migrated source command `{command_name}`.\n\n'
                    f'## Command Template\n\n{body.strip()}\n')
        if path.read_bytes() != expected.encode('utf-8'):
            raise InstallerError(f'modified migrated command skill: {path}')


def disable(descriptor: dict[str, Any], repo_root: Path, home: Path, platform: str) -> None:
    """Remove verified discovery entries; retain runtime, shared files and data.

    Preflight every target before removing any. A changed or unmanaged target is
    a conflict, not permission to erase it. Repeating after partial removal is safe.
    """
    pairs = discovery_targets(descriptor, repo_root, home)
    manifest = _disable_manifest(descriptor, home, platform)
    remove = []
    for source, target in pairs:
        marker = marker_for(source, target)
        _safe_home_path(home, marker)
        if not target.exists() and not marker.exists():
            continue
        if not marker.is_file() or marker.read_text(encoding='utf-8') != MANAGED_MARKER:
            raise InstallerError(f'unmanaged discovery target: {target}')
        if target.exists():
            paths = [target, *target.rglob('*')] if target.is_dir() else [target]
            for path in paths:
                if path.is_symlink() or not (path.is_dir() or path.is_file()):
                    raise InstallerError(f'non-regular discovery content: {path}')
                relative = path.relative_to(target)
                if path.is_file() and '__pycache__' in relative.parts and path.suffix != '.pyc':
                    raise InstallerError(f'unverified cache content: {path}')
                if path.name == '.agent-tools-managed' and path != marker:
                    raise InstallerError(f'unverified nested marker: {path}')
            if not (manifest.get(str(target)) == fingerprint(target) or compare_tree(source, target)):
                raise InstallerError(f'modified discovery target: {target}')
            _verify_migrated_commands(target)
        remove.append((target, marker))
    _, executable, launcher = runtime_paths(descriptor, home, platform)
    _safe_home_path(home, launcher)
    if launcher.exists():
        expected = (f'@echo off\r\n"{executable}" %*\r\n' if platform == 'win11'
                    else f'#!/usr/bin/env bash\nexec "{executable}" "$@"\n')
        expected_bytes = {expected.encode('ascii' if platform == 'win11' else 'utf-8')}
        if platform == 'win11':
            expected_bytes.add(expected.replace('\r\n', '\r\r\n').encode('ascii'))
        if not launcher.is_file() or launcher.read_bytes() not in expected_bytes:
            raise InstallerError(f'unmanaged or modified launcher: {launcher}')
    marketplace, data, matches = _marketplace_state(home, descriptor)
    if not remove and not launcher.exists() and not matches:
        return
    guard = repo_root / 'scripts/codex_target_guard.py'
    subprocess.run([sys.executable, str(guard), '--platform', 'win11' if platform == 'win11' else 'auto',
                    '--codex-home', str(home / '.codex'), '--cc-switch-db', str(home / '.cc-switch/cc-switch.db'),
                    '--path-only', '--allow-missing-config', '--allow-missing-cc-switch',
                    '--skip-cc-switch-read-check'], check=True, capture_output=True, text=True)
    for target, marker in remove:
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        if marker.exists():
            marker.unlink()
    if launcher.exists():
        launcher.unlink()
    if matches:
        data['plugins'] = [item for item in data['plugins'] if item not in matches]
        marketplace.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def install(
    descriptor: dict[str, Any],
    repo_root: Path,
    home: Path,
    platform: str,
    uv: str,
    skip_runtime: bool,
    skip_plugin_registration: bool,
) -> None:
    if descriptor.get('status') == 'disabled':
        raise InstallerError(f"package {descriptor['name']} is disabled; source is retained but installation is prohibited")
    for source, target in target_pairs(descriptor, repo_root, home):
        copy_managed(source, target)
    if not skip_plugin_registration:
        update_marketplace(home, descriptor)
    if not skip_runtime:
        install_runtime(descriptor, repo_root, home, platform, uv)
        write_manifest(descriptor, repo_root, home, platform)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["validate", "pairs", "install", "disable", "check", "managed-status"],
    )
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--platform", choices=["unix", "win11"], default="unix")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--skip-runtime", action="store_true")
    parser.add_argument("--skip-plugin-registration", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        descriptor = load_descriptor(args.descriptor, args.repo_root)
        if args.command == "managed-status":
            if not managed_install_exists(descriptor, args.repo_root, args.home, args.platform):
                print(f'{descriptor["name"]} managed install: absent')
                return 1
            print(f'{descriptor["name"]} managed install: present')
        elif args.command == "pairs":
            for source, target in target_pairs(descriptor, args.repo_root, args.home):
                print(f"{source}\t{target}")
        elif args.command == "install":
            install(
                descriptor,
                args.repo_root,
                args.home,
                args.platform,
                args.uv,
                args.skip_runtime,
                args.skip_plugin_registration,
            )
        elif args.command == "disable":
            disable(descriptor, args.repo_root, args.home, args.platform)
            print(f'{descriptor["name"]} discovery: disabled; runtime and data retained')
        elif args.command == "check":
            checker = disabled_report if descriptor.get("status") == "disabled" else drift_report
            drift = checker(descriptor, args.repo_root, args.home, args.platform)
            if drift:
                for path in drift:
                    print(f"DRIFT: {path}")
                return 1
            print(f'{descriptor["name"]} discovery: disabled' if descriptor.get("status") == "disabled" else f'{descriptor["name"]} managed copies: in sync')
        else:
            print(json.dumps({"name": descriptor["name"], "version": descriptor["resolved_version"]}, sort_keys=True))
        return 0
    except (InstallerError, OSError, subprocess.SubprocessError) as exc:
        print(f"MANAGED_PACKAGE_INSTALLER=RED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
