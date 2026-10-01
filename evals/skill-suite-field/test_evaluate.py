import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import evaluate as field


def case(invocation='discoverable'):
    return {'id':'TEST','prompt':'请完成这项任务。','fixtures':{'files':{}},
            'skill_setup':{'mode':'target_ablation','target_skill':'cleaner','shared_skills':[],
                           'shared_resources':[],'invocation':invocation},
            'primary_check_id':'TEST.1','checks':[{'id':'TEST.1','criterion':'正确完成目标'}, {'id':'TEST.2','criterion':'遵循用户边界'}]}


class FieldTests(unittest.TestCase):
    def test_discovery_catalog_without_forced_read(self):
        module=field.runner()
        for arm in ['skills','control']:
            with tempfile.TemporaryDirectory() as tmp:
                home=Path(tmp);(home/'.codex').mkdir();(home/'.codex/AGENTS.md').write_text('common contract')
                module.setup_skills(case(),arm,home)
                text=(home/'.codex/AGENTS.md').read_text()
                self.assertNotIn('必须先读取',text)
                self.assertNotIn('显式调用',text)
                self.assertIn('Available common capabilities; use when relevant.',text)
                self.assertEqual((home/'.agents/skills/cleaner/SKILL.md').exists(),arm=='skills')
                if arm=='skills':self.assertIn('- cleaner:',text)
                else:self.assertNotIn('cleaner',text)

    def test_explicit_instruction_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);(home/'.codex').mkdir();(home/'.codex/AGENTS.md').write_text('common')
            field.runner().setup_skills(case('explicit'),'skills',home)
            self.assertIn('必须先读取',(home/'.codex/AGENTS.md').read_text())

    def test_read_observation_not_erased_by_later_failure(self):
        body=(field.ROOT/'skills/cleaner/SKILL.md').read_text()
        result=field.runner().observed_target_read([{'type':'item.completed','item':{'id':'read','type':'command_execution','exit_code':127,'aggregated_output':body+'\nrg unavailable'}}],'cleaner')
        self.assertEqual(result['event_ids'],['read'])

    def test_unread_pair_remains_eligible(self):
        raw={'status':'ok','before':{},'model_requested':'gpt-6-sol','effort':'medium','timeout_seconds':420,
             'field_manifest':'same','source_files':{'common':'same'},'installed_skills':[],
             'target_load':{'status':'not_observed'}}
        skills=copy.deepcopy(raw);skills['source_files']['skills/cleaner/SKILL.md']='body';skills['installed_skills']=['cleaner']
        self.assertEqual(field.pair_reasons(case(),raw,skills),[])
        skills['source_files']['unrelated']='bad'
        self.assertIn('non-target source difference',field.pair_reasons(case(),raw,skills))

    def test_judge_receives_actual_context_and_separate_checks(self):
        raw={'actual_user_layer_agents':'ACTUAL USER CONTRACT','before':{},'after':{},'events':[], 'output':'candidate'}
        prompt=field.judge_prompt(case(),raw,{})
        self.assertIn('ACTUAL USER CONTRACT',prompt)
        self.assertIn('TEST.2',prompt)
        schema=field.grader.judge_schema(case())
        self.assertIn('writing_checks',schema['properties'])
        self.assertIn('checks',schema['properties'])

    def test_machine_failure_and_early_exit_not_quality_pass(self):
        c=case();c['grader_side']={'machine_checks':[{'id':'core','scope':'primary','code':'assert False'}]}
        with patch.object(field.mechanisms,'run_check',return_value={'returncode':1,'stdout':'','stderr':'assertion'}):
            self.assertFalse(field.machine_checks(c,{'workspace':'unused','after':{}})['core']['passed'])
        with patch.object(field.mechanisms,'run_check',return_value={'returncode':0,'stdout':'','stderr':''}):
            self.assertFalse(field.machine_checks(c,{'workspace':'unused','after':{}})['core']['passed'])
        with patch.object(field.mechanisms,'run_check',return_value={'returncode':1,'infra_error':True}):
            with self.assertRaises(RuntimeError):field.machine_checks(c,{'workspace':'unused','after':{}})

    def test_completed_timeout_not_resampled(self):
        c=case();raw={'status':'error','error':'timeout','field_manifest':field.digest({'frozen':True}),'case_sha256':field.digest(c),'model_requested':'gpt-6-sol','effort':'medium','timeout_seconds':420,'actual_user_layer_agents':'','instruction_hashes':{'.codex/AGENTS.md':field.hashlib.sha256(b'').hexdigest()}}
        with patch.object(field,'latest',return_value={('TEST','skills',1):(None,raw)}),patch.object(field,'freeze',return_value={'frozen':True}),patch.object(field,'runner') as runner:
            self.assertEqual(field.run_trial(c,'skills',1,Path('/unused'),'gpt-6-sol',True),raw)
            runner.assert_not_called()

    def test_numeric_attempt_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for attempt in [10,2,1]:
                directory=root/('F01-skills-1'+('' if attempt==1 else '-attempt'+str(attempt)))
                directory.mkdir();(directory/'result.json').write_text(json.dumps({'case_id':'F01','variant':'skills','rep':1,'attempt':attempt}))
            self.assertEqual(field.latest(root)[('F01','skills',1)][1]['attempt'],10)

    def test_actual_fixture_machine_checks(self):
        for c in field.cases():
            for label in ['good','bad','empty']:
                spec=c['grader_side']['calibration'][label]
                with self.subTest(case=c['id'],label=label),tempfile.TemporaryDirectory() as tmp:
                    work=Path(tmp)
                    for name,text in c['fixtures']['files'].items():
                        path=work/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
                    for name,text in spec['file_overrides'].items():
                        path=work/name
                        if text is None:path.unlink(missing_ok=True)
                        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
                    raw={'workspace':str(work),'after':field.mechanisms.snapshot(work)}
                    actual=field.machine_checks(c,raw)
                    if label=='good' or (c['id']=='F05' and label=='bad'):
                        # F05 bad satisfies functionality; its missing maintenance handoff is semantic.
                        self.assertTrue(all(x['passed'] for x in actual.values()),actual)
                    if (label=='empty' or label=='bad' and not spec['file_overrides']) and c['id'] in ['F01','F02','F05','F06']:
                        self.assertFalse(all(x['passed'] for x in actual.values()),actual)



if __name__=='__main__':unittest.main()
