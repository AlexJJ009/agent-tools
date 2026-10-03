import json
from pathlib import Path
import tempfile
import unittest
from learning_workflow import runtime as r, hooks, hook_registration as reg


def setUpModule():
    """Producers append to the agent-tools material ledger; keep it out of the user's data root."""
    global _LEDGER_TMP, _LEDGER_ENV
    import json as _json, os as _os, tempfile as _tempfile
    from pathlib import Path as _Path
    from unittest import mock as _mock
    _LEDGER_TMP = _tempfile.TemporaryDirectory(prefix='agent-tools-test-ledger-')
    config = _Path(_LEDGER_TMP.name) / 'config'
    (config / 'agent-tools').mkdir(parents=True)
    (config / 'agent-tools/config.json').write_text(_json.dumps({'data_root': str(_Path(_LEDGER_TMP.name) / 'data')}))
    _LEDGER_ENV = _mock.patch.dict(_os.environ, {'XDG_CONFIG_HOME': str(config), 'XDG_DATA_HOME': str(_Path(_LEDGER_TMP.name) / 'xdg-data')})
    _LEDGER_ENV.start()


def tearDownModule():
    _LEDGER_ENV.stop()
    _LEDGER_TMP.cleanup()


class ScopedTeachingTests(unittest.TestCase):
    def test_binding_scopes_validation_to_current_requested_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); work=root/'work'; work.mkdir(); state=root/'state'
            query=root/'query'; query.write_text('Deliver lesson.md as teaching artifact.')
            decision={'activity':'learning','interaction_mode':'direct','workspace_context':'repository',
                      'selected_skills':[],'excluded_actions':[],'material_refs':[],
                      'output_targets':['lesson.md','other.md'],'rationale':'Requested teaching output.',
                      'unresolved':[]}
            record=Path(r.init(query,decision,work,'session',record=root/'record')['record'])
            artifact=work/'lesson.md'; artifact.write_text('# Requested teaching delivery with missing manifest\n')
            event={'hook_event_name':'Stop','session_id':'session','cwd':str(work)}
            self.assertEqual(hooks.process(event,state),{})
            hooks.bind(record,'session',work,state,teaching_artifacts=['lesson.md'])
            self.assertIn('MANIFEST_MISSING',hooks.process(event,state)['reason'])
            artifact.unlink()
            self.assertIn('READ_ERROR',hooks.process(event,state)['reason'])
            good=Path(__file__).parent/'fixtures/teaching/good_artifact.md'
            artifact.write_text(good.read_text())
            hooks.bind(record,'session',work,state,on_stop=True)
            self.assertIn('other.md',hooks.process(event,state)['reason'])
            hooks.bind(record,'session',work,state,on_stop=False)
            self.assertEqual(hooks.process(dict(event,session_id='other'),state),{})
            query.write_text('Now answer status only.')
            r.input_record(record,'next',query)
            self.assertEqual(hooks.process(event,state),{})
            hooks.bind(record,'session',work,state,on_stop=True)
            self.assertIn('pending input=True',hooks.process(event,state)['reason'])
            self.assertEqual(hooks.process(event,state),{})
            with self.assertRaisesRegex(r.RouteError,'current output'):
                hooks.bind(record,'session',work,state,teaching_artifacts=['old.md'])

    def test_registration_identity_requires_the_actual_teaching_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            for command in (
                'echo .codex/teaching_stop_filter.py',
                'cat .codex/teaching_stop_filter.py',
                'python3 unrelated.py .codex/teaching_stop_filter.py',
                'python3 /unrelated/teaching_stop_filter.py',
                'python3 -c "print(1)" .codex/teaching_stop_filter.py',
            ):
                with self.subTest(command=command):
                    self.assertFalse(reg.teaching_handler({'type':'command','command':command},directory))
            self.assertTrue(reg.teaching_handler({'type':'command','command':'/usr/bin/env python3 .codex/teaching_stop_filter.py'},directory))

    def test_both_host_formats_migrate_and_rollback_without_touching_foreign_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp); config=home/'.codex'; config.mkdir()
            script=home/'skills/teaching-reconstruction/scripts/stop_validate.py'
            script.parent.mkdir(parents=True); script.touch()
            alias=home/'alias.py'; alias.symlink_to(script)
            teaching={'type':'command','command':f'/usr/bin/env python3 {alias}'}
            foreign={'type':'command','command':'echo keep'}
            groups=[{'hooks':[teaching,foreign]}]
            (config/'hooks.json').write_text(json.dumps({'hooks':{'Stop':groups}}))
            (config/'config.toml').write_text('[features]\nhooks = true\n[hooks]\nStop = '+reg.inline(groups)+'\n')
            edits=reg.prepare(home)
            self.assertEqual(len(edits),2)
            reg.apply(edits)
            self.assertEqual(reg.prepare(home),[])
            self.assertIn('echo keep',(config/'config.toml').read_text())
            reg.check(edits)
            reg.apply(edits,restore=True)
            self.assertEqual(len(reg.prepare(home)),2)
