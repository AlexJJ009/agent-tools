import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import evaluate as regression


class RegressionTests(unittest.TestCase):
    def test_copied_packages_checked_against_main_before_model(self):
        runner=regression.field.runner()
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)/'home';folder=home/'.agents/skills/cleaner';folder.mkdir(parents=True)
            (folder/'SKILL.md').write_text('expected main bytes')
            manifest=Path(tmp)/'expected.json'
            sha=hashlib.sha256(b'expected main bytes').hexdigest()
            manifest.write_text(json.dumps({'main_commit':'abc123','files':{'skills/cleaner/SKILL.md':sha}}))
            plan={'packages':['cleaner'],'resources':[]}
            with patch.dict(os.environ,{'AGENT_TOOLS_EVAL_EXPECTED_SKILLS':str(manifest)}):
                runner.verify_installed_skills(plan,home)
                self.assertTrue(plan['merged_main_copy_audit']['verified_before_model_start'])
                self.assertEqual(plan['merged_main_copy_audit']['main_commit'],'abc123')
                (folder/'unexpected.md').write_text('extra')
                with self.assertRaisesRegex(RuntimeError,'differs from merged main'):runner.verify_installed_skills(plan,home)
                (folder/'unexpected.md').unlink();(folder/'SKILL.md').write_text('stale bytes')
                with self.assertRaisesRegex(RuntimeError,'differs from merged main'):runner.verify_installed_skills(plan,home)

    def test_matrix_uses_final_h01_review(self):
        for action in ['score','report']:
            self.assertEqual(regression.matrix.SUITES['challenge'][action][0],'skill-suite-model-matrix-review/reviewed_h01.py')

    def test_retry_policy_never_repeats_quality_or_budget_timeout(self):
        self.assertEqual(regression.retry_class({'status':'ok','output':'wrong answer'}),'complete')
        self.assertEqual(regression.retry_class({'status':'error','error':'timeout'}),'budget_timeout')
        raw={'status':'error','error':'cli_execution','events':[{'type':'turn.failed','error':{'message':'workspace routing discovery failed'}}]}
        self.assertEqual(regression.retry_class(raw),'transport_interruption')
        raw['events'][0]['error']['message']='Selected model is at capacity. Please try a different model.'
        self.assertEqual(regression.retry_class(raw),'serving_capacity')
        raw['events']=[]
        self.assertEqual(regression.retry_class(raw),'unclassified_infrastructure')

    def test_source_aliases_resolve_to_current_checkout(self):
        self.assertEqual(regression.path_for('@mechanisms/run_mechanisms.py'),regression.HERE.parent/'skill-suite-mechanisms/run_mechanisms.py')
        self.assertEqual(regression.path_for('@expected_skills:/tmp/main-files.json'),Path('/tmp/main-files.json'))

    def test_full_inventory_is_25_cases(self):
        total=sum(len(regression.matrix.dataset(s)) for s in regression.matrix.SUITES)+len(regression.field.cases())
        self.assertEqual(total,25)
        self.assertEqual(total*len(regression.matrix.MODELS)*4,400)


if __name__=='__main__':unittest.main()
