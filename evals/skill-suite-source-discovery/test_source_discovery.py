import copy
import json
from pathlib import Path
import tempfile
import unittest
import grade_source_discovery as grader
import run_source_discovery as runner

CASES=json.loads((runner.HERE/'cases.json').read_text())['cases']

class SourceFollowupTests(unittest.TestCase):
    def judge_result(self,case,passed):
        return {'case_id':case['id'],'checks':[{'id':check['id'],'passed':passed,'reason':'authored validation label','evidence':['authored fixture']} for check in case['checks']], 'writing_checks':[{'id':key,'passed':passed,'reason':'authored label','evidence':['fixture']} for key in grader.WRITING_IDS],'summary':'authored protocol test; no model evaluation'}
    def test_schema_primary_and_good_bad_empty_protocol(self):
        for case in CASES:
            with self.subTest(case=case['id']):
                schema=json.dumps(grader.judge_schema(case))
                self.assertIn(case['primary_check_id'],schema)
                self.assertNotIn('H06.1',schema)
                assets=grader.calibration_assets(case)
                self.assertTrue(assets['good']);self.assertTrue(assets['bad']);self.assertEqual(assets['empty'],'')
                for label,passed in [('good',True),('bad',False),('empty',False)]:
                    # Hand-authored labels exercise aggregation, not model semantics.
                    result=grader.combine_verdict(case,{},self.judge_result(case,passed))
                    self.assertEqual(result['primary_pass'],passed,label)
                    self.assertEqual(result['primary_check_id'],case['primary_check_id'])
    def test_mapping_matches_original_machine_policy(self):
        for case in CASES:
            with self.subTest(case=case['id']),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for name,text in case['fixtures']['files'].items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
                before=runner.snapshot(root)
                expected_grader,source=grader.original_grader(case);mapped=copy.deepcopy(case);mapped['id']=source
                expected=expected_grader.grade_programmatic(mapped,before,before,[],root,runner.run_check)
                actual=grader.grade_programmatic(case,before,before,[],root,runner.run_check)
                self.assertEqual(actual,{case['id']+key.removeprefix(source):value for key,value in expected.items()})
    def test_pair_source_difference_is_only_target(self):
        for case in CASES:
            a=runner.source_manifest(case,'skills');b=runner.source_manifest(case,'control');prefix='skills/'+case['target_skill']+'/'
            self.assertEqual({k:v for k,v in a.items() if not k.startswith(prefix)},b)
            self.assertTrue(any(k.startswith('@frozen/evals/skill-suite-mechanisms/') for k in a))
            self.assertTrue(any(k.startswith('@frozen/evals/skill-suite-source-discovery/') for k in a))
    def test_source_observation_requires_actual_content(self):
        case=CASES[0]
        fake={'type':'item.completed','item':{'id':'read','type':'command_execution','command':'cat cleanup.py','exit_code':127,'aggregated_output':'cleanup.py'}}
        self.assertEqual(runner.source_read_observation(case,[fake])['files']['cleanup.py']['status'],'not_observed')
        fake['item']['aggregated_output']=case['fixtures']['files']['cleanup.py']
        self.assertEqual(runner.source_read_observation(case,[fake])['files']['cleanup.py']['status'],'source_content_observed')
    def test_artifact_grader_mapping_available_without_new_glue(self):
        case=copy.deepcopy(CASES[0]);case['followup_design'].update(source_grader_suite='challenge',source_grader_case_id='H09')
        self.assertEqual(grader.original_grader(case)[1],'H09')

if __name__=='__main__':unittest.main()
