"""Checks at the execution boundary for explicitly registered local actions.

Inputs are copied to a private snapshot before launch. This protects declared
files from check/use races; it is not an OS sandbox for arbitrary programs.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from . import runtime
from .contracts import ContractError, digest, file_digest, require, within


def source_event(root, record, ref, *, human=False):
    """Read stored provenance instead of trusting a populated reference field."""
    event = next((e for e in record.get('events', []) if e['id'] == ref), None)
    require(event is not None, f'missing source event: {ref}')
    source = event['source']
    path = within(root, source['path'])
    require(file_digest(path) == source['sha256'], f'source changed: {ref}')
    require(source['quote'] and source['quote'] in path.read_bytes().decode('utf-8'), f'source quote missing: {ref}')
    if human:
        require(source['kind'] == 'user', f'actual user feedback required: {ref}')
        require(source['actor'] != 'simulated-user' or record['mode'] == 'simulation', 'simulated feedback on a real task')
    return event


def choice_errors(root, record, choice_ids):
    errors = []
    choices = {c['id']: c for c in record.get('choices', [])}
    for cid in choice_ids:
        try:
            require(cid in choices, f'unknown choice: {cid}')
            choice = choices[cid]
            delegated = False
            for delegation in record.get('delegations', []):
                if cid in delegation.get('choice_ids', []) and not delegation.get('revoked'):
                    source_event(root, record, delegation['source_ref'], human=True)
                    # A delegation belongs to the recorded choice scope; changes
                    # of meaning invalidate it through the state update path.
                    if delegation.get('scope') == choice['understanding'].get('required_scope'):
                        delegated = True
            resolution = choice.get('resolution')
            require(resolution is not None or delegated, f'{cid}: choice unresolved')
            if resolution:
                source_event(root, record, resolution['source_ref'], human=bool(choice['understanding'].get('required_scope')) and not delegated)
            if delegated:
                continue
            understanding = choice['understanding']
            scope = understanding.get('required_scope')
            if not scope:
                continue
            require(not understanding.get('open_questions'), f'{cid}: understanding questions remain')
            require(understanding.get('explanation_ref'), f'{cid}: explanation missing')
            source_event(root, record, understanding['explanation_ref'])
            matched = False
            for ref in understanding.get('feedback_refs', []):
                feedback = source_event(root, record, ref, human=True)
                payload = feedback['payload']
                if (payload.get('scope') == scope and payload.get('kind') in
                        {'self_report', 'reconstruction', 'decision'}):
                    matched = True
            require(matched, f'{cid}: scoped feedback missing')
        except (ContractError, OSError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    return errors


def evaluate(root, record, action_id, *, phase=None, simulation=False):
    """Pure condition evaluation; no verifier or protected command is run."""
    errors = []
    require(record['schema_version'] == 2, 'migrate to schema 2 for managed actions')
    completion = action_id == 'completion'
    if completion:
        require(phase in record['phases'], 'unknown completion phase')
        action = record['phases'][phase]
    else:
        require(action_id in record['actions'], f'unregistered action: {action_id}')
        action = record['actions'][action_id]
        phase = action['phase']
        if (record['mode'] == 'simulation') != simulation:
            errors.append('simulation execution must be explicitly isolated')
        if simulation and action.get('run_class', 'short_smoke') not in {'short_smoke', 'exploratory'}:
            errors.append('simulation cannot authorize protected production or formal experiment')
    required = action['required_checklist_items']
    require(required, 'action or phase must name required checklist items')
    by_id = {c['id']: c for c in record['checklist']}
    require(set(required) <= by_id.keys(), 'action references missing checklist item')
    for item_id in required:
        try:
            # Technical evidence is independent of legacy human confirmation.
            item = dict(by_id[item_id], human_status='not_requested')
            runtime.verify_item(root, record, item)
        except (ContractError, OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    choice_ids = sorted(set(action.get('choice_ids', [])) | {c['id'] for c in record['choices'] if set(c['affects']) & set(required)})
    errors.extend(choice_errors(root, record, choice_ids))
    for key, pending in record.get('pending_inputs', {}).items():
        if not pending.get('resolved') and (not pending.get('affects') or set(pending['affects']) & set(required)):
            errors.append(f'input {key} needs classification')
    if completion and action.get('require_independent_review'):
        try:
            review = action.get('independent_review', {})
            require(review.get('status') == 'pass', 'independent phase review is pending or failed')
            source_event(root, record, review['source_ref'])
            current = digest({i: runtime.item_object(record, by_id[i]) for i in required})
            require(review.get('input_digest') == current, 'independent review does not cover current inputs')
        except (ContractError, OSError, KeyError, TypeError) as exc:
            errors.append(str(exc))
    if not completion:
        authority_ok = False
        for authority in record.get('execution_authority', []):
            if authority.get('revoked') or action_id not in authority.get('action_ids', []):
                continue
            try:
                source_event(root, record, authority['source_ref'], human=True)
                if authority['scope'] != action.get('authorization_scope'):
                    continue
                if action.get('require_fresh_authorization') and authority.get('input_digest') != input_identity(record, action):
                    continue
                authority_ok = True
            except (ContractError, OSError, KeyError, TypeError):
                continue
        if not authority_ok:
            errors.append(f'{action_id}: execution scope not covered by current user authority')
    return {'status': 'fail' if errors else 'pass', 'ready': not errors,
            'action': action_id, 'phase': phase, 'revision': record['revision'], 'errors': errors,
            'input_digest': None if completion else input_identity(record, action),
            'user_acceptance': {i: by_id[i].get('result_acceptance', {'status': 'pending'}) for i in required}}


def declared_inputs(record, action):
    repo = Path(record['repo'])
    paths = runtime.command_paths(repo, action['argv'], action.get('command_paths', []))
    paths.update(action.get('config_paths', []))
    for item in record['checklist']:
        if item['id'] in action['required_checklist_items']:
            paths.update(runtime.watched(record, item))
    require(paths, 'managed action needs declared input files')
    return {path: file_digest(within(repo, path)) for path in sorted(paths)}


def input_identity(record, action):
    return digest({'action': action, 'files': declared_inputs(record, action)})


def gate_action(root, action_id, *, phase=None, simulation=False):
    with runtime.locked(root) as root:
        record = runtime.read_record(root)
        result = evaluate(root, record, action_id, phase=phase, simulation=simulation)
        runtime.append_event(root, 'managed-gate', result['status'], result)
        return result


def execute(root, action_id, *, simulation=False, expected_digest=None):
    """Recheck at dequeue/entry, then launch the exact validated input snapshot."""
    snapshot = None
    try:
        with runtime.locked(root) as root:
            record = runtime.read_record(root)
            result = evaluate(root, record, action_id, simulation=simulation)
            if expected_digest is not None and expected_digest != result['input_digest']:
                result['errors'].append('queued inputs changed; create a new request')
                result.update(status='fail', ready=False)
            if not result['ready']:
                runtime.append_event(root, 'managed-execute', 'rejected', result)
                return result
            action = record['actions'][action_id]
            require(action.get('run_class', 'short_smoke') in {'short_smoke', 'exploratory'},
                    'this adapter implements local sandbox actions only')
            argv = action['argv']
            require(isinstance(argv, list) and argv and all(isinstance(v, str) for v in argv), 'invalid argv')
            require(1 <= action.get('timeout_seconds', 30) <= 300, 'managed timeout must be 1..300 seconds')
            manifest = declared_inputs(record, action)
            snapshot = tempfile.TemporaryDirectory(prefix='workflow-inputs-')
            folder = Path(snapshot.name)
            for relative, expected in manifest.items():
                src = within(record['repo'], relative)
                dst = within(folder, relative)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                require(file_digest(dst) == expected, f'input changed during snapshot: {relative}')
            require(input_identity(record, action) == result['input_digest'], 'inputs changed after gate')
            actual_argv = []
            for arg in argv:
                path = Path(arg)
                if path.is_absolute() and path.resolve().is_relative_to(Path(record['repo']).resolve()):
                    relative = str(path.resolve().relative_to(Path(record['repo']).resolve()))
                    require(relative in manifest, f'undeclared command input: {relative}')
                    actual_argv.append(str(folder / relative))
                else:
                    actual_argv.append(arg)
            receipt = dict(result, inputs=manifest, argv=actual_argv, at=runtime.now(), snapshot=True)
            record.setdefault('jobs', {})[action_id] = {'status': 'running', 'started_revision': result['revision'],
                                                       'input_digest': result['input_digest']}
            runtime.commit(root, record, 'execute-start', 'running', {'action': action_id, 'input_digest': result['input_digest']})
        # No state lock while the child runs. Subsequent inputs belong to the
        # next invocation; this invocation uses the fixed snapshot just checked.
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        try:
            proc = subprocess.run(actual_argv, cwd=folder, env=env, capture_output=True,
                                  text=True, timeout=action.get('timeout_seconds', 30))
            receipt.update(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
        except subprocess.TimeoutExpired as exc:
            def as_text(value):
                return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            receipt.update(returncode=124, stdout=as_text(exc.stdout), stderr=as_text(exc.stderr), error='execution timeout')
        except OSError as exc:
            receipt.update(returncode=126, stdout='', stderr=str(exc), error='execution unavailable')
        receipt.update(status='pass' if receipt['returncode'] == 0 else 'fail', finished_at=runtime.now())
        with runtime.locked(root) as root:
            path = root / 'evidence' / (uuid.uuid4().hex + '-execution.json')
            runtime.write(path, receipt)
            current = runtime.read_record(root)
            current.setdefault('jobs', {})[action_id] = {'status': 'completed' if receipt['returncode'] == 0 else 'failed',
                                                       'receipt': str(path.relative_to(root)), 'started_revision': result['revision']}
            runtime.commit(root, current, 'execute', receipt['status'], {'receipt': str(path.relative_to(root))})
        return dict(receipt, receipt=str(path))
    finally:
        if snapshot is not None:
            snapshot.cleanup()
