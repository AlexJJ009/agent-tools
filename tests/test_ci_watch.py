"""Native-watch CLI contract; gh fixtures captured from agent-tools PR 72/run 37192612856."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/ci-watch'
STUB = r'''
import json, os, pathlib, sys, time
args = sys.argv[1:]
mode = os.environ['SCENARIO']
with open(os.environ['CALLS'], 'a') as out:
    out.write(json.dumps(args) + '\n')
fixture = pathlib.Path(os.environ['FIXTURES'])
row = json.loads((fixture / 'pass.json').read_text())[0]
if args[0] == 'api':
    if args[1].endswith('/pulls'):
        print(json.dumps([] if mode.startswith('run') else [{'number':72,'head':{'sha':'abc'}}]))
    else:
        print(json.dumps({'sha':'abc'}))
elif args[:2] == ['repo','view']:
    print(json.dumps({'nameWithOwner':'AlexJJ009/agent-tools'}))
elif args[:2] == ['pr','checks']:
    if '--watch' in args:
        assert '--json' not in args
        if mode == 'timeout': time.sleep(5)
        sys.exit(1 if mode in ('fail','external') else 0)
    if mode == 'error':
        print('authentication failed', file=sys.stderr); sys.exit(1)
    if mode == 'none':
        print((fixture/'no-checks.stderr').read_text(), end='', file=sys.stderr); sys.exit(1)
    if mode in ('fail','external'):
        row.update(bucket='fail',state='FAILURE')
        if mode == 'external': row['link']='https://example.org/check/123'
    print(json.dumps([row])); sys.exit(1 if mode in ('fail','external') else 0)
elif args[:2] == ['run','list']:
    rows = json.loads((fixture/'empty-runs.json').read_text()) if mode == 'run-none' else [dict(databaseId=37192612856,name='regression',status='completed',conclusion='failure' if mode=='run-fail' else 'success',url='https://github.com/AlexJJ009/agent-tools/actions/runs/37192612856',headSha='abc')]
    if mode == 'run-late':
        calls = pathlib.Path(os.environ['CALLS']).read_text()
        if calls.count('\"list\"') > 1:
            rows.append(dict(rows[0], databaseId=99))
    print(json.dumps(rows))
elif args[:2] == ['run','watch']:
    sys.exit(1 if mode=='run-fail' else 0)
elif args[:2] == ['run','view']:
    assert '--log-failed' in args
    sample = (fixture/'failed-log.txt').read_text().splitlines()
    print(sample[0])
    for n in range(120): print('regression\tstep\tnoise-'+str(n))
    print(sample[-1])
    print('regression\tstep\tFINAL FAILING LINE')
else:
    raise SystemExit('unexpected gh call: '+repr(args))
'''


class CiWatchTests(unittest.TestCase):
    def invoke(self, scenario, *args):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = root / 'gh'
            stub.write_text(f'#!{sys.executable}\n' + STUB)
            stub.chmod(0o755)
            calls = root / 'calls'
            env = dict(os.environ, PATH=f'{root}:{os.environ["PATH"]}',
                       SCENARIO=scenario, FIXTURES=str(FIXTURES), CALLS=str(calls))
            command = [str(ROOT/'bin/ci-watch'), *(args or ('72',)),
                       '--repo','AlexJJ009/agent-tools','--grace-seconds','0']
            result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=10)
            self.calls = [json.loads(line) for line in calls.read_text().splitlines()]
            return result

    def test_pass(self):
        result = self.invoke('pass')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('All checks passed', result.stdout)
        self.assertTrue(any('--watch' in call for call in self.calls))

    def test_fail_tail(self):
        result = self.invoke('fail')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Failed: regression https://github.com/', result.stdout)
        logs = [line for line in result.stdout.splitlines() if '\t' in line]
        self.assertEqual(len(logs), 80)
        self.assertNotIn('noise-0\n', result.stdout)
        self.assertIn('FINAL FAILING LINE', logs[-1])
        self.assertTrue(any('40261808023' in call and '--job' in call and '121375594326' in call for call in self.calls))

    def test_no_checks(self):
        result = self.invoke('none')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('no checks appeared', result.stdout.lower())
        self.assertIn('not a pass', result.stdout)
        self.assertFalse(any('--watch' in call for call in self.calls))

    def test_timeout(self):
        result = self.invoke('timeout', '72', '--timeout', '0.01')
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn('Timed out', result.stdout)

    def test_external_failure(self):
        result = self.invoke('external')
        self.assertEqual(result.returncode, 1)
        self.assertIn('https://example.org/check/123', result.stdout)
        self.assertFalse(any(call[:2] == ['run','view'] for call in self.calls))

    def test_query_error_is_not_absence(self):
        result = self.invoke('error')
        self.assertEqual(result.returncode, 4)
        self.assertIn('authentication failed', result.stderr)
        self.assertNotIn('not a pass', result.stdout)

    def test_sha_resolves_pr(self):
        self.assertEqual(self.invoke('pass', '--sha','abc').returncode, 0)
        self.assertTrue(any(call[:2] == ['pr','checks'] for call in self.calls))

    def test_branch_without_pr(self):
        self.assertEqual(self.invoke('run-pass', '--branch','feature/slash').returncode, 0)
        self.assertTrue(any('repos/AlexJJ009/agent-tools/commits/feature%2Fslash' in call for call in self.calls))
        self.assertTrue(any(call[:2] == ['run','watch'] for call in self.calls))

    def test_late_run_is_also_watched(self):
        result = self.invoke('run-late', '--sha', 'abc')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(call[:3] == ['run', 'watch', '99'] for call in self.calls))

    def test_run_failure(self):
        result = self.invoke('run-fail','--sha','abc')
        self.assertEqual(result.returncode, 1)
        self.assertIn('FINAL FAILING LINE', result.stdout)

    def test_runs_absent(self):
        result = self.invoke('run-none','--sha','abc')
        self.assertEqual(result.returncode, 2)
        self.assertIn('not a pass', result.stdout)


if __name__ == '__main__':
    unittest.main()
