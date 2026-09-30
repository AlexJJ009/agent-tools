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
    def run_isolated_unix_install(self, home, *, check=True, extra_args=()):
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
        })
        command = [
            "bash", str(ROOT / "install.sh"),
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
            command + list(extra_args), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check
        )

    def test_linux_installer_defaults_to_native_platform_only(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertNotIn("goal-plan", text)
        self.assertIn('${CODEX_HOME:-$HOME/.codex}/skills/manage-worktrees', text)
        self.assertNotIn('/mnt/c/.agents/skills/manage-worktrees', text)

    def test_linux_installer_runs_guard_before_skill_or_config_writes(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        shared_guard = text.rindex("run_codex_target_guard")
        config_write = text.index("if [[ \"$INSTALL_CODEX_CONFIG\" -eq 1 ]]; then", shared_guard)
        agent_wt_write = text.rindex("install_agent_wt")
        self.assertLess(shared_guard, config_write)
        self.assertLess(shared_guard, agent_wt_write)

    def test_win11_installer_runs_native_guard_before_skill_install(self):
        text = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertIn("function Assert-CodexTargetGuard", text)
        guard_call = text.rindex("Assert-CodexTargetGuard -RepoRoot $Root")
        skill_install = text.rindex("Install-AgentWt -RepoRoot $Root")
        self.assertLess(guard_call, skill_install)

    def test_autodl_bootstrap_uses_target_guard_before_provider_setup(self):
        text = (ROOT / "scripts" / "bootstrap_autodl_ai_tools.sh").read_text(encoding="utf-8")
        installer = text.index("run_agent_tools_install", text.index("main()"))
        provider = text.index("configure_codex_from_transfer", installer)
        self.assertLess(installer, provider)

    def test_isolated_unix_install_creates_exactly_one_current_scope_skill(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
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
            self.assertTrue((home / "agent-tools-installed/config/managed-packages/linear-workflow.json").is_file())

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

    def test_windows_launcher_and_migration_are_explicit(self):
        launcher = (ROOT / "bin/agent-wt.ps1").read_text()
        self.assertNotIn(".agents/skills/manage-worktrees", launcher)
        self.assertIn("$env:CODEX_HOME", launcher)
        self.assertIn(".codex/skills/manage-worktrees", launcher)
        installer = (ROOT / "scripts/install-win11.ps1").read_text()
        self.assertIn("($ApplyCodexProviderBucketMigration -or $DryRunCodexProviderBucketMigration -or $KillRunningCodexProviderBucketMigration)", installer)
        self.assertIn("$KillRunningCodexProviderBucketMigration -and -not $NoKillRunningCodexProviderBucketMigration", installer)

    def test_explicit_cron_uses_only_isolated_crontab(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.run_isolated_unix_install(home, extra_args=("--cron",))
            self.assertIn("17 * * * *", (home / "test-crontab").read_text())
            self.assertIn("sync_agent_context_cron.sh", (home / "test-crontab").read_text())

    def test_defaults_are_opt_in_and_registry_flag_rejects_before_writes(self):
        text = (ROOT / "install.sh").read_text()
        self.assertIn("INSTALL_CRON=0", text)
        self.assertIn("INSTALL_CODEX_PROVIDER_BUCKET_MIGRATION=0", text)
        self.assertNotIn("install_registry_links.sh", text)
        for flag in ("--apply-codex-provider-bucket-migration", "--dry-run-codex-provider-bucket-migration", "--kill-running-codex-provider-bucket-migration"):
            self.assertIn(flag + ")\n      INSTALL_CODEX_PROVIDER_BUCKET_MIGRATION=1", text)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-created"
            result = subprocess.run(["bash", str(ROOT / "install.sh"), "--registry-init-db", "--install-dir", str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(target.exists())

    def test_skill_and_guide_keep_v1_harness_and_execution_boundaries(self):
        skill = (ROOT / "skills" / "manage-worktrees" / "SKILL.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "GIT_WORKTREE_AND_AGENT_WT_GUIDE.md").read_text(encoding="utf-8")
        self.assertIn("Ask only when a missing fact would change", skill)
        self.assertIn("never hand-build a worktree", skill)
        self.assertIn("Verified harness support is Codex only", skill)
        self.assertNotIn("--setup", skill)
        product_guide = guide.split("## 15. DRAGAI-88 Prototype challenge matrix", 1)[0]
        self.assertNotIn("--setup", product_guide)
        self.assertIn("recommendation: unsupported", product_guide)
        self.assertIn("不执行任何 hook/setup", product_guide)


if __name__ == "__main__":
    unittest.main()
