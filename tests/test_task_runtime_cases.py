"""External oracle controls for adapted history; not runtime/Agent acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent / 'fixtures/task_runtime'
spec = importlib.util.spec_from_file_location('task_case_oracle', ROOT / 'oracle.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class HistoricalCaseOracleTests(unittest.TestCase):
    def test_case_inventory_and_isolation_refusal(self):
        cases = json.loads((ROOT / 'cases.json').read_text())
        self.assertEqual([x['id'] for x in cases['cases']], ['H01', 'H02', 'H03', 'H04', 'H05'])
        self.assertEqual(cases['provenance']['kind'], 'adapted historical case')
        with o.Sandbox() as s:
            with self.assertRaisesRegex(ValueError, 'escapes'):
                s.python('transform.py', cwd=ROOT)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                s.python('transform.py', paths=[ROOT / 'project/input.txt'])
            with self.assertRaisesRegex(ValueError, 'escapes'):
                s.python('transform.py', ROOT / 'project/input.txt', s.repo / 'out.txt')
            (s.repo / 'escape').symlink_to(ROOT, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                s.scoped(s.repo / 'escape/project/input.txt')
            self.assertTrue((s.other / '.git').is_file())

    def test_h01_actual_cli_and_broken_output(self):
        with o.Sandbox() as s:
            source = s.repo / 'input.txt'
            source.write_text(' Alpha \n\n Beta \n')
            output = s.repo / 'output.txt'
            failed = s.python('transform.py', source, output, '--mode', 'strip', paths=[source, output])
            self.assertNotEqual(failed.returncode, 0)
            code = s.repo / 'transform.py'
            code.write_text(code.read_text().replace("['upper', 'lower']", "['upper', 'lower', 'strip']")
                            .replace("getattr(text, args.mode)()", "('\\n'.join(line.strip() for line in text.splitlines()) + '\\n') if args.mode == 'strip' else getattr(text, args.mode)()"))
            doc = s.repo / 'docs/usage.md'
            doc.write_text(doc.read_text() + '\nUse --mode strip to trim each line.\n')
            result = s.python('transform.py', source, output, '--mode', 'strip', paths=[source, output])
            self.assertEqual(result.returncode, 0, result.stderr)
            o.h01(output, doc)
            o.protected_unchanged(s.protected)
            output.write_text('Alpha\nBeta\n')
            with self.assertRaises(AssertionError):
                o.h01(output, doc)

    def test_h02_revision_and_validity_faults(self):
        good = {'requirements': {'REQ-MODE': 'default lower', 'REQ-BLANK': 'preserve blank lines',
                                 'REQ-INPUT': 'do not modify input'},
                'ordinals': ['REQ-INPUT', 'REQ-MODE', 'REQ-BLANK'], 'stale_write_rejected': True,
                'result_validity': {'REQ-MODE': False, 'REQ-BLANK': True, 'REQ-INPUT': False}}
        o.h02(good)
        for failure in ['lost', 'stale', 'valid', 'overinvalidate', 'ordinal']:
            bad = copy.deepcopy(good)
            if failure == 'lost': del bad['requirements']['REQ-INPUT']
            if failure == 'stale': bad['stale_write_rejected'] = False
            if failure == 'valid': bad['result_validity']['REQ-MODE'] = True
            if failure == 'overinvalidate': bad['result_validity']['REQ-BLANK'] = False
            if failure == 'ordinal': bad['ordinals'] = ['REQ-MODE', 'REQ-BLANK', 'REQ-INPUT']
            with self.subTest(failure=failure), self.assertRaises(AssertionError): o.h02(bad)
        with o.Sandbox() as s:
            source = s.repo / 'input.txt'; before = source.read_bytes()
            code = s.repo / 'transform.py'
            code.write_text(code.read_text().replace("default='upper'", "default='lower'"))
            result = s.python('transform.py', source, s.repo / 'lower.txt')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((s.repo / 'lower.txt').read_bytes(), b'alpha\n\nbeta\n')
            self.assertEqual(source.read_bytes(), before)

    def test_h03_cold_resume_constraints_and_interruption(self):
        good = {'candidates': ['task-transform', 'task-preview'], 'selected': None,
                'pending': ['finish lower-mode output'],
                'prohibitions': ['do not edit source input', 'do not publish']}
        o.h03(good)
        for key, value in [('selected', 'task-transform'), ('pending', []), ('prohibitions', [])]:
            bad = dict(good, **{key: value})
            with self.subTest(key=key), self.assertRaises(AssertionError): o.h03(bad)
        with o.Sandbox() as s:
            # Deliberately stop a real CPU subprocess after partial output.
            code = "from pathlib import Path; import sys; Path('partial.txt').write_text('alpha\\n'); print('ready',flush=True); sys.stdin.readline()"
            proc = subprocess.Popen([sys.executable, '-I', '-c', code], cwd=s.repo,
                                    env=s.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            try:
                self.assertEqual(proc.stdout.readline(), b'ready\n')
                proc.terminate(); proc.wait(timeout=5)
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()
                proc.stdin.close(); proc.stdout.close()
            result = s.python('transform.py', 'input.txt', 'partial.txt', '--mode', 'lower')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((s.repo / 'partial.txt').read_bytes(), b'alpha\n\nbeta\n')
            o.protected_unchanged(s.protected)

    def test_h04_growth_and_stale_view_negative_controls(self):
        with o.Sandbox() as s:
            path = s.data / 'current.json'
            for revision in range(1, 4):
                state = {'revision': revision, 'current_requirement': f'mode-{revision}'}
                path.write_text(json.dumps(state))
                before = o.file_snapshot(s.data)
                # An external correct read/retry outcome, not a runtime mock.
                for _ in range(20): self.assertEqual(json.loads(path.read_text()), state)
                o.h04(state, state, before, o.file_snapshot(s.data), f'mode-{revision}')
                with self.assertRaises(AssertionError):
                    o.h04(state, state, before, before, 'old-mode')
                with path.open('a') as stream: stream.write('\nretry')
                with self.assertRaises(AssertionError):
                    o.h04(state, state, before, o.file_snapshot(s.data), f'mode-{revision}')

    def test_h05_dependency_cleanup_and_wrong_deletion_controls(self):
        with o.Sandbox() as s:
            disposable = s.repo / 'owned-scratch.txt'; disposable.write_text('temporary')
            changed = s.repo / 'changed-after-plan.txt'; changed.write_text('planned bytes')
            planned = changed.read_bytes(); changed.write_text('new user bytes')
            self.assertNotEqual(planned, changed.read_bytes())
            protected = dict(s.protected, **{str(changed): changed.read_bytes()})
            fixed = s.repo / 'tests/fixtures/input.json'; fixed.parent.mkdir()
            fixed.write_bytes((s.repo / 'records/input.json').read_bytes())
            test = s.repo / 'tests/test_transform.py'
            test.write_text(test.read_text().replace('records/input.json', 'tests/fixtures/input.json'))
            (s.repo / 'records/input.json').unlink()
            # Fail-open and reject-all both lose: untouched disposable is not completion.
            with self.assertRaisesRegex(AssertionError, 'not cleaned'): o.h05(s, protected, disposable)
            disposable.unlink()
            o.h05(s, protected, disposable)
            # Retrying after a partly completed cleanup is a no-op at the boundary.
            disposable.unlink(missing_ok=True)
            o.h05(s, protected, disposable)
            for name in protected:
                path = Path(name); content = path.read_bytes(); path.unlink()
                with self.subTest(path=name), self.assertRaises(AssertionError): o.h05(s, protected, disposable)
                path.write_bytes(content)
            test.write_text(test.read_text().replace('tests/fixtures/input.json', 'records/input.json'))
            with self.assertRaises(AssertionError): o.h05(s, protected, disposable)


if __name__ == '__main__':
    unittest.main()
