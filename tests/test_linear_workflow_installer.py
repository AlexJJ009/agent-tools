import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LinearWorkflowInstallerContractTests(unittest.TestCase):
    def test_unix_flags_and_only_mode_are_wired(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        for flag in ("--linear-workflow", "--linear-workflow-only", "--no-linear-workflow"):
            self.assertIn(flag, text)
        only = text.index('if [[ "$LINEAR_WORKFLOW_ONLY" -eq 1 ]]')
        unrelated = text.index("configure_fail2ban_hardening", only)
        self.assertLess(only, unrelated)

    def test_prewrite_guard_precedes_installer_dispatch(self):
        unix = (ROOT / "install.sh").read_text(encoding="utf-8")
        guard = unix.rindex("run_codex_target_guard")
        policy = unix.index("configure_goal_plan_install_policy", guard)
        dispatch = unix.index("install_linear_workflow_only\n  exit 0", policy)
        self.assertLess(guard, policy)
        self.assertLess(policy, dispatch)
        win = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertLess(win.rindex("Assert-CodexTargetGuard -RepoRoot"), win.rindex("Install-LinearWorkflow -RepoRoot"))

    def test_win11_guard_binds_actual_write_home_to_codex_and_cc_switch_profile(self):
        text = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        invocation = "Assert-CodexTargetGuard -RepoRoot $Root -TargetUserHome $UserHome -TargetCodexHome $CodexHome -TargetCcSwitchDb $CcSwitchDb"
        self.assertIn(invocation, text)
        self.assertIn("$normalizedUserHome.Equals($codexProfile", text)
        self.assertIn("$normalizedUserHome.Equals($ccSwitchProfile", text)
        self.assertIn("must belong to the same native Win11 profile", text)

    def test_win11_flags_and_launcher_contract(self):
        text = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$LinearWorkflow", text)
        self.assertIn("[switch]$NoLinearWorkflow", text)
        self.assertIn("[switch]$LegacyGoalPlan", text)
        descriptor = json.loads((ROOT / "config" / "managed-packages" / "linear-workflow.json").read_text())
        self.assertEqual("linear-workflow.cmd", descriptor["launcher"]["windows_name"])

    def test_wsl_descriptor_targets_cannot_escape_unix_home(self):
        descriptor = json.loads((ROOT / "config" / "managed-packages" / "linear-workflow.json").read_text())
        for group in ("codex_targets", "claude_targets", "shared_targets"):
            for target in descriptor[group]:
                destination = target["destination"].replace("{version}", "0.4.0")
                self.assertFalse(destination.startswith(("/mnt/", "C:\\", "\\\\")))
                self.assertNotIn("..", Path(destination).parts)

    def test_default_wsl_cross_profile_mode_is_never(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('GOAL_PLAN_INCLUDE_WSL_WINDOWS="${GOAL_PLAN_INCLUDE_WSL_WINDOWS:-never}"', text)

    def test_goal_plan_defaults_to_deprecation_gated_compatibility(self):
        unix = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('INSTALL_GOAL_PLAN=0', unix)
        self.assertIn('GOAL_PLAN_INSTALL_MODE="${GOAL_PLAN_INSTALL_MODE:-auto}"', unix)
        self.assertIn("deprecation-check", unix)
        self.assertIn("managed-status", unix)
        self.assertIn("--legacy-goal-plan", unix)
        self.assertIn("--skip-plugin-registration", unix)

        win = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertIn('ValidateSet("deprecation-check", "managed-status")', win)
        self.assertIn("-RegisterPlugin:$registerGoalPlan", win)
        self.assertIn("--skip-plugin-registration", win)


if __name__ == "__main__":
    unittest.main()
