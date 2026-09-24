#!/usr/bin/env python3
"""Exercise candidate workflow mechanisms against frozen CPU/loopback oracles.

This is evaluator code. It must never be given to an Agent whose natural
choice-discovery behavior is being assessed. All effects stay in --output.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import select
import shlex
import shutil
import subprocess
import sys
import traceback
import urllib.request
import uuid
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from agent_workflow import managed, runtime
from agent_workflow.contracts import ContractError, digest, file_digest, load

FIXTURES = REPO / 'tests/fixtures/workflow_v2'
CASES = ['AC-01', 'AC-03', 'AC-04', 'AC-05', 'AC-06', 'AC-07', 'AC-08', 'AC-09', 'AC-11']
EXTERNAL = {'AC-02': 'Four isolated natural-discovery Agent traces and oracle comparison',
            'AC-10': 'Actual isolated Codex host and all five event receipts',
            'AC-12': 'Real requested/agreed reporting and resume trace',
            'AC-13': 'Independent cold-read and source-review receipts',
            'AC-14': 'English migration, export/install/relocation and legacy regressions'}


def ensure(condition, reason):
    if not condition:
        raise AssertionError(reason)


def save(path, value):
    runtime.write(path, value)


def matches(actual, expected):
    return all(math.isclose(actual.get(key, float('nan')), value, rel_tol=0, abs_tol=1e-12)
               if isinstance(value, float) else actual.get(key) == value
               for key, value in expected.items())


def initialize_git(repo):
    for argv in (['init', '-q'], ['add', '.'], ['-c', 'user.name=Fixture', '-c',
                 'user.email=fixture@example.invalid', 'commit', '-qm', 'Frozen sample copy']):
        subprocess.run(['git', '-C', str(repo), *argv], check=True, capture_output=True)


def extraction(id, quote, expected, meaning):
    return {'id': id, 'source_quote': quote, 'normalized_value': expected, 'meaning': meaning,
            'requirement_kind': 'acceptance', 'authority': 'user', 'confidence': 1,
            'cost_if_wrong': 'Incorrect local fixture acceptance', 'blocking_question': None,
            'checklist_ids': [id], 'unit': 'observed outcome'}


class Exercise:
    def __init__(self, directory, fixture='algorithm', *, reference=False):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        self.repo = directory / 'repo'
        shutil.copytree(FIXTURES / 'inputs' / fixture, self.repo)
        self.seq = 0
        self.observations = []
        self.effect = directory / 'effect.json'
        self.source_paths = {}
        self.reference = reference
        if fixture == 'algorithm':
            self._cpu()

    def _cpu(self):
        observable = load(FIXTURES / 'oracle/observables.json')['algorithm']
        expected = dict(observable['baseline'])
        if self.reference:
            save(self.repo / 'override.json', observable['reference_override'])
            expected.update(observable['reference_expected'])
        self.expected = expected
        receipts = self.directory / 'consumer-processes.jsonl'
        driver = '''import argparse,json,subprocess,sys,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--effect');p.add_argument('--run-id',default='readback');p.add_argument('--verify',action='store_true');a=p.parse_args()
effect=Path(a.effect) if a.effect else Path(ARTIFACTS)/(uuid.uuid4().hex+'-consumer.json')
if effect.exists(): effect.unlink()
argv=[sys.executable,'-B','launcher.py','--effect',str(effect),'--run-id',a.run_id]
proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
out,err=proc.communicate(timeout=5)
receipt={'argv':argv,'pid':proc.pid,'returncode':proc.returncode,'stdout':out,'stderr':err,'effect':str(effect)}
try:
 observed=json.loads(out)
 valid=proc.returncode==0 and effect.is_file() and json.loads(effect.read_text())==observed and observed.get('pid')==proc.pid
except (ValueError,OSError): valid=False
receipt['effect_verified']=valid
with Path(RECEIPTS).open('a') as stream: stream.write(json.dumps(receipt)+'\\n')
if not valid: print(json.dumps({'effect_verified':False}));sys.exit(3)
if a.verify: observed['reward_12dp']=round(observed['seven_token_correct_answer_reward'],12)
print(json.dumps(observed))
'''.replace('ARTIFACTS', repr(str(self.directory))).replace('RECEIPTS', repr(str(receipts)))
        (self.repo / 'driver.py').write_text(driver)
        specs = {'samples': ('counts', expected['counts']), 'output': ('largest_generated_output', expected['largest_generated_output']),
                 'critic': ('critic_weights', expected['critic_weights']),
                 'reward': ('reward_12dp', expected['seven_token_correct_answer_reward'])}
        paths = ['driver.py', 'launcher.py', 'consumer.py', 'config.json', 'override.json', 'reference_critic.json']
        self.initialize(specs, [sys.executable, '-B', 'driver.py', '--verify'], paths)
        self.register('cpu', [sys.executable, '-B', 'driver.py', '--effect', str(self.effect), '--run-id', 'managed-cpu'],
                      ['config.json', 'override.json', 'reference_critic.json'], ['driver.py', 'launcher.py', 'consumer.py'])

    def initialize(self, specs, argv, paths, query=None):
        query = query or (FIXTURES / 'inputs/requests/algorithm_a.txt').read_text()
        request = self.directory / 'request.txt'
        request.write_text(query)
        # This evaluator supplies mechanism standards from the frozen oracle.
        # Do not mislabel numeric oracle values as words from the natural user.
        oracle_source = self.directory / 'frozen-standards.json'
        save(oracle_source, {'source': 'oracle/observables.json', 'source_sha256': file_digest(FIXTURES / 'oracle/observables.json'),
                            'standards': {id: {'observation': key, 'expected': expected} for id, (key, expected) in specs.items()}})
        items = [extraction(id, oracle_source.read_text(), expected, 'Observe ' + key + ' from the actual consumer') for id, (key, expected) in specs.items()]
        for entry in items:
            entry.update(authority='source_spec', source={'kind': 'code', 'actor': 'Independent evaluator',
                'path': str(oracle_source), 'quote': oracle_source.read_text(), 'sha256': file_digest(oracle_source)})
        checks = {id: {'risk': 'low', 'review_scope': {'must_review': [], 'context_only': []},
            'verifier': {'method': 'command_json', 'argv': argv, 'observation_key': key, 'watched_paths': paths}}
            for id, (key, _) in specs.items()}
        initialize_git(self.repo)
        self.root = runtime.init(request, self.repo, 'bug_fix', {'schema_version': 2, 'items': items, 'checks': checks}, 'simulation')
        self.ids = list(specs)

    def note(self, label, **data):
        entry = {'observation': label, **data}
        self.observations.append(entry)
        save(self.directory / 'observations.json', self.observations)
        return entry

    def turn(self, script, turn_id):
        data = load(FIXTURES / 'inputs/user_scripts' / (script + '.json'))
        turn = next((t for t in data.get('turns', []) if t['id'] == turn_id), None)
        if turn is None:
            turn = data[turn_id]
        path = self.directory / ('user-' + turn_id + '.txt')
        ensure(not path.exists(), 'scripted user turn delivered twice')
        path.write_text(turn['quote'])
        self.note('scripted user turn delivered', script=script, turn=turn_id, source=str(path), revision=self.record()['revision'])
        return path

    def record(self):
        return runtime.read_record(self.root)

    def event(self, kind, payload, *, source=None, affects=None, id=None, base=None):
        self.seq += 1
        if source is None:
            source = self.directory / f'agent-source-{self.seq}.txt'
            source.write_text(json.dumps(payload, ensure_ascii=False))
            source_kind = 'proposal'
        else:
            source_kind = 'user'
        return {'id': id or f'e{self.seq}', 'base_revision': self.record()['revision'] if base is None else base,
                'type': kind, 'source': {'kind': source_kind, 'actor': 'simulated-user' if source_kind == 'user' else 'Agent',
                    'path': str(source), 'quote': source.read_text(), 'sha256': file_digest(source)},
                'affects': self.ids if affects is None else affects, 'payload': payload}

    def update(self, kind, payload, **kwargs):
        return runtime.update(self.root, self.event(kind, payload, **kwargs))

    def register(self, id, argv, config_paths, command_paths, scope=None, fresh=False):
        self.update('action.register', {'action': {'id': id, 'phase': 'baseline', 'choice_ids': [],
            'required_checklist_items': self.ids, 'argv': argv, 'config_paths': config_paths,
            'command_paths': command_paths, 'authorization_scope': scope or {'budget': 0, 'target': 'local CPU demo'},
            'require_fresh_authorization': fresh}})

    def authorize(self, source, action='cpu', fresh=False):
        record = self.record()
        target = record['actions'][action]
        payload = {'id': f'authority-{self.seq}', 'action_ids': [action], 'scope': target['authorization_scope']}
        if fresh:
            payload['input_digest'] = managed.input_identity(record, target)
        self.update('authorization.grant', payload, source=source)

    def check(self, selected=None, succeeds=True):
        with runtime.locked(self.root):
            errors = runtime.check(self.root, selected)
        ensure((not errors) == succeeds, 'Unexpected technical check result: ' + repr(errors))
        self.note('actual verifier result', selected=selected or self.ids, passed=not errors, errors=errors)
        return errors

    def cli(self, args, succeeds=True, through_shell=False):
        argv = [sys.executable, '-B', '-m', 'agent_workflow.cli', *map(str, args)]
        if through_shell:
            argv = ['bash', '-c', shlex.join(argv)]
        proc = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, timeout=30)
        save(self.directory / f'cli-{len(self.observations)}.json', {'argv': argv, 'returncode': proc.returncode, 'stdout': proc.stdout, 'stderr': proc.stderr})
        ensure((proc.returncode == 0) == succeeds, 'Unexpected CLI status: ' + proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def run(self, ready, *, action='cpu', mode='direct', expected_digest=None):
        if self.effect.exists():
            self.effect.unlink()
        if mode == 'shell':
            result = self.cli(['execute', '--record', self.root, '--action', action, '--simulation'], succeeds=ready, through_shell=True)
        else:
            result = managed.execute(self.root, action, simulation=True, expected_digest=expected_digest)
            ensure((result['status'] == 'pass') == ready, 'Unexpected managed execution result: ' + repr(result))
        ensure(self.effect.exists() == ready, 'Refusal/allow disagrees with actual effect marker')
        if ready:
            observed = json.loads(result['stdout'])
            ensure(load(self.effect) == observed, 'Effect differs from actual command output')
            ensure(matches(observed, self.expected), 'CPU effect differs from frozen oracle')
        self.note('managed invocation', mode=mode, action=action, allowed=ready,
                  marker_exists=self.effect.exists(), errors=result.get('errors', []), receipt=result.get('receipt'))
        return result

    def enqueue(self, action='cpu'):
        gate = managed.gate_action(self.root, action, simulation=True)
        request = self.directory / f'queued-{self.seq}.json'
        save(request, {'action': action, 'input_digest': gate['input_digest'], 'record': str(self.root)})
        self.update('job.update', {'id': action, 'status': 'queued', 'queue_request': str(request)})
        self.note('persisted queue request', path=str(request), gate=gate)
        return load(request)['input_digest']

    def choices(self):
        for id in ('critic', 'reward'):
            self.update('choice.propose', {'id': id, 'question': 'Select ' + id + ' semantics',
                'affects': [id], 'required_scope': id}, affects=[id])
            self.update('understanding.explain', {'choice_id': id, 'scope': id,
                'explanation': 'Reference initialization changes initial values; outcome-only reward excludes length penalties.'}, affects=[id])

    def decide(self, id, source):
        self.update('choice.resolve', {'choice_id': id, 'value': 'reference' if id == 'critic' else 'outcome_only',
                    'rationale': 'The user selected the reference comparison.'}, source=source, affects=[id])
        self.update('understanding.feedback', {'choice_id': id, 'scope': id, 'kind': 'reconstruction'}, source=source, affects=[id])


def ac01(directory, manifest=None, trusted=None):
    ensure(manifest is not None and trusted, 'AC-01 requires the independently frozen manifest and trusted SHA-256')
    verifier = FIXTURES / 'oracle/verify_manifest.py'
    argv = [sys.executable, str(verifier), '--manifest', str(manifest), '--trusted-sha256', trusted, '--root', str(REPO)]
    process = subprocess.run(argv, capture_output=True, text=True)
    ensure(process.returncode == 0, 'Frozen baseline integrity failed: ' + process.stdout)
    trial = Exercise(directory)
    trial.note('independent frozen baseline', receipt=json.loads(process.stdout), manifest=str(manifest), trusted_sha256=trusted)
    isolated = directory / 'baseline-copy'
    isolated.mkdir()
    shutil.copytree(FIXTURES, isolated / 'tests/fixtures/workflow_v2')
    target = isolated / 'tests/fixtures/workflow_v2/oracle/acceptance.json'
    original = target.read_bytes()
    for label, contents in [('one-byte change', original + b' '), ('mandatory case removed', json.dumps(dict(load(target), criteria=load(target)['criteria'][1:])).encode())]:
        target.write_bytes(contents)
        denied = subprocess.run(argv[:-1] + [str(isolated)], capture_output=True, text=True)
        ensure(denied.returncode != 0, 'Baseline verifier accepted ' + label)
        trial.note('baseline negative rejected', mutation=label, receipt=json.loads(denied.stdout))
    first = trial.turn('scoped_understanding', 'understanding-1')
    before = deepcopy(trial.record()['protocols'])
    trial.update('requirements.revise', {'updates': [{'protocol_id': 'critic', 'expected': {'value': [0.5, -0.25], 'unit': 'weights'},
        'meaning': 'Use the reference critic starting weights'}], 'reason': 'User selected reference initialization'}, source=first, affects=['critic'])
    record = trial.record()
    event = record['events'][-1]
    ensure(event['detail']['before'][0] == next(p for p in before if p['id'] == 'critic'), 'Previous standard lost')
    ensure(event['payload']['reason'] and record['phase'] == 'baseline', 'Amendment lost reason or phase')
    trial.note('requirement amendment preserved', old=event['detail']['before'], current=record['protocols'][2], revision=record['revision'])
    return trial.observations


def ac03(directory, **_):
    trial = Exercise(directory, reference=True)
    trial.check()
    trial.choices()
    first = trial.turn('scoped_understanding', 'understanding-1')
    trial.decide('critic', first)
    trial.update('understanding.feedback', {'choice_id': 'reward', 'scope': 'reward', 'kind': 'question'}, source=first, affects=['reward'])
    question = trial.record()['events'][-1]['id']
    second = trial.turn('scoped_understanding', 'understanding-2')
    trial.authorize(second)
    denied = trial.run(False)
    ensure(any('reward' in error for error in denied['errors']), 'Refusal did not identify reward scope')
    record = trial.record()
    ensure(record['choices'][0]['resolution'] and record['choices'][1]['resolution'] is None, 'Critic feedback spread to reward')
    text = (trial.repo / 'consumer.py').read_text()
    ensure('def generate' in text, 'Unrelated reading failed')
    trial.note('unrelated source read succeeded', path='consumer.py', sha256=file_digest(trial.repo / 'consumer.py'))
    third = trial.turn('scoped_understanding', 'understanding-3')
    trial.update('understanding.explain', {'choice_id': 'reward', 'scope': 'reward', 'explanation': 'Outcome-only reward scores correctness; a length penalty also subtracts for length.'}, affects=['reward'])
    trial.decide('reward', third)
    trial.update('understanding.feedback', {'choice_id': 'reward', 'scope': 'reward', 'kind': 'reconstruction', 'resolves': [question]}, source=third, affects=['reward'])
    trial.run(True)
    fourth = trial.turn('scoped_understanding', 'understanding-4')
    trial.update('requirements.revise', {'updates': [{'protocol_id': 'reward', 'expected': {'value': .93, 'unit': 'reward'}, 'meaning': 'Length-adjusted reward'}], 'reason': 'New meaning is outside the earlier explanation'}, source=fourth, affects=['reward'])
    trial.run(False)
    ensure(not trial.record()['choices'][1]['understanding']['feedback_refs'], 'Changed meaning inherited prior understanding')
    return trial.observations


def ac04(directory, **_):
    trial = Exercise(directory)
    source = trial.turn('delegation', 'delegation-1')
    trial.choices()
    for id in ('critic', 'reward'):
        trial.update('delegation.grant', {'id': id + '-demo', 'choice_ids': [id], 'scope': id}, source=source, affects=[id])
    trial.authorize(source)
    save(trial.repo / 'override.json', {'samples_per_source': 2})
    trial.check(succeeds=False)
    trial.run(False)
    trial.turn('delegation', 'delegation-2')
    save(trial.repo / 'override.json', {})
    trial.check()
    trial.run(True)
    record = trial.record()
    ensure(len(record['execution_authority']) == 1, 'Routine repair created extra authority')
    ensure(all(not c['understanding']['feedback_refs'] for c in record['choices']), 'Delegation fabricated understanding')
    with monitor(directory / 'ordinary-bug') as bug:
        request = load(FIXTURES / 'inputs/user_scripts/delegation.json')['independent_bug_fix_request']
        bug.render()
        monitor_state(bug, expected_http=200, query=request)
        ensure(bug.record()['route']['class'] == 'lightweight', 'Ordinary bug repair was made high risk')
        page = bug.repo / 'page.py'
        original = page.read_text()
        page.write_text(original.replace('"display_refreshed_at_ns": time.time_ns()', '"display_refreshed_at_ns": "wrong:" + str(time.time_ns())'))
        bug.check(['timestamps'], succeeds=False)
        page.write_text(original)
        bug.check()
        ensure(bug.stats()['count'] == 1, 'Display repair changed cache-refresh behavior')
        trial.note('ordinary display repair remained lightweight', quote=request, observations=bug.observations)
    trial.note('authority reused without a new grant', count=1, understanding_claimed=False)
    return trial.observations


def ac05(directory, **_):
    trial = Exercise(directory)
    source = trial.turn('delegation', 'delegation-1')
    trial.authorize(source); trial.check()
    event = trial.event('input.record', {'id': 'prompt-1'}, source=source, affects=['samples'])
    before = trial.record()['revision']
    with patch.object(runtime, 'refresh_views', side_effect=OSError('acceptance fault: view storage interrupted')):
        committed = runtime.update(trial.root, event)
    ensure(committed['views_error'], 'View fault was not observed')
    ensure(trial.record()['revision'] == before + 1, 'Canonical commit lost at view interruption')
    replay = runtime.update(trial.root, event)
    ensure(replay['duplicate'] and trial.record()['revision'] == before + 1, 'Retry was duplicated')
    ensure(load(trial.root / 'events.json')['events'] == trial.record()['events'], 'Event view did not recover')
    stale = trial.event('input.record', {'id': 'prompt-stale'}, source=source, base=before)
    try:
        runtime.update(trial.root, stale)
        raise AssertionError('Old revision update was accepted')
    except ContractError as exc:
        ensure('revision conflict' in str(exc), 'Unexpected stale update failure')
    counter = trial.directory / 'consumer-processes.jsonl'
    count_before = len(counter.read_text().splitlines())
    trial.cli(['status', '--record', trial.root])
    ensure(len(counter.read_text().splitlines()) == count_before, 'Status executed a verifier')
    trial.run(False)
    ensure((trial.repo / 'README.md').read_text(), 'Unrelated read blocked')
    trial.update('input.resolve', {'id': 'prompt-1', 'disposition': 'no_contract_change', 'reason': 'Only a status request'}, affects=['samples'])
    trial.run(True)
    trial.note('conflict and interruption controls', before_revision=before, committed_revision=committed['revision'], retry_revision=replay['revision'], verifier_count_unchanged=count_before)
    return trial.observations


@contextmanager
def monitor(directory):
    trial = Exercise(directory, fixture='monitor')
    service = subprocess.Popen([sys.executable, '-B', 'server.py', '--journal', str(directory / 'requests.jsonl')],
                               cwd=trial.repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        ensure(select.select([service.stdout], [], [], 5)[0], 'Loopback server startup timed out')
        startup = json.loads(service.stdout.readline())
        trial.base_url = startup['base_url']
        trial.note('loopback server started', **startup)
        def stats():
            with urllib.request.urlopen(trial.base_url + '/stats', timeout=2) as response:
                return json.loads(response.read())
        def render(mode='cache', extra=()):
            argv = [sys.executable, '-B', 'page.py', '--base-url', trial.base_url,
                    '--state', 'cache.json', '--mode', mode, *map(str, extra)]
            proc = subprocess.Popen(argv, cwd=trial.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = proc.communicate(timeout=5)
            ensure(proc.returncode == 0, stderr)
            page = json.loads(stdout)
            trial.note('actual page render', argv=argv, pid=proc.pid, returncode=proc.returncode, page=page, server=stats())
            return page
        trial.stats, trial.render = stats, render
        yield trial
    finally:
        service.terminate()
        try:
            _, stderr = service.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            service.kill(); _, stderr = service.communicate(timeout=3)
        trial.note('loopback server stopped', pid=service.pid, returncode=service.returncode, stderr=stderr)


def monitor_state(trial, expected_http=429, query=None):
    adapter = '''import json,subprocess,sys,urllib.request
URL=BASEURL
def stats():
 with urllib.request.urlopen(URL+'/stats',timeout=2) as response: return json.loads(response.read())
before=stats()
p=subprocess.run([sys.executable,'-B','page.py','--base-url',URL,'--state','cache.json','--mode','cache'],capture_output=True,text=True,check=True)
page=json.loads(p.stdout);after=stats()
print(json.dumps({'timestamp_separation':page['display_refreshed_at_ns']>page['last_observation_at_ns'],
 'http_status':page['latest_observation']['http_status'],
 'failure_preserved':page['displayed_status']==('healthy' if page['latest_observation']['http_status']==200 else 'unavailable'),
 'cached_count_unchanged':before['count']==after['count'],'page':page,'server':after}))
'''.replace('BASEURL', repr(trial.base_url))
    (trial.repo / 'monitor_readback.py').write_text(adapter)
    trial.initialize({'timestamps': ('timestamp_separation', True), 'rate_limit': ('http_status', expected_http),
                      'failure': ('failure_preserved', True), 'cached': ('cached_count_unchanged', True)},
                     [sys.executable, '-B', 'monitor_readback.py'], ['monitor_readback.py', 'page.py', 'cache.json'],
                     query=query or load(FIXTURES / 'inputs/user_scripts/mvp_feedback.json')['turns'][0]['quote'])


def ac06(directory, **_):
    with monitor(directory) as trial:
        initial = trial.render()
        cached = trial.render()
        ensure(initial['last_observation_at_ns'] == cached['last_observation_at_ns'] and trial.stats()['count'] == 1, 'MVP1 cache behavior changed')
        monitor_state(trial, expected_http=429)
        trial.turn('mvp_feedback', 'mvp-1-scope')
        compliment = trial.turn('mvp_feedback', 'mvp-1-appearance')
        trial.update('input.record', {'id': 'appearance'}, source=compliment)
        ensure(all(c['result_acceptance']['status'] == 'pending' for c in trial.record()['checklist']), 'Compliment accepted unseen behavior')
        trial.update('input.resolve', {'id': 'appearance', 'disposition': 'no_contract_change', 'reason': 'General appearance feedback names no accepted item'})
        accepted = trial.turn('mvp_feedback', 'mvp-1-acceptance')
        trial.update('result.feedback', {'kind': 'acceptance', 'items': {'timestamps': 'accepted'}}, source=accepted, affects=['timestamps'])
        trial.update('result.feedback', {'kind': 'next_version', 'items': {'cached': 'pending'}}, source=accepted, affects=['cached'])
        trial.update('phase.define', {'id': 'mvp-2', 'required_checklist_items': []}, affects=[])
        next_source = trial.turn('mvp_feedback', 'mvp-2-request')
        trial.update('requirement.add', {'item': extraction('active_probe', next_source.read_text(), True, 'Every scheduled refresh makes an actual upstream request'),
            'check': {'risk': 'low'}, 'phase': 'mvp-2', 'reason': 'New active behavior for the next MVP'}, source=next_source, affects=[])
        record = trial.record()
        by_id = {c['id']: c for c in record['checklist']}
        ensure(by_id['timestamps']['result_acceptance']['status'] == 'accepted', 'MVP2 revoked accepted cached MVP1')
        ensure(by_id['rate_limit']['result_acceptance']['status'] == 'pending', 'Unseen 429 was accepted')
        ensure(by_id['active_probe']['agent_status'] == 'unverified', 'New requirement inherited verification')
        clarification = trial.turn('mvp_feedback', 'clarification_branch')
        trial.update('result.feedback', {'kind': 'clarification', 'items': {'timestamps': 'pending'}}, source=clarification, affects=['timestamps'])
        ensure(trial.record()['checklist'][0]['result_acceptance']['status'] == 'accepted', 'Clarification changed result acceptance')
        trial.note('MVP scopes and partial acceptance', statuses={k: c['result_acceptance']['status'] for k, c in by_id.items()}, phases=record['phases'])
        # A separate record starts with an already-promised active refresh. The
        # observed unchanged counter is a current defect, not future scope.
        defect_query = trial.turn('mvp_feedback', 'defect_branch')
        defect_record = runtime.init(defect_query, trial.repo, 'bug_fix', {'schema_version': 2,
            'items': [extraction('active_promise', defect_query.read_text(), True, 'Already promised active request each refresh')]}, 'simulation', 'defect')
        source = {'kind': 'user', 'actor': 'simulated-user', 'path': str(defect_query), 'quote': defect_query.read_text(), 'sha256': file_digest(defect_query)}
        before = trial.stats()['count']; trial.render(); after = trial.stats()['count']
        ensure(before == after, 'Defect control unexpectedly performed active request')
        runtime.update(defect_record, {'id': 'reported-defect', 'base_revision': 0, 'type': 'result.feedback', 'source': source,
            'affects': ['active_promise'], 'payload': {'kind': 'defect', 'items': {'active_promise': 'rejected'}}})
        defect = runtime.read_record(defect_record)['checklist'][0]
        ensure(defect['agent_status'] == 'needs_recheck' and defect['result_acceptance']['status'] == 'rejected', 'Existing promise relabeled as future scope')
        trial.note('current-version defect remains current', record=str(defect_record), counts=[before, after], item=defect)
    return trial.observations


def ac07(directory, **_):
    trial = Exercise(directory)
    trial.check()
    baseline = json.loads((trial.directory / 'consumer-processes.jsonl').read_text().splitlines()[-1])
    ensure(baseline['effect_verified'], 'Baseline consumer effect not independently verified')
    observed = json.loads(baseline['stdout'])
    ensure(matches(observed, trial.expected), 'Baseline actual values differ from frozen oracle')
    source = trial.turn('delegation', 'delegation-1'); trial.authorize(source)
    trial.choices()
    for id in ('critic', 'reward'):
        trial.update('delegation.grant', {'id': id, 'choice_ids': [id], 'scope': id}, source=source, affects=[id])
    original_choices = deepcopy(trial.record()['choices'])
    (trial.repo / 'notes.txt').write_text('Unrelated note')
    runtime.status(trial.root)
    ensure(all(c['agent_status'] == 'checked' for c in trial.record()['checklist']), 'Unrelated edit invalidated evidence')
    save(trial.repo / 'override.json', {'samples_per_source': 2})
    trial.check(['samples'], succeeds=False)
    half = json.loads(json.loads((trial.directory / 'consumer-processes.jsonl').read_text().splitlines()[-1])['stdout'])
    ensure(half['counts'] == {'bare': 2, 'privileged': 2}, 'Half-budget negative did not alter consumed counts')
    save(trial.repo / 'override.json', {})
    trial.check()
    receipt = trial.root / trial.record()['checklist'][0]['evidence']['paths'][0]
    receipt.unlink()
    trial.check(['samples'], succeeds=False)
    trial.check(['samples'])
    # Change the expected output from an independent oracle, not observed output.
    oracle_source = trial.directory / 'short-output-oracle.json'
    save(oracle_source, {'source_sha256': file_digest(FIXTURES / 'oracle/observables.json'),
         'standard': load(FIXTURES / 'oracle/observables.json')['algorithm']['negative_overrides']['short_output']})
    event = trial.event('requirements.revise', {'updates': [{'protocol_id': 'output', 'expected': {'value': 17, 'unit': 'tokens'},
        'meaning': 'The short-output oracle requires seventeen emitted tokens'}], 'reason': 'Exercise the frozen short-output negative'}, source=oracle_source, affects=['output'])
    event['source']['kind'] = 'code'; event['source']['actor'] = 'Independent evaluator'
    runtime.update(trial.root, event)
    save(trial.repo / 'override.json', {'max_response_length': 17})
    trial.check(['output'])
    consumer = trial.repo / 'consumer.py'; original = consumer.read_text()
    ensure('output_limit = int(cfg["max_response_length"])' in original, 'Frozen negative edit anchor missing')
    consumer.write_text(original.replace('output_limit = int(cfg["max_response_length"])', 'output_limit = 5'))
    trial.check(['output'], succeeds=False)
    consumer.write_text(original); trial.check(['output'])
    launcher = trial.repo / 'launcher.py'; original_launcher = launcher.read_text()
    launcher.write_text('print(' + repr(json.dumps(observed)) + ')\n')
    trial.check(['samples'], succeeds=False)
    echo = json.loads((trial.directory / 'consumer-processes.jsonl').read_text().splitlines()[-1])
    ensure(not echo['effect_verified'] and not Path(echo['effect']).exists(), 'Expected-echo negative unexpectedly produced actual effect')
    launcher.write_text(original_launcher)
    save(trial.repo / 'override.json', {'max_response_length': 17})
    trial.check()
    ensure(trial.record()['choices'] == original_choices, 'Unrelated output revision reopened critic/reward choices')
    trial.note('CPU actual readback and negative controls', baseline_pid=baseline['pid'], baseline=observed,
               reduced_counts=half['counts'], ignored_output_rejected=True, expected_echo_rejected=True)
    with monitor(directory / 'monitor') as health:
        expected = load(FIXTURES / 'oracle/observables.json')['monitor']
        first = health.render(); cached = health.render()
        ensure(health.stats()['count'] == expected['cached_redraw']['count'], 'Cache redraw performed a request')
        ensure(first['last_observation_at_ns'] == cached['last_observation_at_ns'] and cached['display_refreshed_at_ns'] > first['display_refreshed_at_ns'], 'Cache timestamps not distinct')
        failed = health.render('probe'); again = health.render()
        ensure(health.stats()['count'] == 2 and failed['latest_observation']['http_status'] == 429 and again['displayed_status'] == 'unavailable', '429 hidden by prior success')
        ensure(failed['latest_observation']['retry_after'] == '1' and failed['last_success']['request_count'] == 1, '429 retry/previous success evidence lost')
        monitor_state(health); health.check()
        page = health.repo / 'page.py'; original_page = page.read_text()
        page.write_text(original_page.replace('"healthy" if latest["http_status"] == 200 else "unavailable"', '"healthy" if state.get("last_success") else "unavailable"'))
        health.check(['failure'], succeeds=False)
        page.write_text(original_page); health.check(['failure'])
        recovered = health.render('probe', ['--effect', health.effect, '--version', 'mvp-2'])
        publication = load(health.effect)
        ensure(publication['kind'] == 'sandbox_publication' and publication['version'] == 'mvp-2' and publication['page'] == recovered, 'Sandbox publication effect mismatch')
        slow = health.render('probe', ['--endpoint', '/slow', '--timeout', '.02'])
        ensure(health.stats()['count'] == 4 and slow['latest_observation']['http_status'] is None and slow['displayed_status'] == 'unavailable', 'Actual timeout incorrectly displayed healthy')
    trial.note('loopback runtime verification', observations=health.observations)
    return trial.observations


def ac08(directory, **_):
    trial = Exercise(directory)
    source = trial.turn('delegation', 'delegation-1')
    trial.authorize(source); trial.check(); trial.run(True)
    receipt_id = trial.record()['execution_authority'][0]['source_ref']
    consumer = trial.repo / 'consumer.py'
    consumer.write_text(consumer.read_text() + '\n# Behavior-preserving local implementation repair.\n')
    subprocess.run(['git', '-C', str(trial.repo), 'add', 'consumer.py'], check=True)
    subprocess.run(['git', '-C', str(trial.repo), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Equivalent repair'], check=True, capture_output=True)
    trial.run(False); trial.check(); trial.run(True)
    ensure(len(trial.record()['execution_authority']) == 1 and trial.record()['execution_authority'][0]['source_ref'] == receipt_id, 'New SHA fabricated new user authority')
    trial.register('paid-option', [sys.executable, '-B', 'driver.py', '--effect', str(trial.effect)], ['config.json', 'override.json', 'reference_critic.json'], ['driver.py', 'launcher.py', 'consumer.py'], scope={'budget': 1, 'target': 'paid endpoint option; no actual network call'})
    trial.turn('delegation', 'delegation-3')
    trial.run(False, action='paid-option')
    explicit = Exercise(directory / 'explicit-run')
    explicit.turn('explicit_run_constraint', 'run-constraint-1')
    explicit.register('ask-first', [sys.executable, '-B', 'driver.py', '--effect', str(explicit.effect)], ['config.json', 'override.json', 'reference_critic.json'], ['driver.py', 'launcher.py', 'consumer.py'], fresh=True)
    explicit.check(); explicit.run(False, action='ask-first')
    yes = explicit.turn('explicit_run_constraint', 'run-constraint-2')
    explicit.authorize(yes, action='ask-first', fresh=True); explicit.run(True, action='ask-first')
    save(explicit.repo / 'override.json', {'display_note': 'changed input'})
    explicit.check(); explicit.run(False, action='ask-first')
    ensure(all(c['result_acceptance']['status'] == 'pending' for c in explicit.record()['checklist']), 'Run authorization became result acceptance')
    trial.note('explicit per-run condition retained', observations=explicit.observations)
    return trial.observations


def ac09(directory, **_):
    trial = Exercise(directory)
    for mode in ('direct', 'shell', 'queue'):
        trial.run(False, mode=mode)
    trial.check(); source = trial.turn('delegation', 'delegation-1'); trial.authorize(source)
    for mode in ('direct', 'shell', 'queue'):
        queued = trial.enqueue() if mode == 'queue' else None
        trial.run(True, mode=mode, expected_digest=queued)
    queued = trial.enqueue()
    save(trial.repo / 'override.json', {'display_note': 'after queue'})
    trial.check()
    trial.run(False, mode='queue', expected_digest=queued)
    trial.run(True, mode='queue', expected_digest=trial.enqueue())
    saved_run = subprocess.run
    def mutate_after_snapshot(argv, **kwargs):
        if 'driver.py' in argv:
            save(trial.repo / 'override.json', {'samples_per_source': 2})
        return saved_run(argv, **kwargs)
    with patch('agent_workflow.managed.subprocess.run', side_effect=mutate_after_snapshot):
        result = trial.run(True)
    ensure(json.loads(result['stdout'])['counts'] == {'bare': 4, 'privileged': 4}, 'Action did not consume checked snapshot')
    trial.run(False)
    trial.note('queue and check-to-use boundaries', queue_identity=queued, actual_snapshot_inputs=result['inputs'], requires_hook=False)
    return trial.observations


def ac11(directory, **_):
    trial = Exercise(directory)
    trial.update('phase.define', {'id': 'future', 'required_checklist_items': []}, affects=[])
    source = trial.turn('mvp_feedback', 'mvp-2-request')
    trial.update('requirement.add', {'item': extraction('future_feature', source.read_text(), True, 'Future unimplemented requirement'),
        'check': {'risk': 'low'}, 'phase': 'future', 'reason': 'Future scope is explicit'}, source=source, affects=[])
    denied = managed.gate_action(trial.root, 'completion', phase='baseline')
    ensure(not denied['ready'] and any('samples' in error for error in denied['errors']), 'Missing current requirement did not refuse completion')
    report = trial.directory / 'progress.md'
    report.write_text('# Current progress\n\nThe current CPU requirements are unverified. The future feature is also unverified. No phase is complete.\n')
    trial.update('phase.review', {'id': 'baseline', 'status': 'pass', 'evidence': [str(report)]})
    ensure(not managed.gate_action(trial.root, 'completion', phase='baseline')['ready'], 'A report/review pass closed missing technical evidence')
    trial.check(trial.ids)
    ready = managed.gate_action(trial.root, 'completion', phase='baseline')
    ensure(ready['ready'], 'Future work incorrectly blocks the current phase')
    ensure(not managed.gate_action(trial.root, 'completion', phase='future')['ready'], 'Unimplemented future phase completed')
    ensure(all(value['status'] == 'pending' for value in ready['user_acceptance'].values()), 'Completion fabricated user acceptance')
    trial.note('phase completion is separate from progress and acceptance', denied=denied, ready=ready,
               progress_artifact=str(report), future=trial.record()['phases']['future'])
    return trial.observations


IMPLEMENTATIONS = {key: globals()[key.lower().replace('-', '')] for key in CASES}


def run_cases(output, cases, *, manifest=None, trusted=None):
    output = Path(output).resolve()
    ensure(not output.is_relative_to(REPO), 'Acceptance artifacts must be outside the checkout')
    output.mkdir(parents=True, exist_ok=False)
    acceptance = load(FIXTURES / 'oracle/acceptance.json')
    criteria = {case['id']: case for case in acceptance['criteria']}
    ensure(set(CASES) <= criteria.keys(), 'Frozen acceptance case was removed')
    results = []
    for case in cases:
        try:
            observations = IMPLEMENTATIONS[case](output / case, manifest=manifest, trusted=trusted)
            results.append({'case': case, 'passed': True, 'expected': criteria[case]['expected'], 'observations': observations})
        except Exception as exc:
            results.append({'case': case, 'passed': False, 'expected': criteria[case]['expected'],
                            'error': str(exc), 'traceback': traceback.format_exc()})
        save(output / 'results.json', results)
    summary = {'kind': 'candidate_mechanism_acceptance', 'passed': all(case['passed'] for case in results),
               'candidate_evaluated': True, 'cases': results, 'artifacts': str(output), 'external_receipts_required': EXTERNAL,
               'limits': 'These deterministic mechanisms do not establish natural Agent discovery, host loading, writing quality, PPO learning or real infrastructure readiness.'}
    save(output / 'summary.json', summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--trusted-sha256')
    args = parser.parse_args(argv)
    try:
        # A verifier may run repeatedly with the same argv. Preserve previous
        # evidence instead of overwriting it or failing solely because it exists.
        output = args.output / ('run-' + uuid.uuid4().hex) if args.output.exists() else args.output
        result = run_cases(output, args.case or CASES, manifest=args.manifest, trusted=args.trusted_sha256)
    except Exception as exc:
        result = {'kind': 'candidate_mechanism_acceptance', 'passed': False, 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
