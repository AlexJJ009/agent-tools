#!/usr/bin/env python3
"""Install/check the local Linux/WSL work-report skill without changing model config."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.work-report-managed.json'


def files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()
            and '__pycache__' not in p.parts and p.name != MARKER and p.suffix != '.pyc'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='read-only source/install consistency check')
    args = parser.parse_args(argv)
    if platform.system() != 'Linux':
        parser.error('this installer supports the current Linux/WSL user only')
    home = Path.home().resolve()
    source = ROOT / 'skills/work-report'
    target = home / '.agents/skills/work-report'
    claude = home / '.claude/skills/work-report'
    duplicate = home / '.codex/skills/work-report'
    old = None
    published = False
    created_claude = False
    state = None
    try:
        guard = [sys.executable, str(ROOT / 'scripts/codex_target_guard.py'),
                 '--platform', 'auto', '--codex-home', str(home / '.codex'),
                 '--cc-switch-db', str(home / '.cc-switch/cc-switch.db'), '--path-only',
                 '--allow-missing-config', '--allow-missing-cc-switch',
                 '--skip-cc-switch-read-check', '--json']
        result = subprocess.run(guard, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('target guard rejected installation: ' + result.stdout + result.stderr)
        for required in ['SKILL.md', 'references/rubric.yaml', 'references/judge.md',
                         'assets/report.md', 'scripts/report_tool.py']:
            if not (source / required).is_file():
                raise RuntimeError('missing source: ' + required)
        if duplicate.exists() or duplicate.is_symlink():
            raise RuntimeError(f'duplicate skill location exists: {duplicate}; preserve it and resolve explicitly')
        if claude.exists() or claude.is_symlink():
            if not claude.is_symlink() or claude.resolve() != target.resolve():
                raise RuntimeError(f'unmanaged Claude skill exists: {claude}')
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not (target / MARKER).is_file():
                raise RuntimeError(f'unmanaged Codex skill exists: {target}')
            marker = json.loads((target / MARKER).read_text())
            if marker.get('skill') != 'work-report':
                raise RuntimeError('invalid managed marker')
        for parent in (target.parent, claude.parent):
            if not parent.resolve().is_relative_to(home):
                raise RuntimeError(f'skill directory escapes the current Unix profile: {parent}')
        expected = files(source)
        if args.check:
            if not target.is_dir() or files(target) != expected:
                raise RuntimeError('installed skill differs from source or is missing')
            marker = json.loads((target / MARKER).read_text())
            if marker.get('files') != expected:
                raise RuntimeError('installed manifest differs from actual source')
            if not claude.is_symlink() or claude.resolve() != target.resolve():
                raise RuntimeError('Claude skill link is missing or points elsewhere')
            print(json.dumps({'status': 'pass', 'source': str(source), 'codex_skill': str(target),
                              'claude_skill': str(claude), 'files_checked': len(expected)}))
            return 0
        uv = shutil.which('uv')
        if not uv:
            raise RuntimeError('uv is required; no project dependencies were changed')
        state = home / '.local/state/work-report'
        state.mkdir(parents=True, exist_ok=True)
        state.chmod(0o700)
        with tempfile.TemporaryDirectory(prefix='install-', dir=state) as temporary:
            staged = Path(temporary) / 'work-report'
            shutil.copytree(source, staged, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', MARKER))
            # Warm the isolated script environment before replacing a working installation.
            run = subprocess.run([uv, 'run', '--script', str(staged / 'scripts/report_tool.py'), '--help'],
                                 capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError('report tool preflight failed: ' + run.stderr)
            (staged / MARKER).write_text(json.dumps({'skill': 'work-report', 'source': str(source),
                                                    'files': expected}, indent=2) + '\n')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backups = state / 'install-backups'
                backups.mkdir(exist_ok=True)
                old = backups / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                target.rename(old)
            try:
                staged.rename(target)
                published = True
            except OSError:
                if old is not None and not target.exists():
                    old.rename(target)
                raise
        claude.parent.mkdir(parents=True, exist_ok=True)
        if not claude.is_symlink():
            claude.symlink_to(target, target_is_directory=True)
            created_claude = True
        # Validate both publication and the final installed script location.
        run = subprocess.run([uv, 'run', '--script', str(target / 'scripts/report_tool.py'), '--help'],
                             capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError('installed tool cannot start: ' + run.stderr)
        if files(target) != expected:
            raise RuntimeError('readback differs from source')
        print(json.dumps({'status': 'installed', 'codex_skill': str(target), 'claude_skill': str(claude),
                          'invocation': '$work-report (Codex); /work-report (Claude Code)',
                          'scope': 'current Linux/WSL user; no hooks, schedules, publishing or model config changes'}))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        if published:
            try:
                rejected = state / ('rejected-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
                target.rename(rejected)
                if old is not None:
                    old.rename(target)
                if created_claude and claude.is_symlink():
                    claude.unlink()
            except OSError as rollback_error:
                exc = RuntimeError(f'{exc}; rollback incomplete: {rollback_error}')
        print(json.dumps({'status': 'error', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
