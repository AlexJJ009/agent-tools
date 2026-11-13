"""Install root separation, manifest sync and old data-root layout migration, in temporary profiles."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import install_layout as layout  # noqa: E402

# Last main revision before the install root existed: its installer builds the old layout.
OLD_RELEASE = '9ee7745'
FLAGS = ('--no-fail2ban-hardening', '--no-cc-switch-update', '--no-codex-config', '--no-codex-here',
         '--codex-proxy-wrapper', 'never', '--no-codex-remote-control', '--no-claude-desktop-ssh', '--no-agent-core')


def profile_env(home):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith('XDG_') and k not in ('AGENT_TOOLS_INSTALL_ROOT', 'AGENT_TOOLS_HOME', 'PYTHONPATH')}
    fake = home / 'fake-bin'
    fake.mkdir(parents=True, exist_ok=True)
    crontab = fake / 'crontab'
    crontab.write_text('#!/bin/sh\nif [ "$1" = "-l" ]; then cat "$HOME/test-crontab" 2>/dev/null; '
                       'else cat > "$HOME/test-crontab"; fi\n')
    crontab.chmod(0o755)
    # The old release's report installer only warms its uv script environment.
    uv = fake / 'uv'
    uv.write_text('#!/bin/sh\nexit 0\n')
    uv.chmod(0o755)
    env.update(HOME=str(home), PATH=f'{fake}{os.pathsep}{env["PATH"]}', CODEX_HOME=str(home / '.codex'),
               CC_SWITCH_DB_PATH=str(home / '.cc-switch/cc-switch.db'), TMUX_CONF=str(home / '.tmux.conf'),
               PYTHON_BIN=sys.executable)  # hook commands record the interpreter that installed them
    return env


def snapshot(root, skip=()):
    return {str(p.relative_to(root)): ('link', os.readlink(p)) if p.is_symlink() else ('file', p.read_bytes())
            for p in sorted(root.rglob('*')) if (p.is_file() or p.is_symlink())
            and not any(part in skip for part in p.relative_to(root).parts) and '__pycache__' not in p.parts}


class SyncTreeTests(unittest.TestCase):
    def test_reinstall_deletes_only_previously_managed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'install'
            v1 = {'a.txt': b'one', 'pkg/b.py': b'two', 'pkg/gone.py': b'old'}
            layout.sync_tree(dest, v1)
            (dest / 'pkg/user-notes.txt').write_text('mine')
            (dest / 'foreign').mkdir()
            (dest / 'foreign/x').write_text('kept')
            v2 = {'a.txt': b'one changed', 'pkg/b.py': b'two'}
            report = layout.sync_tree(dest, v2)
            self.assertFalse((dest / 'pkg/gone.py').exists())
            self.assertEqual((dest / 'a.txt').read_bytes(), b'one changed')
            self.assertEqual((dest / 'pkg/user-notes.txt').read_text(), 'mine')
            self.assertEqual((dest / 'foreign/x').read_text(), 'kept')
            self.assertEqual(report['removed'], ['pkg/gone.py'])
            self.assertEqual(report['updated'], ['a.txt'])
            self.assertEqual(sorted(report['unmanaged']), ['foreign/', 'pkg/user-notes.txt'])
            self.assertEqual(layout.read_manifest(dest), {k: layout.sha256(v) for k, v in v2.items()})
            again = layout.sync_tree(dest, v2)
            self.assertEqual((again['added'], again['updated'], again['removed']), ([], [], []))
            drift = layout.check_tree(dest, {**v2, 'a.txt': b'newer'})
            self.assertEqual(drift['changed'], ['a.txt'])

    def test_overlapping_roots_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'share/agent-tools'
            for install in (data, data / 'lib', data.parent):
                with self.subTest(install=install), self.assertRaisesRegex(ValueError, 'overlaps data root'):
                    layout.require_separate(install, data=data)
            self.assertEqual(layout.require_separate(Path(tmp) / 'lib/agent-tools', data=data), data.resolve())
            with self.assertRaisesRegex(ValueError, 'inside data root'):
                layout.require_separate(Path(tmp) / 'lib/agent-tools', source=data / 'src', data=data)


class ScriptRelocationTests(unittest.TestCase):
    def test_reinstall_repoints_old_cron_instruction_and_launcher_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'home'
            home.mkdir()
            env = profile_env(home)
            install = home / '.local/lib/agent-tools'
            data = home / '.local/share/agent-tools'
            (install / 'scripts').mkdir(parents=True)
            for name in layout.RELOCATED_SCRIPTS:
                (install / 'scripts' / name).write_text('new script')
            codex = home / '.codex'
            codex.mkdir()
            agents = codex / 'AGENTS.md'
            agents.write_text(f'bash {install}/install.sh --check\n'
                              f'preserve {install}/install.sh.backup\n')
            (home / 'test-crontab').write_text(f'17 * * * * {install}/install.sh --check\n'
                                              f'18 * * * * {data}/install.sh --check\n')
            launcher = home / '.local/bin/agent-tools-install'
            launcher.parent.mkdir(parents=True)
            launcher.symlink_to(install / 'install.sh')
            with patch.dict(os.environ, env, clear=True):
                updated = layout.repoint_script_consumers(ROOT, install, home)
                self.assertEqual(layout.repoint_script_consumers(ROOT, install, home), [])
            self.assertIn(str(agents), updated)
            self.assertIn(f'bash {install}/scripts/install.sh --check', agents.read_text())
            self.assertIn(f'preserve {install}/install.sh.backup', agents.read_text())
            self.assertEqual(launcher.resolve(), install / 'scripts/install.sh')
            cron = (home / 'test-crontab').read_text()
            self.assertEqual(cron.count(str(install / 'scripts/install.sh')), 2)


class InstallerLayoutTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / 'home'
        (self.home / 'projects').mkdir(parents=True)
        core = self.home / 'agent-core/adapters/claude/CLAUDE.md'
        core.parent.mkdir(parents=True)
        core.write_text('# Core fixture\n')
        self.env = profile_env(self.home)
        self.data = self.home / '.local/share/agent-tools'
        self.lib = self.home / '.local/lib/agent-tools'

    def run_install(self, *args, source=ROOT, check=True, env=None):
        result = subprocess.run(['bash', str(source / ('scripts/install.sh' if (source / 'scripts/install.sh').is_file() else 'install.sh')), '--root', str(self.home / 'projects'),
                                 *FLAGS, *args], env=env or self.env, text=True, capture_output=True, timeout=300)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
        return result

    def run_python(self, script, *args, source=ROOT):
        result = subprocess.run([sys.executable, str(source / script), *args], env=self.env, text=True,
                                capture_output=True, timeout=300)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
        return result

    def old_layout(self):
        """Build the layout earlier releases produced with --install-dir <data root>."""
        old = self.base / 'old-release'
        old.mkdir()
        archive = subprocess.run(['git', '-C', str(ROOT), 'archive', OLD_RELEASE], capture_output=True)
        if archive.returncode:
            self.skipTest(f'old release {OLD_RELEASE} unavailable in this checkout')
        subprocess.run(['tar', '-x', '-C', str(old)], input=archive.stdout, check=True)
        self.run_install('--install-dir', str(self.data), source=old)
        self.run_python('scripts/install_learning_workflow.py', '--with-hooks', source=old)
        self.run_python('scripts/install_claude.py', '--install-packages', '--agent-core-home',
                        str(self.home / 'agent-core'), source=old)
        self.run_python('scripts/install_learning_workflow.py', '--check', source=old)
        return old

    def assert_no_data_root_consumers(self):
        self.assertEqual(layout.references(self.home, self.data, texts=self.consumer_texts(),
                                           links=self.consumer_links()), [])

    def consumer_texts(self):
        with patch.dict(os.environ, self.env, clear=True):
            return layout.consumer_texts(self.home)

    def consumer_links(self):
        with patch.dict(os.environ, self.env, clear=True):
            return layout.consumer_links(self.home)

    def test_fresh_install_keeps_software_out_of_the_data_root(self):
        installed = self.run_install()
        self.assertIn('ci-watch: ', installed.stdout)
        self.assertTrue((self.lib / 'scripts/install.sh').is_file())
        self.assertTrue((self.lib / layout.MANIFEST).is_file())
        self.assertFalse(any(self.data.glob('*.sh')) if self.data.exists() else False)
        self.assertEqual(layout.classify(self.data)['software'], [])
        for launcher in ('agent-wt', 'ci-watch'):
            installed_launcher = self.home / '.local/bin' / launcher
            self.assertTrue(installed_launcher.is_symlink())
            self.assertEqual(installed_launcher.resolve(), self.lib / 'bin' / launcher)
            self.assertTrue(os.access(installed_launcher, os.X_OK))
        self.assertEqual(self.run_install('--check').returncode, 0)
        before = snapshot(self.home)
        self.run_install()
        self.assertEqual(snapshot(self.home), before)

    def test_no_agent_wt_skips_both_launchers(self):
        installed = self.run_install('--no-agent-wt')
        for launcher in ('agent-wt', 'ci-watch'):
            self.assertFalse((self.home / '.local/bin' / launcher).exists())
            self.assertIn(f'{launcher} not installed (--no-agent-wt).', installed.stdout)

    def test_overlapping_install_dir_is_refused_before_writes(self):
        for target in (self.data, self.data / 'software', self.home / '.local/share'):
            with self.subTest(target=target):
                before = snapshot(self.home)
                result = self.run_install('--install-dir', str(target), check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('overlaps data root', result.stderr)
                self.assertEqual(snapshot(self.home), before)

    def test_old_layout_migrates_repoints_consumers_and_keeps_data(self):
        self.old_layout()
        self.assertTrue((self.data / 'learning-workflow/bin/learning-workflow').is_file())
        self.assertTrue((self.data / 'claude/native_hook.py').is_file())
        self.assertIn('native_hook.py', (self.home / '.claude/settings.json').read_text())
        # Data, unknown items and a locally modified software copy.
        (self.data / 'artifacts/t1').mkdir(parents=True)
        (self.data / 'artifacts/t1/out.txt').write_text('task output')
        (self.data / 'views').mkdir()
        (self.data / 'views/PRD.md').write_text('user view')
        (self.data / 'install.sh.new').write_text('local draft')
        with (self.data / 'README.md').open('a') as stream:
            stream.write('\nlocal note\n')
        data_before = snapshot(self.data / 'artifacts') | snapshot(self.data / 'views')
        check = self.run_install('--check', check=False)
        self.assertNotEqual(check.returncode, 0)
        self.assertIn('software_in_data_root', check.stdout)
        self.run_install()
        # Hooks and launchers registered by the retired learning runtime are the operator's to remove;
        # until then their bundle stays in use and the install does not delete it.
        self.run_install()
        self.assertTrue((self.data / 'learning-workflow/bin/learning-workflow').is_file())
        self.assertNotIn('native_hook.py', (self.home / '.claude/settings.json').read_text())
        (self.home / '.codex/hooks.json').unlink()
        (self.home / '.codex/AGENTS.md').unlink()
        (self.home / '.local/bin/learning-workflow').unlink()
        result = self.run_install()
        self.assert_no_data_root_consumers()
        for name in ('task-routing', 'academic-writing'):
            self.assertEqual(os.readlink(self.home / '.agents/skills' / name), str(self.lib / 'skills' / name))
            self.assertEqual(os.readlink(self.home / '.claude/skills' / name), str(self.lib / 'skills' / name))
        self.assertEqual(os.path.realpath(self.home / '.claude/rules/agent-tools.md'), str(self.lib / 'claude/context.md'))
        self.assertNotIn('native_hook.py', (self.home / '.claude/settings.json').read_text())
        # Released copies removed, the modified one archived, data and unknown items untouched.
        groups = layout.classify(self.data)
        self.assertEqual(groups['software'], [], result.stdout[-3000:])
        # Old-release files no longer in the shipped set are left alone as unknown, never deleted.
        self.assertTrue({'install.sh.new', 'views'} <= set(groups['unknown']))
        archived = list((self.data / 'archives').glob('legacy-install-*/README.md'))
        self.assertEqual(len(archived), 1)
        self.assertTrue(archived[0].read_text().endswith('local note\n'))
        self.assertEqual(snapshot(self.data / 'artifacts') | snapshot(self.data / 'views'), data_before)
        self.assertTrue((self.data / 'install.sh.new').is_file())
        # Checks pass; reinstall is a no-op.
        self.run_python('scripts/install_claude.py', '--check')
        self.run_python('scripts/install_skills.py', '--check')
        self.assertEqual(self.run_install('--check').returncode, 0)
        before = snapshot(self.home)
        self.run_install()
        self.assertEqual(snapshot(self.home), before)


if __name__ == '__main__':
    unittest.main()
