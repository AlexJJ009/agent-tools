#!/usr/bin/env python3
"""Install root, managed file sync and old-layout migration for Agent Tools.

Software lives in the install root (default ~/.local/lib/agent-tools); task
state and process materials live in the data root resolved by
shared/materials.py. Installs refuse overlapping roots. Each managed tree keeps
a manifest of the files it installed so a reinstall deletes exactly the files a
previous install wrote and no longer ships; anything else is reported as
unmanaged and kept. Standard library only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MANIFEST = '.agent-tools-manifest.json'
SCHEMA = 'agent-tools.install-manifest/1'
PRODUCER = 'agent-tools-installer'
# Top-level items install.sh ships into the install root.
SHIPPED_FILES = ('README.md', 'agent_context_sync.config.example.json')
RELOCATED_SCRIPTS = ('install.sh', 'pack.sh', 'sync_agent_context.py', 'sync_agent_context_cron.sh',
                     'codex_project_memory.py', 'migrate_codex_provider_bucket.py')
SHIPPED_DIRS = ('bin', 'scripts', 'config', 'docs', 'skills', 'adapters', 'agent_workflow',
                'learning_workflow', 'project_adapters', 'shared')
RETIRED = ('linear_workflow', 'goal_plan', 'experiment_registry')  # shipped by earlier releases
BUNDLES = ('learning-workflow', 'claude')  # owned by their own installers inside the install root
GENERATED = ('agent_context_sync.config.json',)  # written by install.sh
FOREIGN = ('codex_target_guard.py',)  # scripts/codex_fleet_guard.py helper
DATA = ('tasks.sqlite3', 'tasks.sqlite3-wal', 'tasks.sqlite3-shm', 'tasks.sqlite3-journal',
        'artifacts', 'cleanup', 'archives', 'materials', 'logs')
SOFTWARE = SHIPPED_FILES + RELOCATED_SCRIPTS + SHIPPED_DIRS + RETIRED + BUNDLES + GENERATED
LEGACY_DATA_LAYOUT = '.local/share/agent-tools'  # where earlier releases put bundles on Linux/WSL


def install_root(home: Path | None = None) -> Path:
    """The one resolver: AGENT_TOOLS_INSTALL_ROOT, else ~/.local/lib/agent-tools."""
    value = os.environ.get('AGENT_TOOLS_INSTALL_ROOT')
    path = Path(value).expanduser() if value else Path(home or Path.home()) / '.local/lib/agent-tools'
    if not path.is_absolute():
        raise ValueError('install root must be absolute')
    return path.resolve()


def data_root() -> Path:
    from shared import materials
    return materials.data_root()


def overlaps(a: Path, b: Path) -> bool:
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def require_separate(install: Path, *, source: Path | None = None, data: Path | None = None) -> Path:
    data = Path(data or data_root()).resolve()
    if overlaps(install, data):
        raise ValueError(f'install root {Path(install).resolve()} overlaps data root {data}; '
                         'installed software and application data must be separate')
    if source is not None and Path(source).resolve().is_relative_to(data):
        raise ValueError(f'source {Path(source).resolve()} is inside data root {data}; '
                         'install from a checkout or the install root')
    return data


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _skipped(rel: Path) -> bool:
    return '__pycache__' in rel.parts or rel.suffix == '.pyc'


def tree_files(root: Path) -> dict[str, Path]:
    return {p.relative_to(root).as_posix(): p for p in sorted(root.rglob('*'))
            if (p.is_file() or p.is_symlink()) and not _skipped(p.relative_to(root)) and p.name != MANIFEST}


def source_files(source: Path) -> dict[str, Path]:
    """Shipped files; in a Git checkout only tracked or unignored ones (no local reports or secrets)."""
    source = Path(source).resolve()
    names = [n for n in SHIPPED_FILES + SHIPPED_DIRS if (source / n).exists()]
    listed = None
    if (source / '.git').exists():
        run = subprocess.run(['git', '-C', str(source), 'ls-files', '-z', '--cached', '--others',
                              '--exclude-standard', '--', *names], capture_output=True)
        if run.returncode == 0:
            listed = {r for r in run.stdout.decode().split('\0') if r}
    files = {}
    for name in names:
        path = source / name
        candidates = {name: path} if path.is_file() else {f'{name}/{k}': v for k, v in tree_files(path).items()}
        for rel, item in candidates.items():
            if (listed is None or rel in listed) and item.is_file() and not _skipped(Path(rel)):
                files[rel] = item
    return files


def read_manifest(dest: Path) -> dict[str, str] | None:
    path = Path(dest) / MANIFEST
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    if data.get('schema') != SCHEMA or not isinstance(data.get('files'), dict):
        raise ValueError(f'invalid install manifest: {path}')
    return data['files']


def write_manifest(dest: Path, files: dict[str, str]) -> None:
    _atomic(Path(dest) / MANIFEST, (json.dumps({'schema': SCHEMA, 'files': files}, indent=1, sort_keys=True) + '\n').encode(), 0o644)


def _atomic(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix='.agent-tools-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
        os.chmod(raw, mode)
        os.replace(raw, path)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def _prune(path: Path, stop: Path) -> None:
    while path != stop and path.is_dir() and not any(path.iterdir()):
        path.rmdir()
        path = path.parent


def unmanaged(dest: Path, managed, keep=()) -> list[str]:
    """Files under dest that no manifest owns; whole unknown top-level dirs are listed once."""
    dest, managed = Path(dest), set(managed)
    tops = {rel.split('/', 1)[0] for rel in managed}
    result = []
    for child in sorted(dest.iterdir()) if dest.is_dir() else []:
        if child.name in keep or child.name == MANIFEST or _skipped(Path(child.name)):
            continue
        if child.name not in tops:
            result.append(child.name + ('/' if child.is_dir() and not child.is_symlink() else ''))
        elif child.is_dir() and not child.is_symlink():
            result += [f'{child.name}/{rel}' for rel in tree_files(child) if f'{child.name}/{rel}' not in managed]
    return result


def sync_tree(dest: Path, files: dict[str, Path | bytes], *, previous=None, keep=()) -> dict:
    """Make dest hold files; delete files the previous manifest owned that are no longer shipped."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    old = read_manifest(dest)
    old = dict(old if old is not None else previous or {})
    report = {'added': [], 'updated': [], 'removed': [], 'unchanged': 0}
    new = {}
    for rel, src in sorted(files.items()):
        data = src if isinstance(src, bytes) else Path(src).read_bytes()
        mode = 0o644 if isinstance(src, bytes) else (0o755 if os.access(src, os.X_OK) else 0o644)
        new[rel] = sha256(data)
        target = dest / rel
        if target.is_file() and not target.is_symlink() and sha256(target.read_bytes()) == new[rel]:
            if target.stat().st_mode & 0o777 != mode:
                target.chmod(mode)
            report['unchanged'] += 1
            continue
        report['updated' if target.exists() or target.is_symlink() else 'added'].append(rel)
        if target.is_symlink():
            target.unlink()
        _atomic(target, data, mode)
    for rel in sorted(set(old) - set(new)):
        target = dest / rel
        if target.is_file() or target.is_symlink():
            target.unlink()
            report['removed'].append(rel)
        _prune(target.parent, dest)
    write_manifest(dest, new)
    report['unmanaged'] = unmanaged(dest, new, keep)
    return report


