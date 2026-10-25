"""Claude adapter installation tests in temporary profiles; no live profile or CLI writes."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.claude import install as adapter  # noqa: E402
from scripts import install_skills as skills  # noqa: E402


class ClaudeInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.lib = self.home / '.local/lib/agent-tools'
        env = patch.dict(os.environ, {'AGENT_TOOLS_INSTALL_ROOT': str(self.lib)})
        env.start()
        self.addCleanup(env.stop)
        self.core = self.base / 'agent-core'
        self.core_source = self.core / 'adapters/claude/CLAUDE.md'
        self.write(self.core_source, '# Core fixture\n')
        for name in skills.KEPT:
            self.write(self.lib / 'skills' / name / 'SKILL.md', f'# {name}\n')
        self.write(self.lib / 'shared/writing/reader-facing-contract.md', '# Contract fixture\n')
        self.settings_path = self.home / '.claude/settings.json'
        self.foreign = {'env': {'ANTHROPIC_API_KEY': 'test-only'}, 'model': 'fixture',
                        'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'echo user'}]}]}}
        self.write(self.settings_path, json.dumps(self.foreign))

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def snapshot(self):
        return {str(p.relative_to(self.base)): ('link', os.readlink(p)) if p.is_symlink() else ('file', p.read_bytes())
                for p in self.base.rglob('*') if p.is_symlink() or p.is_file()}

    def install(self):
        return adapter.install(self.home, self.core)

    def retired_handler(self, event='Stop'):
        script = self.lib / 'claude/native_hook.py'
        return {'type': 'command', 'command': shlex.join([sys.executable, str(script), '--', 'learning-workflow-hook', event])}

    def test_install_check_idempotence_and_remove(self):
        self.assertEqual(self.install()['status'], 'updated')
        for name in skills.KEPT:
            self.assertEqual(os.readlink(self.home / '.claude/skills' / name), str(self.lib / 'skills' / name))
        self.assertEqual(os.readlink(self.home / adapter.RULE), str(self.lib / 'claude/context.md'))
        self.assertEqual(os.readlink(self.home / '.claude/CLAUDE.md'), str(self.core_source.resolve()))
        context = (self.lib / 'claude/context.md').read_text()
        self.assertIn(str(self.lib / 'shared/writing/reader-facing-contract.md'), context)
        self.assertNotIn('learning-workflow', context)
        before = self.snapshot()
        self.assertEqual(self.install()['status'], 'checked')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(adapter.check(self.home, self.core)['skills'], len(skills.KEPT))
        self.assertEqual(adapter.remove(self.home)['status'], 'removed')
        for name in skills.KEPT:
            self.assertFalse((self.home / '.claude/skills' / name).is_symlink())
        self.assertFalse((self.lib / 'claude/context.md').exists())
        self.assertFalse((self.home / adapter.RULE).is_symlink())
        for path in self.lib.glob('skills/*/SKILL.md'):
            self.assertTrue(path.is_file())

    def test_install_registers_no_hooks_and_disables_memory_keeping_foreign_settings(self):
        initial = deepcopy(self.foreign)
        initial['autoMemoryEnabled'] = True
        self.write(self.settings_path, json.dumps(initial))
        self.install()
        settings = adapter.read_settings(self.home)
        self.assertIs(settings['autoMemoryEnabled'], False)
        self.assertEqual(settings['env'], initial['env'])
        self.assertEqual(settings['model'], 'fixture')
        self.assertEqual(settings['hooks'], self.foreign['hooks'])
        settings['autoMemoryEnabled'] = True
        self.write(self.settings_path, json.dumps(settings))
        with self.assertRaisesRegex(ValueError, 'autoMemoryEnabled'):
            adapter.check(self.home, self.core)
        self.install()
        self.assertIs(adapter.read_settings(self.home)['autoMemoryEnabled'], False)

    def test_retired_hook_entries_are_removed_and_foreign_hooks_kept(self):
        settings = deepcopy(self.foreign)
        settings['hooks']['Stop'] = [{'hooks': [self.retired_handler()]},
                                     {'hooks': [self.retired_handler(), {'type': 'command', 'command': 'echo mixed'}]}]
        settings['hooks']['PreToolUse'] = [{'matcher': 'Bash', 'hooks': [self.retired_handler('PreToolUse')]}]
        settings['hooks']['SessionStart'].append({'hooks': [
            {'type': 'command', 'command': 'echo native_hook.py claude'}]})  # filename in shell data proves nothing
        self.install()
        self.write(self.settings_path, json.dumps(settings))
        with self.assertRaisesRegex(ValueError, 'retired agent-tools hook'):
            adapter.check(self.home, self.core)
        self.install()
        cleaned = adapter.read_settings(self.home)
        self.assertEqual(cleaned['hooks']['Stop'], [{'hooks': [{'type': 'command', 'command': 'echo mixed'}]}])
        self.assertNotIn('PreToolUse', cleaned['hooks'])
        self.assertEqual(cleaned['hooks']['SessionStart'], settings['hooks']['SessionStart'])
        backup = self.settings_path.with_name('settings.json.agent-tools-backup')
        self.assertEqual(json.loads(backup.read_text()), settings)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.install()['status'], 'checked')

    def test_hooks_key_is_dropped_when_only_retired_entries_were_present(self):
        settings = {'model': 'fixture', 'hooks': {'Stop': [{'hooks': [self.retired_handler()]}]}}
        self.write(self.settings_path, json.dumps(settings))
        self.install()
        self.assertEqual(adapter.read_settings(self.home), {'model': 'fixture', 'autoMemoryEnabled': False})

    def test_earlier_release_state_views_and_links_are_migrated(self):
        legacy = self.home / '.local/share/agent-tools'
        self.write(legacy / 'claude/native_hook.py', '# retired adapter\n')
        self.write(self.lib / 'claude/native_hook.py', '# retired adapter\n')
        self.write(self.home / adapter.OLD_STATE, '{}')
        bundle = legacy / 'learning-workflow/skills'
        self.write(bundle / 'academic-writing/SKILL.md', 'old')
        skills_dir = self.home / '.claude/skills'
        skills_dir.mkdir(parents=True)
        (skills_dir / 'academic-writing').symlink_to(bundle / 'academic-writing')
        (skills_dir / 'work-report').symlink_to(self.home / '.agents/skills/work-report')  # dangling
        self.write(self.home / '.claude/skills/own-skill/SKILL.md', 'user skill')
        old_context = legacy / 'claude/context.md'
        self.write(old_context, 'old view')
        rule = self.home / adapter.RULE
        rule.parent.mkdir(parents=True)
        rule.symlink_to(old_context)
        self.install()
        self.assertEqual(os.readlink(skills_dir / 'academic-writing'), str(self.lib / 'skills/academic-writing'))
        self.assertFalse((skills_dir / 'work-report').is_symlink())
        self.assertEqual((skills_dir / 'own-skill/SKILL.md').read_text(), 'user skill')
        self.assertEqual(os.readlink(rule), str(self.lib / 'claude/context.md'))
        self.assertFalse((legacy / 'claude/native_hook.py').exists())
        self.assertFalse((self.lib / 'claude/native_hook.py').exists())
        self.assertFalse((self.home / adapter.OLD_STATE).exists())

    def test_unmanaged_directory_in_the_way_is_preserved_without_failing_the_install(self):
        self.write(self.home / '.claude/skills/task-routing/SKILL.md', 'user copy')
        with self.assertRaisesRegex(ValueError, 'Claude skill links missing or changed: task-routing'):
            self.install()  # the final check reports the preserved entry
        self.assertEqual((self.home / '.claude/skills/task-routing/SKILL.md').read_text(), 'user copy')
        self.assertTrue((self.home / '.claude/skills/academic-writing').is_symlink())

    def test_unrelated_global_context_imports_core_without_writing_through_link(self):
        existing = self.base / 'user-context.md'
        self.write(existing, '# Existing private user context\n')
        global_view = self.home / '.claude/CLAUDE.md'
        global_view.symlink_to(existing)
        before_core, before_user = self.core_source.read_bytes(), existing.read_bytes()
        self.install()
        self.assertIn(f'@{self.core_source.resolve()}\n', (self.lib / 'claude/context.md').read_text())
        self.assertEqual(os.readlink(global_view), str(existing))
        self.assertEqual((existing.read_bytes(), self.core_source.read_bytes()), (before_user, before_core))
        adapter.remove(self.home)
        self.assertEqual(os.readlink(global_view), str(existing))

    def test_core_linked_global_context_gets_no_duplicate_import(self):
        (self.home / '.claude').mkdir(exist_ok=True)
        (self.home / '.claude/CLAUDE.md').symlink_to(self.core_source)
        self.install()
        self.assertNotIn('@', (self.lib / 'claude/context.md').read_text())

    def assert_refused_without_writes(self, message, break_input):
        break_input()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, message):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_missing_core_is_refused_before_any_write(self):
        self.assert_refused_without_writes('Agent Core Claude context missing', self.core_source.unlink)

    def test_missing_contract_is_refused_before_any_write(self):
        self.assert_refused_without_writes(
            'shared writing contract missing', (self.lib / 'shared/writing/reader-facing-contract.md').unlink)

    def test_missing_skill_source_is_refused_before_any_write(self):
        self.assert_refused_without_writes('skill source missing', (self.lib / 'skills/task-routing/SKILL.md').unlink)

    def test_settings_symlink_and_invalid_json_are_refused(self):
        self.settings_path.unlink()
        target = self.base / 'real-settings.json'
        target.write_text('{}')
        self.settings_path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'settings symlink preserved'):
            self.install()
        self.assertEqual(target.read_text(), '{}')


if __name__ == '__main__':
    unittest.main()
