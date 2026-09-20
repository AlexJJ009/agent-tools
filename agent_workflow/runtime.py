"""File-backed checks, receipts and authorization for explicitly protected actions."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from .contracts import (ContractError, digest, extract_query, fields, file_digest,
                        load, require, resolve_bindings, validate, within)


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, indent=2) + '\n'
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.workflow-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if Path(name).exists():
            Path(name).unlink()


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.PIPE).strip()


def git_state(repo):
    return {'branch': git(repo, 'branch', '--show-current'), 'base_sha': git(repo, 'rev-parse', 'HEAD'),
            'working_tree': 'dirty' if git(repo, 'status', '--porcelain') else 'clean'}


@contextmanager
def locked(record_dir):
    record_dir = Path(record_dir).resolve()
    require((record_dir / 'checklist.yaml').is_file(), 'record not initialized')
    with (record_dir / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield record_dir


def init(query, repo, scenario, context=None, mode='local', slug='task'):
    require(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug), 'slug must be lowercase ASCII words')
    repo = Path(repo).resolve()
    state = git_state(repo)
    context = dict(context or {})
    context['scenario'] = scenario
    query_bytes = Path(query).read_bytes()
    text = query_bytes.decode('utf-8')
    require(text.strip(), 'empty query')
    extraction = extract_query(text, context)
    bindings = resolve_bindings(extraction, context)
    stamp = datetime.now(timezone.utc)
    task_id = stamp.strftime('%Y%m%dT%H%M%SZ') + '-' + slug + '-' + uuid.uuid4().hex[:6]
    root = repo / 'docs/agent-workflow/records' / stamp.strftime('%Y-%m-%d') / task_id
    protocols, checklist = [], []
    for item in extraction['items']:
        pid = item['id']
        source = {'path': 'request.txt', 'quote': item['source_quote'], 'authority': item['authority']}
        protocol = {'id': pid, 'source': source, 'meaning': item.get('meaning', str(item['normalized_value'])),
                    'expected': {'value': item['normalized_value'], 'unit': item.get('unit', 'outcome')},
                    'extraction_ref': pid, 'binding': bindings.get(pid)}
        protocols.append(protocol)
        for cid in item['checklist_ids']:
            settings = context.get('checks', {}).get(cid, {})
            high = extraction['route']['class'] != 'lightweight'
            verifier = settings.get('verifier', {'method': 'unconfigured', 'watched_paths': []})
            verifier = dict(verifier, expected_ref=pid + '.expected')
            c = {'id': cid, 'requirement': item.get('label', pid), 'requirement_ref': pid, 'source': source,
                 'risk': settings.get('risk', 'high_risk' if high else 'low'), 'verifier': verifier,
                 'evidence': {'level': 'none', 'paths': [], 'anchors': [], 'object_digest': None},
                 'agent_status': 'unverified', 'human_status': 'not_requested',
                 'review_scope': settings.get('review_scope', {'must_review': ['request.txt:1'] if high else [], 'context_only': []}),
                 'invalidated_by': []}
            if bindings.get(pid):
                c['binding_ref'] = bindings[pid]['id']
            checklist.append(c)
    policy = context.get('formal_run_policy', 'prohibited')
    record = {'schema_version': 1, 'task_id': task_id, 'created_at': now(), 'repo': str(repo), 'mode': mode,
              'protocol_view': context.get('protocol_view', False), 'source': {'query_sha256': hashlib.sha256(query_bytes).hexdigest(), 'query_path': 'request.txt'},
              'route': extraction['route'], 'extraction': extraction,
              'agreement': {'goals': context.get('goals', [text]), 'non_goals': context.get('non_goals', []),
                            'allowed_paths': context.get('allowed_paths', []), 'forbidden_paths': context.get('forbidden_paths', []),
                            'formal_run_policy': policy},
              'protocols': protocols, 'checklist': checklist, 'code_state': state, 'handoff': {'path': 'task.md'},
              'formal_run': {'class': context.get('run_class', 'exploratory'),
                             'status': 'prohibited' if policy == 'prohibited' else 'awaiting_human',
                             'required_checklist_items': [c['id'] for c in checklist],
                             'candidate_sha': None, 'agent_review': {'status': 'unverified', 'evidence': []},
                             'human_confirmation': {'required': any(c['risk'] == 'high_risk' for c in checklist),
                                                    'actor': None, 'confirmed_at': None, 'target_digest': None},
                             'command': context.get('command', []), 'command_paths': context.get('command_paths', []), 'config_paths': context.get('config_paths', []),
                             'command_digest': None, 'config_digest': None, 'agent_target_digest': None}}
    validate(record)
    root.mkdir(parents=True)
    (root / 'request.txt').write_bytes(query_bytes)
    write(root / 'checklist.yaml', record)
    (root / 'task.md').write_text('# Task agreement and work record\n\n'
        '## current_agreement\n\nCanonical requirements, expected values and statuses: [checklist.yaml](checklist.yaml).\n'
        'Original query: [request.txt](request.txt). Do not change expectations to hide failures.\n\n'
        f'## code_handoff\n\nRepository: `{repo}`\nBranch: `{state["branch"]}`\nBase: `{state["base_sha"]}`\n'
        f'Working tree: `{state["working_tree"]}`. Re-read Git diff and untracked files before resuming.\n\n'
        '## work_record\n\nNo checks executed. Investigate bindings and run applicable verifiers.\n\n'
        '## current_state\n\n<!-- workflow-state:start -->\nRunning tasks: none started by init. Human review: not requested.\n'
        'Next action: inspect current project facts, finish unresolved requirements, then check.\n'
        '<!-- workflow-state:end -->\n\nCleanup result: not yet assessed.\n')
    refresh_views(root, record)
    return root


def read_record(root):
    record = load(root / 'checklist.yaml')
    validate(record)
    query = within(root, record['source']['query_path'])
    require(file_digest(query) == record['source']['query_sha256'], 'query changed without a recorded revision')
    sources = [query.read_text()]
    for p in record['protocols']:
        source = within(root, p['source']['path'])
        require(p['source']['quote'] in source.read_text(), 'protocol quote no longer matches source')
        if p['source'].get('sha256'):
            require(file_digest(source) == p['source']['sha256'], 'revision source changed')
        if source != query:
            sources.append(source.read_text())
    # Repeat the route lint with stored facts, without selecting a new Coder.
    fresh = extract_query('\n'.join(sources), {'scenario': record['route']['primary'], 'items': record['extraction']['items'],
                                     'facts': record['route']['facts']})
    require(record['route']['modules'] == fresh['route']['modules'] and record['route']['class'] == fresh['route']['class'], 'route profile/modules mismatch')
    return record


def command_paths(repo, argv, declared=()):
    """Bind explicit inputs plus local argv files, including untracked scripts."""
    paths = set(declared)
    for arg in argv:
        if not Path(arg).is_absolute() and not arg.startswith('-'):
            path = within(repo, arg)
            if path.is_file() or Path(arg).suffix in {'.py', '.sh', '.js', '.mjs'}:
                paths.add(arg)
        elif Path(arg).is_absolute() and Path(arg).resolve().is_relative_to(Path(repo).resolve()):
            paths.add(str(Path(arg).resolve().relative_to(Path(repo).resolve())))
    return paths


def watched(record, item):
    p = next(p for p in record['protocols'] if p['id'] == item['requirement_ref'])
    paths = command_paths(record['repo'], item['verifier'].get('argv', []), item['verifier']['watched_paths'])
    paths.update(a['path'] for a in item['verifier'].get('anchors', []))
    if p['binding']:
        b = p['binding']
        paths.update(b['watched_paths'])
        paths.update(a['path'] for a in b['overrides'])
        paths.update(b[k]['path'] for k in ('definition', 'consumer'))
    require(paths or item['verifier']['method'] == 'unconfigured', f'{item["id"]}: declare relevant input/adapter paths')
    return {x: file_digest(within(record['repo'], x)) for x in sorted(paths)}


def item_object(record, item):
    protocol = next(p for p in record['protocols'] if p['id'] == item['requirement_ref'])
    e = next(e for e in record['extraction']['items'] if e['id'] == protocol['extraction_ref'])
    return digest({'protocol': protocol, 'extraction': e, 'verifier': item['verifier'], 'files': watched(record, item),
                   'risk': item['risk'], 'review_scope': item['review_scope']})


def anchors(record, item):
    p = next(p for p in record['protocols'] if p['id'] == item['requirement_ref'])
    b = p['binding']
    if b:
        for key in ('definition', 'consumer'):
            anchor = b[key]
            lines = within(record['repo'], anchor['path']).read_text().splitlines()
            require(anchor['line'] <= len(lines) and anchor['symbol'] in lines[anchor['line'] - 1],
                    f'{item["id"]}: stale {key} anchor {anchor}')
        for anchor in b['overrides']:
            lines = within(record['repo'], anchor['path']).read_text().splitlines()
            require(anchor['line'] <= len(lines) and anchor['symbol'] in lines[anchor['line'] - 1],
                    f'{item["id"]}: stale override anchor {anchor}')
        definition = b['definition']
        require(b['config_key'] in within(record['repo'], definition['path']).read_text().splitlines()[definition['line'] - 1], 'config_key not present at definition')
        require(b['consumer_symbol'] == b['consumer']['symbol'], f'{item["id"]}: consumer symbol mismatch')


def current_target(record):
    f = record['formal_run']
    if record['agreement']['formal_run_policy'] == 'sandbox_allowed':
        require(f['class'] in {'exploratory', 'short_smoke'}, 'sandbox policy cannot authorize a protected production/experiment action')
    require(f['command'] and isinstance(f['command'], list) and all(isinstance(x, str) for x in f['command']), 'missing formal command')
    require(f['config_paths'], 'missing config scope')
    configs = {x: file_digest(within(record['repo'], x)) for x in f['config_paths']}
    paths = command_paths(record['repo'], f['command'], f.get('command_paths', []))
    require(paths, 'declare command_paths for the actual protected entrypoint')
    command_files = {x: file_digest(within(record['repo'], x)) for x in sorted(paths)}
    return {'command_files': command_files, 'candidate_sha': git(record['repo'], 'rev-parse', 'HEAD'), 'command_digest': digest(f['command']),
            'config_digest': digest(configs),
            'items': {c['id']: item_object(record, c) for c in record['checklist'] if c['id'] in f['required_checklist_items']},
            'policy': record['agreement']['formal_run_policy'], 'class': f['class'], 'mode': record['mode']}


def append_event(root, command, status, detail):
    write(root / 'evidence' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + command + '.json'),
          {'at': now(), 'command': command, 'status': status, 'detail': detail})


def check(root, selected=None):
    record = read_record(root)
    selected = set(selected or [c['id'] for c in record['checklist']])
    require(selected <= {c['id'] for c in record['checklist']}, 'unknown selected checklist ID')
    errors = []
    for item in record['checklist']:
        if item['id'] not in selected:
            continue
        try:
            require(item['human_status'] != 'confirmed' or item.get('human_receipt'), f'{item["id"]}: confirmed without human receipt')
            if item['agent_status'] == 'checked':
                require(item['evidence']['paths'], f'{item["id"]}: readback evidence missing')
                prior = within(root, item['evidence']['paths'][0])
                require(file_digest(prior) == item['evidence'].get('receipt_sha256'), f'{item["id"]}: prior readback missing or changed')
            protocol = next(p for p in record['protocols'] if p['id'] == item['requirement_ref'])
            extracted = next(e for e in record['extraction']['items'] if e['id'] == protocol['extraction_ref'])
            require(not extracted['blocking_question'] and protocol['expected']['value'] is not None, f'{item["id"]}: unresolved interpretation: {extracted["blocking_question"]}')
            anchors(record, item)
            obj = item_object(record, item)
            old = item['evidence']['object_digest']
            if old != obj and item['human_status'] == 'confirmed':
                item['human_status'] = 'invalidated'
                item.pop('human_receipt', None)
            verifier = item['verifier']
            require(verifier['method'] != 'unconfigured', f'{item["id"]}: configure a project verifier')
            if verifier['method'] == 'static_anchor':
                require(item['risk'] == 'low' and not protocol['binding'], 'static check cannot verify a critical parameter')
                require(verifier.get('anchors'), 'static_anchor requires concrete inspected anchors')
                observation = True
                for anchor in verifier['anchors']:
                    fields(anchor, 'path line symbol', 'static anchor')
                    lines = within(record['repo'], anchor['path']).read_text().splitlines()
                    observation = observation and 0 < anchor['line'] <= len(lines) and anchor['symbol'] in lines[anchor['line'] - 1]
                require(type(protocol['expected']['value']) is bool and observation == protocol['expected']['value'], 'static anchor observation differs from expectation')
                result = {'argv': [], 'returncode': 0, 'stdout': '', 'stderr': '', 'observation': observation}
                level = 'static'
            else:
                fields(verifier, 'argv observation_key', 'command verifier')
                argv = verifier['argv']
                require(argv and isinstance(argv, list) and all(isinstance(x, str) for x in argv), 'argv must be a nonempty string list')
                require(1 <= verifier.get('timeout_seconds', 30) <= 300, 'verifier timeout must be 1..300 seconds')
                # Verifiers are explicitly selected project commands, not a sandbox.
                # Skills must inspect them before check and keep them inside authorization.
                proc = subprocess.run(argv, cwd=record['repo'], capture_output=True, text=True,
                                      timeout=verifier.get('timeout_seconds', 30))
                result = {'argv': argv, 'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr}
                result_path = root / 'evidence' / (uuid.uuid4().hex + '-readback.json')
                write(result_path, dict(result, at=now(), object_digest=obj))
                require(proc.returncode == 0, f'{item["id"]}: verifier exit {proc.returncode}; {result_path}')
                output = json.loads(proc.stdout)
                observed = output
                for part in verifier['observation_key'].split('.'):
                    observed = observed[part]
                if protocol['binding']:
                    b = protocol['binding']
                    readback = output
                    for part in b['readback_key'].split('.'):
                        readback = readback[part]
                    require(readback['config_key'] == b['config_key'] and readback['consumer_symbol'] == b['consumer_symbol'],
                            f'{item["id"]}: readback binding identity mismatch')
                    require(readback['value'] == observed, f'{item["id"]}: consumer and binding readback disagree')
                require(observed == protocol['expected']['value'], f'{item["id"]}: expected {protocol["expected"]}, observed {observed!r}; {result_path}')
                require(obj == item_object(record, item), f'{item["id"]}: relevant inputs changed during verifier')
                result['observation'] = observed
                level = 'simulated' if record['mode'] == 'simulation' else 'real'
            receipt = dict(result, at=now(), item_id=item['id'], object_digest=obj, level=level,
                           candidate_sha=git(record['repo'], 'rev-parse', 'HEAD'))
            path = root / 'evidence' / (uuid.uuid4().hex + '-checked.json')
            write(path, receipt)
            relative = str(path.relative_to(root))
            item['evidence'] = {'level': level, 'paths': [relative], 'anchors': item['review_scope']['must_review'],
                                'object_digest': obj, 'receipt_sha256': file_digest(path)}
            item['agent_status'] = 'checked'
            item['invalidated_by'] = []
        except (ContractError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            item['agent_status'] = 'failed'
            if item['human_status'] == 'confirmed':
                item['human_status'] = 'invalidated'
            item['invalidated_by'].append(str(exc))
            errors.append(str(exc))
    f = record['formal_run']
    f['agent_review'] = {'status': 'pass' if all(c['agent_status'] == 'checked' for c in record['checklist']) else 'fail',
                         'evidence': [p for c in record['checklist'] for p in c['evidence']['paths']]}
    if f['command'] and f['config_paths']:
        target = current_target(record)
        f['agent_target_digest'] = digest(target) if f['agent_review']['status'] == 'pass' else None
        for key in ('candidate_sha', 'command_digest', 'config_digest'):
            if f[key] and f[key] != target[key]:
                invalidate_humans(record, 'formal target changed')
            f[key] = target[key]
    record['code_state'] = git_state(record['repo'])
    write(root / 'checklist.yaml', record)
    refresh_views(root, record)
    review_brief(root, record)
    append_event(root, 'check', 'fail' if errors else 'pass', {'selected': sorted(selected), 'errors': errors})
    return errors


def invalidate_humans(record, reason):
    f = record['formal_run']
    if f['status'] != 'prohibited':
        f['status'] = 'awaiting_human'


def verify_item(root, record, c, human=False):
    require(c['agent_status'] == 'checked', f'{c["id"]}: Agent check missing')
    obj = item_object(record, c)
    require(c['evidence']['object_digest'] == obj, f'{c["id"]}: relevant objects changed; needs_recheck')
    require(c['evidence']['paths'], f'{c["id"]}: no evidence')
    receipt_path = within(root, c['evidence']['paths'][0])
    require(file_digest(receipt_path) == c['evidence'].get('receipt_sha256'), f'{c["id"]}: evidence changed')
    receipt = load(receipt_path)
    checked_at = datetime.fromisoformat(receipt['at'])
    require(checked_at.tzinfo is not None and checked_at <= datetime.now(timezone.utc), 'invalid evidence timestamp')
    require(receipt['object_digest'] == obj and receipt['returncode'] == 0 and receipt['item_id'] == c['id'], 'invalid check receipt')
    require(receipt['level'] == c['evidence']['level'], 'evidence level mismatch')
    if record['mode'] == 'simulation':
        require(receipt['level'] in {'simulated', 'static'}, 'simulation cannot claim real evidence')
    if c['risk'] == 'high_risk':
        require(receipt['level'] in {'real', 'simulated'}, 'high-risk check needs execution evidence')
    if c['human_status'] == 'confirmed' or human:
        require(c['human_status'] == 'confirmed' and c.get('human_receipt'), f'{c["id"]}: human confirmation missing')
        h = load(within(root, c['human_receipt']))
        require(h['item_digests'].get(c['id']) == obj and h['choices'].get(c['id']) == 'confirmed', f'{c["id"]}: stale human confirmation')
        feedback = within(root, h['feedback_path'])
        require(file_digest(feedback) == h['feedback_sha256'], 'human feedback changed')
        return h
    return None


def review_brief(root, record=None):
    record = record or read_record(root)
    selected = [c for c in record['checklist'] if c['review_scope']['must_review']]
    if not selected:
        return None
    path = root / 'reviews/human-review.md'
    path.parent.mkdir(exist_ok=True)
    rows = ['# Focused human review', '', 'This navigation is not approval. Report Judge PASS is not code acceptance.', '',
            f'Candidate SHA: `{git(record["repo"], "rev-parse", "HEAD")}`; working tree: `{git_state(record["repo"])["working_tree"]}`.', '',
            'Requirements and statuses: [checklist](../checklist.yaml).', '']
    for c in selected:
        p = next(p for p in record['protocols'] if p['id'] == c['requirement_ref'])
        rows += [f'## {c["id"]} — {c["requirement"]}', '', f'Protocol: `{p["id"]}`. Meaning: {p["meaning"]}. Expected: `{p["expected"]}`.',
                 f'Observation: `{c["agent_status"]}`; evidence level: `{c["evidence"]["level"]}`. Human: `{c["human_status"]}`.', '']
        for ref in c['review_scope']['must_review']:
            base, sep, line = ref.rpartition(':')
            local = within(root if base == 'request.txt' else record['repo'], base if sep and line.isdigit() else ref)
            require(local.exists(), f'review anchor missing: {ref}')
            target = str(local) + (':' + line if sep and line.isdigit() else '')
            rows.append(f'- must_review: [{ref}]({target})')
        rows += [f'- evidence: [{ref}](../{ref})' for ref in c['evidence']['paths']]
        recommendation = ('Confirm this item only after inspecting the linked semantics; confirmation applies to this object.'
                          if c['agent_status'] == 'checked' else 'Request correction; this item has no passing current check.')
        rows += ['', f'Recommended: {recommendation}',
                 'Alternative: reject with the specific semantic disagreement; the protected action stays blocked.', '']
    path.write_text('\n'.join(rows))
    return path


def approve(root, sha, feedback_path, simulation=False):
    record = read_record(root)
    require((record['mode'] == 'simulation') == simulation, 'simulation approval must be explicitly isolated')
    require(record['agreement']['formal_run_policy'] != 'prohibited', 'formal action is prohibited by agreement')
    target = current_target(record)
    require(sha == target['candidate_sha'], 'wrong candidate SHA')
    for c in record['checklist']:
        verify_item(root, record, c)
    feedback = load(feedback_path)
    fields(feedback, 'actor confirmed_at source_quote source_path source_sha256 candidate_sha target_digest choices', 'human feedback')
    require(feedback['actor'] and feedback['source_quote'], 'missing actual human feedback')
    dt = datetime.fromisoformat(feedback['confirmed_at'])
    require(dt.tzinfo is not None and dt <= datetime.now(timezone.utc), 'invalid confirmation timestamp')
    source_path = Path(feedback['source_path'])
    require(file_digest(source_path) == feedback['source_sha256'] and feedback['source_quote'] in source_path.read_text(), 'feedback source mismatch')
    require(feedback['candidate_sha'] == sha and feedback['target_digest'] == digest(target), 'human reviewed a different target')
    needed = {c['id'] for c in record['checklist'] if c['risk'] == 'high_risk'}
    require(set(feedback['choices']) <= needed and all(x in {'confirmed', 'rejected'} for x in feedback['choices'].values()), 'invalid per-item choices')
    for c in record['checklist']:
        if c['id'] in needed and c['id'] not in feedback['choices']:
            verify_item(root, record, c, human=True)
    saved = root / 'evidence' / (uuid.uuid4().hex + '-human-feedback.json')
    write(saved, feedback)
    receipt = dict(feedback, item_digests=target['items'], feedback_path=str(saved.relative_to(root)),
                   feedback_sha256=file_digest(saved), simulation=simulation)
    path = root / 'evidence' / (uuid.uuid4().hex + '-human-receipt.json')
    write(path, receipt)
    for c in record['checklist']:
        if c['id'] in feedback['choices']:
            c['human_status'] = feedback['choices'][c['id']]
            c['human_receipt'] = str(path.relative_to(root))
    f = record['formal_run']
    for key in ('candidate_sha', 'command_digest', 'config_digest'):
        require(f[key] == target[key], 'Agent check is not bound to current formal target')
    f['human_confirmation'] = {'required': bool(needed), 'actor': feedback['actor'], 'confirmed_at': feedback['confirmed_at'], 'target_digest': digest(target)}
    f['status'] = 'authorized' if all(c['human_status'] == 'confirmed' for c in record['checklist'] if c['id'] in needed) else 'awaiting_human'
    write(root / 'checklist.yaml', record)
    refresh_views(root, record)
    review_brief(root, record)
    append_event(root, 'approve', f['status'], {'simulation': simulation, 'receipt': str(path.relative_to(root))})


def gate(root, simulation=False):
    record = read_record(root)
    f = record['formal_run']
    errors = []
    try:
        require(record['route']['primary'] not in {'learning', 'office'}, 'this route does not use the formal-run gate')
        require(record['agreement']['formal_run_policy'] != 'prohibited', 'formal-run prohibited')
        require((record['mode'] == 'simulation') == simulation, 'simulation record cannot authorize real execution')
        if simulation:
            require(f['class'] in {'exploratory', 'short_smoke'}, 'simulation approval is restricted to sandbox checks')
        target = current_target(record)
        if f['agent_review']['status'] != 'pass':
            errors.append('Agent review missing')
        if f.get('agent_target_digest') != digest(target):
            errors.append('Agent target changed; rerun affected checks')
        for key in ('candidate_sha', 'command_digest', 'config_digest'):
            if not f[key] or f[key] != target[key]:
                errors.append(f'stale or missing {key}')
        for c in record['checklist']:
            try:
                h = verify_item(root, record, c)
            except (ContractError, OSError, ValueError, KeyError) as exc:
                c['agent_status'] = 'needs_recheck'
                c['human_status'] = 'invalidated' if c['human_status'] == 'confirmed' else c['human_status']
                c['invalidated_by'].append(str(exc))
                errors.append(str(exc))
                continue
            if c['risk'] == 'high_risk':
                try:
                    h = verify_item(root, record, c, human=True)
                    require(h['simulation'] == simulation, 'human receipt mode mismatch')
                except (ContractError, OSError, ValueError, KeyError) as exc:
                    if c['human_status'] == 'confirmed':
                        c['human_status'] = 'invalidated'
                    errors.append(str(exc))
        require(not errors, '; '.join(errors))
        if any(c['risk'] == 'high_risk' for c in record['checklist']):
            require(f['status'] == 'authorized' and f['human_confirmation']['target_digest'] == digest(target), 'human authorization missing')
    except (ContractError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        errors.append(str(exc))
        invalidate_humans(record, str(exc))
    write(root / 'checklist.yaml', record)
    refresh_views(root, record)
    append_event(root, 'gate', 'fail' if errors else 'pass', {'errors': errors, 'simulation': simulation, 'executes_command': False})
    return errors


def refresh_views(root, record):
    """Render requirements from the canonical protocol; preserve the work record."""
    rows = ['| Item | Protocol / field | Expected | Agent | Human |', '|---|---|---|---|---|']
    for c in record['checklist']:
        p = next(p for p in record['protocols'] if p['id'] == c['requirement_ref'])
        field = p['binding']['config_key'] if p['binding'] else 'material/outcome'
        cells = [c['id'], p['id'] + ' / ' + field, json.dumps(p['expected'], ensure_ascii=False), c['agent_status'], c['human_status']]
        rows.append('| ' + ' | '.join(str(x).replace('|', r'\|').replace('\n', ' ') for x in cells) + ' |')
    state = git_state(record['repo'])
    text = ('<!-- workflow-state:start -->\n' + '\n'.join(rows) +
            f'\n\nCurrent Git: `{state["branch"]}` / `{state["base_sha"]}` / `{state["working_tree"]}`.\n'
            f'Formal action: `{record["formal_run"]["status"]}`. Review: [checklist.yaml](checklist.yaml).\n'
            'Runtime launches no jobs. Re-read external running jobs before resuming.\n'
            'Next action: repair failed/unverified items; review focused high-risk items before any protected action.\n'
            '<!-- workflow-state:end -->')
    task = root / 'task.md'
    task.write_text(re.sub(r'<!-- workflow-state:start -->.*?<!-- workflow-state:end -->', lambda _: text, task.read_text(), flags=re.S))
    if record.get('protocol_view'):
        (root / 'protocol.md').write_text('# Protocol view\n\nDerived from [checklist.yaml](checklist.yaml); edit the canonical record, not this view.\n\n' + '\n'.join(rows) + '\n')


def revise(root, revision_path):
    """Record actual user amendments without rewriting the original request."""
    record = read_record(root)
    revision = load(revision_path)
    fields(revision, 'source_path source_quote updates', 'revision')
    source = Path(revision['source_path'])
    require(revision['source_quote'] and revision['source_quote'] in source.read_text(), 'revision needs a verbatim user source')
    require(revision['updates'], 'empty revision')
    source_target = root / 'evidence' / (uuid.uuid4().hex + '-user-revision.txt')
    source_target.parent.mkdir(exist_ok=True)
    source_target.write_bytes(source.read_bytes())
    affected = []
    before = []
    for update in revision['updates']:
        fields(update, 'protocol_id expected meaning', 'revision update')
        p = next((p for p in record['protocols'] if p['id'] == update['protocol_id']), None)
        require(p is not None, 'unknown revision protocol')
        before.append(json.loads(json.dumps(p)))
        p['expected'] = update['expected']
        p['meaning'] = update['meaning']
        p['source'] = {'path': str(source_target.relative_to(root)), 'quote': revision['source_quote'],
                       'authority': 'user', 'sha256': file_digest(source_target)}
        e = next(e for e in record['extraction']['items'] if e['id'] == p['extraction_ref'])
        e.update(source_quote=revision['source_quote'], normalized_value=p['expected']['value'],
                 meaning=p['meaning'], blocking_question=None, semantic_candidates=[], authority='user')
        for c in record['checklist']:
            if c['requirement_ref'] == p['id']:
                c['source'] = p['source']
                c['agent_status'] = 'needs_recheck'
                c['human_status'] = 'invalidated' if c['human_status'] == 'confirmed' else c['human_status']
                c['invalidated_by'].append('user amendment; previous expectations preserved in revision event')
                affected.append(c['id'])
    validate(record)
    invalidate_humans(record, 'user amendment')
    record['formal_run']['agent_review']['status'] = 'unverified'
    append_event(root, 'revise', 'recorded', {'before': before, 'updates': revision, 'affected': affected})
    write(root / 'checklist.yaml', record)
    refresh_views(root, record)
    return affected
