import unittest
import classify


class PairedDenominatorTests(unittest.TestCase):
    def report(self):
        rows=[]
        for arm in ['control','skills']:
            rows.append({'model':'m','case':'F01','arm':arm,'rep':1,'status':'ok','pair_eligible':True,
                         'target_read':{'status':'not_observed'},'verdict':{'primary_pass':True,'guardrails_pass':True,'writing_pass':True}})
        return {'rows':rows,'pairs':[{'model':'m','case':'F01','rep':1,'structural_reasons':[]}]}

    def test_single_graded_arm_does_not_enter_quality_denominator(self):
        r=self.report();del r['rows'][1]['verdict']
        result=classify.field_case(r,'m','F01')
        self.assertEqual(result['metrics']['primary']['n'],0)
        self.assertTrue(result['pending_or_excluded'])

    def test_missing_read_is_diagnostic_not_exclusion(self):
        r=self.report();result=classify.field_case(r,'m','F01')
        self.assertEqual(result['metrics']['primary']['n'],1)
        self.assertEqual(classify.read_counts(r['rows'],True)['observed'],0)
        self.assertEqual(classify.read_counts(r['rows'],True)['skills_rows'],1)

    def test_timeout_does_not_become_quality_false(self):
        r=self.report();r['rows'][1]['status']='error';r['rows'][1]['error']='timeout'
        self.assertEqual(classify.field_case(r,'m','F01')['metrics']['primary'],{'n':0,'control':0,'skills':0})

    def test_old_reviewed_read_flag_and_unknown_timeout_are_preserved(self):
        rows=[{'arm':'skills','target_read_observed':True,'raw':'/does/not/exist'},
              {'arm':'skills','target_read_observed':None},
              {'arm':'control','target_read_observed':False}]
        result=classify.read_counts(rows)
        self.assertEqual(result['observed'],1)
        self.assertEqual(result['unknown'],1)
        self.assertEqual(result['skills_rows'],2)
        self.assertNotIn('not_observed',result['status_counts'])

    def test_exactly_twenty_five_unique_cases(self):
        ids=[cid for group in classify.GROUPS.values() for cid in group]
        self.assertEqual(len(ids),25);self.assertEqual(len(set(ids)),25)


if __name__=='__main__':unittest.main()
