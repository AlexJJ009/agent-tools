"""Small, local route records with optimistic concurrency and explicit boundaries.

This is a cooperative workflow, not an OS sandbox or an identity authenticator.
Only the explicit entry points below are checked. Semantic intent, supplied
permission scopes, writing quality and learner competence require Agent/human review.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import tempfile
import uuid


class RouteError(ValueError):
    """A route or covered operation violates its declared contract."""


def require(condition, message):
    if not condition:
        raise RouteError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write(path, data):
    write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())


@contextmanager
def locked(root):
    root = Path(root).resolve()
    require(root.is_dir(), 'record directory does not exist')
    with (root / '.route.lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield root


ACTIVITIES = {'delivery', 'learning', 'writing', 'curation', 'answer'}
MODES = {'direct', 'guided', 'practice', 'review'}
ACTIONS = {'read', 'write_artifact', 'curate', 'zotero_read', 'zotero_mutation',
           'formal_close_read', 'remote_read', 'experiment', 'external_publish'}
REQUIRED = {'activity', 'interaction_mode', 'workspace_context', 'selected_skills',
            'excluded_actions', 'material_refs', 'output_targets', 'rationale', 'unresolved'}
OPTIONAL = {'next_stage', 'development_record_ref', 'readpapers_root', 'authorized_read_roots',
            'authorized_actions', 'project_id', 'skill_roots'}


def string_list(value, name):
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value), name + ' must be a string list')
    require(len(value) == len(set(value)), name + ' contains duplicates')


def validate_decision(decision):
    require(isinstance(decision, dict), 'decision must be an object')
    require(REQUIRED <= decision.keys(), 'missing decision fields: ' + str(sorted(REQUIRED - decision.keys())))
    require(not decision.keys() - REQUIRED - OPTIONAL, 'unknown decision fields: ' + str(sorted(decision.keys() - REQUIRED - OPTIONAL)))
    require(decision['activity'] in ACTIVITIES, 'invalid activity')
    require(decision['interaction_mode'] in MODES, 'invalid interaction mode')
    require(decision['workspace_context'] in {'repository', 'readpapers', 'manuscript', 'other'}, 'invalid workspace context')
    require(isinstance(decision['rationale'], str) and decision['rationale'].strip(), 'a short observable rationale is required')
    for name in ['selected_skills', 'excluded_actions', 'material_refs', 'output_targets', 'unresolved', 'authorized_read_roots', 'authorized_actions', 'skill_roots']:
        string_list(decision.get(name, []), name)
    for skill in decision['selected_skills']:
        require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', skill), 'invalid skill name')
    require(set(decision.get('authorized_actions', [])) <= ACTIONS, 'unknown authorized action')
    for name in ('readpapers_root', 'project_id'):
        require(name not in decision or isinstance(decision[name], str) and decision[name].strip(), 'invalid ' + name)
    stage = decision.get('next_stage')
    require(stage is None or isinstance(stage, dict) and stage.get('activity') in ACTIVITIES
            and isinstance(stage.get('continuation'), str) and bool(stage['continuation'].strip()), 'next_stage requires activity and continuation')
    dev = decision.get('development_record_ref')
    require(dev is None or isinstance(dev, dict) and isinstance(dev.get('path'), str)
            and type(dev.get('revision')) is int and dev['revision'] >= 0, 'development_record_ref requires path and revision')
    return decision


def resolve_target(record, target):
    path = Path(target)
    return (Path(record['workspace_root']) / path).resolve() if not path.is_absolute() else path.resolve()


def read(root):
    root = Path(root).resolve()
    record = load(root / 'routing.json')
    require(record.get('schema_version') == 'task-route/1', 'unsupported route schema')
    require(type(record.get('route_revision')) is int and record['route_revision'] >= 1, 'invalid route revision')
    require(Path(record['workspace_root']).is_absolute(), 'workspace_root must be absolute')
    require(isinstance(record.get('session_id'), str) and bool(record['session_id']), 'missing session id')
    require(isinstance(record.get('task_id'), str) and bool(record['task_id']), 'missing task id')
    validate_decision(record['decision'])
    require(isinstance(record.get('inputs'), dict) and isinstance(record.get('history'), list), 'invalid input/history state')
    for item in record['inputs'].values():
        path = (root / item['path']).resolve()
        require(path.is_relative_to(root), 'request snapshot escapes record')
        require(sha(path.read_bytes()) == item['sha256'], 'request snapshot changed')
        require(item['status'] in {'pending', 'classified'}, 'invalid input status')
    return record


def views(root, record):
    d = record['decision']
    # Development task.md is owned by the existing runtime; a route sidecar must not overwrite it.
    filename = 'routing.md' if d.get('development_record_ref') else 'task.md'
    text = (f"# Task Route\n\nTask: {record['task_id']}\n\nActivity: {d['activity']} ({d['interaction_mode']})\n\n"
            f"Revision: {record['route_revision']}\n\nReason: {d['rationale']}\n\n"
            f"Pending input: {', '.join(k for k, v in record['inputs'].items() if v['status'] == 'pending') or 'none'}\n\n"
            f"Unresolved: {json.dumps(d['unresolved'], ensure_ascii=False)}\n\n"
            f"Continuation: {json.dumps(d.get('next_stage'), ensure_ascii=False)}\n\n"
            f"Development record: {json.dumps(d.get('development_record_ref'), ensure_ascii=False)}\n\n"
            "Canonical route: routing.json. This record does not certify intent, learning, or acceptance.\n")
    write_bytes(Path(root) / filename, text.encode())


def save(root, record):
    write(Path(root) / 'routing.json', record)
    views(root, record)
    return record


def init(query, decision, workspace, session_id, task_id=None, record=None):
    validate_decision(decision)
    require(isinstance(session_id, str) and bool(session_id.strip()), 'session id is required')
    workspace = Path(workspace).resolve()
    require(workspace.is_dir(), 'workspace must exist')
    stamp = datetime.now(timezone.utc)
    task_id = task_id or stamp.strftime('%Y%m%dT%H%M%SZ') + '-task-' + uuid.uuid4().hex[:8]
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,159}', task_id), 'invalid task id')
    data = Path(query).read_bytes()
    require(data.decode('utf-8').strip(), 'empty request')
    dev = decision.get('development_record_ref')
    if dev:
        devroot = Path(dev['path']).resolve()
        require((devroot / 'checklist.yaml').is_file(), 'development record is missing')
        require(record is None or Path(record).resolve() == devroot, 'development route must reuse the canonical record directory')
        root = devroot
        request_name = 'routing-request.txt'
    else:
        root = Path(record).resolve() if record else workspace / 'docs/learning-workflow/records' / stamp.strftime('%Y-%m-%d') / task_id
        request_name = 'request.txt'
    root.mkdir(parents=True, exist_ok=True)
    with locked(root):
        require(not (root / 'routing.json').exists(), 'route already exists; use input and classify')
        require(not (root / request_name).exists(), 'request path already exists')
        write_bytes(root / request_name, data)
        result = {'schema_version':'task-route/1', 'task_id':task_id, 'session_id':session_id,
                  'workspace_root':str(workspace), 'created_at':now(), 'route_revision':1,
                  'decision':decision, 'request_refs':[request_name],
                  'inputs':{'initial':{'path':request_name, 'sha256':sha(data), 'status':'classified'}},
                  'history':[{'kind':'classification','input_id':'initial','revision':1,'at':now(),'decision':decision}]}
        save(root, result)
    return {'record':str(root), 'route_revision':1}


def input_record(root, input_id, query):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,159}', input_id), 'invalid input id')
    data = Path(query).read_bytes()
    require(data.decode('utf-8').strip(), 'empty request')
    with locked(root) as root:
        record = read(root)
        if input_id in record['inputs']:
            require(record['inputs'][input_id]['sha256'] == sha(data), 'input id reused with different bytes')
            return record
        rel = 'inputs/' + input_id + '.txt'
        write_bytes(root / rel, data)
        record['inputs'][input_id] = {'path':rel, 'sha256':sha(data), 'status':'pending'}
        record['request_refs'].append(rel)
        record['route_revision'] += 1
        record['history'].append({'kind':'input','input_id':input_id,'revision':record['route_revision'],'at':now()})
        return save(root, record)


def classify(root, input_id, decision, base_revision):
    validate_decision(decision)
    with locked(root) as root:
        record = read(root)
        require(input_id in record['inputs'], 'unknown input id')
        # Idempotence is tied to input plus decision; changed decisions need a new user input.
        old = [e for e in record['history'] if e['kind'] == 'classification' and e['input_id'] == input_id]
        if old:
            require(old[-1]['decision'] == decision, 'input already classified differently')
            return record
        require(record['route_revision'] == base_revision, 'route revision conflict; read current state before classifying')
        order = list(record['inputs'])
        later_classified = any(v['status'] == 'classified' for k, v in record['inputs'].items() if order.index(k) > order.index(input_id))
        require(not later_classified or decision == record['decision'], 'older input cannot overwrite a newer decision; reconcile it with current constraints')
        old_dev = record['decision'].get('development_record_ref')
        new_dev = decision.get('development_record_ref')
        require(bool(old_dev) == bool(new_dev), 'development record ownership cannot change')
        if old_dev:
            require(Path(old_dev['path']).resolve() == Path(new_dev['path']).resolve(), 'development record ownership cannot change')
        record['decision'] = decision
        record['inputs'][input_id]['status'] = 'classified'
        record['route_revision'] += 1
        record['history'].append({'kind':'classification','input_id':input_id,'revision':record['route_revision'],'at':now(),'decision':decision})
        return save(root, record)


def remote_locator(value):
    require(isinstance(value, str) and ':' in value, 'remote locator must be host:/absolute/path')
    host, path = value.split(':', 1)
    require(bool(re.fullmatch(r'[A-Za-z0-9_.@-]+', host)) and path.startswith('/') and not path.startswith('//'), 'invalid remote locator')
    require(path == posixpath.normpath(path) and '..' not in path.split('/'), 'remote path traversal or noncanonical path')
    require(not any(ord(c) < 32 for c in path), 'invalid remote path')
    return host, path


def check(record, action, target=None, base_revision=None):
    require(action in ACTIONS, 'unknown action')
    if action == 'read':
        return {'status':'allowed','coverage':'ordinary read; not an execution authorization'}
    require(record['route_revision'] == base_revision, 'route revision conflict')
    require(not any(v['status'] == 'pending' for v in record['inputs'].values()), 'unclassified user input; resolve it before dependent actions')
    d = record['decision']
    require(not d['unresolved'], 'unresolved route dependencies')
    require(action not in d['excluded_actions'], 'action explicitly excluded')
    require(action not in {'experiment', 'external_publish'}, 'use the existing development/publication authorization entry; a route is not execution authority')
    for skill in d['selected_skills']:
        roots = d.get('skill_roots') or [str(Path.home()/'.agents/skills'), str(Path.home()/'.codex/skills'), str(Path(record['workspace_root'])/'.claude/skills')]
        require(any((Path(p)/skill/'SKILL.md').is_file() for p in roots), 'selected capability unavailable: ' + skill)
    if action in {'zotero_read','zotero_mutation','formal_close_read'}:
        configured = d.get('readpapers_root')
        require(configured and d['workspace_context'] == 'readpapers'
                and Path(record['workspace_root']).is_relative_to(Path(configured).resolve()), 'ReadPapers adapter scope required')
        require('read-paper' in d['selected_skills'], 'read-paper adapter must be selected')
        require(action in d.get('authorized_actions', []), 'library action not explicitly declared in scope')
    if action == 'remote_read':
        require(action in d.get('authorized_actions', []) and target, 'remote read scope is required')
        # Remote roots are opaque host:path prefixes, never passed to a shell here.
        host, remote = remote_locator(target)
        scopes = [remote_locator(p) for p in d.get('authorized_read_roots', [])]
        require(any(host == h and (remote == p or remote.startswith(p.rstrip('/') + '/')) for h, p in scopes), 'remote path outside declared read-only scope')
    if action in {'write_artifact', 'curate'}:
        require(target, 'target required')
        path = resolve_target(record, target)
        require(any(path == resolve_target(record, p) or path.is_relative_to(resolve_target(record, p)) for p in d['output_targets']), 'target outside declared outputs')
    if action == 'curate':
        require(d['activity'] == 'curation' and action in d.get('authorized_actions', []), 'explicit curation scope required')
    return {'status':'allowed','action':action,'route_revision':record['route_revision'],
            'coverage':'declared workflow scope only; no semantic or identity authentication'}


def check_action(root, action, target=None, base_revision=None):
    with locked(root) as root:
        return check(read(root), action, target, base_revision)


def curate(root, source, destination, title, topic, base_revision):
    """Copy an explicitly selected artifact and maintain one relocatable index.

