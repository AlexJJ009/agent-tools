import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class InstallTargetGuardWiringTests(unittest.TestCase):
    def run_isolated_unix_install(self, home, *, check=True):
        install_root = home / "agent-tools-installed"
        env = os.environ.copy()
        env.update({
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
            "--no-codex-sqlite-log-guard", "--no-codex-provider-bucket-migration",
            "--codex-proxy-wrapper", "never", "--no-codex-remote-control",
            "--no-claude-desktop-ssh", "--no-goal-plan", "--no-linear-workflow",
            "--no-cron", "--no-registry", "--no-agent-core",
        ]
        return subprocess.run(
            command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check
        )

    def test_linux_installer_defaults_to_native_platform_only(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('GOAL_PLAN_INCLUDE_WSL_WINDOWS="${GOAL_PLAN_INCLUDE_WSL_WINDOWS:-never}"', text)
        self.assertIn('$HOME/.agents/skills/manage-worktrees', text)
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
            current = home / ".agents" / "skills" / "manage-worktrees"
            legacy = home / ".codex" / "skills" / "manage-worktrees"
            claude = home / ".claude" / "skills" / "manage-worktrees"
            self.assertTrue((current / "SKILL.md").is_file())
            self.assertFalse(legacy.exists())
            self.assertFalse(claude.exists())
            self.assertTrue((home / ".local" / "bin" / "agent-wt").exists())

    def test_isolated_unix_install_rejects_legacy_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            legacy = home / ".codex" / "skills" / "manage-worktrees"
            legacy.mkdir(parents=True)
            (legacy / "SKILL.md").write_text("legacy", encoding="utf-8")
            completed = self.run_isolated_unix_install(home, check=False)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("duplicate manage-worktrees Skill location", completed.stderr)
            self.assertFalse((home / ".agents" / "skills" / "manage-worktrees").exists())

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
