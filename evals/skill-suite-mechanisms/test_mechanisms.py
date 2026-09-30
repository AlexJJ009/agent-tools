"""Known state transitions and counterexamples; no model calls."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from grade_mechanisms import (WRITING_IDS,calibration_assets,combine_verdict,
                              grade_programmatic,grade_runtime,judge_prompt,judge_schema)

HERE=Path(__file__).parent


def cases():
    return {c['id']:c for c in json.loads((HERE/'cases.json').read_text())['cases']}


def snapshot(root):
    result={}
    for path in root.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            data=path.read_bytes()
            result[path.relative_to(root).as_posix()]={'sha256':hashlib.sha256(data).hexdigest(),'content':data.decode()}
    return result


def setup_files(root,files):
    for name,text in files.items():
        path=root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)


def apply_oracle(root,case):
    oracle=case['grader_side'].get('oracle') or {}
    setup_files(root,oracle.get('write',{}))
    for name in oracle.get('delete',[]):
        (root/name).unlink()


def local_check(code,workspace):
    proc=subprocess.run([sys.executable,'-B','-c',code],cwd=workspace,text=True,capture_output=True,timeout=10)
    return {'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}


class ContractTests(unittest.TestCase):
    def test_known_oracles_change_real_files(self):
        for case in cases().values():
            with self.subTest(cid=case['id']),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                apply_oracle(root,case)
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertTrue(grades,'No machine checks implemented')
                self.assertTrue(all(c['passed'] for c in grades.values()),grades)

    def test_noop_cannot_satisfy_stateful_primary(self):
        for case in cases().values():
            if case['id'] in {'L01','L04'}:
                continue  # Resuming an unanswered question must not invent a record mutation.
            with self.subTest(cid=case['id']),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                grades=grade_programmatic(case,before,before,[],root,local_check)
                self.assertTrue(any(not c['passed'] for c in grades.values() if c['scope']=='primary'),grades)

    def test_l01_retains_unanswered_state_without_forcing_write(self):
        case=cases()['L01']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            setup_files(root,case['fixtures']['files'])
            before=snapshot(root)
            grades=grade_programmatic(case,before,before,[],root,local_check)
            self.assertTrue(all(c['passed'] for c in grades.values()))

    def test_learning_record_mutants_fail_real_state_checks(self):
        for cid,mutation in [('L01','invent_attempt'),('L01','finish_unanswered'),
                             ('L01','promote_closure'),('L02','independent'),
                             ('L02','drop_hint'),('L02','drop_response'),
                             ('L02','new_identity'),('L02','drop_source'),('L02','drop_history')]:
            with self.subTest(cid=cid,mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                case=cases()[cid]
                root=Path(tmp)
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                apply_oracle(root,case)
                path=root/'learning-record.json'
                record=json.loads(path.read_text())
                attempts=record['learner_state']['observed_attempts']
                current=attempts[-1]
                if mutation=='invent_attempt':
                    attempts.append({'attempt_id':'fabricated','response':'not actually answered'})
                    # Make the fabricated identity consistent with the fixture ID family.
                    attempts[-1]['attempt_id']='a-fabricated'
                elif mutation=='finish_unanswered':record['learning_checks'][0]['status']='completed'
                elif mutation=='promote_closure':record['knowledge_components'][-1]['status']='independent_pass'
                elif mutation=='independent':current['result']='independent_pass'
                elif mutation=='drop_hint':current['assistance']=[]
                elif mutation=='drop_response':current['response']=None
                elif mutation=='new_identity':current['attempt_id']='replacement'
                elif mutation=='drop_source':record['source_refs']=[]
                elif mutation=='drop_history':attempts.pop(0)
                path.write_text(json.dumps(record,ensure_ascii=False))
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertTrue(any(not c['passed'] for c in grades.values()),grades)

    def test_equivalent_state_field_layout_allowed(self):
        case=cases()['L02']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            setup_files(root,case['fixtures']['files'])
            before=snapshot(root)
            apply_oracle(root,case)
            path=root/'learning-record.json'
            record=json.loads(path.read_text())
            record['attempts']=record['learner_state'].pop('observed_attempts')
            current=record['attempts'][-1]
            current['outcome']={'correct':True,'assisted':True}
            del current['result']
            current['answer']=current.pop('response')
            current['help_received']=current.pop('assistance')
            path.write_text(json.dumps(record,ensure_ascii=False))
            grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
            self.assertTrue(all(c['passed'] for c in grades.values()),grades)

    def test_l03_live_fixture_relocation_and_loss(self):
        for destroy in [False,True]:
            with self.subTest(destroy=destroy),tempfile.TemporaryDirectory() as tmp:
                case=cases()['L03']
                root=Path(tmp)
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                apply_oracle(root,case)
                (root/'tests/fixtures').mkdir()
                (root/'scratch/live-input.txt').rename(root/'tests/fixtures/live.txt')
                (root/'settings.json').write_text('{"fixture":"tests/fixtures/live.txt"}')
                if destroy:(root/'evidence/observed-input.txt').unlink()
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertEqual(all(c['passed'] for c in grades.values()),not destroy,grades)

    def test_l03_runtime_actual_state_required(self):
        case=cases()['L03']
        before={'task_id':'real-id','state':'active','criteria':[{'id':'AC-1','user_acceptance':'pending'}]}
        self.assertTrue(all(c['passed'] for c in grade_runtime(case,before,before).values()))
        wrong={'task_id':'another-id','state':'closed','criteria':[{'id':'AC-1','user_acceptance':'accepted'}]}
        self.assertTrue(all(not c['passed'] for c in grade_runtime(case,before,wrong).values()))
        with self.assertRaises(ValueError):grade_runtime(case,None,None)

    def test_l04_pending_question_allowed_but_mastery_and_answer_not_invented(self):
        for mutation in ['pending','mastered','fabricated_answer','source_changed']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                case=cases()['L04']
                root=Path(tmp)
                setup_files(root,case['fixtures']['files'])
                before=snapshot(root)
                path=root/'learning-record.json'
                state=json.loads(path.read_text())
                if mutation=='pending':
                    state['learning_checks'].append({'id':'check-failure-state','target_id':'kc-failure-state','status':'pending','prompt':'判断已有条目在失败后是否保留'})
                elif mutation=='mastered':
                    state['knowledge_components'][-1]['status']='independent_pass'
                elif mutation=='fabricated_answer':
                    state['learner_state']['observed_attempts'].append({'attempt_id':'invented','result':'hinted_pass','response':'A'})
                else:
                    (root/'cache.py').write_text('# changed source\n')
                path.write_text(json.dumps(state,ensure_ascii=False))
                grades=grade_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertEqual(all(c['passed'] for c in grades.values()),mutation=='pending',grades)

    def test_calibration_assets_present_and_hidden(self):
        for case in cases().values():
            with self.subTest(cid=case['id']):
                assets=calibration_assets(case)
                self.assertTrue(assets['good'])
                self.assertTrue(assets['bad'])
                self.assertEqual(assets['empty'],'')
                prompt=judge_prompt(case,'candidate',[],{}, {}, {})
                self.assertNotIn('"grader_side"',prompt)
                self.assertNotIn('"known_good_text"',prompt)
                self.assertNotIn('"variant"',prompt)


if __name__=='__main__':
    unittest.main()
