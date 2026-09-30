"""Scoped correction controls; no old artifacts or old source are rewritten."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

import reviewed_challenge_v3 as v3

CHALLENGE=Path(__file__).resolve().parent.parent/'skill-suite-challenge'
sys.path.insert(0,str(CHALLENGE))
from test_challenge import setup_files,snapshot,apply_oracle,local_check
CASES={c['id']:c for c in json.loads((CHALLENGE/'cases.json').read_text())['cases']}


class ScopingTests(unittest.TestCase):
    def test_h08_stale_schema_does_not_override_core_success(self):
        case=CASES['H08']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            setup_files(root,case['fixtures']['files']);before=snapshot(root)
            apply_oracle(root,case)
            (root/'schema.json').write_text(case['fixtures']['files']['schema.json'])
            grades=v3.corrected_programmatic(case,before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values() if g['scope']=='primary'),grades)
            self.assertFalse(grades['H08.schema_and_existing_tests']['passed'])
            self.assertEqual(grades['H08.schema_and_existing_tests']['scope'],'guardrail')

    def test_h08_oracle_passes_both_scopes(self):
        case=CASES['H08']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setup_files(root,case['fixtures']['files']);before=snapshot(root)
            apply_oracle(root,case)
            grades=v3.corrected_programmatic(case,before,snapshot(root),[],root,local_check)
            self.assertTrue(all(g['passed'] for g in grades.values()),grades)

    def test_h08_noop_and_core_regression_still_fail_primary(self):
        case=CASES['H08']
        for mode in ['noop','lost_zero','append']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);setup_files(root,case['fixtures']['files']);before=snapshot(root)
                if mode!='noop':
                    apply_oracle(root,case)
                    if mode=='lost_zero':
                        path=root/'records.py';path.write_text(path.read_text().replace('"id": row["id"]','"id": int(row["id"])'))
                    else:
                        (root/'importer.py').write_text('import json\nfrom records import read_records\ndef convert(source,destination):\n    rows=read_records(source)\n    with open(destination,"a") as f: f.write(json.dumps(rows))\n    return rows\n')
                grades=v3.corrected_programmatic(case,before,snapshot(root),[],root,local_check)
                self.assertFalse(grades['H08.core_behavior']['passed'],grades)

    def test_h09_infinity_example_valid_but_optional_advice_wrong(self):
        case=CASES['H09']
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);setup_files(root,case['fixtures']['files'])
            code='''from ratio import ratio
assert ratio({})==10.0
assert ratio({"denominator":float("inf")})==1
try: ratio({"denominator":0})
except ZeroDivisionError: pass
else: raise AssertionError("zero should raise")
config={"denominator":0}
denominator=config.get("denominator",1) or 1
assert 10/denominator==10.0
assert 10/denominator!=1
'''
            self.assertEqual(local_check(code,root)['returncode'],0)

    def test_unchanged_cases_keep_previous_identities(self):
        raw={'case_id':'fixture','rep':1,'variant':'skills'}
        for cid in ['H01','H03','H04','H10']:
            with self.subTest(cid=cid):
                self.assertEqual(v3.identity(CASES[cid],raw),v3.legacy.identity(CASES[cid],raw))
        for cid in ['H08','H09']:
            with self.subTest(cid=cid):
                self.assertNotEqual(v3.identity(CASES[cid],raw),v3.legacy.identity(CASES[cid],raw))

    def test_only_h09_semantic_prompt_changes(self):
        for cid in ['H03','H08','H09']:
            case=CASES[cid];original=copy.deepcopy(case)
            actual=v3.corrected_prompt(case,'candidate',[],{}, {}, {})
            previous=v3.legacy.corrected_prompt(case,'candidate',[],{}, {}, {})
            if cid=='H09':
                self.assertNotEqual(actual,previous)
                self.assertIn('不限定必须缺键',actual)
                self.assertIn('不要求额外修复建议',actual)
            else:self.assertEqual(actual,previous)
            self.assertEqual(case,original)

    def test_report_and_score_identity_share_same_binding(self):
        report=Mock()
        report.pair_validity=lambda case,a,b:['target skill body read was not observed']
        v3.install_report(report)
        self.assertIs(report.grading_identity,v3.identity)
        self.assertIsNot(report.pair_validity,None)

    def test_full_body_read_fix_delegated_without_source_change(self):
        relative='skills/teaching-reconstruction/SKILL.md'
        body=(v3.scoring.ROOT/relative).read_bytes()
        raw={'skill_setup':{'target':'teaching-reconstruction'},
             'source_files':{relative:hashlib.sha256(body).hexdigest()},
             'events':[{'type':'item.completed','item':{'id':'x','type':'command_execution',
                 'exit_code':1,'aggregated_output':body.decode()+'\nlater command failed'}}]}
        self.assertEqual(v3.legacy.full_body_read(raw),['x'])
        raw['events'][0]['item']['aggregated_output']=body.decode()[:100]
        self.assertEqual(v3.legacy.full_body_read(raw),[])


if __name__=='__main__':unittest.main()
