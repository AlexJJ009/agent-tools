#!/usr/bin/env python3
"""Remove verified client copies of a retired package whose source is gone.

A retirement record lists each formerly installed discovery target with the
fingerprint of its last shipped content. Only marked copies that match that
fingerprint (or the profile's own install manifest) are removed; runtime, shared
files and application data under ~/.local/share/<package> are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


class RetirementError(RuntimeError):
    pass


MANAGED_MARKER = "managed by agent-tools managed_package_installer.py\n"
IGNORED = {".agent-tools-managed", "migrated-command-skills", "__pycache__"}
DISCOVERY_ROOTS = (('.codex', 'skills'), ('.claude', 'skills'), ('.claude', 'commands'))


def load_record(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementError(f"invalid retirement record {path}: {exc}") from exc
    missing = {"schema_version", "name", "version", "targets", "plugin_registration", "launcher"} - set(data)
    if missing:
        raise RetirementError(f"retirement record missing fields: {', '.join(sorted(missing))}")
    if data["schema_version"] != 1 or not isinstance(data["targets"], list):
        raise RetirementError("unsupported retirement record")
    for target in data["targets"]:
        if set(target) != {"destination", "kind", "sha256"} or target["kind"] not in ("dir", "file"):
            raise RetirementError(f"invalid retirement target: {target}")
    return data


def marker_for(kind: str, target: Path) -> Path:
    return target / ".agent-tools-managed" if kind == "dir" else Path(str(target) + ".agent-tools-managed")


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file() and not IGNORED.intersection(p.parts)]
    for file in sorted(files, key=lambda item: str(item.relative_to(path) if path.is_dir() else item.name)):
        relative = str(file.relative_to(path)) if path.is_dir() else file.name
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def runtime_paths(record: dict[str, Any], home: Path, platform: str) -> tuple[Path, Path, Path]:
    runtime_home = home / ".local" / "share" / record["name"] / "runtime"
    launcher = record["launcher"]
    if platform == "win11":
        return (runtime_home, runtime_home / ".venv" / "Scripts" / f'{launcher["entrypoint"]}.exe',
                home / ".local" / "bin" / launcher["windows_name"])
    return runtime_home, runtime_home / ".venv" / "bin" / launcher["entrypoint"], home / ".local" / "bin" / launcher["name"]


def _safe_home_path(home: Path, path: Path) -> None:
    home = home.absolute()
    path = path.absolute()
    if path == home or not path.is_relative_to(home) or '..' in path.parts:
        raise RetirementError(f"discovery target escapes home: {path}")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise RetirementError(f"symlink in discovery path: {part}")
        if part == home:
            break


def discovery_targets(record: dict[str, Any], home: Path) -> list[tuple[dict[str, Any], Path]]:
    """Only recorded client targets, including sibling versions of a cache target."""
    pairs = []
    for item in record['targets']:
        destination = item['destination']
        target = home / destination.format(version=record['version'])
        _safe_home_path(home, target)
        relative = Path(destination)
        if relative.parts[:2] in DISCOVERY_ROOTS and target.parent.is_dir():
            for backup in target.parent.glob(target.name + '.backup-*'):
                _safe_home_path(home, backup)
                discoverable = backup / 'SKILL.md' if item['kind'] == 'dir' else backup
                if discoverable.exists() or discoverable.is_symlink():
                    raise RetirementError(f'unmanaged discoverable backup must be resolved explicitly: {backup}')
        pairs.append((item, target))
        # Do not glob the profile: only this explicitly recorded package cache.
        if '{version}' in destination:
            if relative.name != '{version}' or relative.parts[:3] != ('.codex', 'plugins', 'cache'):
                raise RetirementError('version expansion is only supported for declared plugin cache directories')
            if target.parent.is_dir():
                for sibling in sorted(target.parent.iterdir()):
                    if sibling != target:
                        _safe_home_path(home, sibling)
                        pairs.append((item, sibling))
    retained = home / '.local/share' / record['name']
    unique = {}
    for item, target in pairs:
        if target.is_relative_to(retained) or retained.is_relative_to(target):
            raise RetirementError(f'discovery target overlaps retained runtime/shared storage: {target}')
        unique[str(target)] = (item, target)
    return list(unique.values())


def _marketplace_state(home: Path, record: dict[str, Any]):
    path = home / '.agents/plugins/marketplace.json'
    _safe_home_path(home, path)
    if not path.exists():
        return path, None, []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementError(f'cannot inspect marketplace: {exc}') from exc
    if not isinstance(data, dict) or not isinstance(data.get('plugins', []), list):
        raise RetirementError('invalid personal marketplace shape')
    registration = record['plugin_registration']
    matching = []
    for item in data.get('plugins', []):
        if not isinstance(item, dict):
            raise RetirementError('invalid personal marketplace plugin entry')
        if item.get('name') == registration['name']:
            if item.get('source') != {'source': 'local', 'path': registration['path']}:
                raise RetirementError('same-name marketplace entry has an unmanaged source')
            matching.append(item)
    return path, data, matching


def remaining_report(record: dict[str, Any], home: Path, platform: str) -> list[str]:
    remaining = []
    for item, target in discovery_targets(record, home):
        if target.exists() or marker_for(item['kind'], target).exists():
            remaining.append(str(target))
    _, _, launcher = runtime_paths(record, home, platform)
    _safe_home_path(home, launcher)
    if launcher.exists():
        remaining.append(str(launcher))
    path, _, matches = _marketplace_state(home, record)
    if matches:
        remaining.append(str(path) + '#' + record['plugin_registration']['name'])
    return remaining


def _install_manifest(record, home, platform):
    runtime_home, _, _ = runtime_paths(record, home, platform)
    path = runtime_home.parent / 'install-manifest.json'
    _safe_home_path(home, path)
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetirementError(f'cannot inspect install manifest: {exc}') from exc
    if (manifest.get('package') != record['name'] or manifest.get('home') != str(home.resolve())
            or manifest.get('platform') != platform):
        raise RetirementError('install manifest belongs to a different package or profile')
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
            raise RetirementError(f'unverified migrated discovery content: {path}')
        command_name = parts[2].removeprefix('source-command-')
        command = target / 'commands' / f'{command_name}.md'
        if not command.is_file():
            raise RetirementError(f'migrated skill has no verified command: {path}')
        text = command.read_text(encoding='utf-8')
        if not text.startswith('---\n') or '\n---\n' not in text[4:]:
            raise RetirementError(f'unsupported command frontmatter: {command}')
        header, body = text[4:].split('\n---\n', 1)
        descriptions = [line[len('description: '):] for line in header.splitlines() if line.startswith('description: ')]
        if len(descriptions) != 1:
            raise RetirementError(f'unsupported command description: {command}')
        name = f'source-command-{command_name}'
        expected = (f'---\nname: {json.dumps(name, ensure_ascii=False)}\n'
                    f'description: {json.dumps(descriptions[0], ensure_ascii=False)}\n---\n\n'
                    f'# {name}\n\n'
                    f'Use this skill when the user asks to run the migrated source command `{command_name}`.\n\n'
                    f'## Command Template\n\n{body.strip()}\n')
        if path.read_bytes() != expected.encode('utf-8'):
            raise RetirementError(f'modified migrated command skill: {path}')


def remove(record: dict[str, Any], repo_root: Path, home: Path, platform: str) -> None:
    """Preflight every target before removing any; repeating after partial removal is safe.

    A changed or unmanaged target is a conflict, not permission to erase it.
    """
    pairs = discovery_targets(record, home)
    manifest = _install_manifest(record, home, platform)
    doomed = []
    for item, target in pairs:
        marker = marker_for(item['kind'], target)
        _safe_home_path(home, marker)
        if not target.exists() and not marker.exists():
            continue
        if not marker.is_file() or marker.read_text(encoding='utf-8') != MANAGED_MARKER:
            raise RetirementError(f'unmanaged discovery target: {target}')
        if target.exists():
            paths = [target, *target.rglob('*')] if target.is_dir() else [target]
            for path in paths:
                if path.is_symlink() or not (path.is_dir() or path.is_file()):
                    raise RetirementError(f'non-regular discovery content: {path}')
                relative = path.relative_to(target)
                if path.is_file() and '__pycache__' in relative.parts and path.suffix != '.pyc':
                    raise RetirementError(f'unverified cache content: {path}')
                if path.name == '.agent-tools-managed' and path != marker:
                    raise RetirementError(f'unverified nested marker: {path}')
            if fingerprint(target) not in (item['sha256'], manifest.get(str(target))):
                raise RetirementError(f'modified discovery target: {target}')
            _verify_migrated_commands(target)
        doomed.append((target, marker))
    _, executable, launcher = runtime_paths(record, home, platform)
    _safe_home_path(home, launcher)
    if launcher.exists():
        expected = (f'@echo off\r\n"{executable}" %*\r\n' if platform == 'win11'
                    else f'#!/usr/bin/env bash\nexec "{executable}" "$@"\n')
        expected_bytes = {expected.encode('ascii' if platform == 'win11' else 'utf-8')}
        if platform == 'win11':
            expected_bytes.add(expected.replace('\r\n', '\r\r\n').encode('ascii'))
        if not launcher.is_file() or launcher.read_bytes() not in expected_bytes:
            raise RetirementError(f'unmanaged or modified launcher: {launcher}')
    marketplace, data, matches = _marketplace_state(home, record)
    if not doomed and not launcher.exists() and not matches:
        return
    guard = repo_root / 'scripts/codex_target_guard.py'
    subprocess.run([sys.executable, str(guard), '--platform', 'win11' if platform == 'win11' else 'auto',
                    '--codex-home', str(home / '.codex'), '--cc-switch-db', str(home / '.cc-switch/cc-switch.db'),
                    '--path-only', '--allow-missing-config', '--allow-missing-cc-switch',
                    '--skip-cc-switch-read-check'], check=True, capture_output=True, text=True)
    for target, marker in doomed:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["remove", "check"])
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--platform", choices=["unix", "win11"], default="unix")
    args = parser.parse_args()
    try:
        record = load_record(args.record)
        if args.command == "remove":
            remove(record, args.repo_root, args.home, args.platform)
            print(f'{record["name"]} discovery: removed; runtime and data retained')
            return 0
        remaining = remaining_report(record, args.home, args.platform)
        for path in remaining:
            print(f"REMAINING: {path}")
        if not remaining:
            print(f'{record["name"]} discovery: absent')
        return 1 if remaining else 0
    except (RetirementError, OSError, subprocess.SubprocessError) as exc:
        print(f"RETIRED_PACKAGE_CLEANUP=RED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
