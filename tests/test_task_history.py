"""Audit visibility and recovery use real task storage and cleanup journals."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from agent_workflow.task_store import Store, TaskError, digest, fingerprint
from agent_workflow.process_cleanup import run_cleanup, abort_cleanup


class Crash(BaseException):
    pass


class TaskHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'; self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / '.gitignore').write_text('scratch/\n')
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        self.store = Store(self.root / 'data')
        self.task = self.store.mutate('create', dict(operation_id='create', workspace=str(self.repo),
                      title='Audit', requirements='private requirements body', criteria=[]))['task_id']
        self.n = 0

    def mutate(self, action, **fields):
        self.n += 1
        return self.store.mutate(action, dict(task_id=self.task, operation_id=f'op-{self.n}',
                                 base_revision=self.store.read(self.task)['revision'], **fields))

    def packet(self):
        (self.repo / 'scratch').mkdir(exist_ok=True)
        p = self.repo / 'scratch/old.txt'; p.write_text('disposable')
        return dict(task_id=self.task, operation_id='legacy-cleanup', workspace=str(self.repo),
                    authorization=dict(quote='delete the obsolete output', source_ref='test-user'),
                    process_materials_reviewed=True, rationale='delivered old output', process_roots=['scratch'],
                    files=[dict(path='scratch/old.txt', sha256=digest(p.read_bytes()), disposition='delete', category='process-output')])

    def test_updates_deletes_and_retries_keep_metadata_not_bodies(self):
        self.mutate('artifact', name='note', content='private artifact body')
        self.mutate('artifact', name='note', content='replacement secret')
        q = dict(task_id=self.task, operation_id='retire', base_revision=self.store.read(self.task)['revision'],
                 names=['note'], rationale='delivered')
        first = self.store.mutate('retire', q)
        self.assertEqual(first, self.store.mutate('retire', q))
        history = self.store.history(self.task, detail=True)
        self.assertEqual(history['total'], 4)
        by_op = {e['operation_id']: e for e in history['events']}
        e = by_op['retire']; self.assertEqual(e['status'], 'done')
        self.assertIsNotNone(e['started_at']); self.assertIsNotNone(e['completed_at'])
        self.assertEqual(e['targets'][0]['name'], 'note'); self.assertIsNone(e['targets'][0]['after'])
        self.assertEqual(e['targets'][0]['before']['sha256'], digest(b'replacement secret'))
        for secret in ['private requirements body', 'private artifact body', 'replacement secret']:
            self.assertNotIn(secret, json.dumps(history))
        self.assertEqual(self.store.history(self.task, limit=1)['total'], 4)
        self.assertTrue(self.store.history(self.task, limit=1)['truncated'])

    def test_interrupted_process_cleanup_visible_and_recovered_by_task(self):
        q = self.packet()
        def fail(stage, index):
            if stage == 'quarantined': raise Crash()
        with self.assertRaises(Crash): run_cleanup(self.store.root, q, fault=fail)
        view = self.store.read(self.task)
        self.assertTrue(view['recovery_pending'])
        self.assertTrue(self.store.history(self.task)['recovery_pending'])
        self.assertEqual(view['cleanup']['pending'], ['legacy-cleanup'])
        self.assertTrue(self.store.list()[0]['recovery_pending'])
        event = next(e for e in self.store.history(self.task)['events'] if e['source'] == 'process-cleanup')
        self.assertEqual(event['status'], 'prepared')
        self.store.recover(self.task)
        self.assertFalse(self.store.read(self.task)['recovery_pending'])
        self.assertFalse((self.repo / 'scratch/old.txt').exists())
        self.assertEqual(self.store.read(self.task)['state'], 'draft')

    def test_committed_receipt_reports_pending_physical_cleanup(self):
        self.mutate('artifact', name='note', content='obsolete')
        q = dict(task_id=self.task, operation_id='committed-crash', base_revision=self.store.read(self.task)['revision'],
                 names=['note'], rationale='retire delivered note')
        def fail(stage):
            if stage == 'committed': raise Crash()
        with self.assertRaises(Crash): Store(self.store.root, fault=fail).mutate('retire', q)
        h = self.store.history(self.task)
        self.assertTrue(h['recovery_pending'])
        self.assertEqual(next(e for e in h['events'] if e['operation_id'] == q['operation_id'])['status'], 'done')
        self.store.recover(self.task)
        self.assertFalse(self.store.history(self.task)['recovery_pending'])

    def test_cancelled_attempt_is_auditable_and_old_receipt_dates_unknown(self):
        self.mutate('artifact', name='note', content='keep on abort')
        q = dict(task_id=self.task, operation_id='cancel-me', base_revision=self.store.read(self.task)['revision'],
                 names=['note'], rationale='test cancellation')
        def fail(stage):
            if stage == 'file_deleted': raise Crash()
        with self.assertRaises(Crash): Store(self.store.root, fault=fail).mutate('retire', q)
        self.store.abort(self.task, 'cancel-me')
        e = next(e for e in self.store.history(self.task, True)['events'] if e['operation_id'] == 'cancel-me')
        self.assertEqual(e['status'], 'cancelled')
        self.assertEqual(self.store.artifact_read(self.task, 'note')['content'], 'keep on abort')
        with self.store.connection(write=True) as db:
            db.execute('UPDATE operations SET result=? WHERE scope=? AND id=?',
                       (json.dumps(dict(task_id=self.task, revision=1, state='draft')), 'create:create', 'create'))
        e = next(e for e in self.store.history(self.task)['events'] if e['operation_id'] == 'create')
        self.assertTrue(e['legacy']); self.assertIsNone(e['started_at']); self.assertIsNone(e['completed_at'])

    def test_queries_do_not_initialize_store_and_history_scope_isolated(self):
        other = Store(self.root / 'absent')
        self.assertEqual(other.history('unknown')['total'], 0)
        self.assertFalse(other.root.exists())
        task2 = self.store.mutate('create', dict(operation_id='other', workspace=str(self.repo), title='other'))['task_id']
        self.assertEqual(self.store.history(task2)['total'], 1)
        self.assertEqual(self.store.history(self.task)['total'], 1)

    def test_pending_cleanup_blocks_forget_and_corrupt_journal_is_visible(self):
        # A closed task can still have separately authorized process cleanup.
        with self.store.connection(write=True) as db:
            t = self.store._task(db, self.task); t['state'] = 'closed'
            db.execute('UPDATE tasks SET body=? WHERE id=?', (json.dumps(t), self.task))
        q = self.packet()
        def fail(stage, index):
            if stage == 'planned': raise Crash()
        with self.assertRaises(Crash): run_cleanup(self.store.root, q, fault=fail)
        with self.assertRaises(TaskError) as cm: self.mutate('forget')
        self.assertEqual(cm.exception.code, 'recovery_pending')
        abort_cleanup(self.store.root, self.task, q['operation_id'])
        journal = next((self.store.root / 'cleanup').glob('*/*/journal.json'))
        journal.write_text('{broken')
        with self.assertRaises(ValueError): self.store.read(self.task)
        with self.assertRaises(ValueError): self.store.history(self.task)

    def test_rejected_cleanup_revalidates_task_after_rebind(self):
        """A failed preflight is not a prepared recovery authorization."""
        from agent_workflow.process_cleanup import workspace_info
        from agent_workflow.task_store import require
        q = self.packet()
        path = self.repo / q['files'][0]['path']
        path.write_text('changed before first attempt')
        def validate(packet):
            task = self.store.read(packet['task_id'])
            require(workspace_info(packet['workspace']) == task['workspace'],
                    'workspace_mismatch', 'current workspace required')
        with self.assertRaises(TaskError):
            run_cleanup(self.store.root, q, validate_task=validate)
        self.assertFalse(self.store.read(self.task)['recovery_pending'])
        other = self.root / 'other'
        subprocess.run(['git', 'init', '-q', str(other)], check=True)
        self.mutate('rebind', workspace=str(other))
        path.write_text('disposable')
        with self.assertRaises(TaskError) as cm:
            run_cleanup(self.store.root, q, validate_task=validate)
        self.assertEqual(cm.exception.code, 'workspace_mismatch')
        self.assertEqual(path.read_text(), 'disposable')

    def test_scoped_recovery_leaves_other_task_journal_untouched(self):
        q1 = self.packet()
        task2 = self.store.mutate('create', dict(operation_id='second-task', workspace=str(self.repo), title='second'))['task_id']
        q2 = copy.deepcopy(q1)
        q2.update(task_id=task2, operation_id='other-cleanup')
        q2['files'][0]['path'] = 'scratch/other.txt'
        (self.repo / 'scratch/other.txt').write_text('disposable')
        def fail(stage, index):
            if stage == 'planned': raise Crash()
        for q in (q1, q2):
            with self.assertRaises(Crash): run_cleanup(self.store.root, q, fault=fail)
        from agent_workflow.process_cleanup import read_cleanup
        before = read_cleanup(self.store.root, task2, q2['operation_id'])
        self.store.recover(self.task)
        self.assertFalse((self.repo / 'scratch/old.txt').exists())
        self.assertEqual((self.repo / 'scratch/other.txt').read_text(), 'disposable')
        self.assertEqual(read_cleanup(self.store.root, task2, q2['operation_id']), before)
        self.assertTrue(self.store.read(task2)['recovery_pending'])

    def test_cleanup_lock_excludes_separate_process_task_mutation(self):
        """The file-journal lock also serializes database-only mutations."""
        import sys
        from agent_workflow.process_cleanup import _lock
        packet = dict(task_id=self.task, operation_id='competing-revise', base_revision=1,
                      title='must not commit while cleanup owns lock')
        code = '''import json,sys
from agent_workflow.task_store import Store,TaskError
try:
 Store(sys.argv[1]).mutate('revise',json.loads(sys.argv[2]))
except TaskError as exc:
 print(exc.code)
else:
 raise SystemExit('unexpected commit')
'''
        with _lock(self.store.root / 'cleanup'):
            result = subprocess.run([sys.executable, '-c', code, str(self.store.root), json.dumps(packet)],
                                    capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'operation_busy')
        self.assertEqual(self.store.read(self.task)['revision'], 1)
        self.assertEqual(self.store.read(self.task)['title'], 'Audit')
