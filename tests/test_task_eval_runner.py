"""Runner failure/isolation regressions with dummy credentials and a fake model CLI."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'scripts/evaluate_task_runtime.py'


class TaskEvaluationRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='task-eval-review-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.live = self.root / 'dummy-profile'
        self.live.mkdir()
        (self.live / 'auth.json').write_text('{"dummy":"not-a-real-credential"}')
        (self.live / 'config.toml').write_text(
            'model="dummy-model"\nmodel_provider="custom"\n'
            '[model_providers.custom]\nbase_url="http://127.0.0.1:1"\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.marker = self.root / 'fake-model-calls.jsonl'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        FAKE_MODEL_MARKER=str(self.marker),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        fake = self.bin / 'codex'
        fake.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
assert all(k not in os.environ for k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'OPENAI_API_KEY'))
assert sys.argv[sys.argv.index('--sandbox') + 1] == 'read-only'
with open(os.environ['FAKE_MODEL_MARKER'], 'a') as stream:
    stream.write(json.dumps(sys.argv) + '\\n')
pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text(json.dumps({
    'pending_ids': ['AC-1', 'AC-2'], 'exclusions': ['network', 'GPU', 'queue'],
    'user_accepted': False, 'next_step': 'Implement first; skip tests.'}))
print(json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1, 'output_tokens': 1}}))
''')
        fake.chmod(0o755)

    def run_runner(self, output='output with spaces'):
        out = self.root / output
        result = subprocess.run(
            [sys.executable, str(RUNNER), '--native', '--output', str(out),
             '--codex-home', str(self.live)], env=self.env,
            capture_output=True, text=True, timeout=30)
        return result, out

    def assert_credentials_removed(self, out):
        for profile in out.glob('h03-*/home/.codex'):
            self.assertFalse((profile / 'auth.json').exists())
            self.assertFalse((profile / 'config.toml').exists())
        self.assertEqual((self.live / 'auth.json').read_text(),
                         '{"dummy":"not-a-real-credential"}')

    def test_setup_failure_cleans_copied_credentials_before_model_launch(self):
        fake_git = self.bin / 'git'
        fake_git.write_text('#!/bin/sh\nexit 17\n')
        fake_git.chmod(0o755)
        result, out = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.marker.exists())
        self.assert_credentials_removed(out)

    def test_all_groups_isolate_git_state_and_do_not_certify_semantic_answer(self):
        original = self.root / 'protected-repository'
        git = shutil.which('git')
        subprocess.run([git, 'init', '-q', str(original)], env=self.env, check=True)
        (original / 'original.txt').write_text('Original project bytes.\n')
        subprocess.run([git, '-C', str(original), 'add', '.'], env=self.env, check=True)
        index = original / '.git/index'
        before = index.read_bytes()
        self.env.update(GIT_DIR=str(original / '.git'), GIT_WORK_TREE=str(original),
                        GIT_INDEX_FILE=str(index), OPENAI_API_KEY='dummy-must-not-propagate')
        result, out = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(index.read_bytes(), before)
        self.assertEqual((original / 'original.txt').read_text(), 'Original project bytes.\n')
        results = json.loads((out / 'native-results.json').read_text())
        self.assertEqual([r['group'] for r in results], ['A', 'B', 'B', 'A'])
        self.assertEqual(len(self.marker.read_text().splitlines()), 4)
        for row in results:
            self.assertEqual(row['exit_code'], 0)
            self.assertTrue(row['mechanical_pass'])
            self.assertTrue(row['semantic_review'].startswith('pending:'))
            self.assertNotIn('oracle_pass', row)
            if row['group'] == 'B':
                self.assertIn('task_store.py', row['tool_hashes'])
        self.assert_credentials_removed(out)


if __name__ == '__main__':
    unittest.main()
