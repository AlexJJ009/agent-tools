"""Hook input provenance, action scoping, bounded stop and install portability."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow import hooks, managed, runtime
from agent_workflow.contracts import ContractError, file_digest
from tests.workflow_support import item

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('workflow_hook_installer', ROOT / 'scripts/install_agent_workflow_hooks.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class HookTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.state = self.base / 'hooks'
        (self.repo / 'worker.py').write_text('print("{\\"value\\": 1}")\n')
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        query = self.base / 'request.txt'
        query.write_text('SIMULATION: check the local value, then run the isolated example.')
        c = {'schema_version': 2, 'items': [item('VALUE', query.read_text(), 1, kind='acceptance')],
             'checks': {'VALUE-001': {'risk': 'low', 'review_scope': {'must_review': [], 'context_only': []},
                'verifier': {'method': 'command_json', 'argv': [sys.executable, 'worker.py'],
                             'observation_key': 'value', 'watched_paths': ['worker.py']}}}}
        self.root = runtime.init(query, self.repo, 'bug_fix', c, 'simulation')
        self.count = 0
        self.update('action.register', {'id': 'sample', 'phase': 'baseline', 'choice_ids': [],
                    'required_checklist_items': ['VALUE-001'], 'argv': [sys.executable, 'worker.py'],
                    'config_paths': [], 'command_paths': ['worker.py'], 'authorization_scope': 'isolated fixture'})
        hooks.bind('session-a', self.repo, self.root, state_root=self.state)

    def update(self, kind, payload, human=False, affects=None):
        self.count += 1
        source = self.base / f'event-{self.count}.txt'
        source.write_text('SIMULATION ONLY: ' + json.dumps(payload))
        record = runtime.read_record(self.root)
        return runtime.update(self.root, {'id': f'e{self.count}', 'base_revision': record['revision'],
            'type': kind, 'affects': affects if affects is not None else ['VALUE-001'], 'payload': payload,
            'source': {'kind': 'user' if human else 'proposal', 'actor': 'simulated-user' if human else 'agent',
                       'path': str(source), 'sha256': file_digest(source), 'quote': source.read_text()}})

    def event(self, name, **extra):
        return {'hook_event_name': name, 'session_id': 'session-a', 'turn_id': 'turn-a',
                'cwd': str(self.repo), **extra}

    def call(self, name, **extra):
        return hooks.process(self.event(name, **extra), state_root=self.state)

    def command(self):
        return shlex.join(['agent-workflow', 'execute', '--record', str(self.root), '--action', 'sample', '--simulation'])

    def ready(self):
        with runtime.locked(self.root):
            self.assertEqual(runtime.check(self.root), [])
        self.update('authorization.grant', {'id': 'grant', 'action_ids': ['sample'], 'scope': 'isolated fixture'}, human=True)

    def test_no_binding_or_another_session_does_not_initialize_or_capture(self):
        output = hooks.process(self.event('UserPromptSubmit', session_id='foreign', prompt='hello'), state_root=self.state)
        self.assertEqual(output, {})
        self.assertEqual(runtime.read_record(self.root)['pending_inputs'], {})
        self.assertEqual(self.call('UserPromptSubmit', agent_id='subagent', prompt='hello'), {})

    def test_resume_restores_only_explicit_binding(self):
        output = self.call('SessionStart', source='resume')['hookSpecificOutput']['additionalContext']
        self.assertIn(str(self.root), output)
        with self.assertRaises(ContractError):
            hooks.bind('session-a', self.base, self.root, state_root=self.state)

    def test_explicit_unbind_removes_only_session_binding(self):
        hooks.bind('session-b', self.repo, self.root, state_root=self.state)
        self.assertTrue(hooks.unbind('session-a', self.repo, state_root=self.state)['binding_removed'])
        self.assertEqual(self.call('SessionStart', source='resume'), {})
        other = hooks.process(self.event('SessionStart', session_id='session-b'), state_root=self.state)
        self.assertIn('hookSpecificOutput', other)
        self.assertTrue((self.root / 'checklist.yaml').is_file())

    def test_prompt_bytes_are_idempotent_and_agent_resolves_them(self):
        self.ready()
        prompt = 'Status only?\r\nKeep the existing scope.\n'
        self.call('UserPromptSubmit', prompt=prompt)
        first = runtime.read_record(self.root)
        self.call('UserPromptSubmit', prompt=prompt)
        record = runtime.read_record(self.root)
        self.assertEqual(record['revision'], first['revision'])
        self.assertEqual(len(record['pending_inputs']), 1)
        pending_id = next(iter(record['pending_inputs']))
        self.assertEqual((self.root / 'hook-inputs' / (pending_id + '.txt')).read_bytes(), prompt.encode())
        denied = self.call('PreToolUse', tool_name='Bash', tool_use_id='blocked', tool_input={'command': self.command()})
        self.assertEqual(denied['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(self.call('PreToolUse', tool_name='Bash', tool_input={'command': 'cat README.md'}), {})
        self.update('input.resolve', {'id': pending_id, 'disposition': 'no_contract_change', 'reason': 'Status-only request; no requirements changed.'})
        self.assertEqual(self.call('PreToolUse', tool_name='Bash', tool_use_id='allowed', tool_input={'command': self.command()}), {})

    def test_raw_workload_requires_entry_and_post_result_does_not_accept(self):
        self.ready()
        output = self.call('PreToolUse', tool_name='Bash', tool_use_id='raw',
                           tool_input={'command': shlex.join([sys.executable, 'worker.py'])})
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        command = {'command': self.command()}
        self.call('PreToolUse', tool_name='Bash', tool_use_id='entry', tool_input=command)
        output = self.call('PostToolUse', tool_name='Bash', tool_use_id='entry', tool_input=command,
                           tool_response={'exit_code': 0, 'stdout': '{"value":1}'})
        self.assertIn('Observed tool result', output['hookSpecificOutput']['additionalContext'])
        record = runtime.read_record(self.root)
        self.assertEqual(record['checklist'][0]['result_acceptance']['status'], 'pending')
        observations = list((self.root / 'evidence').glob('*-hook-post-tool.json'))
        self.assertEqual(len(observations), 1)
        self.assertEqual(json.loads(observations[0].read_text())['detail']['tool_use_id'], 'entry')
        self.assertEqual(self.call('PostToolUse', tool_name='Bash', tool_use_id='entry', tool_input=command), {})

    def test_stop_is_opt_in_and_bounded_not_project_completion(self):
        self.assertEqual(self.call('Stop'), {})
        hooks.bind('session-a', self.repo, self.root, state_root=self.state, on_stop=True)
        self.assertEqual(self.call('Stop')['decision'], 'block')
        second = self.call('Stop', stop_hook_active=True)
        self.assertIn('unmet', second['systemMessage'])
        self.assertEqual(self.call('Stop'), {})
        self.assertEqual(runtime.read_record(self.root)['checklist'][0]['agent_status'], 'unverified')

    def test_bad_known_state_denies_entry_but_unrelated_read_continues(self):
        (self.root / 'checklist.yaml').write_text('{}')
        output = self.call('PreToolUse', tool_name='Bash', tool_input={'command': self.command()})
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        output = self.call('PreToolUse', tool_name='Bash', tool_input={'command': 'cat README.md'})
        self.assertNotIn('hookSpecificOutput', output)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.source = self.base / 'source'
        shutil.copytree(ROOT / 'agent_workflow', self.source / 'agent_workflow', ignore=shutil.ignore_patterns('__pycache__'))
        self.package = installer.runtime_target(self.home) / 'agent_workflow'
        shutil.copytree(self.source / 'agent_workflow', self.package)
        self.path = self.home / '.codex/hooks.json'
        self.path.parent.mkdir()
        self.foreign = {'hooks': [{'type': 'command', 'command': 'echo foreign', 'statusMessage': 'foreign'}]}
        self.path.write_text(json.dumps({'description': 'kept', 'hooks': {'PreToolUse': [self.foreign]}}))

    def operation(self, op='install'):
        with patch.object(installer, 'target_guard') as guard:
            result = installer.operate(self.home, op)
            self.assertEqual(guard.call_count, int(op != 'check'))
            return result

    def test_guard_rejection_writes_nothing(self):
        before = self.path.read_bytes()
        with patch.object(installer, 'target_guard', side_effect=ValueError('guard rejected')):
            with self.assertRaises(ValueError):
                installer.operate(self.home)
        self.assertEqual(self.path.read_bytes(), before)

    def test_merge_is_idempotent_and_remove_preserves_foreign(self):
        result = self.operation()
        self.assertEqual(result['trust_status'], 'not_checked_by_installer')
        self.assertEqual(result['groups_changed'], 5)
        before = self.path.read_bytes()
        self.operation()
        self.assertEqual(self.path.read_bytes(), before)
        self.operation('check')
        self.operation('remove')
        self.assertEqual(json.loads(self.path.read_text()), {'description': 'kept', 'hooks': {'PreToolUse': [self.foreign]}})

    def test_installed_command_runs_when_source_directory_is_gone(self):
        self.operation()
        self.source.rename(self.base / 'source-moved')
        self.assertFalse(self.source.exists())
        unrelated = self.base / 'unrelated-workspace'
        unrelated.mkdir()
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        command = installer.hook_command(self.home)
        proc = subprocess.run(command, shell=True, cwd=unrelated, input='{"hook_event_name":"SessionStart","session_id":"unbound","cwd":"/tmp"}',
                              capture_output=True, text=True, env=environment)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {})
        self.assertNotIn(str(ROOT), command)

    def test_malformed_or_external_target_is_preserved(self):
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):
            self.operation()
        self.assertEqual(self.path.read_text(), '{broken')
        self.path.unlink()
        foreign = self.base / 'outside.json'
        foreign.write_text('{}')
        self.path.symlink_to(foreign)
        with self.assertRaises(ValueError):
            self.operation()
        self.assertEqual(foreign.read_text(), '{}')


if __name__ == '__main__':
    unittest.main()
