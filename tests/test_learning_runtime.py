"""Behavioral checks: stale intent cannot perform curation; safe work can recover."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from learning_workflow import runtime as r, hooks


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.work=self.base/'project'; self.work.mkdir()
        self.q=self.base/'query.txt'; self.q.write_text('只整理这个项目的笔记，不发布。')
        self.decision={'activity':'curation','interaction_mode':'direct','workspace_context':'repository',
                       'selected_skills':[],'excluded_actions':['external_publish','zotero_mutation'],
                       'material_refs':[],'output_targets':['notes'],'rationale':'User requested explicit curation.',
                       'unresolved':[],'authorized_actions':['curate'],'project_id':'test-project'}
        self.root=Path(r.init(self.q,self.decision,self.work,'session-a')['record'])
        self.source=self.work/'lesson.md'; self.source.write_text('# Lesson\n\nAn evidence-bounded note.\n')
        self.state=self.base/'hooks'

    def event(self,name,**extra):
        return dict(hook_event_name=name,session_id='session-a',cwd=str(self.work),**extra)

    def test_changed_input_blocks_real_entry_but_read_and_classify_recover(self):
        self.q.write_text('先不要整理，先回答我。')
        r.input_record(self.root,'turn-2',self.q)
        with self.assertRaisesRegex(r.RouteError,'unclassified'):
            r.curate(self.root,self.source,'notes','Lesson','test',2)
        self.assertFalse((self.work/'notes').exists())
        self.assertEqual(r.check_action(self.root,'read',base_revision=1)['status'],'allowed')
        changed=dict(self.decision,activity='answer',authorized_actions=[])
        with self.assertRaisesRegex(r.RouteError,'revision conflict'):
            r.classify(self.root,'turn-2',changed,1)
        r.classify(self.root,'turn-2',changed,2)
        with self.assertRaisesRegex(r.RouteError,'explicit curation'):
            r.curate(self.root,self.source,'notes','Lesson','test',3)

    def test_input_and_classification_retries_do_not_overwrite_newer_decision(self):
        self.q.write_text('继续整理。'); r.input_record(self.root,'t2',self.q)
        r.classify(self.root,'t2',self.decision,2)
        self.q.write_text('改为直接写稿。'); r.input_record(self.root,'t3',self.q)
        new=dict(self.decision,activity='writing',authorized_actions=[])
        r.classify(self.root,'t3',new,4)
        retried=r.classify(self.root,'t2',self.decision,2)
        self.assertEqual(retried['decision']['activity'],'writing')
        self.assertEqual(retried['route_revision'],5)
        with self.assertRaisesRegex(r.RouteError,'different bytes'):
            r.input_record(self.root,'t2',self.q)

    def test_out_of_order_pending_classification_preserves_latest_exclusions(self):
        r.input_record(self.root,'older',self.q)
        self.q.write_text('Do not curate; answer only.')
        r.input_record(self.root,'newer',self.q)
        latest=dict(self.decision,activity='answer',authorized_actions=[])
        r.classify(self.root,'newer',latest,3)
        with self.assertRaisesRegex(r.RouteError,'older input'):
            r.classify(self.root,'older',self.decision,4)
        resolved=r.classify(self.root,'older',latest,4)
        self.assertEqual(resolved['decision']['activity'],'answer')
        self.assertFalse(any(x['status']=='pending' for x in resolved['inputs'].values()))

    def test_task_session_and_workspace_binding_are_isolated(self):
        hooks.bind(self.root,'session-a',self.work,self.state)
        with self.assertRaisesRegex(r.RouteError,'does not match'):
            hooks.bind(self.root,'session-b',self.work,self.state)
        other=hooks.process(dict(hook_event_name='UserPromptSubmit',session_id='session-b',cwd=str(self.work),prompt='Stop'),self.state)
        self.assertIn('Short answers need no record',str(other))
        self.assertEqual(r.read(self.root)['route_revision'],1)
        hooks.process(self.event('UserPromptSubmit',prompt='先不要整理',turn_id='second'),self.state)
        self.assertEqual(r.read(self.root)['route_revision'],2)
        hooks.process(self.event('UserPromptSubmit',prompt='先不要整理',turn_id='second'),self.state)
        self.assertEqual(r.read(self.root)['route_revision'],2)

    def test_hook_covers_known_entry_not_all_shell_and_stop_is_bounded(self):
        hooks.bind(self.root,'session-a',self.work,self.state,on_stop=True)
        hooks.process(self.event('UserPromptSubmit',prompt='Wait',turn_id='2'),self.state)
        for tool,inp in [('Bash',{'command':'learning-workflow curate --record somewhere'}),('exec_command',{'cmd':'python3 -m learning_workflow curate --record somewhere'})]:
            result=hooks.process(self.event('PreToolUse',tool_name=tool,tool_input=inp),self.state)
            self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(hooks.process(self.event('PreToolUse',tool_name='Bash',tool_input={'command':'cat lesson.md'}),self.state),{})
        self.assertEqual(hooks.process(self.event('Stop'),self.state)['decision'],'block')
        self.assertEqual(hooks.process(self.event('Stop'),self.state),{})

    def test_missing_record_does_not_silently_allow_known_entry(self):
        hooks.bind(self.root,'session-a',self.work,self.state)
        (self.root/'routing.json').unlink()
        result=hooks.process(self.event('PreToolUse',tool_name='Bash',tool_input={'command':'learning-workflow curate --record somewhere'}),self.state)
        self.assertEqual(result['hookSpecificOutput']['permissionDecision'],'deny')
        self.assertEqual(hooks.process(self.event('PreToolUse',tool_name='Bash',tool_input={'command':'cat lesson.md'}),self.state),{})

    def test_request_integrity_and_symlink_output_escape(self):
        (self.work/'notes').symlink_to(self.base/'outside',target_is_directory=True)
        # Resolved declared outputs follow the same location; authority is path based.
        # A narrower declared file cannot authorize its sibling.
        data=r.read(self.root); data['decision']['output_targets']=['allowed/result.md']; r.save(self.root,data)
        with self.assertRaisesRegex(r.RouteError,'outside declared'):
            r.curate(self.root,self.source,'notes','Lesson','test',1)
        (self.root/'request.txt').write_text('tampered')
        with self.assertRaisesRegex(r.RouteError,'snapshot changed'):
            r.read(self.root)

    def test_curation_is_deduplicated_relocatable_and_preserves_edits(self):
        first=r.curate(self.root,self.source,'notes','Lesson','test',1)
        second=r.curate(self.root,self.source,'notes','Lesson','test',1)
        self.assertEqual(first,second)
        index=r.load(first['index']); self.assertEqual(len(index['entries']),1)
        entry=next(iter(index['entries'].values())); self.assertEqual(entry['source_path'],'lesson.md')
        moved=self.base/'relocated'; shutil.copytree(self.work/'notes',moved)
        self.assertTrue(next(iter(r.inspect_index(moved/'artifact-index.json',self.work).values()))['artifact_unchanged'])
        self.source.unlink()
        self.assertEqual(next(iter(r.inspect_index(moved/'artifact-index.json',self.work).values()))['source_status'],'unavailable')
        self.source.write_text('new source'); Path(first['artifact']).write_text('user edits')
        with self.assertRaisesRegex(r.RouteError,'preserve edits'):
            r.curate(self.root,self.source,'notes','Lesson','test',1)

    def test_curation_requires_project_identity_before_writing(self):
        rec=r.read(self.root); del rec['decision']['project_id']; r.save(self.root,rec)
        with self.assertRaisesRegex(r.RouteError,'stable project_id'):
            r.curate(self.root,self.source,'notes','Lesson','test',1)
        self.assertFalse((self.work/'notes').exists())

    def test_curation_cannot_write_its_own_routing_directory(self):
        rec=r.read(self.root); rec['decision']['output_targets']=['.']; r.save(self.root,rec)
        with self.assertRaisesRegex(r.RouteError,'outside routing state'):
            r.curate(self.root,self.source,self.root,'Lesson','test',1)

    def test_library_scope_and_remote_read_never_grant_execution(self):
        rec=r.read(self.root)
        with self.assertRaisesRegex(r.RouteError,'ReadPapers'):
            r.check(rec,'zotero_read',base_revision=1)
        rec['decision'].update(authorized_actions=['remote_read'],authorized_read_roots=['testhost:/repo'])
        self.assertEqual(r.check(rec,'remote_read','testhost:/repo/file.py',1)['status'],'allowed')
        with self.assertRaisesRegex(r.RouteError,'outside'):
            r.check(rec,'remote_read','testhost:/repository/file.py',1)
        for target in ['testhost:/repo/../secret','testhost:/repo/./file','testhost:/repo//file','otherhost:/repo/file']:
            with self.assertRaises(r.RouteError):
                r.check(rec,'remote_read',target,1)
        with self.assertRaisesRegex(r.RouteError,'not execution authority'):
            r.check(rec,'experiment',base_revision=1)

    def test_outside_library_request_cannot_be_declared_authorized(self):
        wrong=dict(self.decision,activity='learning',selected_skills=['read-paper'],authorized_actions=['zotero_mutation'])
        with self.assertRaisesRegex(r.RouteError,'already configured ReadPapers'):
            r.init(self.q,wrong,self.work,'session-b',record=self.work/'wrong')
        self.assertFalse((self.work/'wrong').exists())
        r.input_record(self.root,'library-request',self.q)
        with self.assertRaisesRegex(r.RouteError,'already configured ReadPapers'):
            r.classify(self.root,'library-request',wrong,2)
        # A pre-migration invalid declaration remains inspectable and recoverable.
        legacy=r.read(self.root); legacy['decision']=wrong; r.save(self.root,legacy)
        self.assertEqual(r.check_action(self.root,'read',base_revision=2)['status'],'allowed')
        handoff=dict(self.decision,activity='answer',authorized_actions=[])
        self.assertEqual(r.classify(self.root,'library-request',handoff,2)['decision']['activity'],'answer')
        # A separate explicitly configured project can select the same adapter.
        valid=dict(wrong,workspace_context='readpapers',readpapers_root=str(self.work))
        self.assertEqual(r.init(self.q,valid,self.work,'session-c',record=self.work/'valid')['route_revision'],1)

    def test_missing_skill_fails_dependent_action_but_read_works(self):
        rec=r.read(self.root); rec['decision']['selected_skills']=['unavailable']; rec['decision']['skill_roots']=[str(self.base/'empty')]
        r.save(self.root,rec)
        with self.assertRaisesRegex(r.RouteError,'unavailable'):
            r.curate(self.root,self.source,'notes','Lesson','test',1)
        self.assertEqual(r.check_action(self.root,'read',base_revision=1)['status'],'allowed')

    def test_project_skill_discovery_and_recovery_keep_the_existing_record(self):
        # The project-only installation must work without a user-level alias.
        skill=self.work/'.agents/skills/read-paper/SKILL.md'
        skill.parent.mkdir(parents=True); skill.write_text('# Project adapter\n')
        d=dict(self.decision,activity='learning',workspace_context='readpapers',
               readpapers_root=str(self.work),selected_skills=['read-paper'],
               authorized_actions=['zotero_read'])
        root=Path(r.init(self.q,d,self.work,'project-session',record=self.work/'project-record')['record'])
        from unittest.mock import patch
        with patch.object(Path,'home',return_value=self.base/'isolated-home'):
            self.assertEqual(r.check_action(root,'zotero_read',base_revision=1)['status'],'allowed')
            skill.unlink()
            with self.assertRaisesRegex(r.RouteError,'capability unavailable'):
                r.check_action(root,'zotero_read',base_revision=1)
            # An inspected nonstandard root is a correction, not a new task/authority.
            other=self.work/'custom-skills/read-paper/SKILL.md'
            other.parent.mkdir(parents=True); other.write_text('# Adapter\n')
            r.input_record(root,'capability-recovery',root/'request.txt')
            fixed=dict(d,skill_roots=[str(other.parents[1])],rationale='Same request; inspected adapter path corrected.')
            r.classify(root,'capability-recovery',fixed,2)
            self.assertEqual(r.check_action(root,'zotero_read',base_revision=3)['status'],'allowed')
            self.assertEqual(r.read(root)['session_id'],'project-session')
            self.assertEqual(len(list((self.work/'project-record').rglob('routing.json'))),1)

    def test_cli_rejects_pending_without_hook(self):
        r.input_record(self.root,'new',self.q)
        result=subprocess.run([sys.executable,'-m','learning_workflow','curate','--record',str(self.root),'--source',str(self.source),'--destination','notes','--title','x','--topic','x','--base-revision','2'],capture_output=True,text=True)
        self.assertEqual(result.returncode,1)
        self.assertIn('unclassified',result.stderr)
        self.assertFalse((self.work/'notes').exists())

    def test_development_sidecar_preserves_existing_authority_and_task_view(self):
        dev=self.work/'dev'; dev.mkdir(); (dev/'checklist.yaml').write_text('revision: 4\n')
        (dev/'task.md').write_text('canonical development state'); (dev/'request.txt').write_text('development request')
        d=dict(self.decision,development_record_ref={'path':str(dev),'revision':4})
        root=Path(r.init(self.q,d,self.work,'session-a')['record'])
        self.assertEqual(root,dev)
        self.assertEqual((dev/'task.md').read_text(),'canonical development state')
        self.assertEqual((dev/'request.txt').read_text(),'development request')
        self.assertTrue((dev/'routing.md').exists())


if __name__=='__main__':
    unittest.main()
