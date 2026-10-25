"""The packaged copy of the reader-facing contract is generated from the canonical source."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / 'scripts/sync_writing_contract.py'


class ContractSyncTests(unittest.TestCase):
    def test_repository_copy_matches_source(self):
        result = subprocess.run([sys.executable, str(SYNC_SCRIPT), '--check'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_sync_detects_drift_and_restores_the_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            script = repo / 'scripts/sync_writing_contract.py'
            script.parent.mkdir(parents=True)
            shutil.copy2(SYNC_SCRIPT, script)
            source = repo / 'shared/writing/reader-facing-contract.md'
            source.parent.mkdir(parents=True)
            source.write_text('W1 through W9 fixture\n')

            def run(flag):
                return subprocess.run([sys.executable, str(script), flag], capture_output=True, text=True)

            self.assertNotEqual(run('--check').returncode, 0)  # copy absent
            self.assertEqual(run('--write').returncode, 0)
            self.assertEqual(run('--check').returncode, 0)
            target = repo / 'skills/academic-writing/references/writing-contract.md'
            self.assertEqual(target.read_text(), source.read_text())
            target.write_text('drift\n')
            self.assertNotEqual(run('--check').returncode, 0)
            self.assertEqual(run('--write').returncode, 0)
            self.assertEqual(target.read_text(), source.read_text())


if __name__ == '__main__':
    unittest.main()
