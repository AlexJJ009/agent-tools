import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install_work_report.py'
spec = importlib.util.spec_from_file_location('install_work_report', SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class WorkReportInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.repo = self.base / 'repo'
        self.source = self.repo / 'skills/work-report'
        for rel in ['SKILL.md', 'references/rubric.yaml', 'references/judge.md',
                    'assets/report.md', 'scripts/report_tool.py']:
            p = self.source / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture source ' + rel)
        self.calls = []
        self.guard_ok = True
        self.tool_ok = True

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        guard = 'codex_target_guard.py' in args[1]
        code = 0 if (self.guard_ok if guard else self.tool_ok) else 1
        return SimpleNamespace(returncode=code, stdout='{}', stderr='fixture refusal' if code else '')

    def install(self, args=()):
        with patch.object(installer, 'ROOT', self.repo), patch.object(Path, 'home', return_value=self.home), \
             patch.object(installer.platform, 'system', return_value='Linux'), \
             patch.object(installer.shutil, 'which', return_value='/fixture/uv'), \
             patch.object(installer.subprocess, 'run', side_effect=self.run_command), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return installer.main(list(args))

    def test_guard_failure_writes_nothing(self):
        self.guard_ok = False
        self.assertEqual(self.install(), 1)
        self.assertFalse((self.home / '.agents').exists())
        self.assertFalse((self.home / '.local').exists())

    def test_install_readback_and_source_drift(self):
        self.assertEqual(self.install(), 0)
        target = self.home / '.agents/skills/work-report'
        self.assertEqual(installer.files(target), installer.files(self.source))
        self.assertEqual((self.home / '.claude/skills/work-report').resolve(), target)
        self.assertEqual(self.install(['--check']), 0)
        (target / 'SKILL.md').write_text('changed installed content')
        self.assertEqual(self.install(['--check']), 1)

    def test_unmanaged_directory_preserved(self):
        target = self.home / '.agents/skills/work-report'
        target.mkdir(parents=True)
        (target / 'personal.txt').write_text('keep')
        self.assertEqual(self.install(), 1)
        self.assertEqual((target / 'personal.txt').read_text(), 'keep')

    def test_failed_tool_preflight_preserves_installed_version(self):
        self.assertEqual(self.install(), 0)
        target = self.home / '.agents/skills/work-report'
        before = installer.files(target)
        (self.source / 'SKILL.md').write_text('new source')
        self.tool_ok = False
        self.assertEqual(self.install(), 1)
        self.assertEqual(installer.files(target), before)

    def test_failed_post_install_validation_restores_previous_install(self):
        self.assertEqual(self.install(), 0)
        target = self.home / '.agents/skills/work-report'
        before = installer.files(target)
        (self.source / 'SKILL.md').write_text('new source')
        normal = self.run_command
        def fail_published_path(args, **kwargs):
            if len(args) > 3 and str(target / 'scripts/report_tool.py') in args:
                return SimpleNamespace(returncode=1, stdout='', stderr='post-install fixture failure')
            return normal(args, **kwargs)
        with patch.object(self, 'run_command', side_effect=fail_published_path):
            self.assertEqual(self.install(), 1)
        self.assertEqual(installer.files(target), before)
        self.assertEqual((self.home / '.claude/skills/work-report').resolve(), target)

    def test_duplicate_codex_location_is_not_overwritten(self):
        duplicate = self.home / '.codex/skills/work-report'
        duplicate.mkdir(parents=True)
        (duplicate / 'SKILL.md').write_text('personal')
        self.assertEqual(self.install(), 1)
        self.assertEqual((duplicate / 'SKILL.md').read_text(), 'personal')

    def test_symlinked_parent_outside_profile_is_rejected(self):
        external = self.base / 'external'
        external.mkdir()
        (self.home / '.agents').symlink_to(external, target_is_directory=True)
        self.assertEqual(self.install(), 1)
        self.assertEqual(list(external.iterdir()), [])

    def test_check_only_does_not_create_missing_install(self):
        self.assertEqual(self.install(['--check']), 1)
        self.assertFalse((self.home / '.agents').exists())


if __name__ == '__main__':
    unittest.main()
