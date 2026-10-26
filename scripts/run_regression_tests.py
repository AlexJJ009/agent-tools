#!/usr/bin/env python3
"""Run scoped component regressions."""
import argparse
import fnmatch
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
# One test file belongs to one automatic group. The repository alias is retained
# for a deliberate full top-level run; it is not also run by `active`.
ROOT_GROUPS = {
    'claude-adapter': ('test_install_claude.py',),
    'project-evals': ('test_project_eval_skills.py',),
    'ci-watch': ('test_ci_watch.py',),
    'learning': ('test_teaching_*', 'test_writing_contract_*'),
    'test-runner': ('test_regression_runner.py',),
    'installation': ('test_install_*', 'test_codex_*', 'test_direct_configuration_*', 'test_retired_*'),
}
SUITES = {
    'repository': 'tests',
    **{name: 'tests' for name in ROOT_GROUPS},
    'worktrees': 'skills/manage-worktrees/tests',
}
ACTIVE = tuple(name for name in SUITES if name != 'repository')


def root_group(filename):
    for name, patterns in ROOT_GROUPS.items():
        if any(fnmatch.fnmatchcase(filename, pattern) for pattern in patterns):
            return name
    raise ValueError(f'Unclassified top-level test module: {filename}')


def select_suites(paths):
    """Conservative component dependencies, not a claim of line-level coverage."""
    selected = set()
    for path in paths:
        nested = next((name for name, directory in SUITES.items()
                       if name not in ROOT_GROUPS and name != 'repository'
                       and path.startswith(directory + '/')), None)
        if nested:
            selected.add(nested)
            continue
        if path.startswith('.github/') or path in ('scripts/install.sh', 'scripts/install-win11.ps1',
                                                  'scripts/run_regression_tests.py', 'scripts/codex_target_guard.py'):
            return ACTIVE
        if path.startswith('.agents/skills/'):
            selected.add('project-evals')
        elif path.startswith(('adapters/claude/', 'scripts/install_claude.py', 'scripts/install_skills.py')):
            selected.update(('claude-adapter', 'installation'))
        elif path.startswith('tests/test_'):
            selected.add(root_group(Path(path).name))
        elif path.startswith(('shared/writing/', 'skills/academic-writing/', 'scripts/sync_writing_contract.py')):
            selected.update(('learning', 'claude-adapter', 'installation'))
        elif path.startswith(('skills/teaching-', 'skills/task-routing/', 'skills/retrieval-practice/',
                              'skills/evidence-anchor/', 'skills/learning-artifact-compiler/',
                              'tests/fixtures/teaching/')):
            selected.update(('learning', 'installation'))
        elif path == 'bin/ci-watch':
            selected.update(('ci-watch', 'installation'))
        elif path.startswith(('skills/manage-worktrees/', 'bin/agent-wt')):
            selected.update(('worktrees', 'installation'))
        elif path.startswith(('scripts/', 'config/', 'bin/')):
            selected.add('installation')
        elif path.startswith('docs/') or path in ('README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'CLAUDE.md', 'LICENSE'):
            continue  # Documentation edits need semantic review, not unchanged runtimes.
        else:
            return ACTIVE  # Unknown production paths must not silently lose coverage.
    return tuple(name for name in ACTIVE if name in selected)


class ExecutionResult(unittest.TextTestResult):
    # unittest counts skipped subtests separately from testsRun.
    executed_success = False

    def addSuccess(self, test):
        self.executed_success = True
        super().addSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is None:
            self.executed_success = True
        super().addSubTest(test, subtest, err)


def run_directory(directory, stream=None, group=None):
    """Import errors, assertions, and empty/all-skipped discovery fail the command."""
    stream = stream or sys.stderr
    loader = unittest.TestLoader()
    if group:
        files = [p for p in sorted(directory.glob('test_*.py')) if root_group(p.name) == group]
        suite = unittest.TestSuite(loader.discover(str(directory), pattern=p.name) for p in files)
    else:
        suite = loader.discover(str(directory))
    if not suite.countTestCases():
        print(f'No tests discovered: {directory} ({group or "all"})', file=stream)
        return 1
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=ExecutionResult).run(suite)
    if result.wasSuccessful() and not result.executed_success:
        print('All discovered tests were skipped; no behavior was checked.', file=stream)
        return 1
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=('active', *SUITES), default='active', nargs='?')
    parser.add_argument('--list', action='store_true', help='Print selected active suites without executing')
    parser.add_argument('--changed-from', help='Select affected active suites from a Git base revision')
    args = parser.parse_args()
    if (args.changed_from or args.list) and args.suite != 'active':
        parser.error('--changed-from/--list apply only to active')
    if args.suite == 'active':
        selected = ACTIVE
        if args.changed_from:
            paths = subprocess.check_output(['git', 'diff', '--name-only', '-z', args.changed_from, 'HEAD', '--'], cwd=ROOT)
            selected = select_suites(paths.decode().rstrip('\0').split('\0') if paths else [])
        if args.list:
            print(' '.join(selected))
            return 0
        print('Selected component suites: ' + (', '.join(selected) or 'none; documentation or manual-only scope'), flush=True)
        codes = [subprocess.run([sys.executable, __file__, name], cwd=ROOT).returncode for name in selected]
        return int(any(codes))
    sys.path.insert(0, str(ROOT))
    return run_directory(ROOT / SUITES[args.suite], group=args.suite if args.suite in ROOT_GROUPS else None)


if __name__ == '__main__':
    raise SystemExit(main())
