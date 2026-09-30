"""Independent Task Runtime behavior and real crash/recovery checks."""
import concurrent.futures
import copy
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow.task_store import Store, TaskError, data_root, fingerprint

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('task_store_case_oracle', ROOT / 'tests/fixtures/task_runtime/oracle.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class Crash(BaseException):
    pass


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = o.Sandbox()
        self.s = self.sandbox.__enter__()
        self.addCleanup(self.sandbox.__exit__, None, None, None)
        self.store = Store(self.s.data)
        self.counter = 0

    def create(self, title='transform'):
        self.counter += 1
        result = self.store.mutate('create', {
            'operation_id': f'create-{self.counter}', 'workspace': str(self.s.repo),
            'title': title, 'requirements': 'default upper; preserve blank lines',
            'criteria': [dict(id='REQ-MODE', name='Mode default', requirement='default upper', expected='ALPHA'),
                         dict(id='REQ-BLANK', name='Blank lines', requirement='preserve blank lines', expected='blank line retained')]})
        return result['task_id']

    def mutate(self, task, action, **fields):
        self.counter += 1
        request = {'operation_id': f'op-{self.counter}', 'task_id': task,
                   'base_revision': self.store.read(task)['revision'], **fields}
        return self.store.mutate(action, request)

    def result(self, task, item='REQ-MODE', **fields):
        return self.mutate(task, 'result', item_id=item, verification='passed', source='external',
                           method='python transform.py with literal output comparison',
                           watched_paths=['input.txt'], input_digest=fingerprint(self.s.repo, ['input.txt']),
                           **fields)

    def accepted(self, task):
        for item in ('REQ-MODE', 'REQ-BLANK'):
            self.result(task, item)
        self.mutate(task, 'submit')
        self.mutate(task, 'feedback', outcome='accepted', quote='I accept these two checked behaviors.',
                    source_ref='test-user-turn-4', items=['REQ-MODE', 'REQ-BLANK'])

    def close(self, task, dispositions, **fields):
        return self.mutate(task, 'closeout', dispositions=dispositions, documents_reviewed=True,
                           rationale='Reviewed usage; retain durable docs, remove owned scratch.', **fields)

    def assert_code(self, code, callback):
        with self.assertRaises(TaskError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code, str(caught.exception))

    def test_retire_active_artifact_preserves_task_and_replays(self):
        task = self.create()
        self.mutate(task, 'revise', recovery='continue implementation')
        self.mutate(task, 'artifact', name='inventory', content='obsolete inventory')
        before = self.store.read(task, True)
        path = self.store.root / before['artifacts']['inventory']['path']
        request = dict(task_id=task, operation_id='retire-inventory',
                       base_revision=before['revision'], names=['inventory'], rationale='User has received the inventory.')
        result = self.store.mutate('retire', request)
        self.assertEqual(result, self.store.mutate('retire', request))
        after = self.store.read(task, True)
        self.assertFalse(path.exists())
        self.assertEqual(after['artifacts'], {})
        for key in ('state', 'requirements', 'criteria', 'recovery'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after['revision'], before['revision'] + 1)
        self.assert_code('idempotency_conflict', lambda: self.store.mutate('retire', dict(request, rationale='different')))

    def test_retire_rejects_preserved_referenced_and_modified_artifacts(self):
        task = self.create()
        self.mutate(task, 'artifact', name='protected', content='keep', preserve=True)
        self.assert_code('cleanup_blocked', lambda: self.mutate(task, 'retire', names=['protected'], rationale='obsolete'))
        self.mutate(task, 'artifact', name='evidence', content='unique evidence')
        self.result(task, evidence=['evidence'])
        self.mutate(task, 'revise', criteria=[dict(id='REQ-MODE', withdrawn=True)])
        self.assert_code('cleanup_blocked', lambda: self.mutate(task, 'retire', names=['evidence'], rationale='old'))
        self.mutate(task, 'artifact', name='edited', content='original')
        path = self.store.root / self.store.read(task, True)['artifacts']['edited']['path']
        path.write_text('user annotation')
        self.assert_code('artifact_conflict', lambda: self.mutate(task, 'retire', names=['edited'], rationale='old'))
        self.assertEqual(path.read_text(), 'user annotation')

    def test_retire_reference_oracle_detects_disabled_guard(self):
        # Adapted from the historical records/evidence dependency failure.
        # This isolated mutation checks the oracle, not model effectiveness.
        from agent_workflow import task_store
        task = self.create()
        self.mutate(task, 'artifact', name='proof', content='sole evidence')
        self.result(task, evidence=['proof'])
        path = self.store.root / self.store.read(task, True)['artifacts']['proof']['path']
        original_require = task_store.require
        def without_reference_guard(condition, code, message):
            if message != 'artifact is referenced by a result':
                original_require(condition, code, message)
        with patch.object(task_store, 'require', side_effect=without_reference_guard):
            self.mutate(task, 'retire', names=['proof'], rationale='deliberate test fault')
        with self.assertRaises(AssertionError):
            self.assertTrue(path.exists(), 'referenced evidence was lost')

    def test_retire_interruption_abort_and_committed_recovery(self):
        task = self.create()
        self.mutate(task, 'artifact', name='inventory', content='obsolete')
        before = self.store.read(task, True)
        path = self.store.root / before['artifacts']['inventory']['path']
        q = dict(task_id=task, operation_id='retire-crash', base_revision=before['revision'],
                 names=['inventory'], rationale='delivered')
        def fail(stage):
            if stage == 'file_deleted':
                raise Crash()
        with self.assertRaises(Crash):
            Store(self.s.data, fault=fail).mutate('retire', q)
        self.assert_code('recovery_pending', lambda: self.store.read(task))
        self.store.abort(task, q['operation_id'])
        self.assertEqual(path.read_text(), 'obsolete')
        q['operation_id'] = 'retire-after-abort'
        def fail_commit(stage):
            if stage == 'committed':
                raise Crash()
        with self.assertRaises(Crash):
            Store(self.s.data, fault=fail_commit).mutate('retire', q)
        self.assertTrue(self.store.read(task)['recovery_pending'])
        self.store.recover(task)
        self.assertFalse(path.exists())
        self.assertFalse(self.store.read(task)['recovery_pending'])

    def test_queries_do_not_create_storage_and_location_config_is_cwd_independent(self):
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.store.resolve('fresh', self.s.repo)['candidates'], [])
        self.assertFalse(self.s.data.joinpath('tasks.sqlite3').exists())
        config = self.s.root / 'config/agent-tools'; config.mkdir(parents=True)
        (config / 'config.json').write_text(json.dumps({'data_root': str(self.s.root / 'configured')}))
        with patch.dict(os.environ, {'XDG_CONFIG_HOME': str(config.parent)}):
            self.assertEqual(data_root(), self.s.root / 'configured')
            self.assertEqual(data_root(self.s.data), self.s.data)
        self.assert_code('invalid_input', lambda: data_root('relative'))

    def test_checklist_queries_scope_search_ordinals_and_withdrawal(self):
        task = self.create(); other = self.create('other')
        self.mutate(other, 'revise', criteria=[dict(id='OTHER', name='Secret mode', requirement='unique-other', expected='x')])
        full = self.store.checklist(task)
        self.assertEqual([x['id'] for x in full['items']], ['REQ-MODE', 'REQ-BLANK'])
        self.assertEqual(full['revision'], 1)
        self.assertEqual(self.store.checklist(task, search='unique-other')['items'], [])
        match = self.store.checklist(task, search='DEFAULT')['items']
        self.assertEqual(match[0]['matched_fields'], ['name', 'requirement'])
        detail = self.store.checklist(task, item_id='REQ-MODE', detail=True)['items'][0]
        self.assertEqual(detail['expected'], 'ALPHA')
        self.assertEqual((detail['verification'], detail['validity'], detail['user_acceptance']),
                         ('not_run', 'unknown', 'pending'))
        self.mutate(task, 'revise', order=['REQ-BLANK', 'REQ-MODE'])
        self.assertEqual(self.store.checklist(task, ordinal=1)['items'][0]['id'], 'REQ-BLANK')
        self.assertEqual(self.store.checklist(task, item_id='REQ-MODE')['items'][0]['id'], 'REQ-MODE')
        for ordinal in (0, 3):
            self.assert_code('not_found', lambda: self.store.checklist(task, ordinal=ordinal))
        self.assert_code('not_found', lambda: self.store.checklist(task, item_id='missing'))
        self.assert_code('invalid_input', lambda: self.store.checklist(task, ordinal=1, search='mode'))
        self.mutate(task, 'revise', criteria=[{'id': 'REQ-MODE', 'withdrawn': True}])
        self.assert_code('not_found', lambda: self.store.checklist(task, item_id='REQ-MODE'))
        self.assert_code('invalid_input', lambda: self.mutate(task, 'revise', criteria=[{'id':'REQ-MODE', 'name':'reuse'}]))

    def test_h02_feedback_revision_invalidates_only_affected_same_task(self):
        task = self.create(); self.accepted(task)
        old_revision = self.store.read(task)['revision']
        self.mutate(task, 'revise', requirements='default lower; preserve blank lines; do not modify input',
                    affected=['REQ-MODE'], criteria=[{'id':'REQ-MODE', 'requirement':'default lower', 'expected':'alpha'},
                    dict(id='REQ-INPUT', name='Source untouched', requirement='do not modify input', expected='identical bytes')],
                    order=['REQ-INPUT', 'REQ-MODE', 'REQ-BLANK'])
        stale = {'operation_id':'stale-writer', 'task_id':task, 'base_revision':old_revision,
                 'requirements':'default upper'}
        self.assert_code('revision_conflict', lambda: self.store.mutate('revise', stale))
        current = self.store.read(task); rows=current['criteria']
        self.assertEqual(current['task_id'], task)
        o.h02({'requirements': {c['id']:c['requirement'] for c in rows},
               'ordinals':[c['id'] for c in rows], 'stale_write_rejected':True,
               'result_validity': {c['id']:c['validity']=='current' for c in rows}})
        self.assertEqual({c['id']:c['user_acceptance'] for c in rows},
                         {'REQ-INPUT':'pending','REQ-MODE':'invalidated','REQ-BLANK':'accepted'})
        self.assertEqual(len(self.store.list()), 1)

    def test_external_results_dirty_inputs_and_scoped_feedback(self):
        task=self.create()
        self.assert_code('invalid_input', lambda: self.mutate(task,'result',item_id='REQ-MODE',verification='passed',source='runtime',method='fake'))
        self.assert_code('stale_result', lambda: self.mutate(task,'result',item_id='REQ-MODE',verification='passed',source='external',method='observed',input_digest='wrong'))
        self.result(task)
        self.mutate(task,'feedback',outcome='accepted',quote='Mode only.',source_ref='turn-1',items=['REQ-MODE'])
        self.assertEqual(self.store.checklist(task,item_id='REQ-BLANK')['items'][0]['user_acceptance'],'pending')
        before=fingerprint(self.s.repo)
        (self.s.repo/'untracked.txt').write_text('new input')
        self.assertNotEqual(before,fingerprint(self.s.repo))
        self.assertEqual(self.store.checklist(task,item_id='REQ-MODE')['items'][0]['validity'],'current')
        (self.s.repo/'input.txt').write_text('changed')
        row=self.store.checklist(task,item_id='REQ-MODE')['items'][0]
        self.assertEqual((row['verification'],row['validity'],row['user_acceptance']),('passed','stale','invalidated'))
        self.assert_code('stale_result', lambda: self.mutate(task,'feedback',outcome='accepted',quote='Old result.',source_ref='turn-2',items=['REQ-MODE']))

    def test_h03_ambiguous_resume_binding_and_rebind(self):
        task=self.create('task-transform'); self.create('task-preview')
        self.mutate(task,'revise',recovery=json.dumps({'pending':['finish lower-mode output'],
                    'prohibitions':['do not edit source input','do not publish']}))
        resolver=self.store.resolve('new-session',self.s.repo)
        restored=self.store.read(task); recovery=json.loads(restored['recovery'])
        o.h03({'candidates':[c['title'] for c in resolver['candidates']], 'selected':None,**recovery})
        self.mutate(task,'bind',session_id='new-session',workspace=str(self.s.repo))
        self.assertEqual(self.store.resolve('new-session',self.s.repo)['task_id'],task)
        self.assertEqual(self.store.resolve('new-session',self.s.other)['status'],'unbound')
        self.result(task)
        self.mutate(task,'rebind',workspace=str(self.s.other))
        self.assertEqual(self.store.resolve('new-session',self.s.repo)['status'],'unbound')
        self.assertEqual(self.store.read(task)['criteria'][0]['validity'],'stale')

    def test_h04_queries_and_idempotent_retries_do_not_grow(self):
        task=self.create()
        for revision in range(3):
            request={'task_id':task,'operation_id':f'revision-{revision}',
                     'base_revision':self.store.read(task)['revision'],'requirements':f'mode-{revision}'}
            first=self.store.mutate('revise',request)
            before=self.store.read(task); files=o.file_snapshot(self.s.data)
            for _ in range(20):
                self.store.list(); self.store.checklist(task); self.store.resolve('none',self.s.repo)
                self.assertEqual(self.store.mutate('revise',request),first)
            after=self.store.read(task)
            o.h04({'current_requirement':before['requirements'],'task':before},
                  {'current_requirement':after['requirements'],'task':after},files,o.file_snapshot(self.s.data),f'mode-{revision}')
            changed=dict(request,requirements='different')
            self.assert_code('idempotency_conflict',lambda:self.store.mutate('revise',changed))

    def test_concurrent_identical_operation_has_single_revision_and_artifact(self):
        task=self.create()
        request={'operation_id':'same','task_id':task,'base_revision':1,'name':'note','content':'complete'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:Store(self.s.data).mutate('artifact',request),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.store.read(task)['revision'],2)
        self.assertEqual(len(list((self.s.data/'artifacts').rglob('*.txt'))),1)
        self.assertEqual(self.store.artifact_read(task,'note')['content'],'complete')

    def test_concurrent_different_revision_writers_do_not_lose_winner(self):
        task=self.create()
        def write(value):
            try:return Store(self.s.data).mutate('revise',{'operation_id':value,'task_id':task,'base_revision':1,'requirements':value})
            except TaskError as e:return e.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,['first','second']))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertIn(next(r for r in results if isinstance(r,str)),('revision_conflict','recovery_pending'))
        self.assertEqual(self.store.read(task)['revision'],2)

    def test_artifact_publication_faults_recover_complete_version(self):
        for stage in ('prepared','file_written','file_published','before_commit','committed'):
            with self.subTest(stage=stage):
                task=self.create(stage)
                self.mutate(task,'artifact',name='draft',content='old')
                revision=self.store.read(task)['revision']
                request={'operation_id':'replace','task_id':task,'base_revision':revision,'name':'draft','content':'new complete body'}
                def crash(point):
                    if point==stage:raise Crash(point)
                with self.assertRaises(Crash):Store(self.s.data,fault=crash).mutate('artifact',request)
                restarted=Store(self.s.data)
                if stage!='committed':
                    self.assert_code('recovery_pending',lambda:restarted.read(task))
                    restarted.recover(task)
                self.assertEqual(restarted.artifact_read(task,'draft')['content'],'new complete body')
                result=restarted.mutate('artifact',request)
                self.assertEqual(result['revision'],revision+1)
                self.assertFalse(list((self.s.data/'artifacts'/task).glob('*.pending')))
                self.assertEqual(len(list((self.s.data/'artifacts'/task).glob('*.txt'))),1)

    def test_real_process_death_after_publish_then_recover(self):
        task=self.create(); packet=self.s.root/'packet.json'
        packet.write_text(json.dumps({'operation_id':'die','task_id':task,'base_revision':1,'name':'note','content':'durable'}))
        code="import json,os,sys; from agent_workflow.task_store import Store; Store(sys.argv[1],fault=lambda p:os._exit(73) if p=='file_published' else None).mutate('artifact',json.load(open(sys.argv[2])))"
        proc=subprocess.run([sys.executable,'-c',code,str(self.s.data),str(packet)],cwd=ROOT,capture_output=True,timeout=15)
        self.assertEqual(proc.returncode,73,proc.stderr)
        self.assert_code('recovery_pending',lambda:self.store.read(task))
        Store(self.s.data).recover(task)
        self.assertEqual(Store(self.s.data).artifact_read(task,'note')['content'],'durable')

    def test_closeout_delete_fault_recovery_retains_unrelated_files(self):
        task=self.create(); self.mutate(task,'artifact',name='scratch',content='owned')
        self.accepted(task); revision=self.store.read(task)['revision']
        request={'operation_id':'close','task_id':task,'base_revision':revision,'dispositions':{'scratch':'delete'},
                 'documents_reviewed':True,'rationale':'No durable content in scratch.','retain_task':False}
        def crash(point):
            if point=='file_deleted':raise RuntimeError('interrupt after deletion')
        with self.assertRaises(RuntimeError):Store(self.s.data,fault=crash).mutate('closeout',request)
        self.assert_code('recovery_pending',lambda:self.store.read(task))
        self.store.recover(task)
        result=self.store.mutate('closeout',request)
        self.assertEqual(result['state'],'closed')
        self.assertEqual(self.store.read(task)['criteria'],[])
        o.protected_unchanged(self.s.protected)

    def test_cleanup_rejects_preserved_referenced_changed_missing_and_symlink(self):
        for danger in ('preserved','referenced','changed','missing','symlink'):
            with self.subTest(danger=danger):
                task=self.create(danger)
                art=self.mutate(task,'artifact',name='evidence',content='original',preserve=danger=='preserved')
                self.result(task,evidence=['evidence'] if danger=='referenced' else [])
                self.result(task,'REQ-BLANK')
                self.mutate(task,'feedback',outcome='accepted',quote='Accept.',source_ref='turn',items=['REQ-MODE','REQ-BLANK'])
                path=self.s.data/art['artifact']['path']
                if danger=='changed':path.write_text('user edit')
                if danger=='missing':path.unlink()
                if danger=='symlink':
                    path.unlink(); path.symlink_to(self.s.repo/'keep.txt')
                self.assert_code('artifact_conflict' if danger in ('changed','missing') else 'cleanup_blocked',
                                 lambda:self.close(task,{'evidence':'delete'},retain_task=True))
                self.assertNotEqual(self.store.read(task)['state'],'closed')
                o.protected_unchanged(self.s.protected)

    def test_changed_after_preparation_stops_delete_recovery(self):
        task=self.create(); art=self.mutate(task,'artifact',name='scratch',content='old'); self.accepted(task)
        request={'operation_id':'close','task_id':task,'base_revision':self.store.read(task)['revision'],
                 'dispositions':{'scratch':'delete'},'documents_reviewed':True,'rationale':'scratch'}
        def crash(point):
            if point=='prepared':raise Crash()
        with self.assertRaises(Crash):Store(self.s.data,fault=crash).mutate('closeout',request)
        path=self.s.data/art['artifact']['path']; path.write_text('new user content')
        self.assert_code('artifact_conflict',lambda:self.store.recover(task))
        self.assertEqual(path.read_text(),'new user content')
        self.assert_code('recovery_pending',lambda:self.store.read(task))

    def test_external_evidence_edit_invalidates_acceptance_and_closeout(self):
        task=self.create(); art=self.mutate(task,'artifact',name='receipt',content='checked input')
        self.result(task,evidence=['receipt']); self.result(task,'REQ-BLANK')
        self.mutate(task,'feedback',outcome='accepted',quote='Both accepted.',source_ref='turn',items=['REQ-MODE','REQ-BLANK'])
        (self.s.data/art['artifact']['path']).write_text('externally changed receipt')
        item=self.store.checklist(task,item_id='REQ-MODE',detail=True)['items'][0]
        self.assertEqual((item['validity'],item['user_acceptance']),('stale','invalidated'))
        self.assert_code('stale_result',lambda:self.mutate(task,'feedback',outcome='accepted',quote='Again.',source_ref='next-turn',items=['REQ-MODE']))
        self.assert_code('stale_result',lambda:self.close(task,{'receipt':'keep'}))

    def test_prune_release_and_forget_remove_closed_task_receipts(self):
        task=self.create(); art=self.mutate(task,'artifact',name='keep',content='user record',preserve=True)
        self.accepted(task); self.close(task,{'keep':'keep'},retain_task=False)
        self.assert_code('cleanup_blocked',lambda:self.mutate(task,'prune',names=['keep'],rationale='finished'))
        self.assert_code('invalid_input',lambda:self.mutate(task,'artifact-policy',name='keep',preserve=False))
        self.mutate(task,'artifact-policy',name='keep',preserve=False,quote='You can remove this now.',source_ref='release-turn')
        self.mutate(task,'prune',names=['keep'],rationale='User released retained scratch.')
        self.assertFalse((self.s.data/art['artifact']['path']).exists())
        self.mutate(task,'forget')
        self.assertEqual(self.store.list(),[])
        with sqlite3.connect(self.store.db) as db:
            rows=db.execute('SELECT result FROM operations').fetchall()
        self.assertFalse(any(task in (row[0] or '') for row in rows))

    def test_invalid_revision_fields_leave_original_queryable(self):
        task=self.create(); before=self.store.read(task)
        for fields in ({'criteria':[{'id':'REQ-MODE','name':None}]},
                       {'criteria':[{'id':'REQ-MODE','requirement':42}]},
                       {'criteria':[{'id':'REQ-MODE','expected':''}]},
                       {'requirements':[]}, {'recovery':{}}):
            with self.subTest(fields=fields):
                self.assert_code('invalid_input',lambda:self.mutate(task,'revise',**fields))
                self.assertEqual(self.store.read(task),before)
                self.assertEqual(len(self.store.checklist(task,search='default')['items']),1)

    def test_internal_directory_symlink_cannot_redirect_owned_cleanup(self):
        task=self.create(); art=self.mutate(task,'artifact',name='scratch',content='owned')
        self.accepted(task)
        original=self.s.data/art['artifact']['path']; parent=original.parent
        relocated=self.s.data/'unowned-alias-target'; parent.rename(relocated)
        parent.symlink_to(relocated,target_is_directory=True)
        self.assert_code('cleanup_blocked',lambda:self.close(task,{'scratch':'delete'}))
        self.assertEqual((relocated/original.name).read_text(),'owned')

    def test_failed_scoped_feedback_rolls_back_entire_operation(self):
        task=self.create(); self.result(task)
        before=self.store.read(task)
        # First ID is valid; second has no result. No partial acceptance may survive.
        self.assert_code('stale_result',lambda:self.mutate(task,'feedback',outcome='accepted',
                         quote='Both accepted.',source_ref='turn',items=['REQ-MODE','REQ-BLANK']))
        self.assertEqual(self.store.read(task),before)

    def test_create_replay_and_legacy_import_preserve_source_without_promoting_acceptance(self):
        request={'operation_id':'stable-create','workspace':str(self.s.repo),'title':'one task'}
        first=self.store.mutate('create',request)
        self.assertEqual(self.store.mutate('create',request),first)
        self.assert_code('idempotency_conflict',lambda:self.store.mutate('create',dict(request,title='different')))
        legacy=self.s.root/'legacy'; legacy.mkdir()
        (legacy/'request.txt').write_text('Keep original requirement.')
        (legacy/'checklist.yaml').write_text(json.dumps({'repo':str(self.s.repo),'source':{'query_path':'request.txt'},
            'protocols':[{'id':'p','expected':{'value':'same'}}],
            'checklist':[{'id':'AC-1','requirement':'Keep original requirement.','requirement_ref':'p',
                          'agent_status':'passed','human_status':'confirmed'}]}))
        snapshot=o.file_snapshot(legacy)
        result=self.store.mutate('import',{'operation_id':'import','workspace':str(self.s.repo),
                                           'title':'imported','source':str(legacy)})
        item=self.store.checklist(result['task_id'],item_id='AC-1')['items'][0]
        self.assertEqual((item['verification'],item['validity'],item['user_acceptance']),('not_run','unknown','pending'))
        self.assertEqual(o.file_snapshot(legacy),snapshot)
        self.assertFalse((self.s.repo/'docs/_local').exists())

    def test_pending_closeout_stale_workspace_abort_then_recheck(self):
        for stage in ('prepared', 'file_deleted'):
            with self.subTest(stage=stage):
                task=self.create(stage)
                art=self.mutate(task,'artifact',name='scratch',content='original owned bytes')
                self.accepted(task)
                request={'operation_id':'pending-close','task_id':task,'base_revision':self.store.read(task)['revision'],
                         'dispositions':{'scratch':'delete'},'documents_reviewed':True,'rationale':'Remove scratch.'}
                def crash(point):
                    if point==stage:raise Crash()
                with self.assertRaises(Crash):Store(self.s.data,fault=crash).mutate('closeout',request)
                listed=next(t for t in self.store.list() if t['task_id']==task)
                self.assertEqual(listed['state'],'closing')
                self.assertTrue(listed['recovery_pending'])
                path=self.s.data/art['artifact']['path']; trash=Path(str(path)+'.trash')
                if stage=='file_deleted':
                    self.assertFalse(path.exists())
                    self.assertEqual(trash.read_text(),'original owned bytes')
                (self.s.repo/'input.txt').write_text('new input '+stage)
                self.assert_code('stale_result',lambda:self.store.recover(task))
                self.assert_code('recovery_pending',lambda:self.store.read(task))
                self.assertEqual(self.store.abort(task,'pending-close')['status'],'cancelled')
                self.assertEqual(self.store.abort(task,'pending-close')['status'],'cancelled')
                self.assertEqual(path.read_text(),'original owned bytes')
                self.assertFalse(trash.exists())
                self.assert_code('operation_cancelled',lambda:self.store.mutate('closeout',request))
                self.mutate(task,'revise',recovery='Abort preserved scratch; check changed input.')
                self.accepted(task)
                self.assertEqual(self.close(task,{'scratch':'delete'})['state'],'closed')
                self.assertFalse(path.exists())
                o.protected_unchanged(self.s.protected)

    def test_logical_artifact_replacement_never_exposes_mixed_revision(self):
        for finish in ('recover','abort'):
            with self.subTest(finish=finish):
                task=self.create(finish)
                old=self.mutate(task,'artifact',name='same-logical-name',content='old version')
                old_path=self.s.data/old['artifact']['path']
                request={'operation_id':'replace-logical','task_id':task,'base_revision':self.store.read(task)['revision'],
                         'name':'same-logical-name','content':'complete new version'}
                def crash(point):
                    if point=='file_deleted':raise Crash()
                with self.assertRaises(Crash):Store(self.s.data,fault=crash).mutate('artifact',request)
                self.assert_code('recovery_pending',lambda:self.store.artifact_read(task,'same-logical-name'))
                self.assert_code('recovery_pending',lambda:self.store.read(task,detail=True))
                self.assertFalse(old_path.exists())
                self.assertEqual(Path(str(old_path)+'.trash').read_text(),'old version')
                if finish=='recover':
                    self.store.recover(task)
                    current=self.store.artifact_read(task,'same-logical-name')
                    self.assertEqual(current['content'],'complete new version')
                    self.assertEqual(current['revision'],old['revision']+1)
                    self.assertEqual(self.store.mutate('artifact',request)['revision'],current['revision'])
                else:
                    self.store.abort(task,'replace-logical')
                    current=self.store.artifact_read(task,'same-logical-name')
                    self.assertEqual(current['content'],'old version')
                    self.assertEqual(current['revision'],old['revision'])
                self.assertFalse(list(old_path.parent.glob('*.trash')))
                self.assertEqual(len(list(old_path.parent.glob('*.txt'))),1)

    def test_boolean_and_null_inputs_rejected_without_mutation(self):
        task=self.create(); before=self.store.read(task)
        bad_requests=[('revise',{'criteria':[{'id':'REQ-MODE','withdrawn':'false'}]}),
                      ('artifact',{'name':'scratch','content':'bytes','preserve':'false'})]
        for action,fields in bad_requests:
            with self.subTest(action=action):
                self.assert_code('invalid_input',lambda:self.mutate(task,action,**fields))
                self.assertEqual(self.store.read(task),before)
        count=len(self.store.list())
        self.assert_code('invalid_input',lambda:self.store.mutate('create',
                         {'operation_id':'null-title','title':None,'workspace':str(self.s.repo)}))
        self.assertEqual(len(self.store.list()),count)
        self.assertEqual(self.store.checklist(task,item_id='REQ-MODE')['items'][0]['verification'],'not_run')

    def test_scoped_garbage_collection_preserves_other_task_quarantine(self):
        one=self.create('one'); two=self.create('two')
        for task in (one,two):
            self.mutate(task,'artifact',name='scratch',content=task)
            self.accepted(task)
        # Stop both after commit, before their garbage is physically collected.
        paths={}
        for task in (one,two):
            current=self.store.read(task,detail=True)
            path=self.s.data/current['artifacts']['scratch']['path']; paths[task]=Path(str(path)+'.trash')
            request={'operation_id':'gc-close','task_id':task,'base_revision':current['revision'],
                     'dispositions':{'scratch':'delete'},'documents_reviewed':True,'rationale':'Finished scratch.'}
            def crash(point):
                if point=='committed':raise Crash()
            with self.assertRaises(Crash):Store(self.s.data,fault=crash).mutate('closeout',request)
        self.assertEqual(paths[two].read_text(),two)
        self.store.recover(one)
        self.assertFalse(paths[one].exists())
        self.assertEqual(paths[two].read_text(),two)
        self.assertEqual(self.store.read(two)['state'],'closing')
        self.store.recover(two)
        self.assertFalse(paths[two].exists())

    def test_feedback_rejection_accepts_changed_inputs_and_acceptance_is_scoped(self):
        task=self.create()
        self.result(task)
        self.mutate(task,'result',item_id='REQ-BLANK',verification='passed',source='external',
                    method='Independent usage check',watched_paths=['docs/usage.md'],
                    input_digest=fingerprint(self.s.repo,['docs/usage.md']))
        (self.s.repo/'docs/usage.md').write_text('changed documentation')
        # B is stale, but A's observed input and requested acceptance are current.
        self.mutate(task,'feedback',outcome='accepted',quote='Accept mode only.',source_ref='accept-A',items=['REQ-MODE'])
        self.assertEqual(self.store.checklist(task,item_id='REQ-MODE')['items'][0]['user_acceptance'],'accepted')
        self.assertEqual(self.store.checklist(task,item_id='REQ-BLANK')['items'][0]['validity'],'stale')
        (self.s.repo/'input.txt').write_text('new input after review')
        self.mutate(task,'feedback',outcome='rejected',quote='This no longer meets my request.',source_ref='reject-A',items=['REQ-MODE'])
        row=self.store.checklist(task,item_id='REQ-MODE')['items'][0]
        self.assertEqual(row['user_acceptance'],'rejected')
        self.assertEqual(row['validity'],'stale')
        self.assertEqual(self.store.read(task)['state'],'active')

    def test_active_replacement_pending_is_visible_in_all_current_views(self):
        from agent_workflow.task_cli import render_markdown
        task = self.create()
        self.mutate(task, 'artifact', name='scratch', content='old')
        request = dict(operation_id='replace-before-gc', task_id=task,
                       base_revision=self.store.read(task)['revision'], name='scratch', content='new')
        def crash(point):
            if point == 'committed':
                raise Crash()
        with self.assertRaises(Crash):
            Store(self.s.data, fault=crash).mutate('artifact', request)
        for view in (self.store.read(task), self.store.read(task, detail=True),
                     self.store.checklist(task), self.store.checklist(task, detail=True)):
            self.assertTrue(view['recovery_pending'])
            self.assertIn('Recovery pending:', render_markdown(view))
        self.store.recover(task)
        for view in (self.store.read(task), self.store.checklist(task)):
            self.assertFalse(view['recovery_pending'])
            self.assertNotIn('Recovery pending:', render_markdown(view))

    def test_committed_closeout_retry_collects_quarantine_and_clears_pending(self):
        task=self.create(); art=self.mutate(task,'artifact',name='report',content='full private report')
        self.accepted(task)
        request={'operation_id':'closed-before-gc','task_id':task,'base_revision':self.store.read(task)['revision'],
                 'dispositions':{'report':'delete'},'documents_reviewed':True,'rationale':'Report no longer needed.'}
        def crash(point):
            if point=='committed':raise Crash()
        with self.assertRaises(Crash):Store(self.s.data,fault=crash).mutate('closeout',request)
        trash=Path(str(self.s.data/art['artifact']['path'])+'.trash')
        self.assertEqual(trash.read_text(),'full private report')
        listed=next(t for t in self.store.list() if t['task_id']==task)
        self.assertEqual(listed['state'],'closing')
        self.assertTrue(listed['recovery_pending'])
        # Subprocess timeout makes a nested SQLite write-lock deadlock observable.
        packet=self.s.root/'retry-close.json'; packet.write_text(json.dumps(request))
        proc=subprocess.run([sys.executable,'-m','agent_workflow.task_cli','closeout',
                             '--data-root',str(self.s.data),'--input',str(packet)],
                            cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stderr+proc.stdout)
        replay=json.loads(proc.stdout)
        self.assertEqual(replay['revision'],request['base_revision']+1)
        self.assertEqual(replay['state'],'closed')
        self.assertEqual(self.store.mutate('closeout',request),replay)
        self.assertFalse(trash.exists())
        listed=next(t for t in self.store.list() if t['task_id']==task)
        self.assertEqual(listed['state'],'closed')
        self.assertFalse(listed['recovery_pending'])

    def test_changed_unrelated_evidence_does_not_block_recovery_mutations(self):
        task=self.create(); art=self.mutate(task,'artifact',name='receipt',content='old receipt')
        self.result(task,evidence=['receipt'])
        receipt=self.s.data/art['artifact']['path']; receipt.write_text('external edit')
        self.mutate(task,'feedback',outcome='rejected',quote='Reject that result.',source_ref='reject-edited',items=['REQ-MODE'])
        self.assertEqual(self.store.checklist(task,item_id='REQ-MODE')['items'][0]['user_acceptance'],'rejected')
        self.mutate(task,'revise',requirements='Recheck the changed input and receipt.',affected=['REQ-MODE'])
        self.mutate(task,'artifact-policy',name='receipt',preserve=True,quote='Keep my edited receipt.',source_ref='keep-edit')
        self.mutate(task,'rebind',workspace=str(self.s.other))
        current=self.store.read(task,detail=True)
        self.assertEqual(current['workspace']['path'],str(self.s.other))
        self.assertTrue(current['artifacts']['receipt']['preserve'])
        self.assertEqual(receipt.read_text(),'external edit')
        self.assertEqual(current['requirements'],'Recheck the changed input and receipt.')

    def test_new_schema_and_storage_error_are_non_successful_cli_results(self):
        task=self.create()
        with sqlite3.connect(self.store.db) as db:db.execute('PRAGMA user_version=99')
        self.assert_code('schema_version',lambda:self.store.read(task))
        cmd=[sys.executable,'-m','agent_workflow.task_cli','list','--data-root',str(self.s.data)]
        proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(proc.returncode,0)
        self.assertEqual(json.loads(proc.stdout)['code'],'schema_version')
        bad=self.s.root/'not-a-directory'; bad.write_text('sentinel')
        packet=self.s.root/'create.json'; packet.write_text(json.dumps({'operation_id':'new','workspace':str(self.s.repo),'title':'new'}))
        proc=subprocess.run([sys.executable,'-m','agent_workflow.task_cli','create','--data-root',str(bad),'--input',str(packet)],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertNotEqual(proc.returncode,0)
        self.assertEqual(json.loads(proc.stdout)['code'],'storage_unavailable')
        self.assertEqual(bad.read_text(),'sentinel')


if __name__ == '__main__':
    unittest.main()
