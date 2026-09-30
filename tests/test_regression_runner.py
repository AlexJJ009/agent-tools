"""A CI command must not turn missing coverage or failed imports into green."""
import importlib.util
import io
from pathlib import Path
import tempfile
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
