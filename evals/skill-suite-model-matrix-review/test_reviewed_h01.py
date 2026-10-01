import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import reviewed_h01 as review

CASES = {c['id']: c for c in json.loads((review.HERE.parent / 'skill-suite-challenge/cases.json').read_text())['cases']}


class ReviewTests(unittest.TestCase):
    def test_only_h01_identity_changes(self):
        raw = {'case_id': 'fixture', 'variant': 'skills', 'rep': 1}
        for cid, case in CASES.items():
            with self.subTest(cid=cid):
                same = review.identity(case, raw) == review.previous.identity(case, raw, 'gpt-6.1-sol')
                self.assertEqual(same, cid != 'H01')
        self.assertNotEqual(review.identity(CASES['H01'], raw, 'gpt-6.1-sol'), review.identity(CASES['H01'], raw, 'gpt-6-sol'))

    def test_primary_covers_draft_without_filename_only_rule(self):
        case = CASES['H01']; before = copy.deepcopy(case)
        with patch.object(review.previous, 'corrected_prompt', side_effect=lambda c, *a, **k: json.dumps(c, ensure_ascii=False)):
            prompt = review.corrected_prompt(case)
        parsed = json.loads(prompt.split('\nH01.1 证据核查')[0])
        self.assertEqual(parsed['checks'][0]['criterion'], parsed['primary_atomic_check'])
        for required in ['未完成、未交付本身不构成废弃依据', 'H01.1 必须为 false', '允许材料等价保留或迁移', '不要求原文件名原路径']:
            self.assertIn(required, parsed['primary_atomic_check'])
        self.assertEqual(case, before)
        self.assertEqual(parsed['checks'][1:], before['checks'][1:])

    def test_other_prompts_unchanged(self):
        for cid in CASES:
            if cid == 'H01': continue
            args = (CASES[cid], 'candidate', [], {}, {}, {})
            self.assertEqual(review.corrected_prompt(*args), review.previous.corrected_prompt(*args))

    def test_report_identity_matches_score(self):
        report = Mock()
        report.pair_validity = lambda *args: []
        review.install_report(report)
        self.assertIs(report.grading_identity, review.identity)

    def test_export_delegates_with_review_identity_and_records_correction(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            def fake_export(runs, scored, out, reps):
                report = Mock(); report.pair_validity = lambda *a: []
                review.previous.install_report(report)
                self.assertIs(report.grading_identity, review.identity)
                review.scoring.dump(out / 'summary.json', {'rubric_corrections': {'H09': {'existing': True}}})
                review.scoring.dump(out / 'measurement-corrections.json', {'rubrics': {'H09': {'existing': True}}})
                (out / 'RESULTS.md').write_text('existing report\n')
                return 0
            with patch.object(review.previous, 'export_report', side_effect=fake_export):
                self.assertEqual(review.export_report(output, output, output, 2), 0)
            summary = json.loads((output / 'summary.json').read_text())
            self.assertIn('H01', summary['rubric_corrections'])
            self.assertEqual(summary['rubric_corrections']['H09'], {'existing': True})


if __name__ == '__main__': unittest.main()
