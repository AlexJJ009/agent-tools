"""Real ignored files, Git boundaries and interruptible cleanup operations."""
import concurrent.futures
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow.process_cleanup import run_cleanup, read_cleanup, abort_cleanup
from agent_workflow.task_store import TaskError


class Crash(BaseException):
    pass


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        self.git('init', '-q')
        (self.repo / '.gitignore').write_text('scratch/\n')
        (self.repo / 'scratch').mkdir()
        self.data = self.root / 'data'
        self.packet = dict(workspace=str(self.repo), task_id='task-1', operation_id='cleanup-1',
                           authorization=dict(quote='Remove these reviewed files', source_ref='turn-7'),
                           process_materials_reviewed=True, rationale='Expired process output.',
                           process_roots=['scratch'], files=[])
        self.add('scratch/a.txt', 'archive')
        self.add('scratch/b.txt', 'delete')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True, check=True)

    def add(self, name, disposition):
        p = self.repo / name
        p.write_text(name)
        self.packet['files'].append(dict(path=name, disposition=disposition, category='process-output',
                                         sha256=hashlib.sha256(p.read_bytes()).hexdigest()))

    def run_packet(self, **kwargs):
        return run_cleanup(self.data, self.packet, **kwargs)

    def fail(self, code, packet=None):
        with self.assertRaises(TaskError) as cm:
            run_cleanup(self.data, packet or self.packet)
        self.assertEqual(cm.exception.code, code)

    def test_archive_delete_and_exact_replay(self):
        result = self.run_packet()
        self.assertEqual(result['status'], 'complete')
        self.assertFalse((self.repo/'scratch/a.txt').exists())
        self.assertFalse((self.repo/'scratch/b.txt').exists())
        archives = list(self.data.rglob('*.archive'))
        self.assertEqual([p.read_text() for p in archives], ['scratch/a.txt'])
        self.assertEqual(self.run_packet(), result)
        self.packet['rationale'] = 'Different request'
        self.fail('idempotency_conflict')

    def test_faults_recover_with_exact_packet(self):
        for stage in ['planned', 'archived', 'quarantined', 'committed', 'disposed']:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                data = Path(tmp)/'data'
                for item in self.packet['files']:
                    (self.repo/item['path']).write_text(item['path'])
                def fault(actual, index):
                    if actual == stage:
                        raise Crash()
                with self.assertRaises(Crash):
                    run_cleanup(data, self.packet, fault=fault)
                self.assertEqual(run_cleanup(data, self.packet)['status'], 'complete')

    def test_abort_restores_before_commit(self):
        def fault(stage, index):
            if stage == 'quarantined':
                raise Crash()
        with self.assertRaises(Crash):
            self.run_packet(fault=fault)
        result = abort_cleanup(self.data, 'task-1', 'cleanup-1')
        self.assertEqual(result['status'], 'aborted')
        for item in self.packet['files']:
            self.assertEqual((self.repo/item['path']).read_text(), item['path'])
        self.fail('operation_aborted')

    def test_abort_replay_does_not_touch_later_files(self):
        def fault(stage, index):
            if stage == 'quarantined':
                raise Crash()
        with self.assertRaises(Crash):
            self.run_packet(fault=fault)
        result = abort_cleanup(self.data, 'task-1', 'cleanup-1')
        (self.repo/'scratch/a.txt').unlink()
        quarantine = Path(result['entries'][0]['quarantine'])
        quarantine.write_text('unrelated later file')
        self.assertEqual(abort_cleanup(self.data, 'task-1', 'cleanup-1'), result)
        self.assertEqual(quarantine.read_text(), 'unrelated later file')
        self.assertFalse((self.repo/'scratch/a.txt').exists())

    def test_abort_after_commit_rejected(self):
        self.run_packet()
        with self.assertRaises(TaskError) as cm:
            abort_cleanup(self.data, 'task-1', 'cleanup-1')
        self.assertEqual(cm.exception.code, 'already_committed')

    def test_archive_verified_before_source_move(self):
        def fault(stage, index):
            if stage == 'archived':
                self.assertTrue((self.repo/'scratch/a.txt').is_file())
                archive = next(self.data.rglob('*.archive'))
                self.assertEqual(archive.read_text(), 'scratch/a.txt')
                raise Crash()
        with self.assertRaises(Crash):
            self.run_packet(fault=fault)
        self.assertEqual(self.run_packet()['status'], 'complete')

    def test_archive_corruption_preserves_source(self):
        def fault(stage, index):
            if stage == 'archived':
                next(self.data.rglob('*.archive')).write_text('corrupt')
                raise Crash()
        with self.assertRaises(Crash):
            self.run_packet(fault=fault)
        self.fail('content_conflict')
        self.assertTrue((self.repo/'scratch/a.txt').exists())

    def test_changed_source_and_changed_quarantine_rejected(self):
        (self.repo/'scratch/a.txt').write_text('changed')
        self.fail('content_conflict')
        (self.repo/'scratch/a.txt').write_text('scratch/a.txt')
        def fault(stage, index):
            if stage == 'quarantined':
                journal = read_cleanup(self.data, 'task-1', 'cleanup-1')
                Path(journal['entries'][0]['quarantine']).write_text('new bytes')
                raise Crash()
        with self.assertRaises(Crash):
            self.run_packet(fault=fault)
        self.fail('content_conflict')
        abort_cleanup(self.data, 'task-1', 'cleanup-1')
        self.assertEqual((self.repo/'scratch/a.txt').read_text(), 'new bytes')

    def test_all_files_preflight_before_any_move(self):
        self.git('add', '-f', 'scratch/b.txt')
        self.fail('unsafe_path')
        self.assertTrue((self.repo/'scratch/a.txt').exists())
        self.assertFalse(list(self.data.rglob('*.archive')))

    def test_inherited_git_routing_cannot_hide_tracked_files(self):
        self.git('add', '-f', 'scratch/a.txt')
        environment = {'GIT_INDEX_FILE': str(self.root/'alternate-index'),
                       'GIT_WORK_TREE': str(self.root/'elsewhere'),
                       'GIT_DIR': str(self.root/'elsewhere/.git'),
                       'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.worktree',
                       'GIT_CONFIG_VALUE_0': str(self.root/'elsewhere')}
        with patch.dict(os.environ, environment):
            self.fail('unsafe_path')
            self.assertEqual(os.environ['GIT_INDEX_FILE'], environment['GIT_INDEX_FILE'])
        self.assertEqual((self.repo/'scratch/a.txt').read_text(), 'scratch/a.txt')

    def test_unignored_file_and_directory_rejected(self):
        (self.repo/'.gitignore').write_text('')
        self.fail('unsafe_path')
        (self.repo/'.gitignore').write_text('scratch/\n')
        (self.repo/'scratch/a.txt').unlink()
        (self.repo/'scratch/a.txt').mkdir()
        self.fail('unsafe_path')

    def test_paths_and_scope_rejected(self):
        for name in ['../escape', '/tmp/escape', 'scratch/../a', 'scratch/.git/config', 'scratch//a', 'scratch/a\\b', 'other/a']:
            with self.subTest(name=name):
                packet = copy.deepcopy(self.packet)
                packet['files'][0]['path'] = name
                self.fail('unsafe_path', packet)
        for root in ['', '.', '../scratch', '/scratch', '.git']:
            packet = copy.deepcopy(self.packet)
            packet['process_roots'] = [root]
            self.fail('unsafe_path', packet)

    def test_symlink_file_parent_and_nested_repo_rejected(self):
        original = self.repo/'scratch/a.txt'
        original.unlink()
        original.symlink_to(self.repo/'scratch/b.txt')
        self.fail('unsafe_path')
        original.unlink()
        original.write_text('scratch/a.txt')
        (self.repo/'scratch').rename(self.repo/'real')
        (self.repo/'scratch').symlink_to(self.repo/'real', target_is_directory=True)
        self.fail('unsafe_path')
        (self.repo/'scratch').unlink()
        (self.repo/'real').rename(self.repo/'scratch')
        subprocess.run(['git', '-C', str(self.repo/'scratch'), 'init', '-q'], check=True)
        self.fail('workspace_mismatch')

    def test_linked_worktree_is_not_owned_by_parent_workspace(self):
        self.git('add', '.gitignore')
        self.git('-c', 'user.name=Test User', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'fixture')
        self.git('worktree', 'add', '--detach', str(self.repo/'scratch/other'), 'HEAD')
        nested = self.repo/'scratch/other/scratch'
        nested.mkdir()
        target = nested/'other.txt'
        target.write_text('foreign')
        packet = copy.deepcopy(self.packet)
        packet['files'] = [dict(path='scratch/other/scratch/other.txt', sha256=hashlib.sha256(b'foreign').hexdigest(),
                               disposition='delete', category='process-output')]
        self.fail('workspace_mismatch', packet)
        self.assertEqual(target.read_text(), 'foreign')

    def test_concurrent_request_gets_busy_and_can_retry(self):
        import threading
        entered, release = threading.Event(), threading.Event()
        def fault(stage, index):
            if stage == 'planned':
                entered.set()
                release.wait(5)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.run_packet, fault=fault)
            self.assertTrue(entered.wait(5))
            try:
                self.fail('operation_busy')
            finally:
                release.set()
            result = future.result()
        self.assertEqual(self.run_packet(), result)
        self.assertEqual(len(list(self.data.rglob('*.archive'))), 1)

    def test_complete_and_committed_retry_verify_all_archives(self):
        def fault(stage, index):
            if stage == 'disposed' and index == 1:
                raise Crash()
        with self.assertRaises(Crash):
            self.run_packet(fault=fault)
        archive = next(self.data.rglob('*.archive'))
        archive.write_text('corrupt')
        self.fail('content_conflict')
        archive.write_text('scratch/a.txt')
        self.run_packet()
        archive.unlink()
        self.fail('archive_missing')

    def test_authorization_and_category_required(self):
        for mutate in [lambda p:p.update(process_materials_reviewed=False),
                       lambda p:p.update(authorization={}),
                       lambda p:p['files'][0].update(category='document')]:
            packet = copy.deepcopy(self.packet); mutate(packet)
            self.fail('invalid_input', packet)


if __name__ == '__main__':
    unittest.main()
