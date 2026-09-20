"""Executable positive/negative controls through the public CLI, no paid workloads."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from agent_workflow import runtime
from agent_workflow.contracts import digest, file_digest, load
from tests.workflow_support import ROOT, context, repository


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        evidence_root = os.environ.get('WORKFLOW_TEST_EVIDENCE')
        if evidence_root:
            self.path = Path(evidence_root) / self.id().split('.')[-1]
            self.path.mkdir(parents=True, exist_ok=False)
        else:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            self.path = Path(temp.name)
        self.repo = repository(self.path / 'repo')
        self.calls = 0

    def cli(self, *args, expected=0):
        self.calls += 1
        cmd = [sys.executable, '-m', 'agent_workflow.cli', *map(str, args)]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        runtime.write(self.path / f'call-{self.calls:03}.json', {'argv': cmd, 'returncode': proc.returncode,
                                                               'stdout': proc.stdout, 'stderr': proc.stderr})
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return json.loads(proc.stdout) if proc.stdout else None

    def initialize(self, name='algorithm', change=None):
        oracle, c = context(name)
        if change:
            change(c)
        query = self.path / (name + '-query.txt')
        query.write_text(oracle['query'])
        ctx = self.path / (name + '-context.json')
        runtime.write(ctx, c)
        result = self.cli('init', '--query', query, '--repo', self.repo, '--scenario', oracle['scenario'], '--context', ctx, '--mode', 'simulation', '--slug', name)
        root = Path(result['record'])
        self.assertEqual((root / 'request.txt').read_bytes(), query.read_bytes())
        self.assertEqual(load(root / 'checklist.yaml')['route']['modules'], oracle['modules'])
        return root

    def mutate(self, root, callback):
        data = load(root / 'checklist.yaml')
        callback(data)
        runtime.write(root / 'checklist.yaml', data)

    def check(self, root, expected=0, item=None):
        args = ['check', '--record', root, '--phase', 'agent']
        if item:
            args += ['--item', item]
        return self.cli(*args, expected=expected)

    def gate(self, root, expected=1, simulation=True):
        return self.cli('gate', '--record', root, '--action', 'formal-run', *(['--simulation'] if simulation else []), expected=expected)

    def authorized(self):
        def change(c):
            c.update(formal_run_policy='sandbox_allowed', run_class='short_smoke')
        root = self.initialize(change=change)
        self.check(root)
        self.approve(root)
        return root

    def approve(self, root):
        target = self.cli('target', '--record', root)
        source = self.path / 'simulated-human.txt'
        source.write_text('SIMULATION ONLY: confirm these fixture objects for the local sandbox gate test.')
        data = load(root / 'checklist.yaml')
        feedback = {'actor': 'simulated-human', 'confirmed_at': runtime.now(), 'source_quote': source.read_text(),
                    'source_path': str(source), 'source_sha256': file_digest(source),
                    'candidate_sha': target['target']['candidate_sha'], 'target_digest': target['target_digest'],
                    'choices': {c['id']: 'confirmed' for c in data['checklist'] if c['risk'] == 'high_risk'}}
        path = self.path / 'feedback.json'
        runtime.write(path, feedback)
        self.cli('approve', '--record', root, '--sha', feedback['candidate_sha'], '--feedback', path, '--simulation')

    def test_entrypoint_dirty_change_invalidates(self):
        root = self.authorized()
        # The protected entrypoint is independent of the check adapter scope.
        runner = self.repo / 'train.py'
        runner.write_text('print("first")\n')
        self.mutate(root, lambda x: x['formal_run'].update(command=[sys.executable, 'train.py']))
        self.check(root)
        self.approve(root)
        self.gate(root, expected=0)
        runner.write_text('print("different operation")\n')
        self.gate(root)

    def test_low_risk_entrypoint_change_invalidates(self):
        root = self.initialize('business')
        self.mutate(root, lambda x: (x['route'].update(primary='bug_fix', **{'class':'lightweight'}, facts={}),
                                    x['formal_run'].update(**{'class':'short_smoke'})))
        # Use a fresh low-risk request, without billing side effects.
        query = self.path / 'ordinary-query.txt'
        query.write_text('Fix a local number display')
        c = context('business')[1]
        c.update(facts={}, formal_run_policy='sandbox_allowed', run_class='short_smoke', command=[sys.executable, 'run_task.py'])
        c['items'][0].update(source_quote=query.read_text(), meaning='Display fixture balance')
        c['checks']['REFUND-001'].update(risk='low', review_scope={'must_review':[], 'context_only':[]})
        (self.repo / 'run_task.py').write_text('print("first")\n')
        ctx = self.path / 'ordinary-context.json'
        runtime.write(ctx, c)
        root = Path(self.cli('init', '--query', query, '--repo', self.repo, '--scenario', 'bug_fix', '--context', ctx, '--mode', 'simulation')['record'])
        self.check(root)
        self.gate(root, expected=0)
        (self.repo / 'run_task.py').write_text('print("changed")\n')
        self.gate(root)

    def test_empty_binding_key_rejected(self):
        root = self.initialize()
        self.mutate(root, lambda x: x['protocols'][0]['binding'].update(config_key=''))
        self.check(root, expected=1)

    def test_missing_binding_readback_rejected(self):
        root = self.initialize()
        file = self.repo / 'consumer.py'
        file.write_text(file.read_text().replace("'_bindings'", "'_unused'"))
        self.check(root, expected=1)

    def test_revision_only_invalidates_affected_item(self):
        root = self.authorized()
        original = load(root / 'checklist.yaml')
        source = self.path / 'new-query.txt'
        source.write_text('K 改为每来源 8；预算另审，不启动正式训练。')
        rev = self.path / 'revision.json'
        runtime.write(rev, {'source_path': str(source), 'source_quote': source.read_text(),
                            'updates': [{'protocol_id': 'K', 'expected': {'value': {'bare': 8, 'privileged': 8}, 'unit': 'samples_per_source'}, 'meaning': 'Eight samples per enabled source.'}]})
        self.cli('revise', '--record', root, '--revision', rev)
        data = load(root / 'checklist.yaml')
        self.assertEqual(data['checklist'][0]['agent_status'], 'needs_recheck')
        self.assertEqual(data['checklist'][1]['human_status'], 'confirmed')
        self.assertEqual(data['checklist'][1]['evidence'], original['checklist'][1]['evidence'])
        runtime.write(self.repo / 'override.json', {'samples_per_source': 8})
        self.check(root, item='K-001')
        self.gate(root)  # budget/authorization remains pending

    def test_check_rejects_deleted_readback(self):
        root = self.initialize()
        self.check(root)
        data = load(root / 'checklist.yaml')
        (root / data['checklist'][0]['evidence']['paths'][0]).unlink()
        self.check(root, expected=1)

    def test_protocol_view_is_derived(self):
        root = self.initialize(change=lambda c: c.update(protocol_view=True))
        self.assertIn('samples_per_source', (root / 'protocol.md').read_text())
        self.check(root)
        self.assertIn('checked', (root / 'protocol.md').read_text())

    def test_wrong_parameter_alias_rejected(self):
        root = self.initialize()
        self.mutate(root, lambda x: x['protocols'][1]['binding'].update(config_key='context_window', definition={'path':'config.json','line':1,'symbol':'context_window'}))
        self.check(root, expected=1)

    def test_static_evidence_is_observation_not_expected_echo(self):
        query = self.path / 'static-query.txt'
        query.write_text('Confirm the local label exists')
        c = context('office')[1]
        c['items'][0].update(source_quote=query.read_text(), normalized_value=True)
        c['checks'] = {'CONTENT-001': {'risk':'low', 'verifier': {'method':'static_anchor', 'watched_paths':['refund.py'],
                         'anchors':[{'path':'refund.py','line':2,'symbol':'def refund'}]}, 'review_scope':{'must_review':[], 'context_only':[]}}}
        ctx = self.path / 'static-context.json'
        runtime.write(ctx,c)
        root = Path(self.cli('init','--query',query,'--repo',self.repo,'--scenario','office','--context',ctx,'--mode','simulation')['record'])
        self.check(root)
        self.assertEqual(load(root/'checklist.yaml')['checklist'][0]['evidence']['level'],'static')
        (self.repo/'refund.py').write_text('label absent\n')
        self.check(root,expected=1)

    def test_s02_help_and_missing_arguments(self):
        p = subprocess.run([sys.executable, '-m', 'agent_workflow.cli', '--help'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.cli('init', expected=2)

    def test_s03_s05_algorithm_execution(self):
        root = self.initialize()
        self.assertRegex(root.name, r'^\d{8}T\d{6}Z-algorithm-[a-f0-9]+$')
        self.check(root)
        data = load(root / 'checklist.yaml')
        self.assertTrue(all(c['agent_status'] == 'checked' for c in data['checklist']))
        self.assertTrue(all(c['evidence']['level'] == 'simulated' for c in data['checklist']))
        self.assertTrue((root / 'reviews/human-review.md').is_file())
        self.gate(root)

    def test_five_queries(self):
        for name in ('algorithm', 'infra', 'business', 'learning', 'office'):
            root = self.initialize(name)
            data = load(root / 'checklist.yaml')
            if name in {'algorithm', 'infra', 'business'}:
                self.check(root)
            else:
                self.assertNotIn('cleaner', data['route']['modules'])
                self.assertTrue(all(c['evidence']['level'] == 'none' for c in data['checklist']))

    def test_s04_schema_negative_controls(self):
        root = self.initialize()
        original = load(root / 'checklist.yaml')
        mutations = [lambda x: x['checklist'].pop(),
                     lambda x: x['checklist'][0].pop('source'),
                     lambda x: x['checklist'][0].pop('binding_ref'),
                     lambda x: x['checklist'][0].pop('verifier'),
                     lambda x: x['checklist'][0].pop('evidence'),
                     lambda x: x['checklist'][0].pop('review_scope'),
                     lambda x: x['checklist'][0].update(agent_status='pending'),
                     lambda x: x['checklist'][0].update(requirement_ref='missing'),
                     lambda x: x['checklist'].append(copy.deepcopy(x['checklist'][0]))]
        for mutation in mutations:
            data = copy.deepcopy(original)
            mutation(data)
            runtime.write(root / 'checklist.yaml', data)
            self.cli('validate', '--record', root, expected=1)
        runtime.write(root / 'checklist.yaml', original)
        self.cli('validate', '--record', root)

    def test_unused_same_name_field(self):
        root = self.initialize()
        file = self.repo / 'consumer.py'
        lines = file.read_text().splitlines()
        lines[3] = lines[3].replace("range(cfg['samples_per_source'])", "range(1)") + "  # cfg['samples_per_source'] remains unused"
        file.write_text('\n'.join(lines) + '\n')
        self.check(root, expected=1)
        self.assertIn('observed', load(root / 'checklist.yaml')['checklist'][0]['invalidated_by'][-1])

    def test_launcher_overrides_correct_config(self):
        root = self.initialize()
        runtime.write(self.repo / 'override.json', {'samples_per_source': 1})
        self.check(root, expected=1)
        runtime.write(self.repo / 'override.json', {})
        self.check(root, item='K-001')
        self.assertEqual(load(root / 'checklist.yaml')['checklist'][0]['agent_status'], 'checked')

    def test_stale_consumer_anchor(self):
        root = self.initialize()
        file = self.repo / 'consumer.py'
        file.write_text(file.read_text().replace("cfg['samples_per_source']", "cfg.get('samples_per_source')"))
        self.check(root, expected=1)
        self.mutate(root, lambda x: x['protocols'][0]['binding'].update(consumer_symbol="cfg.get('samples_per_source')", consumer={'path': 'consumer.py', 'line': 4, 'symbol': "cfg.get('samples_per_source')"}))
        self.check(root, item='K-001')

    def test_ambiguous_8k(self):
        oracle, c = context('algorithm')
        query = self.path / 'ambiguous.txt'
        query.write_text('训练回答 8K')
        c['items'] = [dict(c['items'][1], source_quote='8K', normalized_value=None, confidence=0.5,
                           blocking_question='Does 8K mean output limit or total context?', semantic_candidates=['output_limit', 'context_window'])]
        c['checks'] = {'RESPONSE-001': c['checks']['RESPONSE-001']}
        path = self.path / 'ambiguous.json'
        runtime.write(path, c)
        root = Path(self.cli('init', '--query', query, '--repo', self.repo, '--scenario', 'algorithm', '--context', path, '--mode', 'simulation')['record'])
        self.check(root, expected=1)
        self.gate(root)
        self.assertIsNone(load(root / 'checklist.yaml')['protocols'][0]['expected']['value'])

    def test_wrong_harbor_route(self):
        root = self.initialize('infra')
        self.mutate(root, lambda x: x['route'].update(primary='bug_fix', facts={}, modules=['intent-to-contract', 'cleaner']))
        self.cli('validate', '--record', root, expected=1)

    def test_missing_readback(self):
        root = self.authorized()
        data = load(root / 'checklist.yaml')
        (root / data['checklist'][0]['evidence']['paths'][0]).unlink()
        self.gate(root)

    def test_forged_human_status(self):
        root = self.initialize(change=lambda c: c.update(formal_run_policy='sandbox_allowed', run_class='short_smoke'))
        self.check(root)
        self.mutate(root, lambda x: x['checklist'][0].update(human_status='confirmed'))
        self.check(root, expected=1)
        self.gate(root)

    def test_s07_valid_simulated_approval(self):
        root = self.authorized()
        self.gate(root, expected=0)
        self.gate(root, simulation=False)

    def test_wrong_candidate_sha(self):
        root = self.authorized()
        self.mutate(root, lambda x: x['formal_run'].update(candidate_sha='0' * 40))
        self.gate(root)

    def test_missing_config_or_command(self):
        root = self.authorized()
        original = load(root / 'checklist.yaml')
        for key in ('config_digest', 'command_digest'):
            data = copy.deepcopy(original)
            data['formal_run'][key] = None
            runtime.write(root / 'checklist.yaml', data)
            self.gate(root)

    def test_changed_command_invalidates_authorization(self):
        root = self.authorized()
        self.mutate(root, lambda x: x['formal_run'].update(command=['echo', 'different']))
        self.gate(root)

    def test_changed_uncommitted_consumer(self):
        root = self.authorized()
        file = self.repo / 'consumer.py'
        file.write_text(file.read_text() + '\n# modified candidate\n')
        self.gate(root)
        changed = load(root / 'checklist.yaml')['checklist'][0]
        self.assertEqual(changed['agent_status'], 'needs_recheck')
        self.assertEqual(changed['human_status'], 'invalidated')

    def test_local_invalidation_keeps_unrelated_refund_evidence(self):
        root = self.initialize('business')
        self.check(root)
        before = load(root / 'checklist.yaml')['checklist'][0]['evidence']
        (self.repo / 'consumer.py').write_text('unrelated algorithm edit\n')
        record = runtime.read_record(root)
        runtime.verify_item(root, record, record['checklist'][0])
        self.assertEqual(before, record['checklist'][0]['evidence'])

    def test_human_pending_preserves_agent_checked(self):
        root = self.initialize(change=lambda c: c.update(formal_run_policy='sandbox_allowed', run_class='short_smoke'))
        self.check(root)
        self.gate(root)
        self.assertTrue(all(c['agent_status']=='checked' for c in load(root/'checklist.yaml')['checklist']))
        self.assertTrue(all(c['human_status']=='not_requested' for c in load(root/'checklist.yaml')['checklist']))

    def test_no_agent_check_no_approval(self):
        root = self.initialize(change=lambda c: c.update(formal_run_policy='sandbox_allowed', run_class='short_smoke'))
        self.gate(root)

    def test_cannot_launder_simulated_evidence(self):
        root = self.authorized()
        self.mutate(root, lambda x: x['checklist'][0]['evidence'].update(level='real'))
        self.gate(root)


if __name__ == '__main__':
    unittest.main()