def check_tree(dest: Path, files: dict[str, Path | bytes], keep=()) -> dict:
    dest = Path(dest)
    owned = read_manifest(dest) if dest.is_dir() else None
    drift = {'missing': [], 'changed': [], 'stale': [], 'unmanaged': []}
    if owned is None:
        drift['missing'] = ['(no install manifest)']
        return drift
    for rel, src in sorted(files.items()):
        data = src if isinstance(src, bytes) else Path(src).read_bytes()
        target = dest / rel
        if not target.is_file():
            drift['missing'].append(rel)
        elif sha256(target.read_bytes()) != sha256(data) or owned.get(rel) != sha256(data):
            drift['changed'].append(rel)
    drift['stale'] = sorted(rel for rel in set(owned) - set(files) if (dest / rel).exists())
    drift['unmanaged'] = unmanaged(dest, files, keep)
    return drift


# -- consumers and old data-root layouts ---------------------------------------------------------

def _crontab() -> str | None:
    if not shutil.which('crontab'):
        return None
    run = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
    return run.stdout if run.returncode == 0 else None


def consumer_texts(home: Path) -> dict[str, str]:
    home = Path(home)
    codex = Path(os.environ.get('CODEX_HOME', home / '.codex'))
    texts = {}
    for path in (codex / 'hooks.json', codex / 'config.toml', codex / 'AGENTS.md',
                 home / '.claude/settings.json'):
        if path.is_file():
            texts[str(path)] = path.read_text(errors='replace')
    cron = _crontab()
    if cron:
        texts['crontab'] = cron
    return texts


def consumer_links(home: Path) -> dict[str, str]:
    home = Path(home)
    codex = Path(os.environ.get('CODEX_HOME', home / '.codex'))
    links = {}
    for base in (home / '.agents/skills', codex / 'skills', home / '.claude/skills',
                 home / '.claude/rules', home / '.local/bin'):
        for entry in sorted(base.iterdir()) if base.is_dir() else []:
            if entry.is_symlink():
                links[str(entry)] = os.path.abspath(os.path.join(entry.parent, os.readlink(entry)))
    for entry in (home / '.claude/CLAUDE.md', codex / 'AGENTS.md'):
        if entry.is_symlink():
            links[str(entry)] = os.path.abspath(os.path.join(entry.parent, os.readlink(entry)))
    return links


