import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import run_mechanisms as runner
import report_mechanisms as report
import score_mechanisms as scorer

CASES={case['id']:case for case in json.loads((runner.HERE/'cases.json').read_text())['cases']}

class MechanismHarnessTests(unittest.TestCase):
    def test_mixed_command_failure_preserves_real_read_evidence(self):
        body=(runner.ROOT/'skills/teaching-reconstruction/SKILL.md').read_text()
        event={'type':'item.completed','item':{'id':'mixed','type':'command_execution','command':'cat SKILL.md && missing-tool','exit_code':127,'aggregated_output':body+'\nmissing-tool: not found'}}
        self.assertEqual(runner.observed_target_read([event],'teaching-reconstruction')['status'],'read_output_observed')
        self.assertEqual(event['item']['exit_code'],127)
        event['item']['aggregated_output']='name: teaching-reconstruction'
        self.assertEqual(runner.observed_target_read([event],'teaching-reconstruction')['status'],'not_observed')
    def test_l04_shared_retrieval_has_no_target_body_in_control(self):
        case=CASES['L04'];module=runner.module_for_run()
        with tempfile.TemporaryDirectory() as temp:
            for variant in ('skills','control'):
                home=Path(temp)/variant;(home/'.codex').mkdir(parents=True);(home/'.codex/AGENTS.md').write_text('common writing')
                plan=module.setup_skills(case,variant,home)
                self.assertTrue((home/'.agents/skills/retrieval-practice/SKILL.md').is_file())
                self.assertEqual((home/'.agents/skills/teaching-reconstruction/SKILL.md').is_file(),variant=='skills')
                self.assertTrue((home/'.agents/skills/teaching-reconstruction/references/portable-learning-record.md').is_file())
            a=runner.snapshot(Path(temp)/'control/.agents');b=runner.snapshot(Path(temp)/'skills/.agents')
            for key in a:self.assertEqual(a[key],b[key],key)
    def test_runtime_real_create_bind_read_and_equal_seed(self):
        case=CASES['L03'];signatures=[]
        with tempfile.TemporaryDirectory() as temp:
            for arm in ('a','b'):
                run=Path(temp)/arm
                for name in ('workspace','home','runtime','data'):(run/name).mkdir(parents=True)
                shutil.copytree(runner.ROOT/'agent_workflow',run/'runtime/agent_workflow')
                for name,text in case['fixtures']['files'].items():
                    path=run/'workspace'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
                command=runner.base.sandbox_command(run/'workspace',run/'home',runtime=run/'runtime',data=run/'data')
                for args in [['git','init','-q'],['git','add','.'],['git','-c','user.name=Fixture','-c','user.email=f@example.invalid','commit','-qm','fixture']]:subprocess.run(command+args,check=True)
                task=runner.prepared_runtime(case,run,command);state=runner.runtime_read(command,task)
                self.assertEqual(scorer.task_ids(state['_task_inventory']),{task})
                self.assertTrue(all(c['user_acceptance']=='pending' for c in state['criteria']))
                self.assertIn('_history',state);self.assertIn('_checklist',state)
                signatures.append(runner.runtime_initial_signature({'runtime_before':state}))
            self.assertEqual(signatures[0],signatures[1])
    def test_pair_gate_allows_equal_reference_files_only(self):
        case=CASES['L04'];target=case['target_skill'];body=(runner.ROOT/'skills'/target/'SKILL.md').read_text()
        common={'status':'ok','case_sha256':scorer.digest(case),'skill_setup':runner.skill_plan(case,'control'),'before':case['fixtures']['files'],'model_requested':'gpt-5.5','model_observed':None,'effort':'medium','timeout_seconds':300}
        a={**copy.deepcopy(common),'source_files':runner.source_manifest(case,'control'),'installed_skills':['retrieval-practice']}
        b={**copy.deepcopy(common),'source_files':runner.source_manifest(case,'skills'),'installed_skills':['retrieval-practice',target],'events':[{'type':'item.completed','item':{'id':'mixed','type':'command_execution','exit_code':127,'aggregated_output':body}}]}
        b['target_load']=runner.observed_target_read(b['events'],target)
        self.assertEqual(report.pair_validity(case,a,b),[])
        a['source_files']['skills/'+target+'/SKILL.md']='leak'
        self.assertIn('target source leaked into control',report.pair_validity(case,a,b))

if __name__=='__main__':unittest.main()
