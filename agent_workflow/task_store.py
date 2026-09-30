"""Local task state and owned artifacts. No model, scheduler, or hook is required.

A persisted operation plan precedes file changes. While a plan is pending,
readers refuse that task rather than return a database/file mixture. Recovery
replays the exact plan, never re-interprets the user's request.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

SCHEMA = 1


class TaskError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def require(condition, code, message):
    if not condition:
        raise TaskError(code, message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else encoded(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def data_root(explicit=None):
    """Resolve once, independent of cwd; keep the existing installer dependency-free."""
    if explicit is not None:
        value = Path(explicit).expanduser()
    else:
        config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
        config = config_home / 'agent-tools/config.json'
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
    require(value.is_absolute(), 'invalid_input', 'data-root must be absolute')
    return value.resolve()


def git(workspace, *args):
    result = subprocess.run(['git', '-C', str(workspace), *args], capture_output=True, text=True)
    require(result.returncode == 0, 'workspace_mismatch', result.stderr.strip())
    return result.stdout.strip()


def workspace_info(path):
    root = Path(path).resolve()
    require(root.is_dir(), 'workspace_mismatch', 'workspace is missing; explicitly rebind it')
    top = Path(git(root, 'rev-parse', '--show-toplevel')).resolve()
    require(root == top, 'workspace_mismatch', 'workspace must be the worktree root')
    common = Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve()
    git_dir = Path(git(root, 'rev-parse', '--absolute-git-dir')).resolve()
    return {'path': str(root), 'common_dir': str(common), 'git_dir': str(git_dir),
            'id': digest({'common': str(common), 'git_dir': str(git_dir)})[:24]}


def fingerprint(workspace, paths=None):
    """Content, not just HEAD: include dirty and untracked files, never follow links."""
    root = Path(workspace)
    if paths is None:
        proc = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], capture_output=True)
        require(proc.returncode == 0, 'workspace_mismatch', 'cannot enumerate worktree inputs')
        paths = sorted(set(os.fsdecode(p) for p in proc.stdout.split(b'\0') if p))
    values = {}
    for name in paths:
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts, 'invalid_input', 'input paths must be workspace-relative')
        p = root / relative
        require(p.parent.resolve().is_relative_to(root.resolve()), 'workspace_mismatch', 'input parent escapes workspace')
        if p.is_symlink():
            values[name] = {'link': os.readlink(p)}
        elif p.is_file():
            h = hashlib.sha256()
            with p.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            values[name] = {'sha256': h.hexdigest(), 'executable': bool(p.stat().st_mode & 0o111)}
        else:
            values[name] = {'missing_or_directory': True}
    return digest({'head': git(root, 'rev-parse', 'HEAD'), 'paths': values})


def criterion(spec):
    require(isinstance(spec, dict), 'invalid_input', 'criterion must be an object')
    require('withdrawn' not in spec or type(spec['withdrawn']) is bool, 'invalid_input', 'withdrawn must be boolean')
    for key in ('id', 'name', 'requirement', 'expected'):
        require(key in spec and isinstance(spec[key], str) and spec[key].strip(), 'invalid_input', 'criterion requires nonempty ' + key)
    return dict(spec, requirement_revision=1, verification='not_run', validity='unknown',
                user_acceptance='pending', result=None, feedback=None, withdrawn=False, invalidation_reason='')


class Store:
    def __init__(self, root=None, fault=None):
        self.root = data_root(root)
        self.db = self.root / 'tasks.sqlite3'
        self.fault = fault or (lambda _: None)

    @contextmanager
    def connection(self, write=False):
        if not self.db.exists() and not write:
            yield None
            return
        if write:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(str(self.db) if write else self.db.as_uri() + '?mode=ro', uri=not write, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            require(version <= SCHEMA, 'schema_version', 'newer task schema; use a compatible tool, do not overwrite')
            if version == 0:
                require(write, 'schema_version', 'uninitialized database')
                db.executescript('''BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS operations(scope TEXT NOT NULL, id TEXT NOT NULL, request_hash TEXT NOT NULL,
                        state TEXT NOT NULL, plan TEXT NOT NULL, result TEXT, PRIMARY KEY(scope,id));
                    CREATE UNIQUE INDEX IF NOT EXISTS one_pending ON operations(scope) WHERE state='pending';
                    CREATE TABLE IF NOT EXISTS garbage(path TEXT PRIMARY KEY, sha256 TEXT NOT NULL);
                    CREATE TABLE IF NOT EXISTS bindings(session TEXT NOT NULL, workspace TEXT NOT NULL, task TEXT NOT NULL,
                        PRIMARY KEY(session,workspace));
                    PRAGMA user_version=1;
                    COMMIT;''')
            if write:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _task(self, db, task_id):
        row = db.execute('SELECT body FROM tasks WHERE id=?', (task_id,)).fetchone() if db else None
        require(row is not None, 'not_found', 'task not found')
        return json.loads(row[0])

    def _pending(self, db, task_id):
        return db.execute("SELECT id FROM operations WHERE scope=? AND state='pending'", (task_id,)).fetchone() if db else None

    def _pending_closeout(self, db, task_id):
        row = db.execute("SELECT plan FROM operations WHERE scope=? AND state='pending'", (task_id,)).fetchone()
        return row and json.loads(row[0]).get('action') == 'closeout'

    def list(self, workspace=None):
        with self.connection() as db:
            if db is None:
                return []
            items = [json.loads(row[0]) for row in db.execute('SELECT body FROM tasks ORDER BY id')]
            return [{'task_id': t['task_id'], 'title': t['title'], 'revision': t['revision'], 'state': ('closing' if self._pending_closeout(db, t['task_id']) or (t['state'] == 'closed' and self._has_garbage(db, t['task_id'])) else t['state']),
                     'workspace': t['workspace']['path'], 'recovery_pending': bool(self._pending(db, t['task_id'])) or self._has_garbage(db, t['task_id'])}
                    for t in items if workspace is None or str(Path(workspace).resolve()) == t['workspace']['path']]

    def read(self, task_id, detail=False):
        with self.connection() as db:
            task = self._task(db, task_id)
            require(not self._pending(db, task_id), 'recovery_pending', 'task has an interrupted operation; run recover')
            task['recovery_pending'] = self._has_garbage(db, task_id)
            if task['recovery_pending']:
                if task['state'] == 'closed':
                    task['state'] = 'closing'
            for item in task['criteria']:
                result = item.get('result')
                if result and item['validity'] == 'current':
                    try:
                        if not self._current(task, result):
                            item['validity'] = 'stale'
                            item['invalidation_reason'] = 'Workspace inputs, identity, or evidence changed since this check'
                            if item['user_acceptance'] == 'accepted':
                                item['user_acceptance'] = 'invalidated'
                    except (OSError, TaskError):
                        item['validity'] = 'unknown'
                        item['invalidation_reason'] = 'Workspace or evidence cannot be verified'
            if not detail:
                task = {k: task[k] for k in ('task_id', 'title', 'revision', 'state', 'workspace', 'requirements', 'recovery', 'criteria', 'recovery_pending')}
                for item in task['criteria']:
                    if item.get('result'):
                        item['result'] = {k: v for k, v in item['result'].items() if k not in ('stdout', 'stderr')}
            return task

    def checklist(self, task_id, item_id=None, ordinal=None, search=None, detail=False):
        task = self.read(task_id, detail=True)
        rows = [r for r in task['criteria'] if not r.get('withdrawn')]
        require(sum(x is not None for x in (item_id, ordinal, search)) <= 1, 'invalid_input', 'select id, ordinal, or search')
        if item_id is not None:
            rows = [r for r in rows if r['id'] == item_id]
            require(rows, 'not_found', 'criterion not found')
        if ordinal is not None:
            require(1 <= ordinal <= len(rows), 'not_found', 'ordinal out of range')
            rows = [rows[ordinal - 1]]
        if search is not None:
            rows = [dict(r, matched_fields=[k for k in ('name', 'requirement') if search.casefold() in r[k].casefold()])
                    for r in rows if any(search.casefold() in r[k].casefold() for k in ('name', 'requirement'))]
        if not detail:
            rows = [{k: v for k, v in row.items() if k in ('id', 'name', 'requirement', 'verification', 'validity', 'user_acceptance', 'matched_fields', 'invalidation_reason')} for row in rows]
        return {'task_id': task_id, 'revision': task['revision'], 'recovery_pending': task['recovery_pending'], 'items': rows}

    def resolve(self, session, workspace):
        root = str(Path(workspace).resolve())
        with self.connection() as db:
            row = db.execute('SELECT task FROM bindings WHERE session=? AND workspace=?', (session, root)).fetchone() if db else None
        if row:
            return self.read(row[0])
        return {'status': 'unbound', 'candidates': [t for t in self.list(root) if t['state'] != 'closed']}

    def _path(self, relative):
        p = self.root / relative
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'invalid_input', 'invalid artifact path')
        require(p.resolve() == p and not p.is_symlink(), 'cleanup_blocked', 'artifact path escapes root or is a symlink')
        return p

    def _current(self, task, result):
        if workspace_info(task['workspace']['path'])['id'] != task['workspace']['id']:
            return False
        for name in result.get('evidence', []):
            a = task['artifacts'].get(name)
            if not a:
                return False
            path = self._path(a['path'])
            if not path.is_file() or digest(path.read_bytes()) != a['sha256']:
                return False
        return result['input_digest'] == fingerprint(task['workspace']['path'], result.get('watched_paths'))

    def artifact_read(self, task_id, name):
        task = self.read(task_id, detail=True)
        a = task['artifacts'].get(name)
        require(a is not None, 'not_found', 'artifact not found')
        p = self._path(a['path'])
        raw = p.read_bytes()
        require(digest(raw) == a['sha256'], 'artifact_conflict', 'artifact content changed')
        return {'name': name, 'content': raw.decode('utf-8'), 'sha256': a['sha256'], 'revision': task['revision']}

    def mutate(self, action, request):
        require(isinstance(request, dict), 'invalid_input', 'request must be an object')
        request = deepcopy(request)
        for field in ('preserve', 'retain_task', 'documents_reviewed'):
            require(field not in request or type(request[field]) is bool, 'invalid_input', field + ' must be boolean')
        for field in ('affected', 'order', 'items', 'evidence', 'watched_paths', 'names'):
            if field in request and request[field] is not None:
                require(isinstance(request[field], list) and all(isinstance(x, str) for x in request[field]), 'invalid_input', field + ' must be a list of strings')
                require(len(request[field]) == len(set(request[field])), 'invalid_input', field + ' contains duplicates')
        if 'criteria' in request:
            require(isinstance(request['criteria'], list) and all(isinstance(c, dict) for c in request['criteria']), 'invalid_input', 'criteria must be a list of objects')
        if 'base_revision' in request:
            require(type(request['base_revision']) is int, 'invalid_input', 'base_revision must be an integer')
        if 'dispositions' in request:
            require(isinstance(request['dispositions'], dict), 'invalid_input', 'dispositions must be an object')
        op = request.get('operation_id')
        require(isinstance(op, str) and 0 < len(op) <= 200, 'invalid_input', 'operation_id is required')
        # A create key is globally unique within this user's data root.
        scope = request.get('task_id') or ('create:' + op)
        request_hash = digest({'action': action, 'request': request})
        with self.connection(write=True) as db:
            prior = db.execute('SELECT * FROM operations WHERE scope=? AND id=?', (scope, op)).fetchone()
            if prior:
                require(prior['request_hash'] == request_hash, 'idempotency_conflict', 'operation_id reused with different input')
                require(prior['state'] != 'cancelled', 'operation_cancelled', 'operation was aborted; use a new operation_id')
                if prior['state'] == 'done':
                    result = json.loads(prior['result'])
                    self._gc_rows(db, result['task_id'])
                    return result
            else:
                require(not self._pending(db, scope), 'recovery_pending', 'recover the pending task operation first')
                plan = self._plan(db, action, request)
                db.execute('INSERT INTO operations VALUES(?,?,?,?,?,NULL)', (scope, op, request_hash, 'pending', encoded(plan)))
        self.fault('prepared')
        return self._finish(scope, op)

    def _plan(self, db, action, q):
        puts, deletes = [], []
        task_id = q.get('task_id')
        if action in ('create', 'import'):
            require(not task_id, 'invalid_input', 'create/import assigns a task ID')
            task_id = uuid.uuid4().hex
            specs = q.get('criteria', [])
            task = {'task_id': task_id, 'title': q.get('title', ''), 'requirements': q.get('requirements', ''),
                    'workspace': workspace_info(q['workspace']), 'revision': 0, 'state': 'draft',
                    'criteria': [criterion(x) for x in specs], 'recovery': '', 'artifacts': {},
                    'created_at': now(), 'feedback': None, 'retained': False}
            require(isinstance(task['title'], str) and task['title'].strip(), 'invalid_input', 'title is required')
            if action == 'import':
                source = Path(q['source']).resolve()
                record = json.loads((source / 'checklist.yaml').read_text())
                require(Path(record['repo']).resolve() == Path(q['workspace']).resolve(), 'workspace_mismatch', 'legacy record is for another workspace')
                query_path = (source / record['source']['query_path']).resolve()
                require(query_path.is_relative_to(source), 'invalid_input', 'legacy query escapes selected record')
                task['requirements'] = query_path.read_text()
                task['criteria'] = [criterion({'id': c['id'], 'name': c['requirement'], 'requirement': c['requirement'],
                                               'expected': encoded(next(p['expected'] for p in record['protocols'] if p['id'] == c['requirement_ref']))})
                                    for c in record['checklist']]
                task['recovery'] = 'Imported requirements only; legacy execution/acceptance is not current verification.'
                task['import_source'] = {'path': str(source), 'sha256': digest((source / 'checklist.yaml').read_bytes())}
        else:
            require(isinstance(task_id, str), 'invalid_input', 'task_id is required')
            task = self._task(db, task_id)
            require(q.get('base_revision') == task['revision'], 'revision_conflict', 'reread current task revision')
            require(task['state'] != 'closed' or action in ('reopen', 'forget', 'prune', 'artifact-policy'), 'invalid_state', 'closed task; explicitly reopen retained task')
            if action not in ('rebind', 'forget', 'prune', 'artifact-policy'):
                require(workspace_info(task['workspace']['path'])['id'] == task['workspace']['id'], 'workspace_mismatch', 'workspace identity changed; rebind explicitly')
        preconditions = []
        if action in ('result', 'submit', 'feedback', 'closeout'):
            if action == 'result':
                preconditions = [{'input_digest': q.get('input_digest'), 'watched_paths': q.get('watched_paths')}]
            else:
                preconditions = [c['result'] for c in task['criteria'] if c.get('result') and not c['withdrawn']
                                 and (action != 'feedback' or (q.get('outcome') == 'accepted' and c['id'] in q.get('items', [])))]
        def find_item():
            matches = [c for c in task['criteria'] if c['id'] == q.get('item_id') and not c['withdrawn']]
            require(matches, 'not_found', 'criterion not found')
            return matches[0]
        if action == 'revise':
            require(task['state'] != 'closing', 'invalid_state', 'finish/recover closeout before revising')
            affected = set(q.get('affected', []))
            if 'requirements' in q:
                task['requirements'] = q['requirements']
                # Missing dependency declaration conservatively invalidates all.
                if 'affected' not in q:
                    affected = {c['id'] for c in task['criteria']}
            for change in q.get('criteria', []):
                old = next((c for c in task['criteria'] if c['id'] == change['id']), None)
                if old is None:
                    task['criteria'].append(criterion(change))
                else:
                    require(not old['withdrawn'], 'invalid_input', 'withdrawn IDs cannot be reused')
                    allowed = {'id', 'name', 'requirement', 'expected', 'method', 'source', 'withdrawn'}
                    require(set(change) <= allowed, 'invalid_input', 'cannot edit result fields through revise')
                    old.update(change)
                    affected.add(old['id'])
            require(affected <= {c['id'] for c in task['criteria']}, 'not_found', 'affected criterion missing')
            for c in task['criteria']:
                if c['id'] in affected:
                    c['requirement_revision'] += 1
                    c['validity'] = 'stale' if c['result'] else 'unknown'
                    c['invalidation_reason'] = 'Requirement revised'
                    if c['user_acceptance'] == 'accepted':
                        c['user_acceptance'] = 'invalidated'
            if 'order' in q:
                require(len(q['order']) == len(task['criteria']) and set(q['order']) == {c['id'] for c in task['criteria']}, 'invalid_input', 'order must list every stable ID once')
                task['criteria'].sort(key=lambda c: q['order'].index(c['id']))
            if 'recovery' in q:
                task['recovery'] = q['recovery']
            task['state'] = 'active'
        elif action == 'result':
            c = find_item()
            require(q.get('verification') in ('passed', 'failed', 'error'), 'invalid_input', 'verification must be passed/failed/error')
            require(q.get('source') == 'external', 'invalid_input', 'CLI imports externally observed results, not runtime-executed checks')
            require(isinstance(q.get('method'), str) and q['method'].strip(), 'invalid_input', 'method description is required')
            require(q.get('input_digest') == fingerprint(task['workspace']['path'], q.get('watched_paths')), 'stale_result', 'inputs changed or missing observed fingerprint')
            for name in q.get('evidence', []):
                require(name in task['artifacts'], 'not_found', 'evidence artifact missing')
            c.update(verification=q['verification'], validity='current', invalidation_reason='', user_acceptance='pending', feedback=None,
                     result={k: q[k] for k in ('source', 'method', 'input_digest', 'watched_paths', 'evidence', 'stdout', 'stderr', 'returncode') if k in q})
            c['result'].update(at=now(), requirement_revision=c['requirement_revision'])
            task['state'] = 'active'
        elif action == 'submit':
            active = [c for c in task['criteria'] if not c['withdrawn']]
            require(active and all(c['verification'] == 'passed' and c['validity'] == 'current' and self._current(task, c['result']) for c in active), 'invalid_state', 'current passing checks required')
            task['state'] = 'awaiting_acceptance'
        elif action == 'feedback':
            require(q.get('outcome') in ('accepted', 'rejected'), 'invalid_input', 'feedback outcome required')
            require(isinstance(q.get('quote'), str) and q['quote'].strip() and q.get('source_ref'), 'invalid_input', 'feedback requires user quote and source_ref')
            ids = q.get('items', [])
            require(ids and set(ids) <= {c['id'] for c in task['criteria'] if not c['withdrawn']}, 'invalid_input', 'explicit feedback scope is required')
            feedback = {k: q[k] for k in ('outcome', 'quote', 'source_ref', 'items')}
            feedback['revision'] = task['revision']
            for c in task['criteria']:
                if c['id'] in ids:
                    if q['outcome'] == 'accepted':
                        require(c['result'] and c['validity'] == 'current' and c['verification'] == 'passed' and self._current(task, c['result']), 'stale_result', 'cannot accept stale/unverified criterion')
                    c['user_acceptance'] = q['outcome']
                    c['feedback'] = feedback
            task['feedback'] = feedback
            task['state'] = 'active' if q['outcome'] == 'rejected' else 'awaiting_acceptance'
        elif action == 'artifact':
            name = q.get('name')
            require(isinstance(name, str) and name and '/' not in name and '\\' not in name and name not in ('.', '..'), 'invalid_input', 'artifact name must be a simple logical name')
            require(isinstance(q.get('content'), str), 'invalid_input', 'artifact content must be UTF-8 text')
            old = task['artifacts'].get(name)
            if old:
                require(not old.get('preserve'), 'cleanup_blocked', 'artifact explicitly preserved')
                require(not any(name in (c.get('result') or {}).get('evidence', []) for c in task['criteria']), 'cleanup_blocked', 'artifact is referenced by a result')
                deletes.append(old)
            content = q['content']
            relative = 'artifacts/' + task_id + '/' + uuid.uuid4().hex + '.txt'
            a = {'path': relative, 'sha256': digest(content.encode()), 'purpose': q.get('purpose', 'scratch'), 'preserve': bool(q.get('preserve', False))}
            task['artifacts'][name] = a
            puts.append(dict(a, content=content))
        elif action == 'closeout':
            active = [c for c in task['criteria'] if not c['withdrawn']]
            require(active and all(c['user_acceptance'] == 'accepted' for c in active), 'invalid_state', 'explicit user acceptance required')
            for c in active:
                require(c['result'] and c['validity'] == 'current' and self._current(task, c['result']), 'stale_result', 'closeout requires current evidence; revise/recheck changed behavior')
            require(q.get('rationale') and q.get('documents_reviewed') is True, 'invalid_input', 'Cleaner must review documents and state disposition rationale')
            dispositions = q.get('dispositions', {})
            require(set(dispositions) == set(task['artifacts']), 'invalid_input', 'provide one disposition for every owned artifact')
            retained = bool(q.get('retain_task', False))
            for name, decision in dispositions.items():
                require(decision in ('keep', 'delete'), 'invalid_input', 'disposition is keep or delete')
                a = task['artifacts'][name]
                if decision == 'delete':
                    require(not a.get('preserve'), 'cleanup_blocked', 'user-preserved artifact cannot be deleted')
                    require(not retained or not any(name in (c.get('result') or {}).get('evidence', []) for c in task['criteria']), 'cleanup_blocked', 'retained task still references evidence')
                    deletes.append(a)
            task['artifacts'] = {n: a for n, a in task['artifacts'].items() if dispositions[n] == 'keep'}
            task['state'], task['retained'] = 'closed', retained
            task['closed_at'] = now()
            if not retained:
                task.update(requirements='', recovery='', criteria=[], feedback=None)
                task.pop('import_source', None)
        elif action == 'reopen':
            require(task['state'] == 'closed' and task['retained'], 'invalid_state', 'only a retained task can reopen')
            task['state'] = 'active'
        elif action == 'rebind':
            task['workspace'] = workspace_info(q['workspace'])
            for c in task['criteria']:
                c['validity'] = 'stale' if c['result'] else 'unknown'
                if c['user_acceptance'] == 'accepted':
                    c['user_acceptance'] = 'invalidated'
        elif action == 'bind':
            require(q.get('session_id') and str(Path(q['workspace']).resolve()) == task['workspace']['path'], 'workspace_mismatch', 'binding requires session and matching workspace')
        elif action == 'artifact-policy':
            require(q.get('name') in task['artifacts'] and type(q.get('preserve')) is bool and q.get('quote') and q.get('source_ref'), 'invalid_input', 'explicit user retention instruction required')
            task['artifacts'][q['name']]['preserve'] = q['preserve']
        elif action == 'prune':
            require(task['state'] == 'closed' and not task['retained'], 'invalid_state', 'prune is for closed, non-retained task artifacts')
            require(q.get('rationale') and q.get('names'), 'invalid_input', 'explicit artifact names and rationale required')
            for name in q['names']:
                require(name in task['artifacts'], 'not_found', 'artifact not found')
                a = task['artifacts'][name]
                require(not a.get('preserve'), 'cleanup_blocked', 'release user retention before deletion')
                deletes.append(a)
            task['artifacts'] = {n: a for n, a in task['artifacts'].items() if n not in q['names']}
        elif action == 'forget':
            require(task['state'] == 'closed' and not task['artifacts'], 'cleanup_blocked', 'forget requires closed task without retained artifacts')
        elif action not in ('create', 'import'):
            raise TaskError('invalid_input', 'unknown task action')
        require(len({c['id'] for c in task['criteria']}) == len(task['criteria']), 'invalid_input', 'duplicate criterion IDs')
        for c in task['criteria']:
            criterion(c)  # Validate semantic fields after partial updates as well.
        require(isinstance(task['requirements'], str) and isinstance(task['recovery'], str), 'invalid_input', 'requirements/recovery must be strings')
        for a in deletes:
            p = self._path(a['path'])
            require(p.is_file() and digest(p.read_bytes()) == a['sha256'], 'artifact_conflict', 'owned artifact changed or missing before cleanup')
        task['revision'] += 1
        result = {'task_id': task_id, 'revision': task['revision'], 'state': task['state']}
        if action == 'artifact':
            result['artifact'] = task['artifacts'][q['name']]
        evidence_names = set()
        if action == 'result':
            evidence_names.update(q.get('evidence', []))
        elif action in ('submit', 'feedback'):
            for c in task['criteria']:
                if not c['withdrawn'] and (action == 'submit' or (q.get('outcome') == 'accepted' and c['id'] in q.get('items', []))):
                    evidence_names.update((c.get('result') or {}).get('evidence', []))
        elif action == 'closeout':
            evidence_names.update(task['artifacts'])
        validation_artifacts = [task['artifacts'][name] for name in evidence_names]
        return {'task': task, 'puts': puts, 'deletes': deletes, 'preconditions': preconditions, 'validation_artifacts': validation_artifacts, 'action': action, 'result': result,
                'binding': {'session': q['session_id'], 'workspace': task['workspace']['path']} if action == 'bind' else None}

    def _finish(self, scope, op):
        with self.connection(write=True) as db:
            row = db.execute('SELECT * FROM operations WHERE scope=? AND id=?', (scope, op)).fetchone()
            require(row is not None, 'not_found', 'operation missing')
            if row['state'] == 'done':
                result = json.loads(row['result'])
                self._gc_rows(db, result['task_id'])
                return result
            require(row['state'] == 'pending', 'operation_cancelled', 'operation is not pending')
            plan = json.loads(row['plan'])
            for a in plan.get('validation_artifacts', []):
                path = self._path(a['path'])
                require(path.is_file() and digest(path.read_bytes()) == a['sha256'], 'artifact_conflict', 'required evidence changed during operation')
            for condition in plan.get('preconditions', []):
                require(condition['input_digest'] == fingerprint(plan['task']['workspace']['path'], condition.get('watched_paths')), 'stale_result', 'inputs changed during operation; abort pending operation and recheck')
            for a in plan['puts']:
                p = self._path(a['path'])
                p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temp = self._path(a['path'] + '.pending')
                require(not p.exists() or digest(p.read_bytes()) == a['sha256'], 'artifact_conflict', 'published artifact changed')
                with temp.open('wb') as stream:
                    stream.write(a['content'].encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                self.fault('file_written')
                os.replace(temp, p)
                self._sync(p.parent)
                self.fault('file_published')
            for a in plan['deletes']:
                p = self._path(a['path'])
                trash = self._path(a['path'] + '.trash')
                if trash.exists():
                    require(not p.exists() and digest(trash.read_bytes()) == a['sha256'], 'artifact_conflict', 'quarantined artifact changed')
                else:
                    require(p.is_file() and digest(p.read_bytes()) == a['sha256'], 'artifact_conflict', 'owned file missing or changed since cleanup preparation')
                    os.replace(p, trash)
                    self._sync(p.parent)
                db.execute('INSERT OR REPLACE INTO garbage VALUES(?,?)', (a['path'] + '.trash', a['sha256']))
                self.fault('file_deleted')
            self.fault('before_commit')
            task = plan['task']
            if plan['action'] == 'forget':
                create_op = self._create_operation(db, task['task_id'])
                db.execute('DELETE FROM operations WHERE scope=?', ('create:' + create_op,))
                db.execute('DELETE FROM tasks WHERE id=?', (task['task_id'],))
                db.execute('DELETE FROM bindings WHERE task=?', (task['task_id'],))
                db.execute('DELETE FROM operations WHERE scope=?', (scope,))
            else:
                db.execute('INSERT OR REPLACE INTO tasks VALUES(?,?)', (task['task_id'], encoded(task)))
                if plan['binding']:
                    b = plan['binding']
                    db.execute('INSERT OR REPLACE INTO bindings VALUES(?,?,?)', (b['session'], b['workspace'], task['task_id']))
                if plan['action'] in ('closeout', 'rebind'):
                    db.execute('DELETE FROM bindings WHERE task=?', (task['task_id'],))
                if plan['action'] == 'closeout':
                    # Keep replay hashes and compact results; discard request/plan prose.
                    db.execute("UPDATE operations SET plan='{}' WHERE scope=? AND state='done'", (scope,))
                    db.execute("UPDATE operations SET plan='{}' WHERE scope=? AND state='done'", ('create:' + self._create_operation(db, task['task_id']),))
                db.execute("UPDATE operations SET state='done',result=?,plan='{}' WHERE scope=? AND id=?", (encoded(plan['result']), scope, op))
        self.fault('committed')
        self._collect_garbage(plan['task']['task_id'])
        return plan['result']

    @staticmethod
    def _create_operation(db, task_id):
        for row in db.execute("SELECT id,result FROM operations WHERE scope LIKE 'create:%'"):
            if row['result'] and json.loads(row['result']).get('task_id') == task_id:
                return row['id']
        return ''

    @staticmethod
    def _sync(directory):
        if os.name == 'posix':
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    def _gc_rows(self, db, task_id=None):
        for row in list(db.execute('SELECT path,sha256 FROM garbage')):
            if task_id is not None and not row['path'].startswith('artifacts/' + task_id + '/'):
                continue
            p = self._path(row['path'])
            if p.exists():
                require(digest(p.read_bytes()) == row['sha256'], 'artifact_conflict', 'committed garbage changed; preserve it')
                p.unlink()
                self._sync(p.parent)
            db.execute('DELETE FROM garbage WHERE path=?', (row['path'],))

    def _collect_garbage(self, task_id=None):
        with self.connection(write=True) as db:
            self._gc_rows(db, task_id)

    @staticmethod
    def _has_garbage(db, task_id):
        return db.execute('SELECT 1 FROM garbage WHERE path LIKE ? LIMIT 1', ('artifacts/' + task_id + '/%',)).fetchone() is not None

    def abort(self, task_id, operation_id):
        """Roll back only an uncommitted plan, preserving original artifact bytes."""
        with self.connection(write=True) as db:
            row = db.execute('SELECT * FROM operations WHERE scope=? AND id=?', (task_id, operation_id)).fetchone()
            require(row is not None and row['state'] in ('pending', 'cancelled'), 'invalid_state', 'only a pending operation can be aborted')
            if row['state'] == 'cancelled':
                return {'status': 'cancelled', 'operation_id': operation_id}
            plan = json.loads(row['plan'])
            for a in plan['deletes']:
                p, trash = self._path(a['path']), self._path(a['path'] + '.trash')
                if trash.exists():
                    require(not p.exists() and digest(trash.read_bytes()) == a['sha256'], 'artifact_conflict', 'cannot restore modified quarantine')
                    os.replace(trash, p)
                    self._sync(p.parent)
            for a in plan['puts']:
                p = self._path(a['path'])
                if p.exists():
                    require(digest(p.read_bytes()) == a['sha256'], 'artifact_conflict', 'cannot discard changed pending output')
                    p.unlink()
                temp = self._path(a['path'] + '.pending')
                temp.unlink(missing_ok=True)
            db.execute("UPDATE operations SET state='cancelled',plan='{}' WHERE scope=? AND id=?", (task_id, operation_id))
        return {'status': 'cancelled', 'operation_id': operation_id}

    def recover(self, task_id=None):
        with self.connection() as db:
            rows = list(db.execute("SELECT scope,id FROM operations WHERE state='pending'")) if db else []
        result = [self._finish(row['scope'], row['id']) for row in rows if task_id is None or row['scope'] == task_id]
        if self.db.exists():
            self._collect_garbage(task_id)
        return result
