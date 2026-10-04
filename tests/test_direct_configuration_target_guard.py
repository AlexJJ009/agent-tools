import subprocess
import os
import tempfile
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
CODEX_HOME_PLACEHOLDER = "<codex_home>"
CC_SWITCH_DB_PLACEHOLDER = "<cc_switch_db>"


class DirectConfigurationTargetGuardTests(unittest.TestCase):
    def assert_rejected_before_write(self, script: Path, *args: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home / ".codex"
            codex.mkdir()
            (codex / "config.toml").write_text('note = "C:/Users/other/project"\n')
            (codex / "auth.json").write_text('{"fixture":"preserve"}')
            def snapshot():
                return {str(p.relative_to(home)): p.read_bytes() if p.is_file() else None
                        for p in home.rglob("*")}
            before = snapshot()
            replacements = {CODEX_HOME_PLACEHOLDER: str(codex),
                            CC_SWITCH_DB_PLACEHOLDER: str(home / ".cc-switch/cc-switch.db")}
            completed = subprocess.run(
                [sys.executable, str(script), *(replacements.get(arg, arg) for arg in args)],
                env=dict(os.environ, HOME=str(home), CODEX_HOME=str(codex),
                         CC_SWITCH_DB_PATH=replacements[CC_SWITCH_DB_PLACEHOLDER]),
                text=True, capture_output=True, check=False, timeout=15,
            )
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            self.assertIn("CODEX_TARGET_GUARD=RED", completed.stdout + completed.stderr)
            self.assertEqual(snapshot(), before)

    def test_fast_mode_direct_script_rejects_polluted_profile_without_writes(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "configure_codex_app_fast_mode.py",
            "--codex-home",
            CODEX_HOME_PLACEHOLDER,
        )

    def test_sqlite_guard_direct_script_rejects_polluted_profile_without_writes(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "configure_codex_sqlite_log_guard.py",
            "--mode",
            "enable",
            "--codex-home",
            CODEX_HOME_PLACEHOLDER,
        )

    def test_win11_bearer_script_requires_native_windows(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "configure_codex_win11_subscription.py",
            "--codex-home",
            CODEX_HOME_PLACEHOLDER,
            "--cc-switch-db",
            CC_SWITCH_DB_PLACEHOLDER,
        )

    def test_provider_bucket_apply_rejects_polluted_profile_without_writes(self):
        self.assert_rejected_before_write(
            ROOT / "scripts" / "migrate_codex_provider_bucket.py",
            "--codex-dir",
            CODEX_HOME_PLACEHOLDER,
            "--cc-switch-db",
            CC_SWITCH_DB_PLACEHOLDER,
            "--skip-history",
            "--skip-live-config",
            "--skip-cc-switch",
            "--apply",
            "--yes",
        )


if __name__ == "__main__":
    unittest.main()
