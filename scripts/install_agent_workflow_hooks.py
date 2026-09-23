#!/usr/bin/env python3
"""Explicitly install/check/remove workflow hooks for the current Linux/WSL user.

Install the workflow suite first. This helper does not enable the hook feature,
change permissions, trust hooks, or modify authentication/provider settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'agent-workflow-v2'
EVENTS = ('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop')


def runtime_target(home):
    return home / '.local/share/agent-workflow'


def hook_command(home):
    python = str(Path(sys.executable).resolve())
    return shlex.join(['env', f'PYTHONPATH={runtime_target(home)}', python,
                       '-P', '-m', 'agent_workflow.hooks', 'hook'])


def managed_group(event, home):
    handler = {'type': 'command', 'command': hook_command(home), 'timeout': 30,
               'statusMessage': MARKER}
    if event != 'Stop':
        handler['additionalContextLimit'] = 2500
    group = {'hooks': [handler]}
    if event == 'SessionStart':
        group['matcher'] = 'startup|resume|clear|compact'
    elif event in {'PreToolUse', 'PostToolUse'}:
        group['matcher'] = '.*'
    return group


def owned(group, home):
    handlers = group.get('hooks') if isinstance(group, dict) else None
    if not isinstance(handlers, list) or len(handlers) != 1:
        return False
    handler = handlers[0]
    if not isinstance(handler, dict) or handler.get('type') != 'command' or handler.get('statusMessage') != MARKER:
        return False
    try:
        parts = shlex.split(handler.get('command', ''))
    except (TypeError, ValueError):
        return False
    return (len(parts) == 7 and parts[:2] == ['env', f'PYTHONPATH={runtime_target(home)}']
            and Path(parts[2]).is_absolute() and Path(parts[2]).name.startswith('python')
            and parts[3:] == ['-P', '-m', 'agent_workflow.hooks', 'hook'])


def target_guard(home):
    args = [sys.executable, str(ROOT / 'scripts/codex_target_guard.py'),
            '--platform', 'auto', '--codex-home', str(home / '.codex'),
            '--cc-switch-db', str(home / '.cc-switch/cc-switch.db'), '--path-only',
            '--allow-missing-config', '--allow-missing-cc-switch',
            '--skip-cc-switch-read-check', '--json']
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('target guard rejected workflow hook change: ' + result.stdout + result.stderr)


def hooks_file(home):
    path = home / '.codex/hooks.json'
    if path.is_symlink() or not path.parent.resolve().is_relative_to(home.resolve()):
        raise ValueError('workflow hook target escapes the current profile or is a symlink')
    return path


def read_hooks(path, missing_ok=False):
    if not path.exists():
        if missing_ok:
            return {'hooks': {}}
        raise ValueError(f'hooks file is missing: {path}')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise ValueError('invalid hooks JSON preserved: expected object and hooks object')
    data.setdefault('hooks', {})
    for event in EVENTS:
        if event in data['hooks'] and not isinstance(data['hooks'][event], list):
            raise ValueError(f'invalid hooks JSON preserved: hooks.{event} must be a list')
    return data


def write_hooks(path, data, home):
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        directory = home / '.local/state/agent-workflow/hooks-install-backups'
        if not directory.resolve().is_relative_to(home.resolve()):
            raise ValueError('backup directory escapes the current profile')
        directory.mkdir(parents=True, exist_ok=True)
        backup = directory / ('hooks-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix='.workflow-hooks-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return str(backup) if backup else None


def operate(home, operation='install'):
    home = Path(home).resolve()
    if operation != 'check':
        target_guard(home)
    path = hooks_file(home)
    data = read_hooks(path, missing_ok=operation == 'install')
    if operation != 'remove':
        runtime = runtime_target(home) / 'agent_workflow/hooks.py'
        if not runtime.is_file() or not runtime.resolve().is_relative_to(home):
            raise ValueError('installed workflow hook runtime is missing or outside the current profile; install the suite first')
    changed = 0
    for event in EVENTS:
        groups = data['hooks'].get(event, [])
        expected = managed_group(event, home)
        matches = [i for i, group in enumerate(groups) if owned(group, home)]
        if operation == 'check':
            if len(matches) != 1 or groups[matches[0]] != expected:
                raise ValueError(f'missing, duplicated, or changed managed hook: {event}')
        elif operation == 'remove':
            kept = [group for group in groups if not owned(group, home)]
            changed += len(groups) - len(kept)
            if kept:
                data['hooks'][event] = kept
            else:
                data['hooks'].pop(event, None)
        else:
            if matches:
                groups[matches[0]] = expected
                for index in reversed(matches[1:]):
                    groups.pop(index)
            else:
                groups.append(expected)
                changed += 1
            data['hooks'][event] = groups
    backup = None if operation == 'check' else write_hooks(path, data, home)
    return {'status': {'install': 'installed', 'check': 'pass', 'remove': 'removed'}[operation],
            'hooks': str(path), 'events': list(EVENTS), 'groups_changed': changed,
            'backup': backup, 'trust_status': 'not_checked_by_installer',
            'native_acceptance': 'Review and trust these definitions in native /hooks; installation is not activation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--remove', action='store_true')
    args = parser.parse_args(argv)
    if platform.system() != 'Linux':
        parser.error('this installer supports Linux/WSL only')
    try:
        print(json.dumps(operate(Path.home(), 'check' if args.check else 'remove' if args.remove else 'install')))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
