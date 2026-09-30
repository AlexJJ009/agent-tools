"""Regression checks for harness protocol validation and external observations."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('run_eval',Path(__file__).with_name('run_eval.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def events(text='done',usage=None,model=None):
    completion={'type':'turn.completed','usage':usage or {'input_tokens':12,'output_tokens':2,'cached_input_tokens':3}}
    if model:completion['model']=model
    return [{'type':'item.completed','item':{'type':'agent_message','text':text}},completion]

class HarnessChecks(unittest.TestCase):
    def test_protocol(self):
        self.assertIsNone(r.validate_completion(events(),0,'gpt-5.5'))
        self.assertEqual(r.validate_completion(events(''),0,'gpt-5.5'),'missing_final_output')
        self.assertEqual(r.validate_completion(events(model='other'),0,'gpt-5.5'),'serving_substitution')
        self.assertEqual(r.validate_completion(events(usage={'input_tokens':1,'output_tokens':2,'cached_input_tokens':3}),0,'gpt-5.5'),'invalid_token_usage')
        self.assertEqual(r.validate_completion(events()+[{'type':'turn.failed'}],0,'gpt-5.5'),'cli_execution')
    def test_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'broken').symlink_to('/does-not-exist');(p/'outside').symlink_to('/etc',target_is_directory=True)
            snap=r.snapshot(p)
            self.assertEqual(snap['broken'],{'symlink':'/does-not-exist'})
            self.assertEqual(snap['outside'],{'symlink':'/etc'})
            self.assertEqual(len(snap),2)
    def test_timeout_is_infrastructure(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.subprocess,'run',side_effect=subprocess.TimeoutExpired('check',30)):
            result=r.run_check('pass',tmp)
            self.assertTrue(result['infra_error'])
    def test_hidden_check_cannot_mutate_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'workspace';workspace.mkdir()
            (workspace/'evidence.txt').write_text('original')
            result=r.run_check("from pathlib import Path;Path('evidence.txt').write_text('changed');Path('new.txt').write_text('new')",workspace)
            self.assertEqual(result['returncode'],0,result)
            self.assertEqual((workspace/'evidence.txt').read_text(),'original')
            self.assertFalse((workspace/'new.txt').exists())
    def test_bootstrap_failure_is_infra(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','bwrap: execvp python3: No such file or directory')):
            self.assertTrue(r.run_check('assert False',tmp)['infra_error'])
    def test_candidate_assertion_is_not_infra(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=r.run_check('assert False, "candidate regression"',tmp)
            self.assertNotEqual(result['returncode'],0)
            self.assertFalse(result['infra_error'])
            self.assertIn('candidate regression',result['stderr'])
            self.assertNotIn('EVAL_CHECK_STARTED_',result['stderr'])
    def test_observer_create_then_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);work=p/'workspace';work.mkdir()
            obs=r.FileObserver({'workspace':work},p/'events.jsonl')
            (work/'temporary.md').write_text('temporary');time.sleep(.15)
            (work/'temporary.md').unlink();time.sleep(.15)
            result=obs.close()
            matching=[e for e in result['events'] if e.get('path')=='temporary.md']
            self.assertTrue(any(e['mask'] & 0x100 for e in matching))
            self.assertTrue(any(e['mask'] & 0x200 for e in matching))
            self.assertFalse(result['overflow'])

if __name__=='__main__':unittest.main()
