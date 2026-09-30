import json
import subprocess
import sys
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class LinearWorkflowInstallerContractTests(unittest.TestCase):

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



    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell unavailable")
    def test_win11_installer_rejects_mismatched_write_profiles_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home, other = root / "home", root / "other"
            for codex, database in ((other / ".codex", home / ".cc-switch/cc-switch.db"),
                                    (home / ".codex", other / ".cc-switch/cc-switch.db")):
                with self.subTest(codex=codex, database=database):
                    result = subprocess.run(
                        ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/install-win11.ps1"),
                         "-UserHome", str(home), "-CodexHome", str(codex), "-CcSwitchDb", str(database)],
                        text=True, errors="replace", capture_output=True, timeout=20,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("must belong to the same native Win11 profile", result.stderr)
                    self.assertEqual(list(root.iterdir()), [])

    def test_disable_rejects_descriptor_path_escape_before_touching_other_profile(self):
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
                    descriptor = json.loads((ROOT / "config/managed-packages/linear-workflow.json").read_text())
                    descriptor["codex_targets"][0]["destination"] = destination
                    path = root / "descriptor.json"
                    path.write_text(json.dumps(descriptor))
                    result = subprocess.run(
                        [sys.executable, str(ROOT / "scripts/managed_package_installer.py"), "disable",
                         "--descriptor", str(path), "--repo-root", str(ROOT), "--home", str(home)],
                        capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("discovery target escapes home", result.stderr)
                    self.assertEqual(sentinel.read_text(), "unrelated user skill")
                    self.assertEqual(list(home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
