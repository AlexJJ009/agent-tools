import copy
import json
import tempfile
from unittest.mock import patch
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import report_challenge as report

class PairValidityTests(unittest.TestCase):
    def fixture(self):
        case={'id':'H01','target_skill':'cleaner'}
        common={'status':'ok','case_sha256':report.digest(case),'skill_setup':{'mode':'target_ablation','target':'cleaner'},'before':{'f':{'sha256':'input'}},'model_requested':'gpt-5.5','model_observed':None,'effort':'medium','timeout_seconds':300,'source_files':{'shared/writing.md':'same','@codex_binary':'same'},'installed_skills':[]}
        control=copy.deepcopy(common);skills=copy.deepcopy(common)
        skills['source_files']['skills/cleaner/SKILL.md']='body'
        skills['installed_skills']=['cleaner'];skills['target_load']={'status':'read_output_observed','event_ids':['read1']}
        skills['events']=[{'type':'item.completed','item':{'id':'read1','type':'command_execution','exit_code':0,'aggregated_output':'x'*120}}]
        return case,control,skills
    def test_valid(self):
        self.assertEqual(report.pair_validity(*self.fixture()),[])
    def test_missing_read_excluded(self):
        case,a,b=self.fixture();b['events']=[]
        self.assertIn('target skill body read was not observed',report.pair_validity(case,a,b))
    def test_different_fixture_excluded(self):
        case,a,b=self.fixture();b['before']['f']['sha256']='other'
        self.assertIn('fixture differs or is missing',report.pair_validity(case,a,b))
    def test_budget_and_resource_confounds_excluded(self):
        case,a,b=self.fixture();b['timeout_seconds']=600;b['source_files']['shared/writing.md']='changed'
        reasons=report.pair_validity(case,a,b)
        self.assertIn('model/budget mismatch: timeout_seconds',reasons)
        self.assertIn('source difference is not exclusively target package',reasons)
    def test_control_target_metadata_excluded(self):
        case,a,b=self.fixture();a['installed_skills']=['cleaner'];a['source_files']['skills/cleaner/SKILL.md']='body'
        reasons=report.pair_validity(case,a,b)
        self.assertIn('target source leaked into control',reasons)
        self.assertIn('installed skill difference is not exactly the target',reasons)
    def test_export_excludes_invalid_pair_from_scores_and_html_data(self):
        case,a,b=self.fixture();case.update(capability='cleanup',prompt='clean up')
        for raw in (a,b):raw['case_sha256']=report.digest(case)
        b['events']=[];a['events']=[]
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);here=base/'source';here.mkdir();(here/'cases.json').write_text(json.dumps({'cases':[case]}))
            runs=base/'runs';scored=base/'scored';output=base/'output';output.mkdir();(scored/'grades').mkdir(parents=True)
            for arm,raw in [('control',a),('skills',b)]:
                raw.update(case_id='H01',variant=arm,rep=1,seconds=1,usage={'input_tokens':10,'cached_input_tokens':0,'output_tokens':1})
                folder=runs/f'H01-{arm}-1';folder.mkdir(parents=True);(folder/'result.json').write_text(json.dumps(raw));(folder/'prompt.txt').write_text('clean up')
                identity=report.grading_identity(case,raw,'gpt-5.5')
                grade={'identity':identity,'case_id':'H01','variant':arm,'rep':1,'case_sha256':report.digest(case),'judge_model_requested':'gpt-5.5','verdict':{'machine_checks':{},'semantic_checks':[],'writing_checks':[],'primary_pass':True,'guardrails_pass':True,'writing_pass':True,'primary_check':{}},'judge_usage':None}
                (scored/'grades'/f'{arm}.json').write_text(json.dumps(grade))
            with patch.object(report,'HERE',here):status=report.export(runs,scored,output,1)
            summary=json.loads((output/'summary.json').read_text())
            self.assertEqual(status,2)
            self.assertEqual(summary['paired_counts'],{})
            self.assertEqual(summary['valid_pair_count'],0)
            self.assertEqual(len(summary['invalid_pairs']),1)
            self.assertEqual((output/'cleaner/v1/results.jsonl').read_text(),'')
            self.assertEqual((output/'cleaner/baseline/results.jsonl').read_text(),'')
    def test_unknown_served_model_does_not_invent_mismatch(self):
        self.assertEqual(report.pair_validity(*self.fixture()),[])
        case,a,b=self.fixture();b['model_observed']='another-model'
        self.assertIn('skills: served model mismatch',report.pair_validity(case,a,b))

if __name__=='__main__':unittest.main()
