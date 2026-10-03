"""A CI command must not turn missing coverage or failed imports into green."""
import importlib.util
import io
from pathlib import Path
import tempfile
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/run_regression_tests.py'
spec = importlib.util.spec_from_file_location('regression_runner', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RegressionRunnerTests(unittest.TestCase):
    def test_empty_suite_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(runner.run_directory(Path(tmp), io.StringIO()), 1)

    def test_real_failure_and_import_error_fail_but_passing_case_succeeds(self):
        for name, body, code in (
            ('passing_probe', 'import unittest\nclass Probe(unittest.TestCase):\n def test_value(self): self.assertEqual(2 + 2, 4)\n', 0),
            ('failing_probe', 'import unittest\nclass Probe(unittest.TestCase):\n def test_value(self): self.assertEqual(2 + 2, 5)\n', 1),
            ('skipped_probe', 'import unittest\n@unittest.skip("unavailable")\nclass Probe(unittest.TestCase):\n def test_value(self): pass\n', 1),
            ('subskip_probe', 'import unittest\nclass Probe(unittest.TestCase):\n def test_value(self):\n  for i in range(2):\n   with self.subTest(i=i): self.skipTest("unavailable")\n', 1),
            ('mixed_probe', 'import unittest\nclass Probe(unittest.TestCase):\n def test_value(self):\n  with self.subTest(i=0): self.assertEqual(2+2,4)\n  with self.subTest(i=1): self.skipTest("unavailable")\n', 0),
            ('import_probe', 'raise ImportError("missing test dependency")\n', 1),
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)
                (path / f'test_{name}.py').write_text(body)
                self.assertEqual(runner.run_directory(path, io.StringIO()), code)


class ComponentSelectionTests(unittest.TestCase):
    def test_related_components_run_and_unrelated_platforms_do_not(self):
        cases = {
            'adapters/claude/native_hook.py': {'claude-adapter'},
            'scripts/install_claude.py': {'claude-adapter'},
            '.claude/skills/build-eval': {'claude-adapter'},
            'tests/test_claude_hooks.py': {'claude-adapter'},
            'tests/test_install_claude.py': {'claude-adapter'},
            '.agents/skills/build-eval/SKILL.md': {'project-evals'},
            'tests/test_project_eval_skills.py': {'project-evals'},
            'agent_workflow/task_store.py': {'task-runtime', 'workflow-records', 'installation'},
            'learning_workflow/runtime.py': {'learning'},
            'skills/work-report/scripts/report_tool.py': {'reports', 'report-integration'},
            'skills/work-report/tests/test_report_tool.py': {'reports'},
            'skills/work-report/references/writing-contract.md': {'reports', 'report-integration', 'learning', 'installation'},
            'skills/manage-worktrees/scripts/agent_wt.py': {'worktrees', 'installation'},
            'skills/codex-win11-patch-safety/scripts/patch_release.py': {'win11-patch', 'installation'},
            'tools/win11-proxy-relay/runtime/probe.py': {'proxy-relay'},
            'config/retired-packages/linear-workflow.json': {'installation'},
            'tests/test_retired_package_cleanup.py': {'installation'},
            'tests/test_task_store.py': {'task-runtime'},
            'scripts/verify_workflow_increment.py': set(),
            'tests/test_workflow_increment_acceptance.py': set(),
            'scripts/evaluate_task_runtime.py': {'evaluation-fixtures'},
            'tests/fixtures/task_runtime/oracle.py': {'evaluation-fixtures', 'task-runtime'},
            'scripts/install_agent_workflow_hooks.py': {'workflow-records', 'installation'},
            'tests/test_install_learning_workflow.py': {'learning'},
            'tests/test_install_work_report.py': {'report-integration'},
            'tests/test_regression_runner.py': {'test-runner'},
            'docs/TASK_RUNTIME.md': set(),
            'CONTRIBUTING.md': set(),
            '.gitignore': {'workflow-records', 'reports'},
            'skills/work-report/scripts/sync_writing_contract.py': {'learning', 'reports', 'report-integration', 'installation'},
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(set(runner.select_suites([path])), expected)
        for path in ('install.sh', '.github/workflows/regression.yml',
                     'scripts/run_regression_tests.py', 'scripts/codex_target_guard.py', 'new_runtime/new_module.py'):
            with self.subTest(path=path):
                self.assertEqual(runner.select_suites([path]), runner.ACTIVE)
        self.assertEqual(set(runner.select_suites(['docs/README.md', 'learning_workflow/runtime.py',
                                                  'tools/win11-proxy-relay/runtime/probe.py'])),
                         {'learning', 'proxy-relay'})

    def test_current_modules_have_one_owner_and_unknown_tests_fail_explicitly(self):
        for path in (runner.ROOT / 'tests').glob('test_*.py'):
            with self.subTest(path=path.name):
                self.assertIn(runner.root_group(path.name), runner.ROOT_GROUPS)
        tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', '*test_*.py'],
                                          cwd=runner.ROOT).decode().split('\0')
        directories = {str(Path(path).parent) for path in tracked if Path(path).name.startswith('test_')
                       and 'fixtures' not in Path(path).parts}
        self.assertEqual(directories, set(runner.SUITES.values()),
                         'A tracked test package is missing from explicit discovery')
        with self.assertRaisesRegex(ValueError, 'Unclassified'):
            runner.root_group('test_new_unclassified_component.py')
