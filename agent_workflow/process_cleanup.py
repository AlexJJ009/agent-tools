"""Explicit legacy process-file cleanup; its journal is not a SQLite task transaction.

Cleaner owns semantic scope, retention and reference review. This module checks
exact files, records authorization, and recovers only the operation's own moves.
There is no discovery, recursive deletion, scheduler, or task-state mutation.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time
import math

from .task_store import TaskError, digest, require


def _git(workspace, *args):
    # Caller-selected indexes/worktrees/config must not redirect safety checks.
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    return subprocess.run(['git', '-C', str(workspace), *args], capture_output=True, text=True, env=env)


def workspace_info(path):
    root = Path(path).resolve()
    def query(*args):
        result = _git(root, 'rev-parse', *args)
        require(result.returncode == 0, 'workspace_mismatch', result.stderr.strip())
        return Path(result.stdout.strip()).resolve()
    require(root.is_dir() and query('--show-toplevel') == root, 'workspace_mismatch', 'workspace must be the worktree root')
    common = query('--path-format=absolute', '--git-common-dir')
    git_dir = query('--absolute-git-dir')
    return {'path': str(root), 'common_dir': str(common), 'git_dir': str(git_dir),
            'id': digest({'common': str(common), 'git_dir': str(git_dir)})[:24]}


def _plain_path(path):
    for p in [path, *path.parents]:
        require(not p.is_symlink(), 'unsafe_path', f'symlink forbidden: {p}')


def _hash(path):
    _plain_path(path)
    require(stat.S_ISREG(path.stat().st_mode), 'unsafe_path', f'not a regular file: {path}')
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _resolve_error(journal):
    error = journal.get('last_error')
    if error is not None and 'resolved_at' not in error:
        error['resolved_at'] = _now()
        return True
    return False


def _save(path, data):
    data['updated_at'] = _now()
    temporary = path.with_suffix('.tmp')
    _plain_path(temporary)
    with temporary.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)
    _sync(path.parent)


def _sync(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


@contextmanager
def _lock(root, timeout=0):
    require(isinstance(timeout, (int, float)) and math.isfinite(timeout) and timeout >= 0, 'invalid_input', 'lock timeout must be finite and nonnegative')
    _plain_path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / '.lock'
    _plain_path(path)
    with path.open('a+b') as f:
        if os.name == 'nt':
            import msvcrt
            f.seek(0)
            if not f.read(1):
                f.write(b'0'); f.flush()
            f.seek(0)
            def acquire():
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TaskError('operation_busy', 'another cleanup holds the lock') from exc
                time.sleep(min(0.02, remaining))
        try:
            yield
        finally:
            if os.name == 'nt':
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def _location(data_root, task_id, operation_id):
    require(isinstance(task_id, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', task_id),
            'invalid_input', 'task_id must be a safe identifier')
    require(isinstance(operation_id, str) and operation_id.strip(), 'invalid_input', 'operation_id required')
    root = Path(data_root).expanduser()
    require(root.is_absolute(), 'invalid_input', 'data_root must be absolute')
    _plain_path(root)
    return root / 'cleanup', root / 'cleanup' / task_id / digest(operation_id)


def _request(request):
    require(isinstance(request, dict), 'invalid_input', 'request must be an object')
    required = {'workspace', 'task_id', 'operation_id', 'authorization', 'process_materials_reviewed', 'rationale', 'process_roots', 'files'}
    require(required <= set(request) <= required | {'storage'}, 'invalid_input', 'request fields must match cleanup contract')
    require(request['process_materials_reviewed'] is True, 'invalid_input', 'Cleaner review is required')
    require(isinstance(request['rationale'], str) and request['rationale'].strip(), 'invalid_input', 'rationale required')
    auth = request['authorization']
    require(isinstance(auth, dict) and all(isinstance(auth.get(k), str) and auth[k].strip()
            for k in ('quote', 'source_ref')), 'invalid_input', 'authorization quote and source_ref required')
    require(isinstance(request['workspace'], str) and Path(request['workspace']).is_absolute(), 'invalid_input', 'absolute workspace required')
    require(request.get('storage', 'workspace') in ('workspace', 'archives'), 'invalid_input', 'invalid storage mode')
    roots = request['process_roots']
    require(isinstance(roots, list) and roots, 'invalid_input', 'explicit process_roots required')
    for name in roots:
        require(isinstance(name, str) and name not in ('', '.') and not name.startswith('/') and '\\' not in name and PurePosixPath(name).as_posix() == name and all(x not in ('.', '..') and x.lower() != '.git' and ':' not in x for x in PurePosixPath(name).parts), 'unsafe_path', 'invalid process root')
    files = request['files']
    require(isinstance(files, list) and files, 'invalid_input', 'explicit nonempty file list required')
    names = set()
    for item in files:
        require(isinstance(item, dict) and {'path', 'sha256', 'disposition', 'category'} <= set(item) <= {'path', 'sha256', 'disposition', 'category', 'retained_copy'}, 'invalid_input', 'invalid file entry')
        name = item['path']
        require(isinstance(name, str) and name and '\\' not in name and '\x00' not in name,
                'unsafe_path', 'path must be a relative POSIX file path')
        p = PurePosixPath(name)
        require(not p.is_absolute() and p.as_posix() == name and all(x not in ('.', '..') and x.lower() != '.git' and ':' not in x for x in p.parts),
                'unsafe_path', f'unsafe relative path: {name}')
        require(any(PurePosixPath(name).is_relative_to(PurePosixPath(root)) and name != root for root in roots), 'unsafe_path', 'file outside declared process roots')
        require(item['category'] in ('process-output', 'cache', 'obsolete-state'), 'invalid_input', 'invalid category')
        require(name not in names, 'invalid_input', 'duplicate file')
        names.add(name)
        require(isinstance(item['sha256'], str) and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'invalid_input', 'sha256 required')
        require(item['disposition'] in ('archive', 'delete'), 'invalid_input', 'disposition must be archive or delete')
        require(request.get('storage') != 'archives' or item['disposition'] == 'delete', 'invalid_input', 'archive storage cleanup only supports delete')
        if 'retained_copy' in item:
            copy = item['retained_copy']
            require(isinstance(copy, dict) and set(copy) == {'path', 'sha256'} and isinstance(copy['path'], str) and Path(copy['path']).is_absolute() and copy['sha256'] == item['sha256'], 'invalid_input', 'retained_copy requires absolute path and matching sha256')


def _eligible(workspace, name, storage='workspace'):
    path = workspace / name
    _plain_path(path)
    require(path.parent.is_dir(), 'unsafe_path', 'parent directory missing')
    if storage == 'archives':
        return path
    owner = _git(path.parent, 'rev-parse', '--show-toplevel')
    require(owner.returncode == 0 and Path(owner.stdout.strip()).resolve() == workspace,
            'workspace_mismatch', 'file belongs to another worktree or nested repository')
    tracked = _git(workspace, '--literal-pathspecs', 'ls-files', '--error-unmatch', '--', name)
    require(tracked.returncode == 1, 'unsafe_path', 'tracked file or failed Git tracking check')
    ignored = _git(workspace, 'check-ignore', '-q', '--', name)
    require(ignored.returncode == 0, 'unsafe_path', 'file must be Git ignored')
    return path


def _content_root(data_root, request, workspace):
    root = Path(data_root).expanduser() / 'archives' if request.get('storage') == 'archives' else workspace
    _plain_path(root)
    require(root.is_dir(), 'unsafe_path', 'content storage directory missing')
    return root


def _retained(request, content_root, item=None):
    items = [item] if item is not None else request['files']
    copies = [entry['retained_copy'] for entry in items if 'retained_copy' in entry]
    if not copies:
        return
    forbidden = {content_root / item['path'] for item in request['files']}
    for i, item in enumerate(request['files']):
        path = content_root / item['path']
        forbidden.add(path.with_name('.cleanup-' + digest([request['task_id'], request['operation_id']])[:24] + '-' + str(i)))
    forbidden = {p.resolve() for p in forbidden}
    for copy in copies:
        path = Path(copy['path'])
        _plain_path(path)
        require(path.resolve() not in forbidden, 'unsafe_path', 'retained copy is also a deletion target')
        require(path.is_file(), 'retained_copy_missing', 'retained copy missing')
        require(_hash(path) == copy['sha256'], 'content_conflict', 'retained copy changed')


def read_cleanup(data_root, task_id, operation_id):
    root, directory = _location(data_root, task_id, operation_id)
    path = directory / 'journal.json'
    _plain_path(path)
    require(path.is_file(), 'operation_missing', 'cleanup operation not found')
    return json.loads(path.read_text(encoding='utf-8'))


def _run_cleanup(data_root, request, *, fault=None):
    """Run/retry an exact request. fault(stage, index) is for crash-injection tests.

    A failed operation remains recoverable with the same request/operation ID;
    changed source content is a conflict, never permission to destroy a copy.
    """
    _request(request)
    root, directory = _location(data_root, request['task_id'], request['operation_id'])
    workspace = Path(request['workspace'])
    _plain_path(workspace)
    info = workspace_info(workspace)
    workspace = Path(info['path'])
    require(not root.resolve().is_relative_to(workspace), 'unsafe_path', 'cleanup storage must be outside workspace')
    content_root = _content_root(data_root, request, workspace)
    storage = request.get('storage', 'workspace')
    def checkpoint(stage, index):
        if fault:
            fault(stage, index)
    _plain_path(directory)
    journal_path = directory / 'journal.json'
    journal = None
    if journal_path.exists():
        journal = read_cleanup(data_root, request['task_id'], request['operation_id'])
        require(journal['request_digest'] == digest(request), 'idempotency_conflict', 'operation ID already has another request')
        require(journal.get('workspace') is None or journal['workspace'] == info, 'workspace_mismatch', 'worktree identity changed')
        if journal['status'] in ('committed', 'complete'):
            for i, entry in enumerate(journal['entries']):
                if entry['disposition'] == 'archive':
                    archive = directory / f'{i}.archive'
                    require(archive.exists(), 'archive_missing', 'committed archive missing')
                    require(_hash(archive) == entry['sha256'], 'content_conflict', 'committed archive changed')
        if journal['status'] == 'complete':
            if _resolve_error(journal):
                _save(journal_path, journal)
            return journal
    if journal is None or journal['status'] == 'rejected':
        created_at = journal.get('created_at') if journal else _now()
        previous_error = journal.get('last_error') if journal else None
        entries = []
        for i, item in enumerate(request['files']):
            path = _eligible(content_root, item['path'], storage)
            require(path.exists(), 'source_missing', str(path))
            require(_hash(path) == item['sha256'], 'content_conflict', str(path))
            quarantine = path.with_name('.cleanup-' + digest([request['task_id'], request['operation_id']])[:24] + '-' + str(i))
            _plain_path(quarantine)
            require(not quarantine.exists(), 'content_conflict', 'quarantine already exists')
            entries.append({**item, 'quarantine': str(quarantine), 'state': 'pending'})
        targets = {str(content_root / item['path']) for item in request['files']}
        require(not any(entry['quarantine'] in targets for entry in entries), 'unsafe_path', 'target collides with quarantine')
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        journal = {'version': 1, 'status': 'prepared', 'request': request, 'request_digest': digest(request),
                   'workspace': info, 'entries': entries}
        if created_at is not None:
            journal['created_at'] = created_at
        if previous_error is not None:
            journal['last_error'] = previous_error
        _retained(request, content_root)
        _save(journal_path, journal)
        checkpoint('planned', -1)
    require(journal['status'] != 'aborted', 'operation_aborted', 'use a new operation ID after abort')
    if journal['status'] == 'prepared':
        _retained(request, content_root)
        for i, entry in enumerate(journal['entries']):
            path = _eligible(content_root, entry['path'], storage)
            quarantine = Path(entry['quarantine'])
            _plain_path(quarantine)
            if quarantine.exists():
                require(not path.exists(), 'content_conflict', 'source recreated while quarantined')
                require(_hash(quarantine) == entry['sha256'], 'content_conflict', 'quarantine changed')
                source = quarantine
            else:
                require(path.exists(), 'source_missing', 'source and quarantine are missing')
                require(_hash(path) == entry['sha256'], 'content_conflict', 'source changed')
                source = path
            if entry['disposition'] == 'archive':
                archive = directory / f'{i}.archive'
                _plain_path(archive)
                if not archive.exists():
                    temporary = directory / f'{i}.archive.tmp'
                    _plain_path(temporary)
                    with source.open('rb') as src, temporary.open('wb') as dest:
                        shutil.copyfileobj(src, dest)
                        dest.flush(); os.fsync(dest.fileno())
                    require(_hash(temporary) == entry['sha256'], 'content_conflict', 'archive copy differs')
                    os.replace(temporary, archive)
                    _sync(directory)
                require(_hash(archive) == entry['sha256'], 'content_conflict', 'archive changed')
                checkpoint('archived', i)
            if source == path:
                require(_hash(path) == entry['sha256'], 'content_conflict', 'source changed before move')
                os.rename(path, quarantine)
                _sync(path.parent)
                checkpoint('quarantined', i)
                require(_hash(quarantine) == entry['sha256'], 'content_conflict', 'source changed during move')
        # Check the whole plan again before making disposal irreversible.
        for i, entry in enumerate(journal['entries']):
            path = _eligible(content_root, entry['path'], storage)
            require(not path.exists(), 'content_conflict', 'source recreated before commit')
            require(_hash(Path(entry['quarantine'])) == entry['sha256'], 'content_conflict', 'quarantine changed before commit')
            if entry['disposition'] == 'archive':
                require(_hash(directory / f'{i}.archive') == entry['sha256'], 'content_conflict', 'archive changed before commit')
        _retained(request, content_root)
        journal['status'] = 'committed'
        _save(journal_path, journal)
        checkpoint('committed', -1)
    for i, entry in enumerate(journal['entries']):
        if entry['state'] == 'done':
            continue
        path = _eligible(content_root, entry['path'], storage)
        quarantine = Path(entry['quarantine'])
        _plain_path(quarantine)
        require(not path.exists(), 'content_conflict', 'source recreated after commit')
        if entry['disposition'] == 'archive':
            require(_hash(directory / f'{i}.archive') == entry['sha256'], 'content_conflict', 'archive changed before disposal')
        _retained(request, content_root, entry)
        if quarantine.exists():
            require(_hash(quarantine) == entry['sha256'], 'content_conflict', 'quarantine changed before disposal')
            quarantine.unlink()
            _sync(path.parent)
        checkpoint('disposed', i)
        entry['state'] = 'done'
        _save(journal_path, journal)
    journal['status'] = 'complete'
    journal['completed_at'] = _now()
    _resolve_error(journal)
    _save(journal_path, journal)
    return journal


def run_cleanup(data_root, request, *, fault=None, validate_task=None):
    """Run or retry a valid explicit request; persist failures without changing task state."""
    _request(request)
    root, directory = _location(data_root, request['task_id'], request['operation_id'])
    with _lock(root):
        _plain_path(directory)
        existing = read_cleanup(data_root, request['task_id'], request['operation_id']) if (directory / 'journal.json').exists() else None
        if existing is not None:
            require(existing['request_digest'] == digest(request), 'idempotency_conflict', 'operation ID already has another request')
        if (existing is None or existing['status'] == 'rejected') and validate_task is not None:
            validate_task(request)
        try:
            return _run_cleanup(data_root, request, fault=fault)
        except Exception as exc:
            # Invalid/conflicting requests must not rewrite another operation.
            try:
                journal_path = directory / 'journal.json'
                _plain_path(directory)
                if journal_path.exists():
                    journal = read_cleanup(data_root, request['task_id'], request['operation_id'])
                    if journal['request_digest'] != digest(request):
                        raise exc
                else:
                    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                    journal = {'version': 1, 'status': 'rejected', 'request': request,
                               'request_digest': digest(request), 'workspace': None,
                               'entries': [], 'created_at': _now()}
                journal['last_error'] = {'code': getattr(exc, 'code', 'io_error'),
                                         'message': str(exc), 'at': _now()}
                _save(journal_path, journal)
            except Exception:
                pass  # A storage failure must not hide the original failure.
            raise


def abort_cleanup(data_root, task_id, operation_id):
    """Restore prepared moves; committed disposal cannot be cancelled."""
    root, directory = _location(data_root, task_id, operation_id)
    with _lock(root):
        journal = read_cleanup(data_root, task_id, operation_id)
        if journal['status'] == 'aborted':
            if _resolve_error(journal):
                _save(directory / 'journal.json', journal)
            return journal
        require(journal['status'] in ('prepared', 'aborted'), 'already_committed', 'cannot abort committed cleanup')
        workspace = Path(journal['workspace']['path'])
        require(workspace_info(workspace) == journal['workspace'], 'workspace_mismatch', 'worktree changed')
        content_root = _content_root(data_root, journal['request'], workspace)
        storage = journal['request'].get('storage', 'workspace')
        for entry in journal['entries']:
            path = _eligible(content_root, entry['path'], storage)
            quarantine = Path(entry['quarantine'])
            _plain_path(quarantine)
            if quarantine.exists():
                require(not path.exists(), 'content_conflict', 'source recreated; cannot restore')
                # Restore the exact surviving bytes even when an editor changed them.
                require(stat.S_ISREG(quarantine.stat().st_mode), 'unsafe_path', 'not regular quarantine')
                os.rename(quarantine, path)
                _sync(path.parent)
            else:
                require(path.is_file(), 'source_missing', 'source and quarantine missing during abort')
        journal['status'] = 'aborted'
        _resolve_error(journal)
        _save(directory / 'journal.json', journal)
        return journal
