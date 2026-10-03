"""Append-only ledger of files that agent-tools runtimes and agents write.

Canonical source: shared/materials.py. Each installed component carries a
byte-identical copy (scripts/sync_shared_materials.py --check). An entry is an
inventory fact for Cleaner, never authority to delete. Standard library only.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

SCHEMA = 'agent-tools.material/1'
EVENTS = ('created', 'updated', 'removed')
LOCK_TIMEOUT = 5


def data_root(explicit=None):
    """Explicit root, then config.json data_root, then the platform data directory."""
    if explicit is not None:
        value = Path(explicit).expanduser()
    else:
        config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'agent-tools/config.json'
        value = None
        if config.is_file():
            options = json.loads(config.read_text())
            if options.get('data_root'):
                value = Path(options['data_root']).expanduser()
        if value is None:
            if sys.platform == 'win32':
                value = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'agent-tools'
            elif sys.platform == 'darwin':
                value = Path.home() / 'Library/Application Support/agent-tools'
            else:
                value = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'agent-tools'
    if not value.is_absolute():
        raise ValueError('data-root must be absolute')
    return value.resolve()


def ledger_path(root=None):
    return data_root(root) / 'materials' / 'ledger.jsonl'


def _locked_append(path, line):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('ab') as stream:
        try:
            import fcntl
        except ImportError:  # Windows: single small O_APPEND writes.
            fcntl = None
        if fcntl:  # Bounded wait: a stuck holder must not stall the producer.
            deadline = time.monotonic() + LOCK_TIMEOUT
            while True:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('ledger lock busy')
                    time.sleep(0.02)
        try:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            if fcntl:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def record(path, producer, purpose, event='created', *, workspace=None, task_id=None,
           session_id=None, kind=None, root=None):
    """Append one entry. Failure never propagates to the producer; it is noted on stderr."""
    try:
        if event not in EVENTS:
            raise ValueError('event must be one of ' + ', '.join(EVENTS))
        target = Path(path).expanduser().absolute().resolve()
        entry = {'schema': SCHEMA, 'at': datetime.now(timezone.utc).isoformat(), 'producer': str(producer),
                 'event': event, 'path': str(target),
                 'kind': kind or ('dir' if target.is_dir() else 'file'),
                 'workspace': str(Path(workspace).expanduser().resolve()) if workspace else None,
                 'task_id': task_id or None, 'session_id': session_id or None,
                 'purpose': ' '.join(str(purpose or '').split())[:200]}
        line = (json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n').encode()
        _locked_append(ledger_path(root), line)
        return entry
    except Exception as exc:  # noqa: BLE001 - recording must not break the producer.
        try:
            print(f'agent-tools materials: not recorded {path}: {exc}', file=sys.stderr)
        except Exception:  # noqa: BLE001
            pass
        return None


def load(root=None):
    """All well-formed entries in append order; malformed lines are skipped."""
    path = ledger_path(root)
    if not path.is_file():
        return []
    entries = []
    with path.open('rb') as stream:
        for raw in stream:
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get('schema') == SCHEMA and isinstance(entry.get('path'), str):
                entries.append(entry)
    return entries
