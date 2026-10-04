import os
import json
import shutil
import importlib.util
from unittest.mock import patch
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class InstallTargetGuardWiringTests(unittest.TestCase):
    def run_isolated_unix_install(self, home, *, check=True, extra_args=(), source_root=None):
        install_root = home / "agent-tools-installed"
        fake_bin = home / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        crontab = fake_bin / "crontab"
        crontab.write_text('#!/bin/sh\nif [ "$1" = "-l" ]; then cat "$HOME/test-crontab" 2>/dev/null; else cat > "$HOME/test-crontab"; fi\n')
        crontab.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "PATH": str(fake_bin) + os.pathsep + env.get("PATH", ""),
            "HOME": str(home),
            "AGENT_TOOLS_HOME": str(install_root),
            "CODEX_HOME": str(home / ".codex"),
            "CC_SWITCH_DB_PATH": str(home / ".cc-switch" / "cc-switch.db"),
            "TMUX_CONF": str(home / ".tmux.conf"),
            "CODEX_MODEL_PROVIDER_ID": "custom",
            "AGENT_TOOLS_CODEX_PROVIDER_BUCKET_APPLY": "1",
            "AGENT_TOOLS_CODEX_PROVIDER_BUCKET_ALL_NON_TARGET": "1",
            "AGENT_TOOLS_CODEX_PROVIDER_BUCKET_ALLOW_RUNNING": "0",
            "AGENT_TOOLS_CODEX_PROVIDER_BUCKET_KILL_RUNNING": "0",
        })
        command = [
            "bash", str((source_root or ROOT) / "scripts/install.sh"),
            "--root", str(home / "projects"),
            "--no-fail2ban-hardening", "--no-cc-switch-update",
            "--no-codex-config", "--no-codex-here",
            "--no-codex-app-fast-mode", "--no-codex-desktop-connection-fast-mode",
            "--no-codex-sqlite-log-guard",
            "--codex-proxy-wrapper", "never", "--no-codex-remote-control",
            "--no-claude-desktop-ssh",
            "--no-agent-core",
        ]
        return subprocess.run(
            command + list(extra_args), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=60
        )

    @staticmethod
    def installation_snapshot(home):
        # The fake crontab executable is test infrastructure, not installer output.
        return {
            str(path.relative_to(home)): (
                ("link", os.readlink(path)) if path.is_symlink()
                else ("file", path.read_bytes()) if path.is_file()
                else ("directory", None)
            )
            for path in home.rglob("*")
            if "fake-bin" not in path.relative_to(home).parts
        }

    def test_unix_guard_rejects_cross_platform_config_before_any_install_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "config.toml").write_text('model_provider = "custom"\nproject = "C:/Users/Alex/project"\n')
            (codex / "auth.json").write_text('{"fixture": "preserve authentication"}')
            (home / ".tmux.conf").write_text("# user settings\n")
            before = self.installation_snapshot(home)
            completed = self.run_isolated_unix_install(home, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Windows path pollution", completed.stdout + completed.stderr)
            self.assertEqual(self.installation_snapshot(home), before)


    def test_static_autodl_installer_before_provider_setup(self):
        text = (ROOT / "scripts" / "bootstrap_autodl_ai_tools.sh").read_text(encoding="utf-8")
        installer = text.index("run_agent_tools_install", text.index("main()"))
        provider = text.index("configure_codex_from_transfer", installer)
        self.assertLess(installer, provider)

    def test_isolated_unix_install_creates_exactly_one_current_scope_skill(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            stale = [home / "agent-tools-installed" / name for name in (
                "linear_workflow/VERSION", "config/managed-packages/linear-workflow.json",
                "scripts/managed_package_installer.py", "docs/linear-workflow/README.md")]
            for path in stale:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("removed release")
            self.run_isolated_unix_install(home)
            current = home / ".codex" / "skills" / "manage-worktrees"
            legacy = home / ".agents" / "skills" / "manage-worktrees"
            claude = home / ".claude" / "skills" / "manage-worktrees"
            self.assertTrue((current / "SKILL.md").is_file())
            self.assertFalse(legacy.exists())
            self.assertFalse((home / "test-crontab").exists())
            self.assertFalse(claude.exists())
            is_wsl = "microsoft" in Path("/proc/version").read_text().lower()
            self.assertEqual((home / ".codex/skills/codex-win11-patch-safety").exists(), is_wsl)
            self.assertTrue((home / ".local" / "bin" / "agent-wt").exists())
            for client in (".codex", ".claude"):
                for skill in ("linear-plan", "linear-deliver"):
                    self.assertFalse((home / client / "skills" / skill).exists())
            self.assertFalse((home / ".local/bin/linear-workflow").exists())
            self.assertTrue((home / "agent-tools-installed/config/retired-packages/linear-workflow.json").is_file())
            for path in stale:
                self.assertFalse(path.parent.exists() if path.parent.name != "scripts" else path.exists(), path)

    def test_isolated_unix_install_rejects_legacy_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            legacy = home / ".agents" / "skills" / "manage-worktrees"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text("legacy", encoding="utf-8")
            completed = self.run_isolated_unix_install(home, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("conflicting manage-worktrees Skill", completed.stderr)
            self.assertFalse((home / ".codex" / "skills" / "manage-worktrees").exists())

    def test_skill_migration_handles_equal_duplicates_and_blocks_modified_legacy(self):
        spec = importlib.util.spec_from_file_location("install_mwt", ROOT / "skills/manage-worktrees/scripts/install_skill.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for kind in ("link", "copies", "conflict", "win-copy"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                legacy = home / ".agents/skills/manage-worktrees"
                target = home / ".codex/skills/manage-worktrees"
                source = ROOT / "skills/manage-worktrees"
                legacy.parent.mkdir(parents=True)
                if kind == "link":
                    legacy.symlink_to(source, target_is_directory=True)
                else:
                    shutil.copytree(source, legacy)
                    if kind != "win-copy":
                        shutil.copytree(source, target)
                    if kind == "conflict":
                        (legacy / "SKILL.md").write_text("user changes")
                with patch.object(module.subprocess, "run") as guard:
                    if kind == "conflict":
                        with self.assertRaises(ValueError):
                            module.install(ROOT, home, home / ".codex", "unix")
                        guard.assert_not_called()
                        self.assertEqual((legacy / "SKILL.md").read_text(), "user changes")
                    else:
                        module.install(ROOT, home, home / ".codex", "win11" if kind == "win-copy" else "unix")
                        guard.assert_called_once()
                        self.assertFalse(legacy.exists())
                        self.assertTrue((target / "SKILL.md").is_file())

    def test_every_committed_manage_worktrees_release_is_a_baseline(self):
        # An installed copy of any earlier commit must stay upgradable, so each
        # committed tree other than the current one needs a baseline entry.
        import hashlib
        prefix = "skills/manage-worktrees/"
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=ROOT)
        if git("rev-parse", "--is-shallow-repository").strip() == b"true":
            self.skipTest("release baselines need full git history")
        spec = importlib.util.spec_from_file_location("install_mwt_history", ROOT / prefix / "scripts/install_skill.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        current = module.tree(ROOT / prefix)
        baselines = [entry["files"] for entry in json.loads((ROOT / prefix / "references/installation-baselines.json").read_text())["releases"]]
        missing = []
        for commit in git("log", "--format=%H", "HEAD", "--", prefix).decode().split():
            files = {}
            for line in git("ls-tree", "-r", commit, "--", prefix).decode().splitlines():
                meta, path = line.split("\t", 1)
                mode, kind, obj = meta.split()
                rel = path[len(prefix):]
                if kind == "blob" and mode != "120000" and "__pycache__/" not in rel:
                    files[rel] = hashlib.sha256(git("cat-file", "blob", obj)).hexdigest()
            if files and files != current and files not in baselines:
                missing.append(commit[:7])
        self.assertEqual(missing, [], "add these releases to installation-baselines.json")

    def test_previous_release_upgrade_and_failed_publish_rollback(self):
        spec = importlib.util.spec_from_file_location("install_mwt_upgrade", ROOT / "skills/manage-worktrees/scripts/install_skill.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        release = json.loads((ROOT / "skills/manage-worktrees/references/installation-baselines.json").read_text())["releases"][0]
        for kind in ("unix-link", "win-copy", "cached-link", "cached-copy", "unknown-cache", "modified", "nested-link", "rollback"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                old_source = home / "old-source"
                for name in release["files"]:
                    file = old_source / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(subprocess.check_output(["git", "show", release["commit"] + ":skills/manage-worktrees/" + name], cwd=ROOT))
                if kind in ("cached-link", "cached-copy", "unknown-cache"):
                    import py_compile
                    py_compile.compile(str(old_source / "scripts/agent_wt.py"), doraise=True)
                    if kind == "unknown-cache":
                        (old_source / "scripts/__pycache__/notes.txt").write_text("user content")
                target = home / ".codex/skills/manage-worktrees"
                legacy = home / ".agents/skills/manage-worktrees"
                target.parent.mkdir(parents=True)
                legacy.parent.mkdir(parents=True)
                if kind in ("unix-link", "cached-link"):
                    target.symlink_to(old_source, target_is_directory=True)
                    legacy.symlink_to(old_source, target_is_directory=True)
                else:
                    shutil.copytree(old_source, target)
                    shutil.copytree(old_source, legacy)
                    (target / ".agent-tools-managed").write_text(module.MARKER)
                    (legacy / ".agent-tools-managed").write_text(module.MARKER)
                before = (target / "SKILL.md").read_bytes()
                if kind == "modified":
                    (legacy / "SKILL.md").write_text("user edit")
                elif kind == "nested-link":
                    (legacy / "extra").symlink_to(old_source / "SKILL.md")
                rename = Path.rename
                def fail_legacy(path, destination):
                    if kind == "rollback" and path == legacy:
                        raise OSError("injected legacy move failure")
                    return rename(path, destination)
                with patch.object(module.subprocess, "run") as guard, patch.object(Path, "rename", fail_legacy):
                    if kind in ("modified", "nested-link", "unknown-cache", "rollback"):
                        with self.assertRaises((ValueError, OSError)):
                            module.install(ROOT, home, home / ".codex", "win11")
                        self.assertEqual((target / "SKILL.md").read_bytes(), before)
                        self.assertTrue(legacy.exists())
                        if kind != "rollback":
                            guard.assert_not_called()
                    else:
                        platform = "unix" if kind in ("unix-link", "cached-link") else "win11"
                        module.install(ROOT, home, home / ".codex", platform)
                        self.assertFalse(legacy.exists())
                        self.assertEqual(module.tree(target), module.tree(ROOT / "skills/manage-worktrees"))
                        if kind in ("unix-link", "cached-link"):
                            self.assertEqual(target.resolve(), ROOT / "skills/manage-worktrees")
                            self.assertEqual((old_source / "SKILL.md").read_bytes(), before)
                        else:
                            manifest = json.loads((target / ".agent-tools-managed").read_text())
                            self.assertEqual(manifest["files"], module.tree(target))
                            (target / "SKILL.md").write_text("later user edit")
                            with self.assertRaises(ValueError):
                                module.install(ROOT, home, home / ".codex", "win11")

    def test_static_windows_launcher_and_migration_wiring(self):
        launcher = (ROOT / "bin/agent-wt.ps1").read_text()
        self.assertNotIn(".agents/skills/manage-worktrees", launcher)
        self.assertIn("$env:CODEX_HOME", launcher)
        self.assertIn(".codex/skills/manage-worktrees", launcher)
        installer = (ROOT / "scripts/install-win11.ps1").read_text()
        self.assertIn("($ApplyCodexProviderBucketMigration -or $DryRunCodexProviderBucketMigration -or $KillRunningCodexProviderBucketMigration)", installer)
        self.assertIn("$KillRunningCodexProviderBucketMigration -and -not $NoKillRunningCodexProviderBucketMigration", installer)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell unavailable")
    def test_win11_installer_rejects_mismatched_write_profiles_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, other = root / "home", root / "other"
            wrapper = root / "capture-installer-error.ps1"
            wrapper_text = (
                "param([string]$Installer, [string]$UserHome, [string]$CodexHome, [string]$CcSwitchDb)\n"
                "$ErrorActionPreference = 'Stop'\n"
                "try {\n"
                "  & $Installer -UserHome $UserHome -CodexHome $CodexHome -CcSwitchDb $CcSwitchDb\n"
                "  exit 0\n"
                "} catch {\n"
                "  [Console]::Error.WriteLine($_.Exception.Message)\n"
                "  exit 1\n"
                "}\n"
            )
            wrapper.write_text(wrapper_text)
            for codex, database in ((other / ".codex", home / ".cc-switch/cc-switch.db"),
                                    (home / ".codex", other / ".cc-switch/cc-switch.db")):
                with self.subTest(codex=codex, database=database):
                    result = subprocess.run(
                        ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(wrapper),
                         "-Installer", "./scripts/install-win11.ps1",
                         "-UserHome", str(home), "-CodexHome", str(codex), "-CcSwitchDb", str(database)],
                        cwd=ROOT, text=True, errors="replace", capture_output=True, timeout=20,
                    )
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertEqual(result.stderr.strip(),
                                     "UserHome, CodexHome, and CcSwitchDb must belong to the same native Win11 profile")
                    self.assertEqual(list(root.iterdir()), [wrapper])
                    self.assertEqual(wrapper.read_text(), wrapper_text)

    def test_explicit_cron_uses_only_isolated_crontab(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.run_isolated_unix_install(home, extra_args=("--cron",))
            self.assertIn("17 * * * *", (home / "test-crontab").read_text())
            self.assertIn("sync_agent_context_cron.sh", (home / "test-crontab").read_text())

    def test_removed_registry_flag_rejects_before_any_install_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "keep.txt").write_text("existing user content")
            before = self.installation_snapshot(home)
            result = self.run_isolated_unix_install(home, check=False, extra_args=("--registry-init-db",))
            self.assertEqual(result.returncode, 2)
            self.assertIn("Experiment Registry installation was removed", result.stderr)
            self.assertEqual(self.installation_snapshot(home), before)

    @staticmethod
    def stage_installer_source(destination):
        # Execute the real installer and guard. Replace only the migration helper:
        # invoking it with --kill-running-codex would affect the test host.
        destination.mkdir()
        for name in (
            "agent_context_sync.config.example.json",
            "bin", "scripts", "config", "skills", "shared",
        ):
            source = ROOT / name
            if source.is_dir():
                shutil.copytree(source, destination / name, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(source, destination / name)
        (destination / "scripts" / "migrate_codex_provider_bucket.py").write_text(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "with (Path(os.environ['HOME']) / 'migration-calls.jsonl').open('a') as output:\n"
            "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        )

    def test_provider_migration_requires_opt_in_and_passes_only_requested_authority(self):
        cases = (
            ((), None),
            (("--dry-run-codex-provider-bucket-migration",),
             ["--target", "custom", "--all-non-target-providers"]),
            (("--apply-codex-provider-bucket-migration",),
             ["--target", "custom", "--apply", "--yes", "--all-non-target-providers"]),
            (("--kill-running-codex-provider-bucket-migration",),
             ["--target", "custom", "--apply", "--yes", "--kill-running-codex", "--all-non-target-providers"]),
            (("--kill-running-codex-provider-bucket-migration", "--no-kill-running-codex-provider-bucket-migration"),
             ["--target", "custom", "--apply", "--yes", "--all-non-target-providers"]),
        )
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            self.stage_installer_source(source)
            for index, (flags, expected) in enumerate(cases):
                with self.subTest(flags=flags):
                    home = Path(temporary) / str(index)
                    codex = home / ".codex"
                    codex.mkdir(parents=True)
                    config = codex / "config.toml"
                    config.write_text('model_provider = "custom"\n')
                    self.run_isolated_unix_install(home, extra_args=flags, source_root=source)
                    calls = home / "migration-calls.jsonl"
                    if expected is None:
                        self.assertFalse(calls.exists(), "ordinary installation must not invoke history migration")
                    else:
                        self.assertEqual([json.loads(line) for line in calls.read_text().splitlines()], [expected])
                    self.assertEqual(config.read_text(), 'model_provider = "custom"\n')


if __name__ == "__main__":
    unittest.main()