def references(home: Path, target: Path, *, texts=None, links=None) -> list[str]:
    """Consumers (skill/launcher links, hook/instruction files, crontab) that still point into target."""
    forms = {str(Path(target).absolute()), str(Path(target).resolve())}
    pattern = re.compile('|'.join(re.escape(form) for form in sorted(forms)) + r'(?![\w.-])')
    texts = consumer_texts(home) if texts is None else texts
    links = consumer_links(home) if links is None else links
    found = [name for name, text in texts.items() if pattern.search(text)]
    found += [name for name, dest in links.items()
              if any(d == f or d.startswith(f + os.sep) for d in (dest, os.path.realpath(dest)) for f in forms)]
    return found


def _git_objects(source: Path) -> set[str]:
    if not (Path(source) / '.git').exists():
        return set()
    run = subprocess.run(['git', '-C', str(source), 'rev-list', '--all', '--objects'],
                         capture_output=True, text=True)
    return {line.split(' ', 1)[0] for line in run.stdout.splitlines()} if run.returncode == 0 else set()


def _blob(data: bytes) -> str:
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def _known(item: Path, name: str, *, source: Path, install: Path, objects: set[str], retired: set[str]) -> bool:
    """True when every file is a released copy: current source, Git history, or a recorded retired bundle."""
    if item.is_dir() and not item.is_symlink() and not tree_files(item):
        return True  # nothing left but empty directories or caches
    if name in BUNDLES:
        from scripts import install_learning_workflow as learning  # bundle digest owner
        return item.is_dir() and learning.digest(item) in retired
    if name in GENERATED:
        current = install / name
        return item.is_file() and current.is_file() and item.read_bytes() == current.read_bytes()
    files = {name: item} if item.is_file() else {f'{name}/{k}': v for k, v in tree_files(item).items()}
    for rel, path in files.items():
        if path.is_symlink():
            return False
        data = path.read_bytes()
        current = source / rel
        if not (current.is_file() and current.read_bytes() == data) and _blob(data) not in objects:
            return False
    return True


def _retired_digests(home: Path) -> set[str]:
    digests = set()
    for path in (Path(home) / '.local/state/learning-workflow/install.json',):
        if path.is_file():
            data = json.loads(path.read_text())
            digests |= {entry['digest'] for entry in data.get('retired_bundles', []) if 'digest' in entry}
    return digests


def repoint_script_consumers(source: Path, install: Path, home: Path) -> list[str]:
    """Rewrite exact former script paths in known instruction/hook files and launcher links."""
    replacements = {str(root / name): str(install / 'scripts' / name)
                    for root in (Path(source).resolve(), Path(install).resolve(), data_root())
                    for name in RELOCATED_SCRIPTS}
    pattern = re.compile('(?:' + '|'.join(re.escape(old) for old in sorted(replacements, key=len, reverse=True))
                         + r')(?![\w./-])')
    updated = []
    texts = consumer_texts(home)
    relative_commands = {}
    config_path = install / 'agent_context_sync.config.json'
    if config_path.is_file():
        from scripts.sync_agent_context import scan_projects, GENERATED_MARKER
        config = json.loads(config_path.read_text())
        for root in config.get('scan_roots', []):
            for state in scan_projects(Path(root).expanduser(), int(config.get('max_depth', 3)), True):
                for path in (state.root / 'AGENTS.md', state.root / 'CLAUDE.md', state.root / '.codex/README.md'):
                    if path.is_file():
                        content = path.read_text()
                        if GENERATED_MARKER in content:
                            texts[str(path)] = content
                            commands = {}
                            for root in (Path(source).resolve(), Path(install).resolve(), data_root()):
                                if root.is_relative_to(state.root):
                                    relative = root.relative_to(state.root)
                                    old = str(relative / 'sync_agent_context.py')
                                    new = str(relative / 'scripts/sync_agent_context.py')
                                    commands[old] = new
                            relative_commands[str(path)] = commands
    for filename, content in texts.items():
        changed = pattern.sub(lambda match: replacements[match.group()], content)
        for old, new in relative_commands.get(filename, {}).items():
            command = re.compile(r'^(python\d*(?:\.\d+)* )' + re.escape(old)
                                 + r'(?= sync \. --direction bidirectional(?:\s|$))', re.MULTILINE)
            changed = command.sub(lambda match: match.group(1) + new, changed)
        if changed == content:
            continue
        if filename == 'crontab':
            subprocess.run(['crontab', '-'], input=changed, text=True, check=True)
        else:
            Path(filename).write_text(changed)
        updated.append(filename)
    for filename, dest in consumer_links(home).items():
        if dest in replacements:
            link = Path(filename)
            link.unlink()
            link.symlink_to(replacements[dest])
            updated.append(filename)
    return updated


