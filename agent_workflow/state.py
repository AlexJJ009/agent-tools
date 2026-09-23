"""Typed, source-backed changes to the canonical workflow record.

These functions validate declared scope and provenance. Agents, not string
classifiers, decide what a request means and whether an explanation is useful.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

from .contracts import digest, fields, file_digest, require, within

EVENT_TYPES = {
    'choice.propose', 'choice.resolve', 'understanding.explain', 'understanding.feedback',
    'delegation.grant', 'delegation.revoke', 'requirements.revise', 'requirement.add',
    'result.feedback', 'phase.define', 'phase.set', 'input.record', 'input.resolve',
    'job.update', 'verifier.configure', 'phase.review', 'action.register', 'authorization.grant', 'authorization.revoke',
}
SOURCE_KINDS = {'user', 'code', 'proposal', 'tool'}


def initialize(record, context=None):
    context = context or {}
    record['schema_version'] = 2
    record.setdefault('revision', 0)
    record.setdefault('events', [])
    record.setdefault('choices', [])
    record.setdefault('delegations', [])
    record.setdefault('execution_authority', [])
    record.setdefault('phase', context.get('phase', 'baseline'))
    record.setdefault('phases', {record['phase']: {
        'required_checklist_items': [c['id'] for c in record['checklist']],
        'independent_review': {'status': 'pending', 'evidence': []},
    }})
    for key in ('actions', 'pending_inputs', 'jobs'):
        record.setdefault(key, {})
    for item in record['checklist']:
        settings = context.get('checks', {}).get(item['id'], {})
        item.setdefault('phase', settings.get('phase', record['phase']))
        item.setdefault('participation', settings.get('participation', 'unspecified'))
        item.setdefault('result_acceptance', {'status': 'pending', 'feedback_refs': []})
    return record


def validate_state(record):
    fields(record, 'revision events phase phases choices delegations execution_authority actions pending_inputs jobs', 'state')
    require(type(record['revision']) is int and record['revision'] >= 0, 'invalid revision')
    require(isinstance(record['events'], list), 'events must be a list')
    event_ids = set()
    revisions = []
    for event in record['events']:
        fields(event, 'id revision input_digest type source affects payload at', 'committed event')
        require(event['id'] not in event_ids, 'duplicate committed event')
        event_ids.add(event['id'])
        revisions.append(event['revision'])
    require(revisions == sorted(set(revisions)) and all(0 < r <= record['revision'] for r in revisions), 'invalid event revisions')
    ids = {c['id'] for c in record['checklist']}
    require(record['phase'] in record['phases'], 'unknown current phase')
    for phase in record['phases'].values():
        fields(phase, 'required_checklist_items', 'phase')
        require(set(phase['required_checklist_items']) <= ids, 'phase references unknown checklist item')
    choices = set()
    for choice in record['choices']:
        fields(choice, 'id discovered_by source_ref question affects resolution understanding', 'choice')
        require(choice['id'] not in choices, 'duplicate choice')
        choices.add(choice['id'])
        require(bool(choice['affects']) and set(choice['affects']) <= ids, 'choice scope is unknown or empty')
        fields(choice['understanding'], 'required_scope explanation_ref feedback_refs open_questions', 'understanding')
        if choice['resolution'] is not None:
            fields(choice['resolution'], 'value rationale source_ref', 'resolution')
    for item in record['checklist']:
        fields(item, 'phase participation result_acceptance', 'state checklist')
        require(item['phase'] in record['phases'], 'unknown item phase')
        require(item['participation'] in {'unspecified', 'explain', 'understanding', 'delegated'}, 'invalid participation')
        fields(item['result_acceptance'], 'status feedback_refs', 'result acceptance')
        require(item['result_acceptance']['status'] in {'pending', 'accepted', 'rejected', 'invalidated'}, 'invalid acceptance status')
    for action in record['actions'].values():
        fields(action, 'id required_checklist_items choice_ids phase argv config_paths command_paths', 'action')
        require(set(action['required_checklist_items']) <= ids, 'action references unknown checklist item')
        require(set(action['choice_ids']) <= choices, 'action references unknown choice')
        require(action['phase'] in record['phases'], 'unknown action phase')
    for pending in record['pending_inputs'].values():
        require(set(pending['affects']) <= ids, 'pending input references unknown item')


def snapshot_source(root, source):
    """Copy source bytes before committing; orphan copies are harmless on failure."""
    from . import runtime
    fields(source, 'kind actor path quote sha256', 'event source')
    require(source['kind'] in SOURCE_KINDS, 'unknown source kind')
    require(isinstance(source['actor'], str) and source['actor'].strip(), 'source needs actor')
    require(isinstance(source['quote'], str) and source['quote'].strip(), 'source needs exact quote')
    path = Path(source['path'])
    if not path.is_absolute():
        path = within(root, source['path'])
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == source['sha256'], 'source hash mismatch')
    require(source['quote'] in data.decode('utf-8'), 'source quote is not verbatim')
    target = root / 'evidence' / 'sources' / (source['sha256'] + '.txt')
    runtime.write_bytes(target, data)
    return dict(source, path=str(target.relative_to(root)))


def validate_source(root, source):
    if source.get('kind') == 'runtime':
        return
    path = within(root, source['path'])
    require(file_digest(path) == source['sha256'], 'committed source changed')
    require(source['quote'] and source['quote'] in path.read_bytes().decode('utf-8'), 'committed source quote changed')


def _choice(record, id):
    choice = next((c for c in record['choices'] if c['id'] == id), None)
    require(choice is not None, f'unknown choice: {id}')
    return choice


def _scope(event, required):
    require(set(required) <= set(event['affects']), 'event affects omits changed items')


def _user(event):
    require(event['source']['kind'] == 'user', 'this feedback requires an actual user source')


def invalidate(record, affected, reason, semantic=False):
    for item in record['checklist']:
        if item['id'] not in affected:
            continue
        item['agent_status'] = 'needs_recheck'
        item['invalidated_by'].append(reason)
        if semantic:
            if item['human_status'] == 'confirmed':
                item['human_status'] = 'invalidated'
            if item['result_acceptance']['status'] == 'accepted':
                item['result_acceptance']['status'] = 'invalidated'
    record['formal_run']['agent_review']['status'] = 'unverified'
    if semantic:
        for grant in record['delegations']:
            if set(grant.get('affects', [])) & set(affected):
                grant.update(revoked=True, invalidated_reason=reason)
        for grant in record['execution_authority']:
            if any(set(record['actions'][a]['required_checklist_items']) & set(affected) for a in grant['action_ids']):
                grant.update(revoked=True, invalidated_reason=reason)
        for choice in record['choices']:
            if set(choice['affects']) & set(affected):
                choice['resolution'] = None
                choice['understanding']['feedback_refs'] = []
                choice['understanding']['explanation_ref'] = None


def revise_requirements(record, updates, source, source_ref, reason, affects):
    require(reason and updates, 'requirement revision needs updates and reason')
    before = []
    for update in updates:
        fields(update, 'protocol_id expected meaning', 'revision update')
        protocol = next((p for p in record['protocols'] if p['id'] == update['protocol_id']), None)
        require(protocol is not None, 'unknown revision protocol')
        require(source['kind'] == 'user' or protocol['source']['authority'] != 'user',
                'code observations cannot replace a user acceptance requirement')
        fields(update['expected'], 'value unit', 'revision expected')
        affected = [c['id'] for c in record['checklist'] if c['requirement_ref'] == protocol['id']]
        require(set(affected) <= set(affects), 'revision affects omits changed items')
        before.append(deepcopy(protocol))
        authority = {'user': 'user', 'code': 'project_fact', 'proposal': 'agent_proposal'}[source['kind']]
        require(authority != 'agent_proposal', 'a proposal cannot revise agreed requirements')
        protocol.update(expected=update['expected'], meaning=update['meaning'],
                        source=dict(source, authority=authority, source_ref=source_ref))
        extraction = next(e for e in record['extraction']['items'] if e['id'] == protocol['extraction_ref'])
        extraction.update(source_quote=source['quote'], source=protocol['source'], normalized_value=update['expected']['value'],
                          meaning=update['meaning'], blocking_question=None, semantic_candidates=[], authority=authority)
        for item in record['checklist']:
            if item['id'] in affected:
                item['source'] = protocol['source']
        invalidate(record, affected, reason, semantic=True)
    return before


def apply(record, event):
    """Apply one declared semantic event. This cannot write verifier success."""
    kind, payload, ref = event['type'], event['payload'], event['id']
    require(kind in EVENT_TYPES, f'unknown event type: {kind}')
    require(isinstance(payload, dict), 'event payload must be an object')
    ids = {c['id'] for c in record['checklist']}
    require(isinstance(event['affects'], list) and set(event['affects']) <= ids, 'event affects has unknown checklist item')
    if kind == 'choice.propose':
        fields(payload, 'id question affects', 'choice proposal')
        require(not any(c['id'] == payload['id'] for c in record['choices']), 'choice already exists')
        _scope(event, payload['affects'])
        require(payload['question'] and payload['affects'], 'choice needs question and scope')
        require(event['source']['kind'] in {'user', 'code', 'proposal'}, 'invalid choice source')
        record['choices'].append({
            'id': payload['id'], 'question': payload['question'], 'affects': payload['affects'],
            'discovered_by': 'user' if event['source']['kind'] == 'user' else 'agent', 'source_ref': ref,
            'options': payload.get('options', []), 'resolution': None,
            'understanding': {'required_scope': payload.get('required_scope'), 'explanation_ref': None,
                              'feedback_refs': [], 'open_questions': []}})
    elif kind == 'choice.resolve':
        fields(payload, 'choice_id value rationale', 'choice resolution')
        choice = _choice(record, payload['choice_id'])
        _scope(event, choice['affects'])
        require(payload['rationale'], 'resolution needs rationale')
        if event['source']['kind'] != 'user':
            grant = next((d for d in record['delegations'] if d['id'] == payload.get('delegation_id') and not d.get('revoked')), None)
            require(grant and choice['id'] in grant['choice_ids'], 'Agent resolution needs an explicit scoped delegation')
        choice['resolution'] = {'value': payload['value'], 'rationale': payload['rationale'], 'source_ref': ref}
    elif kind in {'understanding.explain', 'understanding.feedback'}:
        fields(payload, 'choice_id scope', 'understanding event')
        choice = _choice(record, payload['choice_id'])
        _scope(event, choice['affects'])
        understanding = choice['understanding']
        require(payload['scope'] == understanding['required_scope'] and payload['scope'], 'understanding scope mismatch')
        if kind == 'understanding.explain':
            fields(payload, 'explanation', 'explanation')
            require(payload['explanation'], 'empty explanation')
            understanding['explanation_ref'] = ref
        else:
            _user(event)
            require(payload.get('kind') in {'self_report', 'reconstruction', 'question', 'decision'}, 'invalid understanding feedback kind')
            understanding['feedback_refs'].append(ref)
            if payload['kind'] == 'question':
                understanding['open_questions'].append({'id': ref, 'question': event['source']['quote']})
            for question_id in payload.get('resolves', []):
                require(any(q['id'] == question_id for q in understanding['open_questions']), 'unknown open question')
                understanding['open_questions'] = [q for q in understanding['open_questions'] if q['id'] != question_id]
    elif kind == 'delegation.grant':
        _user(event)
        fields(payload, 'id choice_ids scope', 'delegation')
        require(payload['scope'] and (payload['choice_ids'] or event['affects']), 'delegation needs an explicit scope')
        require(not any(d['id'] == payload['id'] for d in record['delegations']), 'delegation already exists')
        for choice_id in payload['choice_ids']:
            _scope(event, _choice(record, choice_id)['affects'])
        record['delegations'].append(dict(payload, affects=event['affects'], source_ref=ref, revoked=False))
    elif kind in {'delegation.revoke', 'authorization.revoke'}:
        _user(event)
        collection = record['delegations' if kind == 'delegation.revoke' else 'execution_authority']
        found = next((x for x in collection if x['id'] == payload.get('id')), None)
        require(found is not None, 'unknown grant')
        found.update(revoked=True, revoked_by=ref)
    elif kind == 'authorization.grant':
        _user(event)
        fields(payload, 'id action_ids scope', 'authorization')
        require(payload['action_ids'] and set(payload['action_ids']) <= set(record['actions']), 'unknown or empty authorized actions')
        require(not any(a['id'] == payload['id'] for a in record['execution_authority']), 'authorization already exists')
        for action_id in payload['action_ids']:
            _scope(event, record['actions'][action_id]['required_checklist_items'])
        record['execution_authority'].append(dict(payload, source_ref=ref, revoked=False))
    elif kind == 'requirements.revise':
        fields(payload, 'updates reason', 'requirement revision')
        return {'before': revise_requirements(record, payload['updates'], event['source'], ref, payload['reason'], event['affects'])}
    elif kind == 'requirement.add':
        fields(payload, 'item check phase reason', 'requirement addition')
        require(event['source']['kind'] in {'user', 'code'}, 'proposals must first be resolved')
        require(payload['phase'] in record['phases'], 'unknown requirement phase')
        item = deepcopy(payload['item'])
        require(not any(p['id'] == item.get('id') for p in record['protocols']), 'requirement already exists')
        authority = 'user' if event['source']['kind'] == 'user' else 'project_fact'
        source = dict(event['source'], authority=authority, source_ref=ref)
        item.update(source_quote=source['quote'], source=source, authority=authority)
        require(len(item['checklist_ids']) == 1, 'add one checklist item per requirement event')
        cid = item['checklist_ids'][0]
        require(cid not in ids, 'checklist item already exists')
        record['extraction']['items'].append(item)
        record['protocols'].append({'id': item['id'], 'source': source, 'meaning': item['meaning'],
            'expected': {'value': item['normalized_value'], 'unit': item.get('unit', 'outcome')},
            'extraction_ref': item['id'], 'binding': payload.get('binding')})
        check = deepcopy(payload['check'])
        check.update(id=cid, requirement=item.get('label', item['id']), requirement_ref=item['id'], source=source,
            phase=payload['phase'], participation=check.get('participation', 'unspecified'),
            evidence={'level': 'none', 'paths': [], 'anchors': [], 'object_digest': None},
            agent_status='unverified', human_status='not_requested', invalidated_by=[],
            result_acceptance={'status': 'pending', 'feedback_refs': []})
        check.setdefault('risk', 'low')
        check.setdefault('review_scope', {'must_review': [], 'context_only': []})
        check.setdefault('verifier', {'method': 'unconfigured', 'watched_paths': []})
        check['verifier']['expected_ref'] = item['id'] + '.expected'
        if payload.get('binding'):
            check['binding_ref'] = payload['binding']['id']
        record['checklist'].append(check)
        record['phases'][payload['phase']]['required_checklist_items'].append(cid)
    elif kind == 'result.feedback':
        _user(event)
        fields(payload, 'items kind', 'result feedback')
        require(payload['kind'] in {'acceptance', 'defect', 'clarification', 'next_version'}, 'invalid result feedback kind')
        require(payload['items'], 'feedback needs exact item scope')
        _scope(event, payload['items'])
        for cid, outcome in payload['items'].items():
            require(cid in ids, 'unknown feedback item')
            require(outcome in {'accepted', 'rejected', 'pending'}, 'invalid per-item result')
            require(payload['kind'] == 'acceptance' or outcome != 'accepted', 'only result acceptance can accept items')
            item = next(c for c in record['checklist'] if c['id'] == cid)
            item['result_acceptance']['feedback_refs'].append(ref)
            if payload['kind'] in {'acceptance', 'defect'}:
                item['result_acceptance']['status'] = outcome
            if payload['kind'] == 'defect':
                invalidate(record, [cid], 'User-reported defect: ' + ref)
    elif kind == 'phase.define':
        fields(payload, 'id required_checklist_items', 'phase')
        require(payload['id'] not in record['phases'], 'phase already defined; requirements cannot be silently removed')
        require(set(payload['required_checklist_items']) <= ids, 'unknown phase requirement')
        record['phases'][payload['id']] = dict(payload, source_ref=ref)
    elif kind == 'phase.set':
        require(payload.get('id') in record['phases'], 'unknown phase')
        record['phase'] = payload['id']
    elif kind == 'input.record':
        fields(payload, 'id', 'pending input')
        require(payload['id'] not in record['pending_inputs'], 'input already recorded')
        record['pending_inputs'][payload['id']] = dict(payload, affects=event['affects'], resolved=False, source_ref=ref)
    elif kind == 'input.resolve':
        fields(payload, 'id disposition reason', 'input resolution')
        require(payload['id'] in record['pending_inputs'], 'unknown input')
        require(payload['disposition'] in {'applied', 'no_contract_change'} and payload['reason'], 'input needs explicit disposition and reason')
        record['pending_inputs'][payload['id']].update(resolved=True, resolution_ref=ref,
            disposition=payload['disposition'], reason=payload['reason'])
    elif kind == 'verifier.configure':
        fields(payload, 'item_id verifier reason', 'verifier configuration')
        require(payload['item_id'] in ids and payload['reason'], 'invalid verifier item or reason')
        _scope(event, [payload['item_id']])
        item = next(c for c in record['checklist'] if c['id'] == payload['item_id'])
        item['verifier'] = dict(payload['verifier'], expected_ref=item['requirement_ref'] + '.expected')
        invalidate(record, [item['id']], payload['reason'])
    elif kind == 'phase.review':
        fields(payload, 'id status evidence', 'phase review')
        require(payload['id'] in record['phases'], 'unknown review phase')
        require(payload['status'] in {'pass', 'fail', 'pending'}, 'invalid independent review status')
        require(payload['status'] != 'pass' or payload['evidence'], 'review pass requires actual evidence')
        record['phases'][payload['id']]['independent_review'] = dict(payload, source_ref=ref)
    elif kind == 'job.update':
        fields(payload, 'id status', 'job')
        require(payload['status'] in {'queued', 'running', 'completed', 'failed', 'cancelled', 'unknown'}, 'invalid job status')
        record['jobs'][payload['id']] = dict(payload, affects=event['affects'], source_ref=ref)
    elif kind == 'action.register':
        action = deepcopy(payload.get('action', payload))
        fields(action, 'id required_checklist_items choice_ids phase argv config_paths command_paths', 'action')
        _scope(event, action['required_checklist_items'])
        require(action['id'] not in record['actions'], 'action already registered')
        record['actions'][action['id']] = dict(action, source_ref=ref)
    return {}
