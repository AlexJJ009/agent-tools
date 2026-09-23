"""State invariants, conflict controls and recoverable views over real fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow import runtime
from agent_workflow.contracts import ContractError, file_digest, load
from tests.workflow_support import context, item, repository


class StateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.repo = repository(self.path / 'repo')
        self.seq = 0
        self.source = self.path / 'user.txt'
        self.source.write_text('Keep critic initialization. I understand initialization only. Delegate the demo. Accept K only. Change K to eight.\n')

    def initialize(self, schema=2):
        oracle, config = context('algorithm')
        config['schema_version'] = schema
        query = self.path / 'query.txt'
        query.write_text(oracle['query'])
        return runtime.init(query, self.repo, 'algorithm', config, 'simulation')

    def event(self, root, kind, payload, affects=None, source_kind='user'):
        self.seq += 1
        return {'id': f'event-{self.seq}', 'base_revision': load(root / 'checklist.yaml').get('revision', 0),
                'type': kind, 'source': {'kind': source_kind, 'actor': 'Actual User' if source_kind == 'user' else 'Agent',
                    'path': str(self.source), 'quote': self.source.read_text().strip(), 'sha256': file_digest(self.source)},
                'affects': ['K-001'] if affects is None else affects, 'payload': payload}

    def update(self, root, kind, payload, **kwargs):
        return runtime.update(root, self.event(root, kind, payload, **kwargs))

    def choice(self, root, id='D1', affects=None):
        affects = affects or ['K-001']
        self.update(root, 'choice.propose', {'id': id, 'question': 'Which critic initialization?',
            'affects': affects, 'required_scope': 'Initialization'}, affects=affects, source_kind='proposal')

    def test_idempotent_retry_and_conflicting_content(self):
        root = self.initialize()
        event = self.event(root, 'input.record', {'id': 'prompt-1'})
        first = runtime.update(root, event)
        self.assertEqual(first['revision'], 1)
        self.assertTrue(runtime.update(root, event)['duplicate'])
        self.assertEqual(load(root / 'checklist.yaml')['revision'], 1)
        changed = deepcopy(event)
        changed['payload']['id'] = 'prompt-2'
        with self.assertRaisesRegex(ContractError, 'different content'):
            runtime.update(root, changed)
        stale = self.event(root, 'input.resolve', {'id': 'prompt-1', 'disposition': 'no_contract_change', 'reason': 'Status question'})
        stale['base_revision'] = 0
        with self.assertRaisesRegex(ContractError, 'revision conflict'):
            runtime.update(root, stale)
        self.assertFalse(load(root / 'checklist.yaml')['pending_inputs']['prompt-1']['resolved'])

    def test_source_replacement_during_copy_cannot_poison_record(self):
        root = self.initialize()
        event = self.event(root, 'input.record', {'id': 'race'})
        original = self.source.read_bytes()
        read_bytes = Path.read_bytes
        changed = False
        def race(path):
            nonlocal changed
            data = read_bytes(path)
            if path == self.source and not changed:
                changed = True
                self.source.write_bytes(data + b'Concurrent source change.\n')
            return data
        with patch.object(Path, 'read_bytes', race):
            runtime.update(root, event)
        self.assertTrue(changed)
        record = runtime.read_record(root)
        snapshot = root / record['events'][-1]['source']['path']
        self.assertEqual(snapshot.read_bytes(), original)

    def test_interrupted_view_write_recovers_from_canonical_commit(self):
        root = self.initialize()
        event = self.event(root, 'input.record', {'id': 'prompt-1'})
        with patch.object(runtime, 'refresh_views', side_effect=OSError('interrupted view')):
            result = runtime.update(root, event)
        self.assertEqual(result['revision'], 1)
        self.assertIn('interrupted', result['views_error'])
        self.assertTrue(runtime.update(root, event)['duplicate'])
        derived = load(root / 'events.json')
        canonical = load(root / 'checklist.yaml')
        self.assertEqual(derived['events'], canonical['events'])
        (root / 'task.md').unlink()
        runtime.refresh_views(root, canonical)
        self.assertIn('K-001', (root / 'task.md').read_text())

    def test_v1_migration_and_exact_rollback_export(self):
        root = self.initialize(schema=1)
        record = load(root / 'checklist.yaml')
        record['checklist'][0]['human_status'] = 'confirmed'
        runtime.write(root / 'checklist.yaml', record)
        original = (root / 'checklist.yaml').read_bytes()
        runtime.migrate(root)
        migrated = runtime.read_record(root)
        self.assertEqual(migrated['revision'], 1)
        self.assertEqual(migrated['checklist'][0]['human_status'], 'confirmed')
        self.assertEqual(migrated['checklist'][0]['result_acceptance']['status'], 'pending')
        self.assertEqual(migrated['choices'], [])
        self.assertEqual(migrated['delegations'], [])
        exported = self.path / 'rollback.json'
        runtime.rollback(root, exported)
        self.assertEqual(exported.read_bytes(), original)
        self.assertEqual(runtime.read_record(root)['schema_version'], 2)
        self.assertTrue(runtime.migrate(root)['already_migrated'])

    def test_sources_remain_verbatim_and_tampering_fails(self):
        root = self.initialize()
        event = self.event(root, 'input.record', {'id': 'prompt-1'})
        event['source']['quote'] = 'Invented authorization'
        with self.assertRaisesRegex(ContractError, 'verbatim'):
            runtime.update(root, event)
        event['source']['quote'] = self.source.read_text().strip()
        runtime.update(root, event)
        self.source.unlink()
        self.assertTrue(runtime.update(root, event)['duplicate'])
        canonical = runtime.read_record(root)
        (root / canonical['events'][0]['source']['path']).write_text('tampered')
        with self.assertRaisesRegex(ContractError, 'source changed'):
            runtime.read_record(root)

    def test_scoped_understanding_and_delegation_stay_distinct(self):
        root = self.initialize()
        self.choice(root)
        self.choice(root, id='D2', affects=['RESPONSE-001'])
        self.update(root, 'understanding.explain', {'choice_id': 'D1', 'scope': 'Initialization', 'explanation': 'Critic starts from reference weights.'}, source_kind='proposal')
        self.update(root, 'understanding.feedback', {'choice_id': 'D1', 'scope': 'Initialization', 'kind': 'self_report'})
        record = runtime.read_record(root)
        self.assertEqual(len(record['choices'][0]['understanding']['feedback_refs']), 1)
        self.assertEqual(record['choices'][1]['understanding']['feedback_refs'], [])
        self.assertIsNone(record['choices'][0]['resolution'])
        with self.assertRaisesRegex(ContractError, 'actual user'):
            self.update(root, 'understanding.feedback', {'choice_id': 'D1', 'scope': 'Initialization', 'kind': 'self_report'}, source_kind='proposal')
        self.update(root, 'delegation.grant', {'id': 'demo', 'choice_ids': ['D2'], 'scope': 'Response limits'}, affects=['RESPONSE-001'])
        record = runtime.read_record(root)
        self.assertEqual(record['choices'][1]['understanding']['feedback_refs'], [])
        self.assertEqual(record['delegations'][0]['choice_ids'], ['D2'])

    def test_status_is_cheap_local_and_does_not_reopen_choices(self):
        root = self.initialize()
        self.choice(root)
        self.update(root, 'choice.resolve', {'choice_id': 'D1', 'value': 'Reference', 'rationale': 'Maintain baseline'})
        self.assertEqual(runtime.check(root), [])
        prior = runtime.read_record(root)
        runtime.write(self.repo / 'override.json', {'samples_per_source': 2})
        with patch.object(runtime.subprocess, 'run', side_effect=AssertionError('status executed a verifier')), patch.object(runtime, 'git', side_effect=AssertionError('status ran git')):
            current = runtime.status(root)
        self.assertTrue(current['stale'])
        after = runtime.read_record(root)
        self.assertEqual(after['revision'], prior['revision'] + 1)
        self.assertEqual(after['choices'], prior['choices'])
        self.assertEqual(after['checklist'][0]['agent_status'], 'needs_recheck')
        second = runtime.status(root)
        self.assertEqual(second['revision'], after['revision'])

    def test_semantic_change_revokes_scoped_grants_and_preserves_other_choices(self):
        root = self.initialize()
        self.choice(root)
        self.choice(root, id='D2', affects=['RESPONSE-001'])
        self.update(root, 'delegation.grant', {'id': 'demo', 'choice_ids': ['D1'], 'scope': 'Initialization'})
        self.update(root, 'choice.resolve', {'choice_id': 'D1', 'value': 'Reference', 'rationale': 'Maintain baseline', 'delegation_id': 'demo'}, source_kind='proposal')
        self.update(root, 'choice.resolve', {'choice_id': 'D2', 'value': 8192, 'rationale': 'Requested length'}, affects=['RESPONSE-001'])
        self.update(root, 'requirements.revise', {'updates': [{'protocol_id': 'K', 'expected': {'value': {'bare': 8, 'privileged': 8}, 'unit': 'samples'}, 'meaning': 'Eight per source'}], 'reason': 'User changed standard'})
        record = runtime.read_record(root)
        self.assertTrue(record['delegations'][0]['revoked'])
        self.assertIsNone(record['choices'][0]['resolution'])
        self.assertEqual(record['choices'][1]['resolution']['value'], 8192)
        self.assertEqual(record['checklist'][1]['agent_status'], 'unverified')

    def test_result_feedback_is_per_item_and_future_phase_remains_separate(self):
        root = self.initialize()
        self.update(root, 'result.feedback', {'kind': 'acceptance', 'items': {'K-001': 'accepted'}})
        self.update(root, 'phase.define', {'id': 'next', 'required_checklist_items': []}, affects=[])
        self.update(root, 'result.feedback', {'kind': 'next_version', 'items': {'RESPONSE-001': 'pending'}, 'requirement': 'Larger output next time'}, affects=['RESPONSE-001'])
        record = runtime.read_record(root)
        self.assertEqual(record['checklist'][0]['result_acceptance']['status'], 'accepted')
        self.assertEqual(record['checklist'][1]['result_acceptance']['status'], 'pending')
        self.assertEqual(record['phases']['next']['required_checklist_items'], [])
        self.assertEqual(record['phase'], 'baseline')
        with self.assertRaisesRegex(ContractError, 'only result acceptance'):
            self.update(root, 'result.feedback', {'kind': 'next_version', 'items': {'K-001': 'accepted'}})

    def test_mvp_new_requirement_never_inherits_prior_acceptance(self):
        root = self.initialize()
        self.update(root, 'result.feedback', {'kind': 'acceptance', 'items': {'K-001': 'accepted'}})
        self.update(root, 'phase.define', {'id': 'mvp-2', 'required_checklist_items': []}, affects=[])
        self.source.write_text(self.source.read_text() + 'Next MVP should display the total of eight samples.\n')
        self.update(root, 'result.feedback', {'kind': 'next_version', 'items': {'K-001': 'pending'},
            'request': 'Add a visible total in the next version'})
        requirement = item('TOTAL', self.source.read_text().strip(), 8, kind='acceptance',
                           meaning='The next MVP displays the per-source sample total.')
        self.update(root, 'requirement.add', {'item': requirement, 'check': {'risk': 'low'},
            'phase': 'mvp-2', 'reason': 'Explicitly scoped next-version request'}, affects=[])
        record = runtime.read_record(root)
        original = next(c for c in record['checklist'] if c['id'] == 'K-001')
        addition = next(c for c in record['checklist'] if c['id'] == 'TOTAL-001')
        self.assertEqual(original['result_acceptance']['status'], 'accepted')
        self.assertEqual(addition['agent_status'], 'unverified')
        self.assertEqual(addition['result_acceptance'], {'status': 'pending', 'feedback_refs': []})
        self.assertEqual(record['phases']['mvp-2']['required_checklist_items'], ['TOTAL-001'])
        self.assertNotIn('TOTAL-001', record['phases']['baseline']['required_checklist_items'])
        with self.assertRaisesRegex(ContractError, 'omits changed items'):
            self.update(root, 'result.feedback', {'kind': 'acceptance', 'items': {'K-001': 'accepted', 'TOTAL-001': 'accepted'}})
        with self.assertRaisesRegex(ContractError, 'omits changed items'):
            self.update(root, 'result.feedback', {'kind': 'acceptance', 'items': {'*': 'accepted'}}, affects=[])
        self.assertEqual(next(c for c in runtime.read_record(root)['checklist'] if c['id'] == 'TOTAL-001')['result_acceptance']['status'], 'pending')

    def test_all_writers_advance_revision_and_reject_lost_updates(self):
        root = self.initialize()
        stale = runtime.read_record(root)
        runtime.check(root)
        self.assertEqual(runtime.read_record(root)['revision'], 1)
        with self.assertRaisesRegex(ContractError, 'revision conflict'):
            runtime.commit(root, stale, 'test', 'pass', {})
        runtime.gate(root, simulation=True)
        self.assertEqual(runtime.read_record(root)['revision'], 2)
        revision = self.path / 'revision.json'
        runtime.write(revision, {'source_path': str(self.source), 'source_quote': self.source.read_text().strip(), 'updates': [{'protocol_id': 'K', 'expected': {'value': {'bare': 8, 'privileged': 8}, 'unit': 'samples'}, 'meaning': 'Eight per source'}]})
        runtime.revise(root, revision)
        self.assertEqual(runtime.read_record(root)['revision'], 3)

    def test_verifier_configuration_cannot_claim_a_check(self):
        root = self.initialize()
        record = runtime.read_record(root)
        self.update(root, 'verifier.configure', {'item_id': 'K-001', 'verifier': record['checklist'][0]['verifier'], 'reason': 'Readback now configured', 'agent_status': 'checked'}, source_kind='proposal')
        self.assertEqual(runtime.read_record(root)['checklist'][0]['agent_status'], 'needs_recheck')
        self.assertEqual(runtime.check(root), [])
        self.assertEqual(runtime.read_record(root)['checklist'][0]['agent_status'], 'checked')
        brief = runtime.review_brief(root).read_text()
        self.assertIn('"bare": 4', brief)
        self.assertNotIn('Observation: `checked`', brief)

    def test_code_fact_extraction_does_not_impersonate_user(self):
        query = self.path / 'ordinary.txt'
        query.write_text('Inspect the local output default')
        code = self.repo / 'config.json'
        quote = code.read_text().strip()
        extracted = item('CODE', quote, True, kind='acceptance')
        extracted.update(authority='project_fact', source={'kind': 'code', 'actor': 'Agent', 'path': str(code), 'quote': quote, 'sha256': file_digest(code)})
        root = runtime.init(query, self.repo, 'bug_fix', {'schema_version': 2, 'items': [extracted]}, 'simulation')
        record = runtime.read_record(root)
        self.assertEqual(record['protocols'][0]['source']['kind'], 'code')
        self.assertEqual((root / 'request.txt').read_text(), query.read_text())
        self.assertEqual(record['checklist'][0]['risk'], 'low')
        self.assertEqual(record['checklist'][0]['participation'], 'unspecified')


if __name__ == '__main__':
    unittest.main()