The caller supplies the finished note. This function cannot establish that its
contents are self-contained, accurate or free of private data.
"""
    with locked(root) as root:
        record = read(root)
        source, destination = Path(source).resolve(), resolve_target(record, destination)
        check(record, 'curate', str(destination), base_revision)
        require(not destination.is_relative_to(root), 'curation destination must be outside routing state')
        workspace = Path(record['workspace_root'])
        require(source.is_relative_to(workspace) and source.is_file(), 'curation source must be a file in the source workspace')
        require(not source.is_relative_to(root), 'curation cannot copy internal routing state')
        d = record['decision']
        source_rel = source.relative_to(workspace).as_posix()
        project = d.get('project_id')
        require(project, 'curation requires an explicit stable project_id; a directory basename is not a project identity')
        key = sha((project + '\n' + source_rel).encode())[:20]
        destination.mkdir(parents=True, exist_ok=True)
        with locked(destination):
            index_path = destination/'artifact-index.json'
            index = load(index_path) if index_path.exists() else {'schema_version':'artifact-index/1','entries':{}}
            require(index.get('schema_version') == 'artifact-index/1' and isinstance(index.get('entries'),dict), 'invalid artifact index')
            prior = index['entries'].get(key)
            note = destination/(key + source.suffix)
            require(source != note, 'source and destination must differ')
            data = source.read_bytes()
            if note.exists():
                require(prior and prior.get('artifact_sha256') == sha(note.read_bytes()), 'curated artifact changed; preserve edits before reimport')
            write_bytes(note, data)
            import subprocess
            result = subprocess.run(['git','-C',str(workspace),'rev-parse','HEAD'], capture_output=True,text=True)
            revision = result.stdout.strip() if result.returncode == 0 else None
            index['entries'][key] = {'title':title,'topic':topic,'source_project':project,'source_revision':revision,
                                     'source_path':source_rel,'artifact_path':note.name,'artifact_sha256':sha(data),
                                     'source_status':'observed','status':'curated','updated_at':now()}
            write(index_path,index)
        return {'status':'curated','artifact':str(note),'index':str(index_path),'entry':key}


def inspect_index(index_path, source_root=None):
    index_path = Path(index_path).resolve()
    index = load(index_path)
    require(index.get('schema_version') == 'artifact-index/1', 'invalid artifact index')
    observations = {}
    for key, entry in index['entries'].items():
        note = (index_path.parent/entry['artifact_path']).resolve()
        require(note.is_relative_to(index_path.parent), 'index artifact escapes destination')
        original = (Path(source_root).resolve()/entry['source_path']).resolve() if source_root else None
        if original:
            require(original.is_relative_to(Path(source_root).resolve()), 'index source escapes project')
        observations[key] = {'artifact_available':note.is_file(),
                             'artifact_unchanged':note.is_file() and sha(note.read_bytes()) == entry['artifact_sha256'],
                             'source_status':'unavailable' if original is None or not original.is_file() else 'available'}
    return observations
