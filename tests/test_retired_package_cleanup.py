import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "retired_package_cleanup.py"
RECORD = ROOT / "config" / "retired-packages" / "linear-workflow.json"
SPEC = importlib.util.spec_from_file_location("retired_package_cleanup", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
# Last commit that shipped linear_workflow/ source; the record fingerprints its client copies.
LAST_SOURCE = "c2d891216c80b637f52ca7f6f40343a1a3a60cf1"


def git_has(revision):
    return subprocess.run(["git", "cat-file", "-e", f"{revision}^{{commit}}"], cwd=ROOT,
                          capture_output=True).returncode == 0


def command_text(name):
    return f"---\ndescription: Retired {name}\n---\n\nStop: {name} is retired.\n"


class RetiredPackageCleanupTests(unittest.TestCase):
    def record(self):
        return MODULE.load_record(RECORD)

    def seed(self, home, platform='unix'):
        """Materialize marked client copies and return a record fingerprinting them."""
        record = self.record()
        for item in record['targets']:
            target = home / item['destination'].format(version=record['version'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if item['kind'] == 'dir':
                if not target.exists():
                    target.mkdir()
                    (target / 'SKILL.md').write_text(f'retired {target.name}\n')
                    if 'plugin' in item['destination']:
                        (target / 'commands').mkdir()
                        for name in ('linear-plan', 'linear-deliver'):
                            (target / 'commands' / f'{name}.md').write_text(command_text(name))
            else:
                target.write_text(command_text(target.stem))
            MODULE.marker_for(item['kind'], target).write_text(MODULE.MANAGED_MARKER)
            item['sha256'] = MODULE.fingerprint(target)
        marketplace = home / '.agents/plugins/marketplace.json'
        marketplace.parent.mkdir(parents=True)
        registration = record['plugin_registration']
        marketplace.write_text(json.dumps({'name': 'personal', 'plugins': [
            {'name': registration['name'], 'source': {'source': 'local', 'path': registration['path']}}]}))
        runtime, executable, launcher = MODULE.runtime_paths(record, home, platform)
        runtime.mkdir(parents=True)
        (runtime / 'keep-runtime').write_text('retained runtime')
        (runtime.parent / 'tasks.db').write_text('retained state')
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes((f'@echo off\r\n"{executable}" %*\r\n' if platform == 'win11'
                              else f'#!/usr/bin/env bash\nexec "{executable}" "$@"\n').encode())
        return record

    def remove(self, record, home, platform='unix'):
        with patch.dict(os.environ, {'HOME': str(home)}):
            return MODULE.remove(record, ROOT, home, platform)

    @unittest.skipUnless(git_has(LAST_SOURCE), "history with the removed source is unavailable")
    def test_record_fingerprints_last_shipped_client_copies(self):
        archive = subprocess.run(["git", "archive", LAST_SOURCE, "linear_workflow/codex", "linear_workflow/claude"],
                                 cwd=ROOT, capture_output=True, check=True).stdout
        sources = {
            '.codex/skills/linear-plan': 'codex/skills/linear-plan',
            '.codex/skills/linear-deliver': 'codex/skills/linear-deliver',
            'plugins/linear-workflow': 'codex/plugins/linear-workflow',
            '.codex/plugins/cache/personal/linear-workflow/{version}': 'codex/plugins/linear-workflow',
            '.claude/skills/linear-plan': 'claude/skills/linear-plan',
            '.claude/skills/linear-deliver': 'claude/skills/linear-deliver',
            '.claude/commands/linear-plan.md': 'claude/commands/linear-plan.md',
            '.claude/commands/linear-deliver.md': 'claude/commands/linear-deliver.md',
        }
        with tempfile.TemporaryDirectory() as tmp:
            tarfile.open(fileobj=io.BytesIO(archive)).extractall(tmp, filter='data')
            for item in self.record()['targets']:
                with self.subTest(destination=item['destination']):
                    source = Path(tmp) / 'linear_workflow' / sources[item['destination']]
                    self.assertEqual(item['kind'], 'dir' if source.is_dir() else 'file')
                    self.assertEqual(MODULE.fingerprint(source), item['sha256'])

    def test_remove_deletes_only_discovery_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record = self.seed(home)
            marketplace = home / '.agents/plugins/marketplace.json'
            content = json.loads(marketplace.read_text())
            content['plugins'].append({'name': 'other', 'configuration': {'keep': True}})
            content['unrelated'] = {'setting': 'value'}
            marketplace.write_text(json.dumps(content))
            data = home / '.local/share/linear-workflow'
            retained = {str(p): p.read_bytes() for p in data.rglob('*') if p.is_file()}
            self.assertTrue(MODULE.remaining_report(record, home, 'unix'))
            self.remove(record, home)
            self.assertEqual(MODULE.remaining_report(record, home, 'unix'), [])
            self.assertEqual({str(p): p.read_bytes() for p in data.rglob('*') if p.is_file()}, retained)
            content = json.loads(marketplace.read_text())
            self.assertEqual(content['plugins'], [{'name': 'other', 'configuration': {'keep': True}}])
            self.assertEqual(content['unrelated'], {'setting': 'value'})
            before = marketplace.read_bytes()
            self.remove(record, home)
            self.assertEqual(marketplace.read_bytes(), before)

    def test_remove_refuses_all_before_touching_modified_or_unmanaged_state(self):
        for mutation in ['target', 'launcher', 'marker', 'marketplace', 'symlink']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                record = self.seed(home)
                pairs = MODULE.discovery_targets(record, home)
                first, last = pairs[0], pairs[-1][1]
                if mutation == 'target':
                    (first[1] / 'SKILL.md').write_text('user change')
                elif mutation == 'launcher':
                    MODULE.runtime_paths(record, home, 'unix')[2].write_text('user launcher')
                elif mutation == 'marker':
                    MODULE.marker_for(first[0]['kind'], first[1]).write_text('unowned')
                elif mutation == 'symlink':
                    (first[1] / 'extra').symlink_to(home / '.local/share/linear-workflow/tasks.db')
                else:
                    path = home / '.agents/plugins/marketplace.json'
                    data = json.loads(path.read_text())
                    data['plugins'][0]['source']['path'] = './unrelated'
                    path.write_text(json.dumps(data))
                with patch.object(MODULE.subprocess, 'run') as run:
                    with self.assertRaises(MODULE.RetirementError):
                        self.remove(record, home)
                    run.assert_not_called()
                self.assertTrue(last.exists())

    def test_remove_deletes_verified_older_cache_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record = self.seed(home)
            current = home / '.codex/plugins/cache/personal/linear-workflow' / record['version']
            older = current.with_name('previous-version')
            shutil.copytree(current, older)
            self.remove(record, home)
            self.assertFalse(older.exists())
            self.assertEqual(MODULE.remaining_report(record, home, 'unix'), [])

    def test_remove_refuses_unmanaged_cache_and_parent_symlink(self):
        for kind in ['cache', 'parent']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                record = self.seed(home)
                if kind == 'cache':
                    unowned = home / '.codex/plugins/cache/personal/linear-workflow/foreign'
                    unowned.mkdir(); (unowned / 'user.txt').write_text('private')
                else:
                    target = home / '.codex/skills'
                    moved = home / 'original-skills'
                    target.rename(moved)
                    target.symlink_to(moved, target_is_directory=True)
                with self.assertRaises(MODULE.RetirementError):
                    self.remove(record, home)
                self.assertTrue((home / '.claude/skills/linear-plan').exists())

    def test_discoverable_backups_block_remove_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record = self.seed(home)
            backup = home / '.codex/skills/linear-plan.backup-20261001'
            backup.mkdir(); (backup / 'SKILL.md').write_text('old unmanaged skill')
            with self.assertRaises(MODULE.RetirementError):
                self.remove(record, home)
            self.assertTrue((home / '.codex/skills/linear-plan').exists())
            self.assertEqual((backup / 'SKILL.md').read_text(), 'old unmanaged skill')
            backup.rename(home / 'saved-backup')
            self.remove(record, home)
            (home / 'saved-backup').rename(backup)
            with self.assertRaises(MODULE.RetirementError):
                MODULE.remaining_report(record, home, 'unix')

    def test_remove_verifies_exact_codex_generated_command_skills(self):
        for changed in [False, True]:
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                record = self.seed(home)
                plugin = home / '.codex/plugins/cache/personal/linear-workflow' / record['version']
                for name in ['linear-plan', 'linear-deliver']:
                    generated = plugin / '.codex-plugin/migrated-command-skills' / f'source-command-{name}' / 'SKILL.md'
                    generated.parent.mkdir(parents=True)
                    generated.write_text('---\nname: "source-command-' + name + '"\ndescription: '
                                         + json.dumps(f'Retired {name}') + '\n---\n\n# source-command-' + name
                                         + '\n\nUse this skill when the user asks to run the migrated source command `'
                                         + name + '`.\n\n## Command Template\n\nStop: ' + name + ' is retired.\n')
                if changed:
                    generated.write_text(generated.read_text() + 'User modification\n')
                    with self.assertRaises(MODULE.RetirementError):
                        self.remove(record, home)
                    self.assertTrue((home / '.codex/skills/linear-plan').exists())
                    self.assertTrue(generated.exists())
                else:
                    self.remove(record, home)
                    self.assertFalse(plugin.exists())

    def test_remove_rejects_record_overlap_with_retained_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record = self.seed(home)
            overlap = copy.deepcopy(record['targets'][0])
            overlap['destination'] = '.local/share/linear-workflow/runtime'
            record['targets'].append(overlap)
            with self.assertRaises(MODULE.RetirementError):
                self.remove(record, home)
            self.assertTrue((home / '.local/share/linear-workflow/runtime/keep-runtime').exists())
            self.assertTrue((home / '.codex/skills/linear-plan').exists())

    def test_remove_accepts_profile_install_manifest_when_record_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record = self.seed(home)
            manifest = {'package': record['name'], 'home': str(home.resolve()), 'platform': 'unix',
                        'targets': [{'path': str(target), 'sha256': MODULE.fingerprint(target)}
                                    for _, target in MODULE.discovery_targets(record, home)]}
            (home / '.local/share/linear-workflow/install-manifest.json').write_text(json.dumps(manifest))
            for item in record['targets']:
                item['sha256'] = '0' * 64
            self.remove(record, home)
            self.assertEqual(MODULE.remaining_report(record, home, 'unix'), [])

    def test_cli_check_reports_absence_and_remaining_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            command = [sys.executable, str(SCRIPT), 'check', '--record', str(RECORD),
                       '--repo-root', str(ROOT), '--home', str(home)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('discovery: absent', result.stdout)
            self.assertEqual(list(home.iterdir()), [])
            (home / '.local/bin').mkdir(parents=True)
            (home / '.local/bin/linear-workflow').write_text('launcher')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('REMAINING:', result.stdout)

    def test_cli_rejects_record_path_escape_before_touching_other_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir()
            outside = root / "outside"
            outside.mkdir()
            sentinel = outside / "SKILL.md"
            sentinel.write_text("unrelated user skill")
            for destination in (str(outside), "../outside"):
                with self.subTest(destination=destination):
                    record = json.loads(RECORD.read_text())
                    record["targets"][0]["destination"] = destination
                    path = root / "record.json"
                    path.write_text(json.dumps(record))
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), "remove", "--record", str(path),
                         "--repo-root", str(ROOT), "--home", str(home)],
                        capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("discovery target escapes home", result.stderr)
                    self.assertEqual(sentinel.read_text(), "unrelated user skill")
                    self.assertEqual(list(home.iterdir()), [])

    def test_win11_expected_launcher_and_guard_failure_preserves_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            record = self.seed(home, 'win11')
            with patch.object(MODULE.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['guard'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    self.remove(record, home, 'win11')
            self.assertTrue(MODULE.runtime_paths(record, home, 'win11')[2].exists())
            with patch.object(MODULE.subprocess, 'run') as guard:
                self.remove(record, home, 'win11')
                self.assertIn('win11', guard.call_args.args[0])
            self.assertEqual(MODULE.remaining_report(record, home, 'win11'), [])

    def test_removed_unix_flags_reject_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-created"
            for flag in ("--linear-workflow", "--linear-workflow-only"):
                result = subprocess.run(
                    ["bash", str(ROOT / "scripts" / "install.sh"), flag, "--install-dir", str(target)],
                    capture_output=True, text=True, errors="replace",
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Linear Workflow was removed", result.stderr)
                self.assertFalse(target.exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell unavailable")
    def test_removed_win_flag_rejects_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-created"
            result = subprocess.run(
                ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/install-win11.ps1"),
                 "-LinearWorkflow", "-UserHome", str(target), "-CodexHome", str(target / ".codex"),
                 "-CcSwitchDb", str(target / ".cc-switch/cc-switch.db")],
                capture_output=True, text=True, errors="replace",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Linear Workflow was removed", result.stderr)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
