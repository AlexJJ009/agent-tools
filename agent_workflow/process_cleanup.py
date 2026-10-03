"""Explicit legacy process-file cleanup; its journal is not a SQLite task transaction.

Cleaner owns semantic scope, retention and reference review. This module checks
exact files or explicitly declared directories (tree digest), records
authorization, and recovers only the operation's own moves. There is no
discovery, scheduler, or task-state mutation. Completed removals are appended to
the material ledger.
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

from . import materials
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


def _under(path, parent):
    return path == parent or parent in path.parents


def _slug(value):
    slug = re.sub(r'[^A-Za-z0-9._-]+', '-', value.strip().replace('/', '--'))
    return re.sub(r'[-_.]{2,}', '-', slug).strip('-._')


def artifact_roots(workspace):
    """manage-worktrees artifact bases `<repo-parent>/_artifacts/<repo>` for this workspace's repository."""
    common = _git(workspace, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    if common.returncode != 0 or Path(common.stdout.strip()).name != '.git':
        return []
    main = Path(common.stdout.strip()).resolve().parent
    names = {_slug(main.name)}
    url = _git(main, 'config', '--get', 'remote.origin.url').stdout.strip()
    if url:
        names.add(_slug(url.rstrip('/').rsplit('/', 1)[-1].rsplit(':', 1)[-1].removesuffix('.git')))
    parents = {main.parent}
    configs = [main / '.agent-wt.json', Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'agent-wt/config.json']
    for config in configs:
        try:
            value = json.loads(config.read_text()).get('worktree_root') if config.is_file() else None
        except (OSError, ValueError, AttributeError):
            value = None
        if value:
            root = Path(str(value)).expanduser()
            parents.add((root if root.is_absolute() else main / root).resolve().parent)
    if os.environ.get('AGENT_WT_ROOT'):
        parents.add(Path(os.environ['AGENT_WT_ROOT']).expanduser().resolve().parent)
    return sorted({parent / '_artifacts' / name for parent in parents for name in names if name})


def broad_path(path, data_root, workspaces=()):
    """A path whose retirement could take far more than material: `/`, home, the data root,
    a Git worktree root, or an ancestor of any of these."""
    path = Path(path)
    anchors = [Path.home().resolve(), Path(data_root).expanduser().resolve(), *(Path(w).resolve() for w in workspaces)]
    if len(path.parts) <= 1 or any(_under(a, path) for a in anchors):
        return True
    if path.is_dir() and not path.is_symlink():
        top = _git(path, 'rev-parse', '--show-toplevel')
        if (path / '.git').exists() or (top.returncode == 0 and Path(top.stdout.strip()).resolve() == path):
            return True
    return False


def _external_checker(data_root, workspace, task_id):
    """Absolute targets outside the workspace need scope evidence: an unregistered file under this
    task's artifact directory, a managed artifact root of this repository, or a ledger entry."""
    data = Path(data_root).expanduser().resolve()
    task_dir = data / 'artifacts' / task_id
    managed = artifact_roots(workspace)
    cache = {}

    def registered():
        if 'registered' not in cache:
            from .task_store import Store
            task = Store(data).read(task_id, detail=True)
            cache['registered'] = [data / a['path'] for a in task['artifacts'].values()]
        return cache['registered']

    def recorded(path):
        """The nearest recorded path decides: the target itself, or a recorded directory unit above it,
        live, not broad, and owned by this task or workspace."""
        if 'ledger' not in cache:
            cache['ledger'] = {e['path']: e for e in materials.load(data)}
        for unit in [path, *path.parents]:
            entry = cache['ledger'].get(str(unit))
            if entry is not None:
                return (entry['event'] in materials.EVENTS[:2] and (unit == path or entry.get('kind') == 'dir')
                        and (entry.get('task_id') == task_id or entry.get('workspace') == str(workspace))
                        and not broad_path(unit, data, [workspace]))
        return False

    def check(path, kind=None):
        require(not _under(data, path) and not _under(workspace, path), 'unsafe_path', 'refusing the data root, the workspace or an ancestor')
        if _under(path, data):
            require(_under(path, task_dir) and path != task_dir, 'unsafe_path', 'only this task artifact directory is eligible under the data root')
            require(not any(_under(r, path) for r in registered()), 'cleanup_blocked', 'registered task artifact; use task retire')
        else:
            known = any(_under(path, m) and path != m for m in managed) or recorded(path)
            require(known, 'unsafe_path', 'not a recorded or known material path')
        owner = _git(path.parent, 'rev-parse', '--show-toplevel')
        if owner.returncode == 0:
            top = Path(owner.stdout.strip()).resolve()
            require(path != top, 'unsafe_path', 'refusing a Git worktree root')
            tracked = _git(top, '--literal-pathspecs', 'ls-files', '--', str(path))
            require(tracked.returncode == 0 and not tracked.stdout.strip(), 'unsafe_path', 'tracked by Git')
            ignored = _git(top, 'check-ignore', '-q', '--', str(path) + ('/' if kind == 'dir' else ''))
            require(ignored.returncode == 0, 'unsafe_path', 'inside a Git worktree and not ignored')
    return check


def _plain_path(path):
    for p in [path, *path.parents]:
        require(not p.is_symlink(), 'unsafe_path', f'symlink forbidden: {p}')


def _hash(path):
    _plain_path(path)
    require(stat.S_ISREG(path.stat().st_mode), 'unsafe_path', f'not a regular file: {path}')
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def _tree_digest(path):
    """Directory identity, not a content hash: per entry the relative path, type, inode and ctime,
    plus size and mtime for files and the target for links; links are not followed."""
    _plain_path(path)
    require(stat.S_ISDIR(path.lstat().st_mode), 'unsafe_path', f'not a directory: {path}')
    rows = []
    for current, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(dirs + files):
            item = Path(current) / name
            require(name.lower() != '.git', 'unsafe_path', f'nested repository inside directory: {item}')
            info = item.lstat()
            row = [item.relative_to(path).as_posix(), info.st_ino, info.st_ctime_ns]
            if stat.S_ISLNK(info.st_mode):
                rows.append(row + ['link', os.readlink(item)])
            elif stat.S_ISDIR(info.st_mode):
                rows.append(row + ['dir'])
            else:
                require(stat.S_ISREG(info.st_mode), 'unsafe_path', f'special file inside directory: {item}')
                rows.append(row + ['file', info.st_size, info.st_mtime_ns])
    return digest(rows)


def _measure(path, entry):
    return _tree_digest(path) if entry.get('kind') == 'dir' else _hash(path)


def _identity(entry):
    """A directory entry carries `tree_digest` (metadata identity); a file entry carries `sha256`."""
    return entry['tree_digest'] if entry.get('kind') == 'dir' else entry['sha256']


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
    require(request.get('storage', 'workspace') in ('workspace', 'archives', 'external'), 'invalid_input', 'invalid storage mode')
    external = request.get('storage') == 'external'
    def valid(name):
        p = PurePosixPath(name)
        if external:  # Absolute, normalized; ':' is common in run directory names.
            return p.is_absolute() and len(p.parts) > 1 and all(x not in ('.', '..') and x.lower() != '.git' for x in p.parts[1:])
        return name not in ('', '.') and not name.startswith('/') and all(x not in ('.', '..') and x.lower() != '.git' and ':' not in x for x in p.parts)
    roots = request['process_roots']
    require(isinstance(roots, list) and roots, 'invalid_input', 'explicit process_roots required')
    for name in roots:
        require(isinstance(name, str) and '\\' not in name and '\x00' not in name and not name.startswith('//') and PurePosixPath(name).as_posix() == name and valid(name), 'unsafe_path', 'invalid process root')
    files = request['files']
    require(isinstance(files, list) and files, 'invalid_input', 'explicit nonempty file list required')
    names = set()
    for item in files:
        require(isinstance(item, dict) and item.get('kind', 'file') in ('file', 'dir'), 'invalid_input', 'kind must be file or dir')
        identity = 'tree_digest' if item.get('kind') == 'dir' else 'sha256'
        require({'path', identity, 'disposition', 'category'} <= set(item) <= {'path', identity, 'disposition', 'category', 'retained_copy', 'kind'}, 'invalid_input', 'invalid file entry')
        require(item.get('kind') != 'dir' or (item['disposition'] == 'delete' and 'retained_copy' not in item), 'invalid_input', 'a directory entry supports delete only')
        name = item['path']
        require(isinstance(name, str) and name and '\\' not in name and '\x00' not in name,
                'unsafe_path', 'path must be a POSIX path')
        require(not name.startswith('//') and PurePosixPath(name).as_posix() == name and valid(name), 'unsafe_path', f'unsafe path: {name}')
        require(any(PurePosixPath(name).is_relative_to(PurePosixPath(root)) and name != root for root in roots), 'unsafe_path', 'file outside declared process roots')
        require(item['category'] in ('process-output', 'cache', 'obsolete-state'), 'invalid_input', 'invalid category')
        require(name not in names, 'invalid_input', 'duplicate file')
        names.add(name)
        require(isinstance(item[identity], str) and re.fullmatch('[0-9a-f]{64}', item[identity]), 'invalid_input', identity + ' required')
        require(item['disposition'] in ('archive', 'delete'), 'invalid_input', 'disposition must be archive or delete')
        require(request.get('storage') != 'archives' or item['disposition'] == 'delete', 'invalid_input', 'archive storage cleanup only supports delete')
        if 'retained_copy' in item:
            copy = item['retained_copy']
            require(isinstance(copy, dict) and set(copy) == {'path', 'sha256'} and isinstance(copy['path'], str) and Path(copy['path']).is_absolute() and copy['sha256'] == item['sha256'], 'invalid_input', 'retained_copy requires absolute path and matching sha256')


def _eligible(workspace, name, storage='workspace', kind=None):
    path = workspace / name
    _plain_path(path)
    require(path.parent.is_dir(), 'unsafe_path', 'parent directory missing')
    if storage == 'archives':
        return path
    if callable(storage):  # external: absolute path with ledger/known-root scope evidence
        storage(path, kind)
        return path
    owner = _git(path.parent, 'rev-parse', '--show-toplevel')
    require(owner.returncode == 0 and Path(owner.stdout.strip()).resolve() == workspace,
            'workspace_mismatch', 'file belongs to another worktree or nested repository')
    tracked = _git(workspace, '--literal-pathspecs', 'ls-files', '--error-unmatch', '--', name)
    require(tracked.returncode == 1, 'unsafe_path', 'tracked file or failed Git tracking check')
    ignored = _git(workspace, 'check-ignore', '-q', '--', name + ('/' if kind == 'dir' else ''))
    require(ignored.returncode == 0, 'unsafe_path', 'file must be Git ignored')
    return path


def _content_root(data_root, request, workspace):
    storage = request.get('storage')
    root = Path(data_root).expanduser() / 'archives' if storage == 'archives' else Path(workspace.anchor) if storage == 'external' else workspace
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
    if storage == 'external':
        storage = _external_checker(data_root, workspace, request['task_id'])
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
            path = _eligible(content_root, item['path'], storage, item.get('kind'))
            require(path.exists(), 'source_missing', str(path))
            require(_measure(path, item) == _identity(item), 'content_conflict', str(path))
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
        materials.record(directory, 'task-runtime', 'process-cleanup journal ' + request['operation_id'],
                         kind='dir', workspace=info['path'], task_id=request['task_id'], root=Path(data_root).expanduser())
        checkpoint('planned', -1)
    require(journal['status'] != 'aborted', 'operation_aborted', 'use a new operation ID after abort')
    if journal['status'] == 'prepared':
        _retained(request, content_root)
        for i, entry in enumerate(journal['entries']):
            path = _eligible(content_root, entry['path'], storage, entry.get('kind'))
            quarantine = Path(entry['quarantine'])
            _plain_path(quarantine)
            if quarantine.exists():
                require(not path.exists(), 'content_conflict', 'source recreated while quarantined')
                require(_measure(quarantine, entry) == _identity(entry), 'content_conflict', 'quarantine changed')
                source = quarantine
            else:
                require(path.exists(), 'source_missing', 'source and quarantine are missing')
                require(_measure(path, entry) == _identity(entry), 'content_conflict', 'source changed')
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
                require(_measure(path, entry) == _identity(entry), 'content_conflict', 'source changed before move')
                os.rename(path, quarantine)
                _sync(path.parent)
                checkpoint('quarantined', i)
                require(_measure(quarantine, entry) == _identity(entry), 'content_conflict', 'source changed during move')
        # Check the whole plan again before making disposal irreversible.
        for i, entry in enumerate(journal['entries']):
            path = _eligible(content_root, entry['path'], storage, entry.get('kind'))
            require(not path.exists(), 'content_conflict', 'source recreated before commit')
            require(_measure(Path(entry['quarantine']), entry) == _identity(entry), 'content_conflict', 'quarantine changed before commit')
            if entry['disposition'] == 'archive':
                require(_hash(directory / f'{i}.archive') == entry['sha256'], 'content_conflict', 'archive changed before commit')
        _retained(request, content_root)
        journal['status'] = 'committed'
        _save(journal_path, journal)
        checkpoint('committed', -1)
    for i, entry in enumerate(journal['entries']):
        if entry['state'] == 'done':
            continue
        path = _eligible(content_root, entry['path'], storage, entry.get('kind'))
        quarantine = Path(entry['quarantine'])
        _plain_path(quarantine)
        require(not path.exists(), 'content_conflict', 'source recreated after commit')
        if entry['disposition'] == 'archive':
            require(_hash(directory / f'{i}.archive') == entry['sha256'], 'content_conflict', 'archive changed before disposal')
        _retained(request, content_root, entry)
        if quarantine.exists():
            if entry.get('kind') == 'dir':
                # A partially removed tree no longer matches its digest; resume removal.
                if entry['state'] != 'disposing':
                    require(_tree_digest(quarantine) == _identity(entry), 'content_conflict', 'quarantine changed before disposal')
                    entry['state'] = 'disposing'
                    _save(journal_path, journal)
                shutil.rmtree(quarantine)
            else:
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
    for entry in journal['entries']:
        materials.record(content_root / entry['path'], 'task-runtime', 'process-cleanup ' + entry['disposition'], 'removed',
                         kind=entry.get('kind', 'file'), workspace=info['path'], task_id=request['task_id'],
                         root=Path(data_root).expanduser())
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
        if storage == 'external':
            storage = _external_checker(data_root, workspace, journal['request']['task_id'])
        for entry in journal['entries']:
            path = _eligible(content_root, entry['path'], storage, entry.get('kind'))
            quarantine = Path(entry['quarantine'])
            _plain_path(quarantine)
            if quarantine.exists():
                require(not path.exists(), 'content_conflict', 'source recreated; cannot restore')
                # Restore the exact surviving bytes even when an editor changed them.
                mode = quarantine.lstat().st_mode
                require(stat.S_ISDIR(mode) if entry.get('kind') == 'dir' else stat.S_ISREG(mode), 'unsafe_path', 'unexpected quarantine type')
                os.rename(quarantine, path)
                _sync(path.parent)
            else:
                require(path.is_dir() if entry.get('kind') == 'dir' else path.is_file(), 'source_missing', 'source and quarantine missing during abort')
        journal['status'] = 'aborted'
        _resolve_error(journal)
        _save(directory / 'journal.json', journal)
        return journal
