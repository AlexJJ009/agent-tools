import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('r',HERE.parent/'skill-suite-pilot/run_eval.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class AblationTests(unittest.TestCase):
    def case(self):return {'id':'Htest','target_skills':['teaching-reconstruction'],'skill_setup':{'mode':'target_ablation','target_skill':'teaching-reconstruction','shared_skills':[]}}
    def test_both_conditions_only_target_diff(self):
        case=self.case()
        a=r.source_manifest(case,'skills');b=r.source_manifest(case,'control')
        self.assertEqual({k:v for k,v in a.items() if not k.startswith('skills/teaching-reconstruction/')},b)
        with tempfile.TemporaryDirectory() as tmp:
            for variant in ('skills','control'):
                home=Path(tmp)/variant;(home/'.codex').mkdir(parents=True);(home/'.codex/AGENTS.md').write_text('shared writing')
                plan=r.setup_skills(case,variant,home)
                self.assertEqual((home/'.agents/skills/teaching-reconstruction').exists(),variant=='skills')
                self.assertTrue((home/'.agents/skills/work-report/references/writing-contract.md').exists())
                self.assertFalse((home/'.agents/skills/work-report/SKILL.md').exists())
                if variant=='control':self.assertNotIn('teaching-reconstruction',(home/'.codex/AGENTS.md').read_text())
    def test_reject_target_leak(self):
        case=self.case();case['skill_setup']['shared_skills']=['teaching-reconstruction']
        with self.assertRaises(ValueError):r.skill_plan(case,'control')
        case=self.case();case['skill_setup']['shared_resources']=[{'source':'skills/cleaner/SKILL.md','destination':'skills/teaching-reconstruction/SKILL.md'}]
        with self.assertRaises(ValueError):r.skill_plan(case,'control')
    def test_isolated_control_target_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);home=base/'home';work=base/'workspace';work.mkdir();(home/'.codex').mkdir(parents=True);(home/'.codex/AGENTS.md').write_text('shared')
            r.setup_skills(self.case(),'control',home)
            proc=subprocess.run(r.sandbox_command(work,home)+['python3','-c',"from pathlib import Path;assert not Path('/home/alex_mercer').exists();assert not Path('/home/eval/.agents/skills/teaching-reconstruction').exists();assert Path('/home/eval/.agents/skills/work-report/references/writing-contract.md').is_file()"],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
    def test_load_observation(self):
        body=(r.ROOT/'skills/cleaner/SKILL.md').read_text()
        event={'type':'item.completed','item':{'id':'read1','type':'command_execution','exit_code':0,'aggregated_output':body}}
        self.assertEqual(r.observed_target_read([event],'cleaner')['status'],'read_output_observed')
        self.assertEqual(r.observed_target_read([],'cleaner')['status'],'not_observed')

class PairScheduleTests(unittest.TestCase):
    def test_ab_ba_order_and_exact_pair_delta(self):
        spec=importlib.util.spec_from_file_location('driver',HERE/'run_challenge.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
        seen=[]
        case={'id':'Hmock','skill_setup':{'mode':'target_ablation','target_skill':'cleaner'}}
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(output=Path(tmp),model='gpt-5.5',effort='medium',timeout=300,reps=2)
            def fake(case,variant,rep,*unused):
                seen.append((variant,rep))
                return {'status':'ok','rep':rep,'workspace':str(Path(tmp)/variant/'workspace'),'source_files':{'common':'hash',**({'skills/cleaner/SKILL.md':'target'} if variant=='skills' else {})},'before':{'fixture':'same'},'installed_skills':['cleaner'] if variant=='skills' else [],'model_requested':'gpt-5.5','effort':'medium','timeout_seconds':300}
            with patch.object(driver.runner,'run_case',side_effect=fake):pairs=driver.run_case_pairs(case,args,{})
            self.assertEqual(seen,[('skills',1),('control',1),('control',2),('skills',2)])
            self.assertTrue(all(p['target_only_source_difference'] and p['same_fixture'] and p['same_model_budget'] for p in pairs))

if __name__=='__main__':unittest.main()
