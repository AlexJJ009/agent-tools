"""Agent-authored extraction and project bindings; not a natural-language classifier."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCENARIOS = {'algorithm', 'infra', 'business', 'bug_fix', 'office', 'learning'}
MODULES = {
    'algorithm': ['intent-to-contract', 'cleaner', 'acceptance-gate'],
    'infra': ['intent-to-contract', 'infra-verification', 'cleaner', 'acceptance-gate'],
    'business': ['intent-to-contract', 'cleaner', 'acceptance-gate'],
    'bug_fix': ['intent-to-contract', 'cleaner', 'acceptance-gate'],
    'office': ['intent-to-contract', 'office-tools'],
    'learning': ['teaching-reconstruction'],
}
AGENT_STATES = {'unverified', 'checked', 'failed', 'needs_recheck', 'not_applicable'}
HUMAN_STATES = {'not_requested', 'requested', 'confirmed', 'rejected', 'invalidated'}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    # JSON is the deliberately dependency-free YAML 1.2 subset used by v1.
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'duplicate field: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def within(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    require(path.is_relative_to(root), f'path escapes scope: {relative}')
    return path


def fields(obj, names, label):
    require(isinstance(obj, dict), f'{label}: expected object')
    for name in names.split():
        require(name in obj, f'{label}: missing {name}')


def extract_query(query_text, context):
    """Validate an Agent's semantic extraction against verbatim source text.

    Context supplies items and a reasoned route. Without items preserve the whole
    query as an unresolved goal; never infer numeric meaning from a token alone.
    """
    scenario = context.get('scenario', 'bug_fix')
    require(scenario in SCENARIOS, 'unknown scenario')
    items = context.get('items') or [{
        'id': 'QUERY', 'source_quote': query_text, 'normalized_value': None,
        'requirement_kind': 'unknown', 'authority': 'user', 'confidence': 0,
        'cost_if_wrong': 'unknown', 'blocking_question': 'Resolve the goal and acceptance criteria.',
        'semantic_candidates': [], 'checklist_ids': ['QUERY-001'],
    }]
    for item in items:
        fields(item, 'id source_quote normalized_value requirement_kind authority confidence cost_if_wrong blocking_question checklist_ids', 'extraction')
        if context.get('schema_version', 1) == 1 or item['authority'] == 'user':
            require(item['source_quote'] and item['source_quote'] in query_text, 'source_quote is not verbatim query text')
        else:
            source = item.get('source', {})
            fields(source, 'kind actor path quote sha256', 'extraction source')
            require(source['kind'] in {'code', 'proposal'}, 'non-user extraction needs code/proposal source')
            require(source['quote'] == item['source_quote'] and source['quote'], 'source quote mismatch')
        require(item['requirement_kind'] in {'goal', 'constraint', 'protocol', 'acceptance', 'non_goal', 'preference', 'unknown'}, 'invalid requirement_kind')
        require(item['authority'] in {'user', 'project_fact', 'source_spec', 'agent_proposal'}, 'invalid authority')
        require(isinstance(item['confidence'], (int, float)) and 0 <= item['confidence'] <= 1, 'invalid confidence')
        require(isinstance(item['checklist_ids'], list) and item['checklist_ids'], 'missing checklist IDs')
        if len(item.get('semantic_candidates', [])) > 1:
            require(item['normalized_value'] is None and item['blocking_question'], 'ambiguity must remain unresolved')
    facts = context.get('facts', {})
    modules = list(MODULES[scenario])
    infra = bool(facts.get('infra')) or scenario == 'infra'
    if infra and scenario not in {'learning', 'office'}:
        modules.insert(1, 'infra-verification') if 'infra-verification' not in modules else None
    # Conservative lint, not route selection: explicit environment repair cannot
    # be downgraded by a supplied low-risk route. Meaning is still reviewed by Agent.
    if scenario not in {'learning', 'office'} and re.search(r'Harbor|Docker|launcher|训练', query_text, re.I):
        require(infra, 'environment/launcher query needs investigated infra facts and infra-verification')
    high = infra or scenario == 'algorithm' or bool(facts.get('side_effects'))
    if re.search(r'退款|扣款|billing|refund', query_text, re.I) and scenario not in {'learning', 'office'}:
        require(facts.get('side_effects'), 'billing query needs side-effect acceptance facts')
    return {'items': items, 'route': {'primary': scenario, 'class': 'infra_heavy' if infra else ('high_risk' if high else 'lightweight'),
                                     'modules': modules, 'reason': context.get('route_reason', 'Agent-selected route; verify against project facts.'), 'facts': facts}}


def resolve_bindings(extraction, repo_context):
    """Check explicit project-adapter bindings. Static anchors are not execution."""
    bindings = repo_context.get('bindings', {})
    result = {}
    for item in extraction['items']:
        binding = bindings.get(item['id'])
        if binding:
            fields(binding, 'id config_key consumer_symbol definition consumer overrides watched_paths', 'binding')
            result[item['id']] = binding
    return result


def validate(record):
    fields(record, 'schema_version task_id created_at source route agreement extraction protocols checklist code_state handoff formal_run mode repo', 'record')
    require(record['schema_version'] in {1, 2}, 'unsupported schema')
    require(record['mode'] in {'local', 'simulation'}, 'invalid mode')
    require(record['route']['primary'] in SCENARIOS, 'invalid route')
    require(record['agreement']['formal_run_policy'] in {'prohibited', 'sandbox_allowed', 'requires_human'}, 'invalid formal policy')
    require(record['protocols'] and record['checklist'], 'protocols and checklist must not be empty')
    protocols = {}
    binding_ids = set()
    for p in record['protocols']:
        fields(p, 'id source meaning expected extraction_ref binding', 'protocol')
        require(p['id'] not in protocols, 'duplicate protocol ID')
        fields(p['source'], 'path quote authority', 'source')
        fields(p['expected'], 'value unit', 'expected')
        require(p['source']['quote'] and p['meaning'], 'empty protocol meaning/source')
        if p['binding']:
            b = p['binding']
            fields(b, 'id config_key consumer_symbol definition consumer overrides watched_paths', 'binding')
            require(b['id'] not in binding_ids, 'duplicate binding ID')
            binding_ids.add(b['id'])
            for key in ('id', 'config_key', 'consumer_symbol', 'readback_key'):
                require(isinstance(b.get(key), str) and b[key].strip(), f'binding: empty {key}')
            require(isinstance(b['overrides'], list) and b['overrides'], 'binding: missing inspected override order')
            for override in b['overrides']:
                fields(override, 'path line symbol', 'override')
                require(isinstance(override['line'], int) and override['line'] > 0 and override['symbol'], 'invalid override anchor')
            for key in ('definition', 'consumer'):
                fields(b[key], 'path line symbol', key)
                require(isinstance(b[key]['line'], int) and b[key]['line'] > 0 and b[key]['symbol'], 'invalid anchor')
        protocols[p['id']] = p
    ids = set()
    for c in record['checklist']:
        fields(c, 'id requirement requirement_ref source risk verifier evidence agent_status human_status review_scope invalidated_by', 'checklist')
        require(c['id'] not in ids, 'duplicate checklist ID')
        ids.add(c['id'])
        require(c['requirement_ref'] in protocols, 'unknown requirement_ref')
        p = protocols[c['requirement_ref']]
        require(c['source'] == p['source'], 'checklist source differs from protocol')
        require(c['risk'] in {'low', 'high_risk'}, 'invalid risk')
        require(c['agent_status'] in AGENT_STATES, 'invalid agent_status')
        require(c['human_status'] in HUMAN_STATES, 'invalid human_status')
        fields(c['verifier'], 'method expected_ref watched_paths', 'verifier')
        require(c['verifier']['expected_ref'] == p['id'] + '.expected', 'verifier must reference protocol expectation')
        require(c['verifier']['method'] in {'unconfigured', 'command_json', 'static_anchor'}, 'unknown verifier method')
        fields(c['evidence'], 'level paths anchors object_digest', 'evidence')
        require(c['evidence']['level'] in {'none', 'static', 'simulated', 'real'}, 'invalid evidence level')
        fields(c['review_scope'], 'must_review context_only', 'review_scope')
        if c['risk'] == 'high_risk':
            require(c['review_scope']['must_review'], 'high risk requires focused review locations')
        if p['binding']:
            require(c.get('binding_ref') == p['binding']['id'], 'missing or wrong binding_ref')
        require(isinstance(c['verifier']['watched_paths'], list), 'watched_paths must be a list')
        require(isinstance(c['invalidated_by'], list), 'invalidated_by must be a list')
        e = next((x for x in record['extraction']['items'] if x['id'] == p['extraction_ref']), None)
        require(e is not None and c['id'] in e['checklist_ids'], 'missing extraction/checklist linkage')
        require(p['expected']['value'] == e['normalized_value'], 'protocol expectation differs from source extraction')
        if e['requirement_kind'] == 'protocol' and record['route']['primary'] not in {'office', 'learning'}:
            require(p['binding'], 'code protocol requires parameter binding')
    expected_ids = [i for e in record['extraction']['items'] for i in e['checklist_ids']]
    require(len(expected_ids) == len(set(expected_ids)) and set(expected_ids) == ids, 'missing or extra checklist item')
    f = record['formal_run']
    fields(f, 'class status required_checklist_items candidate_sha agent_review human_confirmation command config_paths command_digest config_digest', 'formal_run')
    require(f['class'] in {'exploratory', 'short_smoke', 'formal_experiment', 'production', 'external_publish'}, 'invalid run class')
    require(f['status'] in {'prohibited', 'sandbox_allowed', 'awaiting_human', 'authorized', 'running', 'completed', 'invalidated'}, 'invalid formal status')
    require(set(f['required_checklist_items']) <= ids, 'unknown formal checklist item')
    high_ids = {c['id'] for c in record['checklist'] if c['risk'] == 'high_risk'}
    require(high_ids <= set(f['required_checklist_items']), 'formal run omits high-risk checklist')
    if record['schema_version'] == 1 and record['route']['class'] in {'high_risk', 'infra_heavy'}:
        require(high_ids, 'high-risk route cannot omit high-risk checks')
    if f['class'] in {'formal_experiment', 'production', 'external_publish'}:
        require(high_ids and f['human_confirmation']['required'], 'protected action requires human review')
    if record['schema_version'] == 2:
        from .state import validate_state
        validate_state(record)
    return protocols