def repoint_crontab(data: Path, install: Path) -> bool:
    cron = _crontab()
    old, new = str(data / 'sync_agent_context_cron.sh'), str(install / 'scripts/sync_agent_context_cron.sh')
    if not cron or old not in cron or not Path(new).is_file():
        return False
    subprocess.run(['crontab', '-'], input=cron.replace(old, new), text=True, check=True)
    return True


def classify(data: Path) -> dict[str, list[str]]:
    groups = {'software': [], 'data': [], 'unknown': []}
    for child in sorted(data.iterdir()) if data.is_dir() else []:
        groups['software' if child.name in SOFTWARE else 'data' if child.name in DATA else 'unknown'].append(child.name)
    return groups


def migrate(source: Path, install: Path, home: Path, *, stamp: str | None = None) -> dict:
    """Remove released software copies from the data root once no consumer points into them."""
    from shared import materials
    source, install = Path(source).resolve(), Path(install).resolve()
    data = require_separate(install, source=source)
    report = {'data_root': str(data), 'removed': [], 'archived': [], 'in_use': {}, 'data': [], 'unknown': [],
              'repointed_script_consumers': repoint_script_consumers(source, install, home),
              'crontab_repointed': repoint_crontab(data, install)}
    groups = classify(data)
    report['data'], report['unknown'] = groups['data'], groups['unknown']
    if not groups['software']:
        return report
    objects, retired = _git_objects(source), _retired_digests(home)
    texts, links = consumer_texts(home), consumer_links(home)
    stamp = stamp or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    archive = data / 'archives' / f'legacy-install-{stamp}'
    for name in groups['software']:
        item = data / name
        users = references(home, item, texts=texts, links=links)
        if users:
            report['in_use'][name] = users
            continue
        kind = 'dir' if item.is_dir() and not item.is_symlink() else 'file'
        if _known(item, name, source=source, install=install, objects=objects, retired=retired):
            shutil.rmtree(item) if kind == 'dir' else item.unlink()
            report['removed'].append(name)
            materials.record(item, PRODUCER, 'released software copy removed from the data root', 'removed', kind=kind)
        else:
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(archive / name))
            report['archived'].append(name)
            materials.record(item, PRODUCER, f'modified software copy moved to {archive / name}', 'removed', kind=kind)
    if report['archived']:
        materials.record(archive, PRODUCER, 'software copies from an old data-root install layout', 'created', kind='dir')
        report['archive'] = str(archive)
    return report


def check(source: Path, install: Path, home: Path) -> dict:
    source, install = Path(source).resolve(), Path(install).resolve()
    data = require_separate(install, source=source)
    drift = {} if source == install else check_tree(install, source_files(source), keep=BUNDLES + GENERATED + FOREIGN)
    software = classify(data)['software']
    texts, links = consumer_texts(home), consumer_links(home)
    pointing = {}
    for path in [data / name for name in software] + [Path(home) / LEGACY_DATA_LAYOUT / b for b in BUNDLES]:
        users = references(home, path, texts=texts, links=links)
        if users:
            pointing[str(path)] = users
    bad = any(drift.get(k) for k in ('missing', 'changed', 'stale')) or software or pointing
    return {'status': 'drift' if bad else 'pass', 'install_root': str(install), 'data_root': str(data),
            'tree': drift, 'software_in_data_root': software, 'consumers_into_data_root': pointing}


def _print(report: dict) -> None:
    print(json.dumps(report, indent=1, sort_keys=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('roots', 'sync', 'check', 'migrate'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--install-root', type=Path)
        cmd.add_argument('--source', type=Path, default=ROOT)
        cmd.add_argument('--home', type=Path, default=Path.home())
    sub.add_parser('data-root')
    args = parser.parse_args(argv)
    try:
        if args.command == 'data-root':
            print(data_root())
            return 0
        install = args.install_root.expanduser().resolve() if args.install_root else install_root(args.home)
        if args.command == 'roots':
            require_separate(install, source=args.source)
            print(install)
        elif args.command == 'sync':
            require_separate(install, source=args.source)
            report = sync_tree(install, source_files(args.source), keep=BUNDLES + GENERATED + FOREIGN)
            report['repointed_consumers'] = repoint_script_consumers(args.source, install, args.home)
            _print(report)
        elif args.command == 'migrate':
            _print(migrate(args.source, install, args.home))
        else:
            report = check(args.source, install, args.home)
            _print(report)
            return 0 if report['status'] == 'pass' else 1
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'agent-tools install layout: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
