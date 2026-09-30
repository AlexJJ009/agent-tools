import json
import subprocess
import shutil
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

    def test_deprecated_unix_flags_reject_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-created"
            for flag in ("--linear-workflow", "--linear-workflow-only"):
                result = subprocess.run(
                    ["bash", str(ROOT / "install.sh"), flag, "--install-dir", str(target)],
                    capture_output=True, text=True, errors="replace",
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("deprecated and disabled", result.stderr)
                self.assertFalse(target.exists())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell unavailable")
    def test_deprecated_win_flag_rejects_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "not-created"
            result = subprocess.run(
                ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/install-win11.ps1"),
                 "-LinearWorkflow", "-UserHome", str(target), "-CodexHome", str(target / ".codex"),
                 "-CcSwitchDb", str(target / ".cc-switch/cc-switch.db")],
                capture_output=True, text=True, errors="replace",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("deprecated and disabled", result.stderr)
            self.assertFalse(target.exists())

    def test_defaults_disable_existing_discovery_without_installing(self):
        unix = (ROOT / "install.sh").read_text()
        win = (ROOT / "scripts/install-win11.ps1").read_text()
        self.assertIn("INSTALL_LINEAR_WORKFLOW=0", unix)
        self.assertNotIn("INSTALL_LINEAR_WORKFLOW=1", unix)
        self.assertIn("$installLinearWorkflow = $false", win)
        self.assertNotIn("$installLinearWorkflow = $true", win)
        self.assertIn('managed_package_installer.py" disable', unix)
        self.assertIn('managed_package_installer.py") disable', win)
        self.assertLess(win.index('if ($LinearWorkflow)'), win.index('Install-CodexPatchSafetySkill -RepoRoot $Root'))

    def test_prewrite_guard_precedes_installer_dispatch(self):
        unix = (ROOT / "install.sh").read_text(encoding="utf-8")
        guard = unix.index("run_codex_target_guard before", unix.index("done\n"))
        dispatch = unix.index("install_linear_workflow_only\n  exit 0", guard)
        self.assertLess(guard, dispatch)
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
        self.assertNotIn("GoalPlan", text)
        descriptor = json.loads((ROOT / "config" / "managed-packages" / "linear-workflow.json").read_text())
        self.assertEqual("linear-workflow.cmd", descriptor["launcher"]["windows_name"])

    def test_wsl_descriptor_targets_cannot_escape_unix_home(self):
        descriptor = json.loads((ROOT / "config" / "managed-packages" / "linear-workflow.json").read_text())
        for group in ("codex_targets", "claude_targets", "shared_targets"):
            for target in descriptor[group]:
                destination = target["destination"].replace("{version}", "0.4.0")
                self.assertFalse(destination.startswith(("/mnt/", "C:\\", "\\\\")))
                self.assertNotIn("..", Path(destination).parts)

    def test_goal_plan_is_absent_from_installers(self):
        text = (ROOT / "install.sh").read_text(encoding="utf-8")
        win = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertNotIn("goal-plan", text)
        self.assertNotIn("GoalPlan", win)
        self.assertFalse((ROOT / "goal_plan").exists())
        self.assertFalse((ROOT / "config" / "managed-packages" / "goal-plan.json").exists())


if __name__ == "__main__":
    unittest.main()
