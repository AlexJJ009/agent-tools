"""Candidate integration acceptance over frozen CPU and loopback inputs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow.contracts import file_digest
from scripts import verify_workflow_increment as acceptance


class IncrementAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='workflow-increment-integration-')
        cls.base = Path(cls.temporary.name)
        cls.addClassCleanup(cls.temporary.cleanup)
        # This manifest is only this test's isolated integrity control. The real
        # acceptance run uses the predevelopment manifest and its external hash.
        manifest = cls.base / 'unit-baseline.json'
        manifest.write_text(json.dumps({'repository_root': str(acceptance.REPO),
            'files': [{'path': str(p.relative_to(acceptance.REPO)), 'sha256': file_digest(p)}
                      for p in sorted(acceptance.FIXTURES.rglob('*')) if p.is_file()], 'source_snapshots': []}))
        cls.summary = acceptance.run_cases(cls.base / 'cases', acceptance.CASES,
            manifest=manifest, trusted=file_digest(manifest))

    def test_all_candidate_mechanism_cases_have_actual_pass_observations(self):
        failures = {r['case']: r.get('error') for r in self.summary['cases'] if not r['passed']}
        self.assertEqual(failures, {})
        self.assertTrue(self.summary['passed'])
        self.assertEqual({r['case'] for r in self.summary['cases']}, set(acceptance.CASES))
        self.assertTrue(all(r['observations'] for r in self.summary['cases']))
        raw = json.loads((self.base / 'cases/AC-07/consumer-processes.jsonl').read_text().splitlines()[0])
        self.assertGreater(raw['pid'], 0)
        self.assertTrue(raw['effect_verified'])
        self.assertEqual(json.loads(raw['stdout'])['pid'], raw['pid'])
        journal = self.base / 'cases/AC-07/monitor/requests.jsonl'
        statuses = [json.loads(line)['http_status'] for line in journal.read_text().splitlines()]
        self.assertIn(429, statuses)

    def test_missing_effect_cannot_become_pass_from_a_canned_gate_response(self):
        with patch.object(acceptance.managed, 'execute', return_value={'status': 'pass', 'ready': True, 'stdout': '{}'}):
            result = acceptance.run_cases(self.base / 'false-allow-control', ['AC-09'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['cases'][0]['passed'])
        self.assertIn('Unexpected managed execution', result['cases'][0]['error'])
        self.assertFalse((self.base / 'false-allow-control/AC-09/effect.json').exists())

    def test_cli_case_selection_is_machine_readable_and_does_not_claim_external_cases(self):
        argv = [sys.executable, str(acceptance.REPO / 'scripts/verify_workflow_increment.py'),
                '--output', str(self.base / 'single-case'), '--case', 'AC-05']
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result['passed'])
        self.assertEqual([r['case'] for r in result['cases']], ['AC-05'])
        self.assertTrue({'AC-02', 'AC-10', 'AC-13'} <= result['external_receipts_required'].keys())

    def test_untrusted_baseline_is_nonzero_and_cannot_be_an_ac01_pass(self):
        argv = [sys.executable, str(acceptance.REPO / 'scripts/verify_workflow_increment.py'),
                '--output', str(self.base / 'untrusted-baseline'), '--case', 'AC-01',
                '--manifest', str(self.base / 'unit-baseline.json'), '--trusted-sha256', '0' * 64]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(json.loads(proc.stdout)['passed'])


if __name__ == '__main__':
    unittest.main()
