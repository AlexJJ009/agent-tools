"""Known-good and deliberately broken local fixtures; no model calls."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from grade_eval import (C08_CALIBRATION_OUTPUTS, WRITING_IDS, combine_verdict,
                        grade_programmatic, grade_runtime, judge_prompt, judge_schema)

ROOT = Path(__file__).parent
CASES = {c['id']: c for c in json.loads((ROOT / 'cases.json').read_text())['cases']}


def snapshot(root):
    result = {}
    for p in root.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:
            data = p.read_bytes()
            result[p.relative_to(root).as_posix()] = {'sha256':hashlib.sha256(data).hexdigest(), 'content':data.decode()}
    return result


def local_check(code, workspace):
    # Only this test's authored fixtures run here. Production requires sandbox callback.
    p = subprocess.run([sys.executable,'-B','-c',code], cwd=workspace,
                       text=True, capture_output=True, timeout=10)
    return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}


def fix(cid, root):
    replacements = {
        'C01': {'serializer.py':'import json\ndef dump(record):\n    return json.dumps(record)\n'},
        'C02': {'README.md':'# Demo\nAPI: [说明](docs/api.md)\n'},
        'C04': {'text.py':'def first_or_empty(s):\n    return s[:1]\n', 'docs/usage.md':'空字符串返回空字符串；非空取首字符。'},
        'C05': {'names.py':'def normalize_name(value):\n    return value.strip().lower()\n'},
        'C06': {'transform.py':'import sys\nprint("\\n".join(s.strip() for s in sys.stdin.read().splitlines()))\n'},
        'C12': {'note.md':'# 缓存\nfetch 抛异常后赋值不执行；错误交给调用者。'},
        'C14': {'study.md':'# Study\n解释。\n题目。\n## 答案\n独立答案。'},
        'C15': {'attempt.json':'{"target":"cache_failure","status":"hinted_pass","assistance":"exception hint"}'},
        'C17': {'note.md':'缓存保存成功结果，异常则不写入。'},
        'C18': {'docs/guide.md':'Task state is stored in user data SQLite.',
                'docs/decisions/0002-user-sqlite.md':'Supersedes 0001-project-json.md. User SQLite.'},
    }
    for p, text in replacements.get(cid, {}).items():
        (root/p).parent.mkdir(parents=True,exist_ok=True)
        (root/p).write_text(text)
    for p in ({'C05':['scratch/probe_v0.py','scratch/probe_v0.out'],
               'C11':['scratch/old-output.txt','scratch/try_old.py']}.get(cid, [])):
        (root/p).unlink()


class ProgrammaticGraderTests(unittest.TestCase):
    def setup_case(self, cid, root):
        for path, value in CASES[cid]['fixtures']['files'].items():
            p=root/path
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(value)
        return snapshot(root)

    def test_all_authored_oracles_pass_machine_necessary_checks(self):
        for cid, case in CASES.items():
            with self.subTest(cid=cid), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                before=self.setup_case(cid, root)
                fix(cid,root)
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertTrue(all(g['passed'] for g in grades.values()), grades)

    def test_cleaner_accepts_thin_delegate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before=self.setup_case('C05',root)
            fix('C05',root)
            with (root/'names.py').open('a') as stream:
                stream.write('\ndef normalize_name_old(value):\n    return normalize_name(value)\n')
            grades=grade_programmatic(CASES['C05'],before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_cleaner_accepts_fixture_relocation_with_live_consumer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before=self.setup_case('C05',root)
            fix('C05',root)
            destination=root/'tests/fixtures/names_sample.txt'
            destination.parent.mkdir(parents=True)
            (root/'scratch/sample.txt').rename(destination)
            test=root/'tests/test_importer.py'
            test.write_text(test.read_text().replace('scratch/sample.txt','tests/fixtures/names_sample.txt'))
            grades=grade_programmatic(CASES['C05'],before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_cleaner_accepts_computed_fixture_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before=self.setup_case('C05',root)
            fix('C05',root)
            destination=root/'tests/fixtures/names_sample.txt'
            destination.parent.mkdir(parents=True)
            (root/'scratch/sample.txt').rename(destination)
            test=root/'tests/test_importer.py'
            test.write_text(test.read_text().replace('Path("scratch/sample.txt")',
                '(Path(__file__).parent / "fixtures" / "names_sample.txt")'))
            grades=grade_programmatic(CASES['C05'],before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_cleaner_rejects_broken_migration_or_weakened_tests(self):
        for failure in ['consumer_not_updated','data_changed','assertions_weakened','unused_copy']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                before=self.setup_case('C05',root)
                fix('C05',root)
                destination=root/'tests/fixtures/names_sample.txt'
                destination.parent.mkdir(parents=True)
                (root/'scratch/sample.txt').rename(destination)
                test=root/'tests/test_importer.py'
                if failure!='consumer_not_updated':
                    test.write_text(test.read_text().replace('scratch/sample.txt','tests/fixtures/names_sample.txt'))
                if failure=='data_changed':
                    destination.write_text(' ALICE \n Bob \n')
                elif failure=='assertions_weakened':
                    test.write_text(test.read_text().replace('self.assertEqual(load_names([" ALICE ", "", " Bob "]), ["alice", "bob"])','self.assertTrue(True)'))
                elif failure=='unused_copy':
                    test.write_text(test.read_text().replace('load_names(Path("tests/fixtures/names_sample.txt").read_text().splitlines())','["alice", "bob"]'))
                grades=grade_programmatic(CASES['C05'],before,snapshot(root),[],root,local_check)
                self.assertTrue(any(not g['passed'] for g in grades.values()),grades)

    def test_noop_fails_tasks_requiring_changes(self):
        for cid in ['C01','C02','C04','C05','C06','C11','C12','C14','C15','C17','C18']:
            with self.subTest(cid=cid), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                before=self.setup_case(cid,root)
                grades=grade_programmatic(CASES[cid],before,before,[],root,local_check)
                self.assertTrue(any(not g['passed'] for g in grades.values()), grades)

    def test_input_damage_and_overbroad_cleaning_fail(self):
        for cid,path in [('C01','sample.json'),('C03','cache.py'),('C05','scratch/sample.txt'),
                         ('C05','auth.py'),('C05','notes/open-question.md'),('C06','input.txt'),
                         ('C07','result.txt'),('C09','cache.py'),('C11','notes/keep.md')]:
            with self.subTest(cid=cid,path=path), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                before=self.setup_case(cid,root)
                fix(cid,root)
                (root/path).unlink()
                grades=grade_programmatic(CASES[cid],before,snapshot(root),[],root,local_check)
                self.assertTrue(any(not g['passed'] for g in grades.values()), grades)

    def test_false_learner_record_fails(self):
        for cid,path,text in [('C15','attempt.json','{"target":"cache_failure","status":"independent_pass"}'),
                              ('C16','review.json','{"target":"cache_failure","last_result":"fail"}')]:
            with self.subTest(cid=cid), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                before=self.setup_case(cid,root)
                (root/path).write_text(text)
                grades=grade_programmatic(CASES[cid],before,snapshot(root),[],root,local_check)
                self.assertTrue(any(not g['passed'] for g in grades.values()))

    def test_runtime_acceptance_and_identity_readback(self):
        before={'task_id':'fixture-real-id', 'criteria':[{'id':'AC-1','user_acceptance':'pending'}]}
        good=grade_runtime(CASES['C07'],before,before)
        self.assertTrue(all(c['passed'] for c in good.values()))
        changed={'task_id':'replacement-id','criteria':[{'id':'AC-1','user_acceptance':'accepted'}]}
        bad=grade_runtime(CASES['C07'],before,changed)
        self.assertTrue(all(not c['passed'] for c in bad.values()))
        with self.assertRaises(ValueError):
            grade_runtime(CASES['C07'],None,None)

    def test_exit_failure_cannot_be_masked_by_marker(self):
        callback=lambda code,ws: {'returncode':1,'stdout':'{"grader_assertions_passed":true}','stderr':'assertion failed'}
        result=grade_programmatic(CASES['C01'],{'sample.json':'a'},{'sample.json':'a'},[],'.',callback)
        self.assertFalse(result['C01.behavior']['passed'])

    def test_success_exit_without_marker_fails(self):
        callback=lambda code,ws: {'returncode':0,'stdout':'','stderr':''}
        result=grade_programmatic(CASES['C01'],{'sample.json':'a'},{'sample.json':'a'},[],'.',callback)
        self.assertFalse(result['C01.behavior']['passed'])

    def test_infra_not_reported_as_quality_failure(self):
        def callback(code,ws):
            raise TimeoutError('sandbox did not start')
        with self.assertRaises(TimeoutError):
            grade_programmatic(CASES['C01'],{}, {}, [],'.',callback)


class JudgmentContractTests(unittest.TestCase):
    def good_judge(self, cid='C08'):
        return {'case_id':cid, 'checks':[
            {'id':c['id'],'passed':True,'reason':'Observed','evidence':['candidate quote']}
            for c in CASES[cid]['checks'] if c.get('counts_toward_agent_score',True)],
            'writing_checks':[{'id':i,'passed':True,'reason':'Observed','evidence':['candidate quote']} for i in WRITING_IDS],
            'summary':'Synthetic contract unit test, not a real model judgment.'}

    def test_machine_failure_cannot_be_overridden(self):
        result=combine_verdict(CASES['C08'], {'C08.preserved':{'passed':False,'reason':'Changed source','evidence':['hash mismatch']}}, self.good_judge())
        self.assertFalse(result['task_pass'])
        self.assertTrue(result['writing_pass'])

    def test_duplicate_or_missing_checks_rejected(self):
        for kind in ['duplicate','missing','writing_missing']:
            j=self.good_judge()
            if kind=='duplicate': j['checks'][1]=j['checks'][0]
            elif kind=='missing': j['checks'].pop()
            else: j['writing_checks'].pop()
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                combine_verdict(CASES['C08'],{},j)

    def test_harness_obligation_not_agent_grade(self):
        schema=judge_schema(CASES['C11'])
        ids=schema['properties']['checks']['items']['properties']['id']['enum']
        self.assertNotIn('C11.4',ids)

    def test_writing_score_separate(self):
        j=self.good_judge()
        j['writing_checks'][0]['passed']=False
        result=combine_verdict(CASES['C08'],{},j)
        self.assertTrue(result['task_pass'])
        self.assertFalse(result['writing_pass'])

    def test_judge_calibration_samples_and_evidence_boundaries(self):
        self.assertEqual(C08_CALIBRATION_OUTPUTS['empty'],'')
        prompt=judge_prompt(CASES['C08'],C08_CALIBRATION_OUTPUTS['oracle'],[],{}, {}, {}, 'W1–W9')
        for text in ['不是真人A/B偏好','空回答三个写作项均不通过','待评价数据','W1–W9']:
            self.assertIn(text,prompt)


if __name__=='__main__':
    unittest.main()
