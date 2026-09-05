import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class InstallTargetGuardWiringTests(unittest.TestCase):
    def test_linux_installer_defaults_to_native_platform_only(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS="${CODEX_APP_FAST_MODE_INCLUDE_WSL_WINDOWS:-never}"', text)
        self.assertIn('CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS="${CODEX_SQLITE_LOG_GUARD_INCLUDE_WSL_WINDOWS:-never}"', text)
        self.assertIn("refusing WSL-to-Win11 config writes", text)

    def test_linux_installer_runs_guard_before_skill_or_config_writes(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        shared_guard = text.index("update_cc_switch_cli\nrun_codex_target_guard before")
        config_write = text.index("if [[ \"$INSTALL_CODEX_CONFIG\" -eq 1 ]]; then")
        skill_write = text.rindex("install_codex_patch_safety_skill")
        agent_wt_write = text.rindex("install_agent_wt")
        self.assertLess(shared_guard, config_write)
        self.assertLess(shared_guard, skill_write)
        self.assertLess(shared_guard, agent_wt_write)

    def test_linux_installer_manages_context_window_defaults(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('CODEX_MODEL_CONTEXT_WINDOW="${CODEX_MODEL_CONTEXT_WINDOW:-500000}"', text)
        self.assertIn(
            'CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT="${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT:-430000}"',
            text,
        )
        self.assertIn(
            'CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE="${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE:-total}"',
            text,
        )
        self.assertIn("model_context_window = {context_window}", text)
        self.assertIn("model_auto_compact_token_limit = {auto_compact_limit}", text)
        self.assertIn('model_auto_compact_token_limit_scope = "{auto_compact_scope}"', text)

    def test_win11_installer_runs_native_guard_before_skill_install(self):
        text = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertIn("function Assert-CodexTargetGuard", text)
        guard_call = text.index("Assert-CodexTargetGuard -RepoRoot $Root")
        skill_install = text.rindex("Install-CodexPatchSafetySkill")
        self.assertLess(guard_call, skill_install)

    def test_autodl_bootstrap_uses_target_guard_before_provider_setup(self):
        text = (ROOT / "scripts" / "bootstrap_autodl_ai_tools.sh").read_text(encoding="utf-8")
        guard_call = text.index("run_codex_target_guard\n  configure_codex_from_transfer")
        self.assertGreater(guard_call, 0)
        self.assertIn("--path-only", text)


if __name__ == "__main__":
    unittest.main()
