#!/usr/bin/env python3
"""Run maintained unittest suites explicitly; nested Skill tests are not recursive discovery."""
import argparse
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    'repository': 'tests',
    'reports': 'skills/work-report/tests',
    'worktrees': 'skills/manage-worktrees/tests',
    'win11-patch': 'skills/codex-win11-patch-safety/tests',
    'proxy-relay': 'tools/win11-proxy-relay/runtime/tests',
    'linear-compatibility': 'linear_workflow/shared/runtime/tests',
}
ACTIVE = tuple(name for name in SUITES if name != 'linear-compatibility')


class ExecutionResult(unittest.TextTestResult):
    # unittest counts skipped subtests separately from testsRun. Use successful
    # result callbacks so a mixed pass/skip case is not mistaken for no coverage.
    executed_success = False

    def addSuccess(self, test):
        self.executed_success = True
        super().addSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is None:
            self.executed_success = True
        super().addSubTest(test, subtest, err)


def run_directory(directory, stream=None):
    """Import errors, assertions, and empty discovery must all fail the command."""
    stream = stream or sys.stderr
    suite = unittest.TestLoader().discover(str(directory))
    if not suite.countTestCases():
        print(f'No tests discovered: {directory}', file=stream)
        return 1
    result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=ExecutionResult).run(suite)
    if result.wasSuccessful() and not result.executed_success:
        print('All discovered tests were skipped; no behavior was checked.', file=stream)
        return 1
    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=('active', *SUITES), default='active', nargs='?')
    args = parser.parse_args()
    if args.suite == 'active':
        # Separate processes prevent equally named modules in independent packages
        # from masking one another through sys.modules / unittest discovery.
        codes = [subprocess.run([sys.executable, __file__, name], cwd=ROOT).returncode
                 for name in ACTIVE]
        return int(any(codes))
    sys.path.insert(0, str(ROOT))
    return run_directory(ROOT / SUITES[args.suite])


if __name__ == '__main__':
    raise SystemExit(main())
