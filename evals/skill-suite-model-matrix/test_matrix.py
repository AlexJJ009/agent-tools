import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('matrix',Path(__file__).with_name('evaluate.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MatrixTests(unittest.TestCase):
    def test_exact_model_allowlist_and_fixed_judge(self):
        self.assertEqual(len(m.MODELS),4)
        with self.assertRaises(ValueError):m.selected('gpt-6-astra',m.MODELS)
        for suite in m.SUITES:
            cmd=m.stage_command('score',suite,'gpt-6-luna',Path('/tmp/matrix'))
            self.assertEqual(cmd[cmd.index('--model')+1],'gpt-6.1-sol')
            self.assertIn('/tmp/matrix/gpt-6-luna/'+suite+'/runs',cmd)
            self.assertEqual(cmd[cmd.index('--workers')+1],'1')
    def test_all_original_case_sets_unchanged(self):
        self.assertEqual({suite:len(m.dataset(suite)) for suite in m.SUITES},{'challenge':10,'mechanisms':4,'source-discovery':3,'artifact-followup':2})
        self.assertEqual(sum(len(m.dataset(suite)) for suite in m.SUITES)*len(m.MODELS)*m.REPS*2,304)
    def test_freeze_detects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source.py').write_text('before')
            manifest={'frozen_files':{'source.py':m.sha(root/'source.py')}}
            with patch.object(m,'ROOT',root):
                m.verify_frozen(manifest)
                (root/'source.py').write_text('after')
                with self.assertRaises(RuntimeError):m.verify_frozen(manifest)
    def test_case_job_keeps_ab_ba_and_exact_budget(self):
        case={'id':'X','target_skill':'cleaner'};seen=[]
        class FakeRunner:
            def run_case(self,case,arm,rep,runs,model,timeout,effort):
                seen.append((arm,rep,model,timeout,effort));work=Path(runs)/f'X-{arm}-{rep}'/'workspace';work.mkdir(parents=True)
                return {'workspace':str(work),'status':'ok','model_requested':model,'model_observed':None,'effort':effort,'timeout_seconds':timeout,'before':{'file':'same'},'source_files':{'common':'same',**({'skills/cleaner/SKILL.md':'target'} if arm=='skills' else {})},'installed_skills':['cleaner'] if arm=='skills' else []}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'matrix-manifest.json').write_text(json.dumps({'case_sha256':{'challenge':{'X':m.digest(case)}}}))
            with patch.object(m,'verify_frozen'),patch.object(m,'dataset',return_value=[case]),patch.object(m,'load_runner',return_value=FakeRunner()):
                self.assertEqual(m.run_case_job(out,'challenge','gpt-6-sol','X'),0)
        self.assertEqual([(a,r) for a,r,*_ in seen],[('skills',1),('control',1),('control',2),('skills',2)])
        self.assertTrue(all(model=='gpt-6-sol' and timeout==420 and effort=='medium' for _,_,model,timeout,effort in seen))
    def test_schedule_interleaves_models_by_case(self):
        commands=[]
        with tempfile.TemporaryDirectory() as tmp:
            argv=['evaluate.py','run','--output',tmp,'--suites','challenge','--cases','H01,H02','--workers','1']
            def capture(cmd,log):commands.append(cmd);return 0
            with patch.object(sys,'argv',argv),patch.object(m,'ensure_manifest',return_value={}),patch.object(m,'run_logged',side_effect=capture):self.assertEqual(m.main(),0)
        models=[cmd[cmd.index('--subject-model')+1] for cmd in commands]
        self.assertEqual(models[:4],list(m.MODELS))
        self.assertEqual(models[4:],list(m.MODELS[1:]+m.MODELS[:1]))

if __name__=='__main__':unittest.main()
