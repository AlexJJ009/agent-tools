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
        parse_end = unix.index("run_codex_target_guard\n\nif [[ \"$LINEAR_WORKFLOW_ONLY\"")
        self.assertLess(parse_end, unix.index("install_linear_workflow_only\n  exit 0", parse_end))
        win = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertLess(win.rindex("Assert-CodexTargetGuard -RepoRoot"), win.rindex("Install-LinearWorkflow -RepoRoot"))

    def test_win11_flags_and_launcher_contract(self):
        text = (ROOT / "scripts" / "install-win11.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$LinearWorkflow", text)
        self.assertIn("[switch]$NoLinearWorkflow", text)
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


if __name__ == "__main__":
    unittest.main()
