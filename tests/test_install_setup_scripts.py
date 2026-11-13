"""scripts/setup/*.sh run only what their flags ask for, in a temporary profile."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup"
SCRIPTS = ("codex.sh", "cc-switch.sh", "host.sh")


class SetupScriptTests(unittest.TestCase):
    def run_script(self, home, name, *args, **extra_env):
        env = os.environ.copy()
        env.update({
            "HOME": str(home),
            "CODEX_HOME": str(home / ".codex"),
            "CC_SWITCH_DB_PATH": str(home / ".cc-switch" / "cc-switch.db"),
            "TMUX_CONF": str(home / ".tmux.conf"),
            "SYNC_CC_SWITCH_CODEX_CURRENT": "0",
            **extra_env,
        })
        return subprocess.run(["bash", str(SETUP / name), *args], env=env, cwd=home,
                              text=True, capture_output=True, timeout=60)

    def test_every_script_has_short_help_and_rejects_unknown_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for name in SCRIPTS:
                with self.subTest(script=name):
                    helped = self.run_script(home, name, "--help")
                    self.assertEqual(helped.returncode, 0, helped.stderr)
                    self.assertLess(len(helped.stdout.splitlines()), 40)
                    rejected = self.run_script(home, name, "--no-such-flag")
                    self.assertEqual(rejected.returncode, 2)
                    self.assertIn("unknown argument: --no-such-flag", rejected.stderr)
            self.assertEqual(list(home.iterdir()), [])

    def test_host_runs_only_the_requested_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skipped = self.run_script(home, "host.sh", "--no-fail2ban", "--no-tmux", "--no-desktop-ssh")
            self.assertEqual(skipped.returncode, 0, skipped.stderr)
            self.assertFalse((home / ".tmux.conf").exists())
            self.assertIn("skipped (--no-fail2ban)", skipped.stdout)
            self.assertIn("skipped (--no-desktop-ssh)", skipped.stdout)
            tmux = self.run_script(home, "host.sh", "--no-fail2ban", "--no-desktop-ssh")
            self.assertEqual(tmux.returncode, 0, tmux.stderr)
            self.assertIn("set -g mouse on", (home / ".tmux.conf").read_text())

    def test_codex_configures_defaults_and_honours_no_config(self):
        flags = ("--no-here", "--no-remote-control", "--proxy-wrapper", "never")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            bare = self.run_script(home, "codex.sh", "--no-config", *flags)
            self.assertEqual(bare.returncode, 0, bare.stderr)
            self.assertFalse((home / ".codex" / "config.toml").exists())
            full = self.run_script(home, "codex.sh", *flags)
            self.assertEqual(full.returncode, 0, full.stderr)
            config = (home / ".codex" / "config.toml").read_text()
            self.assertIn("model_context_window = 500000", config)
            self.assertIn("[features]", config)
            self.assertFalse((home / ".local" / "bin" / "codex-here").exists())

    def test_codex_installs_codex_here_from_the_resolved_install_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = self.run_script(home, "codex.sh", "--no-config", "--no-remote-control",
                                     "--proxy-wrapper", "never", AGENT_TOOLS_INSTALL_ROOT=str(ROOT))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((home / ".local" / "bin" / "codex-here").is_file())

    def test_codex_guard_rejects_cross_platform_config_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".codex").mkdir()
            polluted = 'model_provider = "custom"\nproject = "C:/Users/Alex/project"\n'
            (home / ".codex" / "config.toml").write_text(polluted)
            result = self.run_script(home, "codex.sh")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Windows path pollution", result.stdout + result.stderr)
            self.assertEqual((home / ".codex" / "config.toml").read_text(), polluted)
            self.assertFalse((home / ".local" / "bin" / "codex-here").exists())

    def test_cc_switch_skips_every_step_it_is_told_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = self.run_script(home, "cc-switch.sh", "--no-update", "--no-templates", "--no-sync")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("not updated (--no-update)", result.stdout)
            self.assertEqual(list(home.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
