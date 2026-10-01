import tempfile
from pathlib import Path
import unittest
import finalize


class CompletionTests(unittest.TestCase):
    def slot(self, arm, completion='completed', **overrides):
        return dict(model='model', suite='suite', case='H01', rep=1, arm=arm,
                    attempted=True, completion=completion,
                    grade_valid=completion == 'completed', protocol_errors=[], **overrides)

    def test_timeout_is_completion_gap_not_quality_false(self):
        rows = [self.slot('control'), self.slot('skills', 'budget_unfinished')]
        result = finalize.summarize_completion(rows)
        self.assertTrue(result['evaluation_run_complete'])
        self.assertEqual((result['completed'], result['budget_unfinished'], result['expected_slots']), (1, 1, 2))
        self.assertEqual(result['completion_four_cells']['model']['H01']['control_only'], 1)
        quality = finalize.summarize.paired_rows({'rows': [{'case':'H01','arm':'control','rep':1,'primary':True}], 'paired_outcomes':[], 'invalid_pairs':[{'case':'H01','rep':1,'reasons':['missing scored arm']}]})
        self.assertEqual(quality[0], [])
        self.assertEqual(finalize.summarize.metric(quality[0], 'primary')['n'], 0)
        self.assertNotIn('primary', rows[1])

    def test_repeated_attempts_select_numeric_latest_without_new_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            runs = Path(directory)
            for suffix in ('', '-attempt2', '-attempt10'):
                (runs / ('H01-skills-1' + suffix)).mkdir()
            paths = finalize.latest_attempts(runs, 'H01', 'skills', 1)
            self.assertEqual(paths[-1].parent.name, 'H01-skills-1-attempt10')
            row = self.slot('skills', attempt_count=len(paths))
            self.assertEqual(finalize.summarize_completion([row])['expected_slots'], 1)

    def test_error_missing_ungraded_or_bad_protocol_prevents_completion(self):
        for completion in ('error', 'missing'):
            result = finalize.summarize_completion([self.slot('skills', completion)])
            self.assertFalse(result['evaluation_run_complete'])
        row = self.slot('skills'); row['grade_valid'] = False
        self.assertFalse(finalize.summarize_completion([row])['evaluation_run_complete'])
        row['grade_valid'] = True; row['protocol_errors'] = ['effort']
        self.assertFalse(finalize.summarize_completion([row])['evaluation_run_complete'])

    def test_timeout_classifier_requires_explicit_timeout(self):
        self.assertEqual(finalize.status({'status':'error','error':'timeout'}), 'budget_unfinished')
        self.assertEqual(finalize.status({'status':'error','error':'cli_execution'}), 'error')


if __name__ == '__main__':
    unittest.main()
