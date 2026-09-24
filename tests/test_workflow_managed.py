"""Observable execution controls for scoped authority and frozen inputs."""
import json
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow import managed, runtime
from agent_workflow.contracts import file_digest
from tests.workflow_support import item


class ManagedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.marker = self.base / 'executed.json'
        (self.repo / 'config.json').write_text('{"value": 1}\n')
        (self.repo / 'worker.py').write_text(
            'import json,sys\nfrom pathlib import Path\n'
            'data=json.loads(Path("config.json").read_text())\n'
            'if len(sys.argv)>1: Path(sys.argv[1]).write_text(json.dumps(data))\n'
            'print(json.dumps(data))\n')
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        query = self.base / 'request.txt'
        query.write_text('Check the actual local value and run the sandbox within this scope.')
        c = {'schema_version': 2, 'items': [item('VALUE', query.read_text(), 1, kind='acceptance')],
             'checks': {'VALUE-001': {'risk': 'low', 'review_scope': {'must_review': [], 'context_only': []},
                'verifier': {'method': 'command_json', 'argv': [sys.executable, 'worker.py'],
                             'observation_key': 'value', 'watched_paths': ['worker.py', 'config.json']}}}}
        self.root = runtime.init(query, self.repo, 'bug_fix', c, 'simulation')
        self.count = 0
        self.event('action.register', {'action': {'id': 'sample', 'phase': 'baseline', 'choice_ids': [],
                   'required_checklist_items': ['VALUE-001'], 'argv': [sys.executable, 'worker.py', str(self.marker)],
                   'command_paths': ['worker.py'], 'config_paths': ['config.json'],
                   'authorization_scope': {'purpose': 'isolated sample', 'budget': 1}}})

    def event(self, kind, payload, human=False, affects=None):
        self.count += 1
        source = self.base / f'source-{self.count}.txt'
        source.write_text('SIMULATION ONLY: ' + json.dumps(payload))
        with runtime.locked(self.root):
            record = runtime.read_record(self.root)
            return runtime.update(self.root, {'id': f'e{self.count}', 'base_revision': record['revision'],
                'type': kind, 'affects': affects if affects is not None else ['VALUE-001'], 'payload': payload,
                'source': {'kind': 'user' if human else 'proposal', 'actor': 'simulated-user' if human else 'agent',
                           'path': str(source), 'sha256': file_digest(source), 'quote': source.read_text()}})

    def verify(self):
        with runtime.locked(self.root):
            self.assertEqual(runtime.check(self.root), [])

    def authorize(self):
        self.event('authorization.grant', {'id': 'grant', 'action_ids': ['sample'],
                   'scope': {'purpose': 'isolated sample', 'budget': 1}}, human=True)

    def gate(self):
        return managed.gate_action(self.root, 'sample', simulation=True)

    def test_missing_conditions_have_no_effect_then_same_entry_executes(self):
        denied = managed.execute(self.root, 'sample', simulation=True)
        self.assertFalse(denied['ready'])
        self.assertFalse(self.marker.exists())
        self.verify()
        self.assertFalse(self.gate()['ready'])
        self.authorize()
        result = managed.execute(self.root, 'sample', simulation=True)
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(json.loads(self.marker.read_text()), {'value': 1})
        self.assertEqual(runtime.read_record(self.root)['jobs']['sample']['status'], 'completed')
        self.assertEqual(runtime.read_record(self.root)['checklist'][0]['result_acceptance']['status'], 'pending')

    def test_ordinary_repair_rechecks_evidence_without_renewing_authority(self):
        self.verify()
        self.authorize()
        worker = self.repo / 'worker.py'
        worker.write_text(worker.read_text() + '# Equivalent implementation repair\n')
        self.assertFalse(self.gate()['ready'])
        self.verify()
        self.assertTrue(self.gate()['ready'])
        self.assertEqual(len(runtime.read_record(self.root)['execution_authority']), 1)

    def test_queue_rechecks_the_input_identity(self):
        self.verify()
        self.authorize()
        queued = self.gate()['input_digest']
        (self.repo / 'config.json').write_text('{"value": 1, "label": "new input"}\n')
        self.verify()
        denied = managed.execute(self.root, 'sample', simulation=True, expected_digest=queued)
        self.assertFalse(denied['ready'])
        self.assertFalse(self.marker.exists())
        self.assertEqual(managed.execute(self.root, 'sample', simulation=True)['returncode'], 0)

    def test_execution_consumes_snapshot_despite_later_source_mutation(self):
        self.verify()
        self.authorize()
        run = subprocess.run
        def race(argv, **kwargs):
            if argv[1:] and argv[1] == 'worker.py':
                (self.repo / 'config.json').write_text('{"value": 99}\n')
            return run(argv, **kwargs)
        with patch('agent_workflow.managed.subprocess.run', side_effect=race):
            result = managed.execute(self.root, 'sample', simulation=True)
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(json.loads(self.marker.read_text())['value'], 1)
        self.assertFalse(self.gate()['ready'])

    def test_joined_absolute_config_argument_consumes_snapshot(self):
        worker = self.repo / 'joined.py'
        worker.write_text('import json,sys\nfrom pathlib import Path\n'
                         'p=sys.argv[1].split("=",1)[1]\n'
                         'Path(sys.argv[2]).write_text(Path(p).read_text())\n')
        action = dict(runtime.read_record(self.root)['actions']['sample'])
        action.update(id='joined', argv=[sys.executable, 'joined.py',
                      '--config=' + str(self.repo / 'config.json'), str(self.marker)],
                      command_paths=['joined.py'])
        self.event('action.register', {'action': action})
        self.verify()
        self.event('authorization.grant', {'id': 'joined-grant', 'action_ids': ['joined'],
                   'scope': action['authorization_scope']}, human=True)
        run = subprocess.run
        def race(argv, **kwargs):
            if len(argv) > 1 and argv[1] == 'joined.py':
                (self.repo / 'config.json').write_text('{"value": 99}\n')
            return run(argv, **kwargs)
        with patch('agent_workflow.managed.subprocess.run', side_effect=race):
            result = managed.execute(self.root, 'joined', simulation=True)
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(json.loads(self.marker.read_text())['value'], 1)

    def test_schema2_formal_run_cannot_fall_back_to_legacy_gate(self):
        from agent_workflow import cli
        self.verify()
        self.event('choice.propose', {'id': 'method', 'question': 'Which method?',
                   'affects': ['VALUE-001'], 'required_scope': 'method'})
        self.event('input.record', {'id': 'unclassified'}, human=True)
        with patch.object(runtime, 'gate', return_value=[]) as legacy, contextlib.redirect_stdout(io.StringIO()) as output:
            code = cli.main(['gate', '--record', str(self.root), '--action', 'formal-run', '--simulation'])
        self.assertNotEqual(code, 0, output.getvalue())
        legacy.assert_not_called()

    def test_scope_feedback_does_not_cover_another_choice_and_demo_can_delegate(self):
        self.verify()
        self.authorize()
        for cid in ['critic', 'reward']:
            self.event('choice.propose', {'id': cid, 'question': f'Which {cid}?',
                       'affects': ['VALUE-001'], 'required_scope': cid})
            self.event('understanding.explain', {'choice_id': cid, 'scope': cid, 'explanation': 'Explain alternatives and effect.'})
        self.event('choice.resolve', {'choice_id': 'critic', 'value': 'reference', 'rationale': 'Comparable baseline'}, human=True)
        self.event('understanding.feedback', {'choice_id': 'critic', 'scope': 'critic', 'kind': 'reconstruction'}, human=True)
        denied = self.gate()
        self.assertFalse(denied['ready'])
        self.assertTrue(any('reward' in e for e in denied['errors']))
        self.event('delegation.grant', {'id': 'demo', 'choice_ids': ['reward'], 'scope': 'reward'}, human=True)
        self.assertTrue(self.gate()['ready'])

    def test_pending_input_blocks_action_until_classified(self):
        self.verify()
        self.authorize()
        self.event('input.record', {'id': 'new-message'}, human=True)
        self.assertFalse(self.gate()['ready'])
        self.event('input.resolve', {'id': 'new-message', 'disposition': 'no_contract_change', 'reason': 'User requested status only.'})
        self.assertTrue(self.gate()['ready'])

    def test_later_user_question_blocks_previously_delegated_choice(self):
        self.verify()
        self.authorize()
        self.event('choice.propose', {'id': 'reward', 'question': 'Which reward?',
                   'affects': ['VALUE-001'], 'required_scope': 'reward'})
        self.event('delegation.grant', {'id': 'demo', 'choice_ids': ['reward'], 'scope': 'reward'}, human=True)
        self.assertTrue(self.gate()['ready'])
        self.event('understanding.feedback', {'choice_id': 'reward', 'scope': 'reward', 'kind': 'question'}, human=True)
        self.assertFalse(self.gate()['ready'])
        question = runtime.read_record(self.root)['choices'][0]['understanding']['open_questions'][0]['id']
        self.event('understanding.feedback', {'choice_id': 'reward', 'scope': 'reward',
                   'kind': 'decision', 'resolves': [question]}, human=True)
        self.assertTrue(self.gate()['ready'])

    def test_completion_without_training_command_keeps_user_acceptance_pending(self):
        before = managed.gate_action(self.root, 'completion', phase='baseline')
        self.assertFalse(before['ready'])
        self.verify()
        after = managed.gate_action(self.root, 'completion', phase='baseline')
        self.assertTrue(after['ready'])
        self.assertEqual(after['user_acceptance']['VALUE-001']['status'], 'pending')

    def test_simulated_authority_cannot_run_as_real(self):
        self.verify()
        self.authorize()
        self.assertFalse(managed.execute(self.root, 'sample')['ready'])
        self.assertFalse(self.marker.exists())

    def test_code_source_vocabulary_does_not_reclassify_the_user_request(self):
        source = self.base / 'code-notes.txt'
        source.write_text('A reference to a launcher or billing is background code documentation.')
        query = self.base / 'ordinary.txt'
        query.write_text('Check the local number display.')
        requirement = item('CODE', source.read_text(), True, kind='acceptance')
        requirement.update(authority='project_fact', source={'kind': 'code', 'actor': 'agent',
            'path': str(source), 'sha256': file_digest(source), 'quote': source.read_text()})
        record = runtime.init(query, self.repo, 'bug_fix', {'schema_version': 2, 'items': [requirement]}, 'simulation')
        self.assertEqual(runtime.read_record(record)['route']['class'], 'lightweight')


if __name__ == '__main__':
    unittest.main()
