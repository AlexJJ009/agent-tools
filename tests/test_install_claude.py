"""Bounded adapter installation tests; no live profile or CLI writes."""
from copy import deepcopy
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from adapters.claude import install as adapter


class ClaudeInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.core = self.base / "agent-core"
        self.core_source = self.core / "adapters/claude/CLAUDE.md"
        self.write(self.core_source, "# Core fixture\n@../../core/SOUL.md\n")
        bundle = self.home / ".local/lib/agent-tools/learning-workflow"
        for name in adapter.workflow.SKILLS:
            self.write(self.home / ".agents/skills" / name / "SKILL.md", f"# Shared {name}\n")
        for name in adapter.learning.SKILLS:
            self.write(bundle / "skills" / name / "SKILL.md", f"# Shared {name}\n")
        self.write(self.home / ".agents/skills/work-report/SKILL.md", "# Shared report\n")
        self.write(self.home / ".agents/skills/work-report/scripts/report_runtime.py", "# runtime fixture\n")
        self.write(bundle / "bin/learning-workflow-hook", "# runtime fixture\n")
        self.write(bundle / "shared/writing/reader-facing-contract.md", "# Shared writing fixture\n")
        self.write(self.home / ".local/share/agent-workflow/agent_workflow/hooks.py", "# runtime fixture\n")
        self.settings_path = self.home / ".claude/settings.json"
        self.foreign = {"env": {"ANTHROPIC_API_KEY": "test-only"}, "model": "fixture", "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "echo user"}]}]}}
        self.write(self.settings_path, json.dumps(self.foreign))

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def snapshot(self):
        return {str(path.relative_to(self.base)): ("link", os.readlink(path)) if path.is_symlink()
                else ("file", path.read_bytes())
                for path in self.base.rglob("*") if path.is_symlink() or path.is_file()}

    def install(self, legacy=()):
        return adapter.install(self.home, self.core, list(legacy))

    def test_install_check_idempotence_remove_preserves_auth_edits(self):
        source_before = {path: path.read_bytes() for path in self.base.rglob("SKILL.md")}
        self.assertEqual(self.install()["status"], "installed")
        before = self.snapshot()
        self.assertEqual(self.install()["status"], "checked")
        self.assertEqual(self.snapshot(), before)
        state = adapter.load_state(self.home)
        for raw, entry in state["links"].items():
            self.assertEqual(os.readlink(self.home / raw), entry["target"])
        settings = adapter.read_settings(self.home)
        settings["env"]["ANTHROPIC_API_KEY"] = "edited-test-only"
        settings["permissions"] = {"allow": ["Read"]}
        self.write(self.settings_path, json.dumps(settings))
        adapter.check(self.home)
        self.assertEqual(adapter.remove(self.home)["status"], "removed")
        restored = deepcopy(self.foreign)
        restored["env"]["ANTHROPIC_API_KEY"] = "edited-test-only"
        restored["permissions"] = {"allow": ["Read"]}
        self.assertEqual(adapter.read_settings(self.home), restored)
        for raw in state["links"]:
            self.assertFalse((self.home / raw).exists())
            self.assertFalse((self.home / raw).is_symlink())
        self.assertFalse((self.home / adapter.STATE).exists())
        for path, text in source_before.items():
            self.assertEqual(path.read_bytes(), text)

    def test_existing_core_and_shared_target_link_preserved_on_remove(self):
        core_view = self.home / ".claude/CLAUDE.md"
        self.write(core_view, "# Existing user context\n")
        name = adapter.workflow.SKILLS[0]
        target = self.home / ".agents/skills" / name
        skill = self.home / ".claude/skills" / name
        skill.parent.mkdir(parents=True)
        skill.symlink_to(target, target_is_directory=True)
        self.install()
        adapter.remove(self.home)
        self.assertEqual(core_view.read_text(), "# Existing user context\n")
        self.assertEqual(os.readlink(skill), str(target))

    def test_unrelated_existing_global_context_imports_core_without_writing_through_link(self):
        existing = self.base / "user-context.md"
        self.write(existing, "# Existing private user context\n")
        global_view = self.home / ".claude/CLAUDE.md"
        global_view.symlink_to(existing)
        before_core = self.core_source.read_bytes()
        before_user = existing.read_bytes()
        self.install()
        state = adapter.load_state(self.home)
        self.assertEqual(state["core_source"], str(self.core_source.resolve()))
        generated = adapter.context_path(self.home).read_text()
        self.assertIn(f"@{self.core_source.resolve()}\n", generated)
        self.assertEqual(existing.read_bytes(), before_user)
        self.assertEqual(self.core_source.read_bytes(), before_core)
        adapter.check(self.home)
        adapter.remove(self.home)
        self.assertEqual(os.readlink(global_view), str(existing))
        self.assertEqual(existing.read_bytes(), before_user)

    def test_missing_core_refused_even_when_global_context_exists(self):
        self.write(self.home / ".claude/CLAUDE.md", "# Existing unrelated context\n")
        self.core_source.unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Agent Core Claude context missing"):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_check_refuses_missing_core_source(self):
        self.install()
        generated = adapter.context_path(self.home).read_text()
        # The default global view already imports Core, so no duplicate import.
        self.assertNotIn(f"@{self.core_source.resolve()}\n", generated)
        self.core_source.unlink()
        before = self.snapshot()
        for operation in (adapter.check, adapter.remove):
            with self.assertRaisesRegex(ValueError, "Agent Core Claude context missing"):
                operation(self.home)
            self.assertEqual(self.snapshot(), before)

    def test_foreign_regular_directory_or_link_refused_before_writes(self):
        name = adapter.workflow.SKILLS[0]
        path = self.home / ".claude/skills" / name
        for kind in ("directory", "file", "link"):
            with self.subTest(kind=kind):
                if kind == "directory":
                    path.mkdir(parents=True)
                elif kind == "file":
                    self.write(path, "foreign")
                else:
                    outside = self.base / "foreign-skill"
                    outside.mkdir()
                    path.symlink_to(outside, target_is_directory=True)
                before = self.snapshot()
                with self.assertRaises(ValueError):
                    self.install()
                self.assertEqual(self.snapshot(), before)
                path.rmdir() if kind == "directory" else path.unlink()

    def test_settings_symlink_and_escaped_parent_refused_without_writes(self):
        self.settings_path.unlink()
        external = self.base / "external-settings.json"
        self.write(external, json.dumps(self.foreign))
        self.settings_path.symlink_to(external)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.install()
        self.assertEqual(self.snapshot(), before)
        self.settings_path.unlink()
        self.settings_path.parent.rmdir()
        external_dir = self.base / "outside-claude"
        self.write(external_dir / "settings.json", json.dumps(self.foreign))
        self.settings_path.parent.symlink_to(external_dir, target_is_directory=True)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_settings_backup_symlink_refused_without_writes(self):
        external = self.base / "private-backup.json"
        self.write(external, "keep")
        backup = (self.home / adapter.STATE).parent / "settings-before.json"
        backup.parent.mkdir(parents=True)
        backup.symlink_to(external)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "backup symlink"):
            self.install()
        self.assertEqual(self.snapshot(), before)

    def test_legacy_symlink_migrates_and_remove_restores_unchanged_source(self):
        name = adapter.workflow.SKILLS[0]
        legacy = self.base / "legacy-skills"
        source = legacy / name / "SKILL.md"
        self.write(source, "# Legacy source stays unchanged\n")
        destination = self.home / ".claude/skills" / name
        destination.parent.mkdir(parents=True)
        destination.symlink_to(legacy / name, target_is_directory=True)
        before = source.read_bytes()
        self.install([legacy])
        self.assertEqual(destination.resolve(), (self.home / ".agents/skills" / name).resolve())
        self.assertEqual(source.read_bytes(), before)
        adapter.remove(self.home)
        self.assertEqual(os.readlink(destination), str(legacy / name))
        self.assertEqual(source.read_bytes(), before)

    def test_publication_failure_rolls_back_links_settings_and_backup(self):
        before = self.snapshot()
        atomic_write = adapter.atomic_write
        def fail_manifest(path, data):
            if path == self.home / adapter.STATE:
                raise OSError("simulated manifest publication failure")
            return atomic_write(path, data)
        with patch.object(adapter, "atomic_write", side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.install()
        self.assertEqual(self.snapshot(), before)

    def test_failed_legacy_link_creation_restores_previous_link(self):
        name = adapter.workflow.SKILLS[0]
        legacy = self.base / "legacy-skills"
        self.write(legacy / name / "SKILL.md", "legacy")
        destination = self.home / ".claude/skills" / name
        destination.parent.mkdir(parents=True)
        destination.symlink_to(legacy / name, target_is_directory=True)
        before = self.snapshot()
        symlink_to = Path.symlink_to
        def fail_new(path, target, *args, **kwargs):
            if path == destination and str(target) != str(legacy / name):
                raise OSError("simulated link creation failure")
            return symlink_to(path, target, *args, **kwargs)
        with patch.object(Path, "symlink_to", autospec=True, side_effect=fail_new):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.install([legacy])
        self.assertEqual(self.snapshot(), before)

    def test_deliberately_broken_link_or_hooks_rejects_check_and_remove(self):
        self.install()
        state = adapter.load_state(self.home)
        raw = next(iter(state["links"]))
        path = self.home / raw
        path.unlink()
        path.symlink_to(self.base / "wrong-target")
        before = self.snapshot()
        for operation in (adapter.check, adapter.remove):
            with self.assertRaisesRegex(ValueError, "link missing or changed"):
                operation(self.home)
            self.assertEqual(self.snapshot(), before)
        path.unlink()
        path.symlink_to(state["links"][raw]["target"])
        settings = adapter.read_settings(self.home)
        settings["hooks"]["Stop"].pop()
        self.write(self.settings_path, json.dumps(settings))
        before = self.snapshot()
        for operation in (adapter.check, adapter.remove):
            with self.assertRaisesRegex(ValueError, "hook definitions"):
                operation(self.home)
            self.assertEqual(self.snapshot(), before)

    def test_context_parent_escape_rejects_remove_without_external_deletion(self):
        self.install()
        generated = adapter.context_path(self.home)
        outside = self.base / "outside-context"
        outside.mkdir()
        generated.rename(outside / "context.md")
        (generated.parent / "native_hook.py").unlink()
        (generated.parent / adapter.learning.layout.MANIFEST).unlink()
        generated.parent.rmdir()
        generated.parent.symlink_to(outside, target_is_directory=True)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "escapes"):
            adapter.remove(self.home)
        self.assertEqual(self.snapshot(), before)

    def test_upgrade_native_and_hook_definitions_preserves_user_edits(self):
        self.install()
        settings = adapter.read_settings(self.home)
        settings["env"]["ANTHROPIC_API_KEY"] = "changed-test-only"
        settings["hooks"]["Stop"].insert(0, {"hooks": [{"type": "command", "command": "echo private-hook"}]})
        self.write(self.settings_path, json.dumps(settings))
        old_native = adapter.native_path(self.home).read_bytes()
        new_native = old_native + b"\n# fixture native source upgrade\n"
        hook_groups = adapter.hooks.hook_groups
        def upgraded_groups(home):
            groups = hook_groups(home)
            groups["Stop"][0]["hooks"][0]["timeout"] = 31
            return groups
        with patch.object(adapter, "native_source", return_value=new_native), \
                patch.object(adapter.hooks, "hook_groups", side_effect=upgraded_groups):
            with self.assertRaisesRegex(ValueError, "source updated"):
                adapter.check(self.home)
            self.assertEqual(self.install()["status"], "updated")
            self.assertEqual(adapter.native_path(self.home).read_bytes(), new_native)
            state = adapter.load_state(self.home)
            self.assertEqual(state["managed_hooks"]["Stop"][0]["hooks"][0]["timeout"], 31)
            after = adapter.read_settings(self.home)
            self.assertEqual(after["env"]["ANTHROPIC_API_KEY"], "changed-test-only")
            self.assertEqual(after["hooks"]["Stop"][0]["hooks"][0]["command"], "echo private-hook")
            before = self.snapshot()
            self.assertEqual(self.install()["status"], "checked")
            self.assertEqual(self.snapshot(), before)

    def test_remove_after_source_change_uses_installed_hook_ownership(self):
        hook_groups = adapter.hooks.hook_groups
        def previous_groups(home):
            groups = hook_groups(home)
            for event_groups in groups.values():
                event_groups[0]["hooks"][0]["command"] += " --fixture-old-version"
            return groups
        with patch.object(adapter.hooks, "hook_groups", side_effect=previous_groups):
            self.install()
        settings = adapter.read_settings(self.home)
        settings["env"]["ANTHROPIC_API_KEY"] = "changed-test-only"
        self.write(self.settings_path, json.dumps(settings))
        with patch.object(adapter, "native_source", return_value=b"# source now newer\n"):
            with self.assertRaisesRegex(ValueError, "source updated"):
                adapter.check(self.home)
            adapter.remove(self.home)
        expected = deepcopy(self.foreign)
        expected["env"]["ANTHROPIC_API_KEY"] = "changed-test-only"
        self.assertEqual(adapter.read_settings(self.home), expected)
        self.assertFalse(adapter.native_path(self.home).exists())

    def test_upgrade_failure_restores_published_native_context_settings_state(self):
        self.install()
        before = self.snapshot()
        source = adapter.native_path(self.home).read_bytes() + b"\n# fixture upgraded\n"
        atomic_write = adapter.atomic_write
        failed = False
        def fail_publication_once(path, data):
            nonlocal failed
            if path == self.home / adapter.STATE and not failed:
                failed = True
                raise OSError("simulated upgrade publication failure")
            return atomic_write(path, data)
        with patch.object(adapter, "native_source", return_value=source), \
                patch.object(adapter, "atomic_write", side_effect=fail_publication_once):
            with self.assertRaisesRegex(OSError, "simulated upgrade"):
                self.install()
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), before)
        adapter.check(self.home)

    def test_user_native_edits_refuse_refresh_and_removal_without_writes(self):
        self.install()
        native = adapter.native_path(self.home)
        native.write_bytes(native.read_bytes() + b"\n# user private change\n")
        before = self.snapshot()
        for operation in (adapter.check, adapter.remove, lambda home: self.install()):
            with self.assertRaisesRegex(ValueError, "native hook adapter missing or changed"):
                operation(self.home)
            self.assertEqual(self.snapshot(), before)

    def test_copied_installer_loads_its_own_adapter_sources(self):
        copied = self.base / "copied-distribution"
        for name in ("scripts", "adapters"):
            shutil.copytree(adapter.ROOT / name, copied / name, ignore=shutil.ignore_patterns("__pycache__"))
        program = ("from pathlib import Path\nfrom adapters.claude import install, hooks\n"
                   "assert install.ROOT == Path.cwd()\n"
                   "assert install.native_source() == (Path.cwd() / 'adapters/claude/native_hook.py').read_bytes()\n"
                   "assert len(hooks.hook_groups(Path('/tmp/copied-profile'))) == 5\n")
        result = subprocess.run([os.sys.executable, "-c", program], cwd=copied, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([os.sys.executable, str(copied / "scripts/install_claude.py"), "--help"],
                                cwd=copied, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--install-cli", result.stdout)

    def test_remove_failure_restores_legacy_links_settings_and_runtime_files(self):
        name = adapter.workflow.SKILLS[0]
        legacy = self.base / "legacy-skills"
        self.write(legacy / name / "SKILL.md", "legacy")
        destination = self.home / ".claude/skills" / name
        destination.parent.mkdir(parents=True)
        destination.symlink_to(legacy / name, target_is_directory=True)
        self.install([legacy])
        before = self.snapshot()
        symlink_to = Path.symlink_to
        failed = False
        def fail_restore_once(path, target, *args, **kwargs):
            nonlocal failed
            if path == destination and str(target) == str(legacy / name) and not failed:
                failed = True
                raise OSError("simulated legacy link restore failure")
            return symlink_to(path, target, *args, **kwargs)
        with patch.object(Path, "symlink_to", autospec=True, side_effect=fail_restore_once):
            with self.assertRaisesRegex(OSError, "simulated legacy"):
                adapter.remove(self.home)
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), before)
        adapter.check(self.home)
        unlink = Path.unlink
        failed = False
        def fail_native_unlink_once(path, *args, **kwargs):
            nonlocal failed
            if path == adapter.native_path(self.home) and not failed:
                failed = True
                raise OSError("simulated native removal failure")
            return unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", autospec=True, side_effect=fail_native_unlink_once):
            with self.assertRaisesRegex(OSError, "simulated native"):
                adapter.remove(self.home)
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), before)
        adapter.check(self.home)
        adapter.remove(self.home)
        self.assertEqual(os.readlink(destination), str(legacy / name))

    def test_target_guard_rejection_prevents_cli_packages_and_profile_writes(self):
        before = self.snapshot()
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(adapter.platform, "system", return_value="Linux"), \
                patch.object(adapter.workflow, "run_target_guard", side_effect=ValueError("fixture guard denied")) as guard, \
                patch.object(adapter, "install_cli") as cli, \
                patch.object(adapter, "prepare_packages") as packages, \
                contextlib.redirect_stderr(io.StringIO()) as error:
            code = adapter.main(["--install-cli", "--install-packages", "--agent-core-home", str(self.core)])
        self.assertEqual(code, 1)
        self.assertIn("fixture guard denied", error.getvalue())
        guard.assert_called_once_with(self.home)
        cli.assert_not_called()
        packages.assert_not_called()
        self.assertEqual(self.snapshot(), before)


class ClaudeNativeCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.binary = self.home / ".local/bin/claude"

    def test_usable_native_cli_updates_latest_without_using_path_npm(self):
        self.binary.parent.mkdir(parents=True)
        self.binary.write_text("fixture native binary")
        with patch.object(Path, "home", return_value=self.home), \
                patch.object(adapter.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                patch.object(shutil, "which", return_value="/broken/npm/claude") as path_lookup:
            adapter.install_cli()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands, [[str(self.binary), "--version"],
                                    [str(self.binary), "install", "latest"], [str(self.binary), "--version"]])
        path_lookup.assert_not_called()

    def test_absent_or_failed_native_probe_bootstraps_official_latest(self):
        for mode in ("absent", "returncode", "execution_error"):
            with self.subTest(mode=mode):
                if mode != "absent":
                    self.binary.parent.mkdir(parents=True, exist_ok=True)
                    self.binary.write_text("fixture broken native binary")
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    if kwargs.get("capture_output"):
                        if mode == "execution_error":
                            raise PermissionError("fixture native launcher is not executable")
                        return subprocess.CompletedProcess(command, 1)
                    return subprocess.CompletedProcess(command, 0)
                with patch.object(Path, "home", return_value=self.home), \
                        patch.object(adapter.subprocess, "run", side_effect=run), \
                        patch.object(shutil, "which", return_value="/broken/npm/claude") as path_lookup:
                    adapter.install_cli()
                offset = 0 if mode == "absent" else 1
                self.assertEqual(calls[offset][0], "curl")
                self.assertIn("https://claude.ai/install.sh", calls[offset])
                self.assertEqual(calls[offset + 1][0], "bash")
                self.assertEqual(calls[offset + 1][-1], "latest")
                self.assertEqual(calls[-1], [str(self.binary), "--version"])
                path_lookup.assert_not_called()
                self.binary.unlink(missing_ok=True)


class ClaudeInstallerFlagsTests(unittest.TestCase):
    def test_optional_shell_flags_using_only_extracted_parser(self):
        source = (adapter.ROOT / "scripts" / "install.sh").read_text()
        arms = re.search(r"    --claude-code\).*?(?=    --no-registry\))", source, re.S).group()
        validate = re.search(r'case "\$CLAUDE_CODE_MODE" in.*?\nesac', source, re.S).group()
        parser = ('set -eu\nCLAUDE_CODE_MODE=never\nwhile [[ $# -gt 0 ]]; do\ncase "$1" in\n'
                  + arms + '*) exit 3 ;;\nesac\ndone\n' + validate + '\nprintf "%s" "$CLAUDE_CODE_MODE"\n')
        for args, mode in (([], "never"), (["--claude-code", "existing"], "existing"),
                           (["--claude-code", "latest"], "latest"),
                           (["--claude-code", "latest", "--no-claude-code"], "never")):
            result = subprocess.run(["bash", "-c", parser, "flags-only", *args], text=True, capture_output=True)
            with self.subTest(args=args):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, mode)
        for args in (["--claude-code", "invalid"], ["--claude-code"]):
            result = subprocess.run(["bash", "-c", parser, "flags-only", *args], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
