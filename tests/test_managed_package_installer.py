import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "managed_package_installer.py"
SPEC = importlib.util.spec_from_file_location("managed_package_installer", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ManagedPackageInstallerTests(unittest.TestCase):
    def descriptor(self, name):
        return MODULE.load_descriptor(ROOT / "config" / "managed-packages" / f"{name}.json", ROOT)

    def test_linear_descriptor_uses_version_file(self):
        linear = self.descriptor("linear-workflow")
        self.assertEqual(linear["resolved_version"], (ROOT / "linear_workflow" / "VERSION").read_text().strip())

    def test_managed_status_distinguishes_fresh_and_managed_homes(self):
        descriptor = self.descriptor("linear-workflow")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertFalse(MODULE.managed_install_exists(descriptor, ROOT, home, "unix"))
            source, target = MODULE.target_pairs(descriptor, ROOT, home)[0]
            MODULE.copy_managed(source, target)
            self.assertTrue(MODULE.managed_install_exists(descriptor, ROOT, home, "unix"))

    def test_install_can_skip_marketplace_registration(self):
        descriptor = self.descriptor("linear-workflow")
        descriptor["status"] = "active"
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            MODULE.install(
                descriptor,
                ROOT,
                home,
                "unix",
                "uv",
                skip_runtime=True,
                skip_plugin_registration=True,
            )
            self.assertFalse((home / ".agents" / "plugins" / "marketplace.json").exists())
            self.assertTrue((home / ".codex" / "skills" / "linear-plan" / "SKILL.md").is_file())

    def test_managed_reinstall_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            source.mkdir()
            (source / "value").write_text("one", encoding="utf-8")
            self.assertIsNone(MODULE.copy_managed(source, target))
            self.assertIsNone(MODULE.copy_managed(source, target))
            self.assertEqual((target / "value").read_text(), "one")
            self.assertEqual(list(root.glob("target.backup-*")), [])

    def test_unmanaged_target_is_backed_up_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            target = root / "target.txt"
            source.write_text("managed", encoding="utf-8")
            target.write_text("user", encoding="utf-8")
            backup = MODULE.copy_managed(source, target)
            self.assertIsNotNone(backup)
            self.assertEqual(backup.read_text(), "user")
            self.assertEqual(target.read_text(), "managed")

    def test_marketplace_replaces_same_name_and_preserves_other_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".agents" / "plugins" / "marketplace.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"plugins": [{"name": "other", "x": 1}, {"name": "linear-workflow"}]}))
            MODULE.update_marketplace(home, self.descriptor("linear-workflow"))
            plugins = json.loads(path.read_text())["plugins"]
            self.assertEqual([p["name"] for p in plugins], ["other", "linear-workflow"])
            self.assertEqual(plugins[0]["x"], 1)

    def test_drift_iterates_descriptor_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.descriptor("linear-workflow")
            for source, target in MODULE.target_pairs(descriptor, ROOT, home):
                MODULE.copy_managed(source, target)
            drift = MODULE.drift_report(descriptor, ROOT, home, "unix")
            self.assertTrue(any("runtime" in item for item in drift))
            first_target = MODULE.target_pairs(descriptor, ROOT, home)[0][1]
            (first_target / "SKILL.md").write_text("drift", encoding="utf-8")
            drift = MODULE.drift_report(descriptor, ROOT, home, "unix")
            self.assertIn(str(first_target), drift)

    def disable_package(self, descriptor, repo_root, home, platform):
        with patch.dict(os.environ, {'HOME': str(home)}):
            return MODULE.disable(descriptor, repo_root, home, platform)

    def seed(self, home, platform='unix'):
        descriptor = self.descriptor('linear-workflow')
        descriptor['status'] = 'active'
        for source, target in MODULE.target_pairs(descriptor, ROOT, home):
            MODULE.copy_managed(source, target)
        MODULE.update_marketplace(home, descriptor)
        runtime, executable, launcher = MODULE.runtime_paths(descriptor, home, platform)
        runtime.mkdir(parents=True)
        (runtime/'keep-runtime').write_text('retained runtime')
        (runtime.parent/'tasks.db').write_text('retained state')
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes((f'@echo off\r\n"{executable}" %*\r\n' if platform == 'win11'
                             else f'#!/usr/bin/env bash\nexec "{executable}" "$@"\n').encode())
        MODULE.write_manifest(descriptor, ROOT, home, platform)
        descriptor['status'] = 'disabled'
        return descriptor

    def test_disabled_install_fails_before_any_write_or_subprocess(self):
        descriptor = self.descriptor('linear-workflow')
        descriptor['status'] = 'disabled'
        with tempfile.TemporaryDirectory() as tmp, patch.object(MODULE.subprocess, 'run') as run:
            home = Path(tmp)/'new-profile'
            with self.assertRaises(MODULE.InstallerError):
                MODULE.install(descriptor, ROOT, home, 'unix', 'uv', False, False)
            self.assertFalse(home.exists())
            run.assert_not_called()

    def test_disable_removes_only_discovery_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.seed(home)
            marketplace = home/'.agents/plugins/marketplace.json'
            content = json.loads(marketplace.read_text())
            content['plugins'].append({'name': 'other', 'configuration': {'keep': True}})
            content['unrelated'] = {'setting': 'value'}
            marketplace.write_text(json.dumps(content))
            retained = {str(p):p.read_bytes() for p in (home/'.local/share/linear-workflow').rglob('*') if p.is_file()}
            self.assertTrue(MODULE.disabled_report(descriptor, ROOT, home, 'unix'))
            self.disable_package(descriptor, ROOT, home, 'unix')
            self.assertEqual(MODULE.disabled_report(descriptor, ROOT, home, 'unix'), [])
            self.assertEqual({str(p):p.read_bytes() for p in (home/'.local/share/linear-workflow').rglob('*') if p.is_file()}, retained)
            content = json.loads(marketplace.read_text())
            self.assertEqual(content['plugins'], [{'name': 'other', 'configuration': {'keep': True}}])
            self.assertEqual(content['unrelated'], {'setting': 'value'})
            before = marketplace.read_bytes()
            self.disable_package(descriptor, ROOT, home, 'unix')
            self.assertEqual(marketplace.read_bytes(), before)

    def test_disable_refuses_all_before_removing_modified_target_or_launcher(self):
        for mutation in ['target', 'launcher', 'marker', 'marketplace', 'symlink']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                descriptor = self.seed(home)
                pairs = MODULE.discovery_targets(descriptor, ROOT, home)
                target = pairs[-1][1]
                if mutation == 'target':
                    (pairs[0][1]/'SKILL.md').write_text('user change')
                elif mutation == 'launcher':
                    MODULE.runtime_paths(descriptor, home, 'unix')[2].write_text('user launcher')
                elif mutation == 'marker':
                    MODULE.marker_for(*pairs[0]).write_text('unowned')
                elif mutation == 'symlink':
                    (pairs[0][1]/'extra').symlink_to(home/'.local/share/linear-workflow/tasks.db')
                else:
                    path = home/'.agents/plugins/marketplace.json'
                    data = json.loads(path.read_text())
                    data['plugins'][0]['source']['path'] = './unrelated'
                    path.write_text(json.dumps(data))
                with patch.object(MODULE.subprocess, 'run') as run:
                    with self.assertRaises(MODULE.InstallerError):
                        self.disable_package(descriptor, ROOT, home, 'unix')
                    run.assert_not_called()
                self.assertTrue(target.exists())

    def test_disable_removes_verified_older_cache_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.seed(home)
            source = ROOT/'linear_workflow/codex/plugins/linear-workflow'
            older = home/'.codex/plugins/cache/personal/linear-workflow/previous-version'
            MODULE.copy_managed(source, older)
            self.disable_package(descriptor, ROOT, home, 'unix')
            self.assertFalse(older.exists())
            self.assertEqual(MODULE.disabled_report(descriptor, ROOT, home, 'unix'), [])

    def test_disable_refuses_unmanaged_cache_and_parent_symlink(self):
        for kind in ['cache', 'parent']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                descriptor = self.seed(home)
                if kind == 'cache':
                    unowned = home/'.codex/plugins/cache/personal/linear-workflow/foreign'
                    unowned.mkdir(); (unowned/'user.txt').write_text('private')
                else:
                    target = home/'.codex/skills'
                    moved = home/'original-skills'
                    target.rename(moved)
                    target.symlink_to(moved, target_is_directory=True)
                with self.assertRaises(MODULE.InstallerError):
                    self.disable_package(descriptor, ROOT, home, 'unix')
                self.assertTrue((home/'.claude/skills/linear-plan').exists())

    def test_discoverable_backups_block_disable_and_disabled_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.seed(home)
            backup = home/'.codex/skills/linear-plan.backup-20261001'
            backup.mkdir(); (backup/'SKILL.md').write_text('old unmanaged skill')
            with self.assertRaises(MODULE.InstallerError):
                self.disable_package(descriptor, ROOT, home, 'unix')
            self.assertTrue((home/'.codex/skills/linear-plan').exists())
            self.assertEqual((backup/'SKILL.md').read_text(), 'old unmanaged skill')
            # Move the backup outside discovery solely inside this isolated fixture.
            backup.rename(home/'saved-backup')
            self.disable_package(descriptor, ROOT, home, 'unix')
            (home/'saved-backup').rename(backup)
            with self.assertRaises(MODULE.InstallerError):
                MODULE.disabled_report(descriptor, ROOT, home, 'unix')

    def test_disable_verifies_exact_codex_generated_command_skills(self):
        for changed in [False, True]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                descriptor = self.seed(home)
                plugin = home/'.codex/plugins/cache/personal/linear-workflow'/descriptor['resolved_version']
                # Materialize the documented Codex wrapper, independently of verifier.
                for command_name in ['linear-plan', 'linear-deliver']:
                    text = (plugin/'commands'/f'{command_name}.md').read_text()
                    frontmatter, body = text[4:].split('\n---\n', 1)
                    description = next(line.split(': ', 1)[1] for line in frontmatter.splitlines() if line.startswith('description: '))
                    generated = plugin/'.codex-plugin/migrated-command-skills'/f'source-command-{command_name}'/'SKILL.md'
                    generated.parent.mkdir(parents=True)
                    generated.write_text('---\nname: "source-command-' + command_name + '"\ndescription: '
                                         + json.dumps(description) + '\n---\n\n# source-command-' + command_name
                                         + '\n\nUse this skill when the user asks to run the migrated source command `'
                                         + command_name + '`.\n\n## Command Template\n\n' + body.strip() + '\n')
                if changed:
                    generated.write_text(generated.read_text()+'User modification\n')
                    with self.assertRaises(MODULE.InstallerError):
                        self.disable_package(descriptor, ROOT, home, 'unix')
                    self.assertTrue((home/'.codex/skills/linear-plan').exists())
                    self.assertTrue(generated.exists())
                else:
                    self.disable_package(descriptor, ROOT, home, 'unix')
                    self.assertFalse(plugin.exists())

    def test_disable_rejects_descriptor_overlap_with_retained_shared_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.seed(home)
            descriptor['codex_targets'].append(copy.deepcopy(descriptor['shared_targets'][0]))
            with self.assertRaises(MODULE.InstallerError):
                self.disable_package(descriptor, ROOT, home, 'unix')
            self.assertTrue((home/'.local/share/linear-workflow/shared').exists())
            self.assertTrue((home/'.codex/skills/linear-plan').exists())

    def test_disable_accepts_installed_manifest_when_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.seed(home)
            # Matching installed manifest is independent of newer source content.
            with patch.object(MODULE, 'compare_tree', return_value=False):
                self.disable_package(descriptor, ROOT, home, 'unix')
            self.assertEqual(MODULE.disabled_report(descriptor, ROOT, home, 'unix'), [])

    def test_disabled_cli_check_is_absence_not_runtime_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            descriptor = self.descriptor('linear-workflow')
            descriptor['status'] = 'disabled'
            path = root/'descriptor.json'
            path.write_text(json.dumps(descriptor))
            home = root/'home'
            home.mkdir()
            result = subprocess.run([sys.executable, str(SCRIPT), 'check', '--descriptor', str(path),
                                     '--repo-root', str(ROOT), '--home', str(home)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('discovery: disabled', result.stdout)
            self.assertEqual(list(home.iterdir()), [])

    def test_win11_expected_launcher_and_guard_failure_preserves_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            descriptor = self.seed(home, 'win11')
            with patch.object(MODULE.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['guard'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.disable_package(descriptor, ROOT, home, 'win11')
            self.assertTrue(MODULE.runtime_paths(descriptor, home, 'win11')[2].exists())
            with patch.object(MODULE.subprocess, 'run') as guard:
                self.disable_package(descriptor, ROOT, home, 'win11')
                self.assertIn('win11', guard.call_args.args[0])
            self.assertEqual(MODULE.disabled_report(descriptor, ROOT, home, 'win11'), [])


if __name__ == "__main__":
    unittest.main()
