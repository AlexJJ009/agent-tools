"""Material ledger, inventory discovery and directory retirement through process-cleanup."""
import contextlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agent_workflow import materials
from agent_workflow.materials_cli import main as materials_main, inventory
from agent_workflow.process_cleanup import run_cleanup
from agent_workflow.task_cli import main as task_main
from agent_workflow.task_store import Store, TaskError, data_root

ROOT = Path(__file__).resolve().parents[1]


def _append_many(args):
    root, worker = args
    for i in range(40):
        materials.record(f'/tmp/material-{worker}-{i}', 'test', 'p' * 300, root=root)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / 'data'

    def test_concurrent_appends_stay_whole_lines(self):
        with multiprocessing.get_context('fork').Pool(6) as pool:
            pool.map(_append_many, [(str(self.data), w) for w in range(6)])
        lines = materials.ledger_path(self.data).read_bytes().splitlines()
        self.assertEqual(len(lines), 240)
        self.assertEqual(len(materials.load(self.data)), 240)
        self.assertEqual({e['schema'] for e in materials.load(self.data)}, {materials.SCHEMA})

    def test_recording_failure_never_raises(self):
        materials.ledger_path(self.data).mkdir(parents=True)  # A directory cannot be appended to.
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertIsNone(materials.record(self.data, 'test', 'x', root=self.data))
        self.assertIn('not recorded', err.getvalue())

    def test_vendored_copies_are_byte_identical(self):
        source = (ROOT / 'shared/materials.py').read_bytes()
        for copy in ('agent_workflow/materials.py', 'learning_workflow/materials.py', 'skills/work-report/scripts/materials.py'):
            self.assertEqual((ROOT / copy).read_bytes(), source, copy)

    def test_task_store_shares_the_resolver(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME': tmp + '/c', 'XDG_DATA_HOME': tmp + '/d'}):
            self.assertEqual(data_root(), materials.data_root())
            Path(tmp, 'c/agent-tools').mkdir(parents=True)
            Path(tmp, 'c/agent-tools/config.json').write_text(json.dumps({'data_root': tmp + '/configured'}))
            self.assertEqual(data_root(), materials.data_root())
            self.assertEqual(materials.ledger_path(), Path(tmp).resolve() / 'configured/materials/ledger.jsonl')


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.repo, self.data = base / 'repo', base / 'data'
        self.repo.mkdir()
        self.git('init', '-q')
        (self.repo / '.gitignore').write_text('docs/_local/\n')
        self.git('add', '.gitignore')
        self.git('-c', 'user.name=T', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'init')
        self.store = Store(self.data)
        self.task = self.store.mutate('create', {
            'operation_id': 'create-1', 'workspace': str(self.repo), 'title': 'inventory',
            'requirements': 'r', 'criteria': [dict(id='AC-1', name='n', requirement='r', expected='e')]})['task_id']
        self.local = self.repo / 'docs/_local'

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True, check=True)

    def cli(self, main, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([*map(str, args), '--data-root', str(self.data)])
        return code, out.getvalue()

    def write(self, rel, text='x'):
        p = self.local / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def test_list_reports_recorded_and_unrecorded_materials(self):
        for i in range(3):
            self.write(f'exp/run1/{i}.log', 'abc')
        self.write('scratch/t/note.md')
        self.write('scratch/t/deep/a/b.txt')
        self.write('reports/r1/report.md')
        code, out = self.cli(materials_main, 'record', '--path', self.local / 'exp', '--purpose', 'shared experiment',
                             '--task', self.task, '--workspace', self.repo)
        self.assertEqual(code, 0, out)
        self.store.mutate('artifact', {'operation_id': 'a-1', 'task_id': self.task, 'base_revision': 1,
                                       'name': 'notes', 'content': 'hello', 'purpose': 'scratch'})
        stray = self.data / 'artifacts' / self.task / 'stray.txt'
        stray.write_text('unregistered')
        code, out = self.cli(materials_main, 'list', '--workspace', self.repo)
        self.assertEqual(code, 0, out)
        value = json.loads(out)
        by_path = {i['path']: i for i in value['materials']}
        exp = by_path[str(self.local / 'exp')]
        self.assertEqual((exp['producer'], exp['kind'], exp['files'], exp['bytes'], exp['exists']), ('agent', 'dir', 3, 9, True))
        artifact = [i for i in value['materials'] if i['producer'] == 'task-runtime']
        self.assertEqual(len(artifact), 1)
        self.assertIn('notes', artifact[0]['purpose'])
        unrecorded = {u['path']: u for u in value['unrecorded']}
        self.assertIn(str(stray), unrecorded)
        # Wholly unrecorded subtrees collapse at material-directory depth.
        self.assertEqual(unrecorded[str(self.local / 'scratch/t')]['files'], 2)
        self.assertIn(str(self.local / 'reports/r1'), unrecorded)
        self.assertNotIn(str(self.local / 'exp/run1'), unrecorded)
        self.assertEqual(value['totals']['unrecorded'], 3)
        code, md = self.cli(materials_main, 'list', '--task', self.task, '--format', 'markdown')
        self.assertIn('shared experiment', md)
        self.assertIn('Totals:', md)

    def test_location_mentions_inventory(self):
        code, out = self.cli(task_main, 'location')
        value = json.loads(out)
        self.assertEqual(value['materials_ledger'], str(self.data / 'materials/ledger.jsonl'))
        self.assertIn('materials list', value['materials'])

    def packet(self, *paths, op='retire-1'):
        args = ['cleanup-packet', '--task', self.task, '--operation-id', op, '--rationale', 'Obsolete experiment output.',
                '--quote', 'delete the old run', '--source-ref', 'turn-3']
        for p in paths:
            args += ['--path', p]
        code, out = self.cli(materials_main, *args)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_directory_retires_as_a_unit_and_ledger_records_removal(self):
        for i in range(50):
            self.write(f'exp/run1/{i}.bin', str(i))
        loose = self.write('scratch/old.txt', 'old')
        self.cli(materials_main, 'record', '--path', self.local / 'exp/run1', '--task', self.task, '--workspace', self.repo)
        packet = self.packet(self.local / 'exp/run1', loose)
        self.assertEqual([f.get('kind', 'file') for f in packet['files']], ['dir', 'file'])
        self.assertEqual(sorted(packet['process_roots']), ['docs/_local/exp', 'docs/_local/scratch'])
        result = run_cleanup(self.data, packet)
        self.assertEqual(result['status'], 'complete')
        self.assertFalse((self.local / 'exp/run1').exists())
        self.assertFalse(loose.exists())
        removed = [e for e in materials.load(self.data) if e['event'] == 'removed']
        self.assertEqual({e['path'] for e in removed}, {str(self.local / 'exp/run1'), str(loose)})
        listed = inventory(self.store, self.repo)
        self.assertNotIn(str(self.local / 'exp/run1'), [i['path'] for i in listed['materials']])
        journals = [i for i in listed['materials'] if i['purpose'].startswith('process-cleanup journal')]
        self.assertEqual([(j['kind'], j['exists']) for j in journals], [('dir', True)])

    def test_changed_directory_is_not_deleted(self):
        for i in range(3):
            self.write(f'exp/run2/{i}.bin', str(i))
        packet = self.packet(self.local / 'exp/run2', op='retire-2')
        self.write('exp/run2/late.bin', 'new output after review')
        with self.assertRaises(TaskError) as cm:
            run_cleanup(self.data, packet)
        self.assertEqual(cm.exception.code, 'content_conflict')
        self.assertTrue((self.local / 'exp/run2/late.bin').exists())

    def test_directory_with_nested_repository_is_refused(self):
        self.write('exp/run3/.git/HEAD', 'ref')
        code, out = self.cli(materials_main, 'cleanup-packet', '--task', self.task, '--operation-id', 'r3',
                             '--path', self.local / 'exp/run3', '--rationale', 'x', '--quote', 'q', '--source-ref', 's')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['code'], 'unsafe_path')

    def fill(self, directory, count=5):
        directory.mkdir(parents=True)
        for i in range(count):
            (directory / f'{i}.out').write_text(str(i))
        return directory

    def test_unregistered_files_in_task_artifact_dir_are_retireable(self):
        self.store.mutate('artifact', {'operation_id': 'a-1', 'task_id': self.task, 'base_revision': 1,
                                       'name': 'notes', 'content': 'keep me'})
        experiments = self.fill(self.data / 'artifacts' / self.task / 'experiments')
        unrecorded = {u['path']: u for u in inventory(self.store, self.repo)['unrecorded']}
        self.assertEqual(unrecorded[str(experiments)]['files'], 5)
        packet = self.packet(experiments)
        self.assertEqual(packet['storage'], 'external')
        self.assertEqual(run_cleanup(self.data, packet)['status'], 'complete')
        self.assertFalse(experiments.exists())
        registered = self.data / self.store.read(self.task, detail=True)['artifacts']['notes']['path']
        self.assertTrue(registered.is_file())
        with self.assertRaises(TaskError) as cm:
            run_cleanup(self.data, self.packet(registered, op='retire-registered'))
        self.assertEqual(cm.exception.code, 'cleanup_blocked')

    def test_managed_artifact_root_is_discovered_and_retireable(self):
        run = self.fill(self.repo.parent / '_artifacts/repo/main/eval-2026-10-01T10:00')
        worktree = self.repo.parent / '_worktrees/repo/feature'
        self.git('worktree', 'add', '-q', '-b', 'feature', str(worktree))
        from agent_workflow.process_cleanup import artifact_roots
        self.assertEqual(artifact_roots(worktree), [self.repo.parent / '_artifacts/repo'])
        unrecorded = {u['path']: u for u in inventory(self.store, self.repo)['unrecorded']}
        self.assertEqual(unrecorded[str(run)]['files'], 5)
        self.assertEqual(run_cleanup(self.data, self.packet(run))['status'], 'complete')
        self.assertFalse(run.exists())

    def test_recorded_external_path_is_retireable_and_unrecorded_is_refused(self):
        shared = self.fill(self.repo.parent / 'shared/exp-a')
        stray = self.fill(self.repo.parent / 'shared/exp-b')
        self.cli(materials_main, 'record', '--path', shared, '--task', self.task)
        self.assertEqual(run_cleanup(self.data, self.packet(shared))['status'], 'complete')
        self.assertFalse(shared.exists())
        self.assertEqual(materials.load(self.data)[-1]['event'], 'removed')
        for target, op in ((stray, 'stray'), (self.data / 'cleanup', 'journals')):
            with self.subTest(target=target), self.assertRaises(TaskError) as cm:
                target.mkdir(exist_ok=True)
                run_cleanup(self.data, self.packet(target, op=op))
            self.assertEqual(cm.exception.code, 'unsafe_path')
        self.assertTrue(stray.exists())


if __name__ == '__main__':
    unittest.main()
