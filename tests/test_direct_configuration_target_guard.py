import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
WINDOWS_CODEX_HOME = "/mnt/c/Users/Unsafe/.codex"
WINDOWS_CC_SWITCH_DB = "/mnt/c/Users/Unsafe/.cc-switch/cc-switch.db"


class DirectConfigurationTargetGuardTests(unittest.TestCase):
    def assert_rejected_before_write(self, script: Path, *args: str) -> None:
        completed = subprocess.run(
            [sys.executable, str(script), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn("CODEX_TARGET_GUARD=RED", completed.stdout + completed.stderr)

    def test_fast_mode_direct_script_rejects_mounted_windows_profile(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "configure_codex_app_fast_mode.py",
            "--codex-home",
            WINDOWS_CODEX_HOME,
        )

    def test_sqlite_guard_direct_script_rejects_mounted_windows_profile(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "configure_codex_sqlite_log_guard.py",
            "--mode",
            "enable",
            "--codex-home",
            WINDOWS_CODEX_HOME,
        )

    def test_win11_bearer_script_requires_native_windows(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "configure_codex_win11_subscription.py",
            "--codex-home",
            WINDOWS_CODEX_HOME,
            "--cc-switch-db",
            WINDOWS_CC_SWITCH_DB,
        )

    def test_provider_bucket_apply_rejects_mounted_windows_profile(self):
        self.assert_rejected_before_write(
            ROOT / "migrate_codex_provider_bucket.py",
            "--codex-dir",
            WINDOWS_CODEX_HOME,
            "--cc-switch-db",
            WINDOWS_CC_SWITCH_DB,
            "--skip-history",
            "--skip-live-config",
            "--skip-cc-switch",
            "--apply",
            "--yes",
        )


if __name__ == "__main__":
    unittest.main()
