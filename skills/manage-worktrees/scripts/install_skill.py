#!/usr/bin/env python3
"""Install one Codex Skill, preserving conflicts and verifying older releases."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

MARKER = 'managed by agent-tools install-win11.ps1'
SCHEMA = 'agent-tools.manage-worktrees-install/1'


def tree(path):
    result = {}
    for item in path.rglob('*'):
        if item.is_symlink():
            raise ValueError(f'nested symlink in Skill: {item}')
        if item.is_file():
            rel = item.relative_to(path).as_posix()
            cached = re.fullmatch(r'(.+)\.(?:cpython|pypy)-\d+(?:\.opt-\d+)?\.pyc', item.name)
            if item.parent.name == '__pycache__' and cached:
                original = item.parent.parent / (cached.group(1) + '.py')
                if original.is_file() and not original.is_symlink():
                    continue
            if rel != '.agent-tools-managed':
                result[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
        elif not item.is_dir():
            raise ValueError(f'nonregular Skill content: {item}')
    return result


def approved(path, expected, baselines, source, known):
    if not path.is_dir():
        raise ValueError(f'broken or non-directory Skill: {path}')
    actual = tree(path)
    marker = path / '.agent-tools-managed'
    if marker.exists():
        text = marker.read_text(encoding='utf-8-sig').strip()
        if text == MARKER:
            if actual != expected and actual not in baselines:
                raise ValueError(f'old Skill marker without known release contents: {path}')
        else:
            try:
                manifest = json.loads(text)
            except ValueError as exc:
                raise ValueError(f'invalid Skill manifest: {path}') from exc
            if not isinstance(manifest, dict) or manifest.get('schema') != SCHEMA or manifest.get('files') != actual:
                raise ValueError(f'modified Skill content or invalid manifest: {path}')
    elif actual != expected and actual not in baselines:
        # Explicit old-source trust still requires byte identity with that tree.
        if not any(actual == snapshot for snapshot in known):
            raise ValueError(f'conflicting manage-worktrees Skill: {path}; preserve and resolve explicitly')
    return actual


def install(repo, home, codex, platform, known_sources=()):
    source = repo / 'skills/manage-worktrees'
    target = codex / 'skills/manage-worktrees'
    legacy = home / '.agents/skills/manage-worktrees'
    if not (source / 'SKILL.md').is_file():
        raise ValueError(f'Skill source missing: {source}')
    for path in (target, legacy):
        if '..' in path.parts or not path.is_relative_to(home):
            raise ValueError(f'Skill target escapes profile: {path}')
        for parent in path.parents:
            if parent.is_symlink():
                raise ValueError(f'symlink in Skill parent: {parent}')
            if parent == home:
                break
    expected = tree(source)
    baseline_file = source / 'references/installation-baselines.json'
    baselines = [entry['files'] for entry in json.loads(baseline_file.read_text())['releases']]
    known = [tree(p) for p in known_sources if p.is_dir()]
    originals = {}
    for path in (target, legacy):
        if path.exists() or path.is_symlink():
            originals[path] = approved(path, expected, baselines, source, known)
    subprocess.run([sys.executable, str(repo / 'scripts/codex_target_guard.py'),
                    '--platform', 'win11' if platform == 'win11' else 'auto',
                    '--codex-home', str(codex), '--cc-switch-db', str(home / '.cc-switch/cc-switch.db'),
                    '--path-only', '--allow-missing-config', '--allow-missing-cc-switch',
                    '--skip-cc-switch-read-check'], check=True)
    codex.mkdir(parents=True, exist_ok=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Stage outside Skill discovery, on the canonical target's filesystem.
    work = Path(tempfile.mkdtemp(prefix='.manage-worktrees-install-', dir=codex))
    candidate, old, old_legacy = work / 'candidate', work / 'canonical', work / 'legacy'
    published = False
    committed = False
    try:
        if platform == 'win11':
            shutil.copytree(source, candidate)
            (candidate / '.agent-tools-managed').write_text(json.dumps({'schema': SCHEMA, 'files': expected}, sort_keys=True) + '\n')
        else:
            candidate.symlink_to(source, target_is_directory=True)
        if tree(candidate) != expected:
            raise ValueError('staged Skill verification failed')
        for path, snapshot in originals.items():
            if not path.is_dir() or tree(path) != snapshot:
                raise ValueError(f'Skill changed during installation: {path}')
        if target.exists() or target.is_symlink():
            target.rename(old)
        candidate.rename(target)
        published = True
        if tree(target) != expected:
            raise ValueError('published Skill verification failed')
        if legacy.exists() or legacy.is_symlink():
            legacy.rename(old_legacy)
        committed = True
    except BaseException:
        # Never clean backups if rollback itself fails; expose work path for recovery.
        try:
            if old_legacy.exists() or old_legacy.is_symlink():
                old_legacy.rename(legacy)
            if published:
                target.rename(candidate)
            if old.exists() or old.is_symlink():
                old.rename(target)
        except BaseException as rollback_error:
            raise RuntimeError(f'rollback incomplete; preserve {work}') from rollback_error
        shutil.rmtree(work)
        raise
    if committed:
        shutil.rmtree(work)
    print(f'manage-worktrees canonical Skill: {target}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    parser.add_argument('--codex-home', type=Path, required=True)
    parser.add_argument('--platform', choices=('unix', 'win11'), required=True)
    parser.add_argument('--known-source', type=Path, action='append', default=[])
    args = parser.parse_args()
    try:
        install(args.repo_root.resolve(), args.home.absolute(), args.codex_home.absolute(), args.platform, args.known_source)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'manage-worktrees installation refused: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
