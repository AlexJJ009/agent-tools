"""Independent fixture author annotations, distinct from runtime extraction."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/agent_workflow'


def repository(path):
    path.mkdir(parents=True, exist_ok=True)
    for f in FIXTURES.iterdir():
        if f.is_file():
            shutil.copy2(f, path / f.name)
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=Fixture Author', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Independent fixture baseline'], check=True)
    return path


def item(id, quote, expected, kind='protocol', meaning=None):
    return {'id': id, 'source_quote': quote, 'normalized_value': expected, 'requirement_kind': kind,
            'authority': 'user', 'confidence': 1, 'cost_if_wrong': 'invalid experiment' if kind == 'protocol' else 'incorrect deliverable',
            'blocking_question': None, 'checklist_ids': [id + '-001'], 'meaning': meaning or quote, 'unit': 'samples_per_source' if id == 'K' else 'outcome'}


def binding(id, key, line, symbol):
    return {'id': id + '-BINDING', 'config_key': key, 'consumer_symbol': symbol,
            'definition': {'path': 'config.json', 'line': 1, 'symbol': key},
            'consumer': {'path': 'consumer.py', 'line': line, 'symbol': symbol},
            'overrides': [{'path': 'launcher.py', 'line': 5, 'symbol': 'cfg ='},
                          {'path': 'launcher.py', 'line': 6, 'symbol': 'override ='},
                          {'path': 'launcher.py', 'line': 7, 'symbol': 'cfg.update(override)'}],
            'readback_key': '_bindings.' + key,
            'watched_paths': ['config.json', 'override.json', 'launcher.py', 'consumer.py']}


def check(argv, key, paths, anchor, risk='high_risk'):
    return {'risk': risk, 'verifier': {'method': 'command_json', 'argv': argv, 'observation_key': key,
                                      'watched_paths': paths}, 'review_scope': {'must_review': [anchor] if risk == 'high_risk' else [], 'context_only': []}}


def context(name):
    oracle = json.loads((FIXTURES / 'oracles.json').read_text())[name]
    c = {'scenario': oracle['scenario'], 'route_reason': 'Inspect fixture entrypoint, effects and requested deliverable.',
         'facts': {}, 'formal_run_policy': 'prohibited', 'items': [], 'bindings': {}, 'checks': {}}
    if name == 'algorithm':
        c['facts'] = {'infra': True}
        c['items'] = [item('K', 'K=4', {'bare': 4, 'privileged': 4}, meaning='Four samples for EACH enabled source, eight total.'),
                      item('RESPONSE', 'response=8192', 8192, meaning='Maximum output tokens, not prompt or total context.'),
                      item('CAPACITY', 'response=8192', True, kind='acceptance', meaning='Prompt plus requested output fits context capacity.')]
        c['bindings'] = {'K': binding('K', 'samples_per_source', 4, "cfg['samples_per_source']"),
                         'RESPONSE': binding('RESPONSE', 'max_response_length', 5, "cfg['max_response_length']")}
        for id, key in [('K', 'counts'), ('RESPONSE', 'output_limit'), ('CAPACITY', 'capacity_ok')]:
            c['checks'][id + '-001'] = check([sys.executable, 'launcher.py'], key, ['config.json', 'override.json', 'launcher.py', 'consumer.py'], 'consumer.py:4')
        c['command'] = [sys.executable, 'launcher.py']
        c['config_paths'] = ['config.json', 'override.json']
    elif name == 'infra':
        c['facts'] = {'infra': True}
        c['items'] = [item('ENV', oracle['query'], oracle['expected'], kind='acceptance')]
        c['checks'] = {'ENV-001': check([sys.executable, 'infra_probe.py'], 'environment', ['infra_probe.py', 'infra.json'], 'infra_probe.py:5')}
        c['command'] = [sys.executable, 'infra_probe.py']
        c['config_paths'] = ['infra.json']
    elif name == 'business':
        c['facts'] = {'side_effects': ['refund', 'idempotency']}
        c['items'] = [item('REFUND', '退款重复扣款', 20, kind='acceptance', meaning='Repeated same request refunds only once.')]
        c['checks'] = {'REFUND-001': check([sys.executable, 'refund_probe.py'], 'balance', ['refund.py', 'refund_probe.py'], 'refund.py:3')}
        c['command'] = [sys.executable, 'refund_probe.py']
        c['config_paths'] = ['refund.py']
    else:
        c['items'] = [item('CONTENT', oracle['query'], 'Await source material and specialized tool inspection.', kind='goal')]
        # No code verifiers: missing papers/slides are explicit, not fake passes.
    return oracle, c
