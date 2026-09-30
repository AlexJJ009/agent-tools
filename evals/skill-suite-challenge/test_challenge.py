"""Authored oracle/null/mutant checks; never runs a model."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from grade_challenge import (WRITING_IDS, blind_events, calibration_assets,
                             combine_verdict, grade_programmatic, judge_prompt, judge_schema)

ROOT=Path(__file__).parent
CASES={c['id']:c for c in json.loads((ROOT/'cases.json').read_text())['cases']}


def snapshot(root):
    result={}
    for p in root.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            data=p.read_bytes()
            result[p.relative_to(root).as_posix()]={'content':data.decode(),'sha256':hashlib.sha256(data).hexdigest()}
    return result


def local_check(code,workspace):
    # Only authored test fixtures execute locally; production supplies sandbox.
    p=subprocess.run([sys.executable,'-B','-c',code],cwd=workspace,text=True,capture_output=True,timeout=10)
    return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}


def setup_files(root,files):
    for path,content in files.items():
        p=root/path
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(content)


def apply_oracle(root,case):
    oracle=case['grader_side'].get('oracle') or {}
    setup_files(root,oracle.get('write',{}))
    for path in oracle.get('delete',[]):
        (root/path).unlink()


class FileBehaviorTests(unittest.TestCase):
    def test_authored_oracles_on_actual_files(self):
        for cid,case in CASES.items():
            with self.subTest(cid=cid),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                apply_oracle(root,case)
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_noop_rejected_when_primary_requires_file_effect(self):
        for cid in ['H01','H02','H08','H09','H10']:
            with self.subTest(cid=cid),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                case=CASES[cid]
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                grades=grade_programmatic(case,before,before,[],root,local_check)
                self.assertTrue(any(not g['passed'] for g in grades.values() if g['scope']=='primary'),grades)

    def test_meaningful_mutations_rejected(self):
        mutations={
            'H01':('scratch/source-observation.txt',None),
            'H02':('formatters.py','def render_user(v): return "user:"+v.strip().casefold()\ndef render_owner(v): return "owner:"+v.strip().casefold()\ndef render_token(v): return "token:"+v.strip().casefold()\n'),
            'H03':('cache.py',''),
            'H04':('run.log','rewritten success'),
            'H07':('serializer.py','import json\ndef dump(record): return json.dumps(record)\n'),
            'H08':('records.py','import csv\ndef read_records(path):\n    with open(path) as stream:\n        return [{"id":int(r["id"]),"name":r["name"],"region":r["region"]} for r in csv.DictReader(stream)]\n'),
            'H09':('ratio.py','def ratio(config): return 1\n'),
            'H10':('run.log','revision=r2 everything succeeded\n'),
        }
        for cid,(path,value) in mutations.items():
            with self.subTest(cid=cid),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                case=CASES[cid]
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                apply_oracle(root,case)
                if value is None:
                    (root/path).unlink()
                else:
                    (root/path).write_text(value)
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertTrue(any(not g['passed'] for g in grades.values()),grades)

    def test_h01_equivalent_live_fixture_relocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            case=CASES['H01']
            setup_files(root,case['fixtures']['files'])
            before=snapshot(root)
            apply_oracle(root,case)
            (root/'tests/fixtures').mkdir()
            (root/'scratch/current-seed.txt').rename(root/'tests/fixtures/seed.txt')
            config=json.loads((root/'config.json').read_text())
            config['fixture']='tests/fixtures/seed.txt'
            (root/'config.json').write_text(json.dumps(config))
            grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_h02_equivalent_public_package_refactor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            case=CASES['H02']
            setup_files(root,case['fixtures']['files'])
            before=snapshot(root)
            apply_oracle(root,case)
            (root/'formatters').mkdir()
            (root/'formatters.py').rename(root/'formatters/__init__.py')
            grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_h09_h10_unrelated_sections_not_rewritten(self):
        for cid,path in [('H09','note.md'),('H10','article.md')]:
            with self.subTest(cid=cid),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                case=CASES[cid]
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                apply_oracle(root,case)
                (root/path).write_text('# Rewritten whole document\n')
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertFalse(grades[cid+'.unaffected_sections']['passed'])

    def test_sandbox_failure_is_not_quality_failure(self):
        def infra(code,workspace):
            return {'returncode':124,'stdout':'','stderr':'timeout','infra_error':True}
        with self.assertRaises(RuntimeError):
            grade_programmatic(CASES['H02'],{}, {}, [],'.',infra)

    def test_calibration_assets_cover_five_skills(self):
        skills=set()
        for case in CASES.values():
            assets=calibration_assets(case)
            self.assertTrue(assets['good'])
            self.assertTrue(assets['bad'])
            self.assertNotEqual(assets['good'],assets['bad'])
            self.assertEqual(assets['empty'],'')
            skills.add(case['target_skill'])
        self.assertEqual(len(skills),5)


class JudgeContractTests(unittest.TestCase):
    def case(self):
        return {'id':'H00','primary_check_id':'H00.1','capability':'Preserve a meaningful distinction',
                'checks':[{'id':'H00.1','criterion':'Do the task'},{'id':'H00.2','criterion':'Respect scope'}],
                'target_skill':'secret_skill','variant':'secret_variant','grader_side':{'oracle':'SECRET_ORACLE'},
                'prompt':'Do the requested task','fixtures':{'files':{'app.py':'print(1)'}}}
    def judgment(self):
        return {'case_id':'H00','checks':[{'id':i,'passed':True,'reason':'Observed','evidence':['line']} for i in ['H00.1','H00.2']],
                'writing_checks':[{'id':i,'passed':True,'reason':'Observed','evidence':['line']} for i in WRITING_IDS], 'summary':'test only'}
    def test_primary_and_guardrails_separate(self):
        j=self.judgment()
        j['checks'][1]['passed']=False
        r=combine_verdict(self.case(),{},j)
        self.assertTrue(r['primary_pass'])
        self.assertFalse(r['guardrails_pass'])
        self.assertTrue(r['writing_pass'])
        self.assertNotIn('task_pass',r)
    def test_machine_failure_cannot_be_overridden(self):
        r=combine_verdict(self.case(),{'H00.machine':{'passed':False,'reason':'Not observed','evidence':[],'scope':'primary'}},self.judgment())
        self.assertFalse(r['primary_pass'])
        self.assertTrue(r['guardrails_pass'])
    def test_missing_or_duplicate_grade_rejected(self):
        j=self.judgment()
        j['checks'][1]=j['checks'][0]
        with self.assertRaises(ValueError):
            combine_verdict(self.case(),{},j)
    def test_blind_judge_drops_oracle_variant_and_skill_reads(self):
        events=[{'item':{'type':'command_execution','command':'cat .agents/skills/secret/SKILL.md',
                         'aggregated_output':'SECRET_SKILL_INSTRUCTION','exit_code':0}},
                {'item':{'command':'python3 tests/test_app.py','aggregated_output':'1 passed','exit_code':0}}]
        before={'.agents/skills/secret/SKILL.md':{'content':'SECRET_SKILL_FILE'},'app.py':{'content':'print(1)'}}
        p=judge_prompt(self.case(),'candidate',events,before,before,{},'writing contract')
        for secret in ['SECRET_ORACLE','secret_variant','secret_skill','SECRET_SKILL_INSTRUCTION','SECRET_SKILL_FILE']:
            self.assertNotIn(secret,p)
        self.assertIn('1 passed',p)
        self.assertEqual(events[0]['item']['aggregated_output'],'SECRET_SKILL_INSTRUCTION')


if __name__=='__main__':
    unittest.main()
