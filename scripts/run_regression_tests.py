#!/usr/bin/env python3
"""Run component regression suites: all active suites, or one named suite."""
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
    'installation': ('test_install_*', 'test_codex_*'),
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
    parser.add_argument('--list', action='store_true', help='Print the active suites without executing')
    args = parser.parse_args()
    if args.list and args.suite != 'active':
        parser.error('--list applies only to active')
    if args.suite == 'active':
        selected = ACTIVE
        if args.list:
            print(' '.join(selected))
            return 0
        print('Selected component suites: ' + ', '.join(selected), flush=True)
        codes = [subprocess.run([sys.executable, __file__, name], cwd=ROOT).returncode for name in selected]
        return int(any(codes))
    sys.path.insert(0, str(ROOT))
    return run_directory(ROOT / SUITES[args.suite], group=args.suite if args.suite in ROOT_GROUPS else None)


if __name__ == '__main__':
    raise SystemExit(main())
