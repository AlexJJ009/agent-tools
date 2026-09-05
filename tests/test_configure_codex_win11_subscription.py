import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "configure_codex_win11_subscription.py"
SPEC = importlib.util.spec_from_file_location("configure_codex_win11_subscription", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ConfigureCodexWin11SubscriptionTests(unittest.TestCase):
    def test_default_base_url_uses_current_relay(self):
        self.assertEqual(MODULE.DEFAULT_BASE_URL, "http://15.204.46.107:8080")

    def test_patch_config_removes_top_level_stream_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / ".codex"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                'stream_idle_timeout_ms = 1\n'
                'stream_max_retries = 2\n'
                'model_provider = "custom"\n\n'
                '[features]\nmemories = true\n',
                encoding="utf-8",
            )
            MODULE.patch_config(
                codex_home=codex_home,
                provider_id="custom",
                base_url=MODULE.DEFAULT_BASE_URL,
                bearer_token="secret",
                model="gpt-5.5",
                reasoning_effort="high",
                service_tier="priority",
                model_context_window=500000,
                model_auto_compact_token_limit=430000,
                model_auto_compact_token_limit_scope="total",
                stream_idle_timeout_ms=1800000,
                stream_max_retries=20,
                approval_policy="on-request",
                sandbox_mode="workspace-write",
                approvals_reviewer="guardian_subagent",
            )
            text = (codex_home / "config.toml").read_text(encoding="utf-8")
            preamble, provider = text.split("[model_providers.custom]", 1)
            self.assertNotIn("stream_idle_timeout_ms", preamble)
            self.assertNotIn("stream_max_retries", preamble)
            self.assertIn("model_context_window = 500000", preamble)
            self.assertIn("model_auto_compact_token_limit = 430000", preamble)
            self.assertIn('model_auto_compact_token_limit_scope = "total"', preamble)
            self.assertIn("stream_idle_timeout_ms = 1800000", provider)
            self.assertIn("stream_max_retries = 20", provider)

    def test_cc_switch_provider_config_includes_context_defaults(self):
        text = MODULE.cc_switch_provider_config(
            "custom",
            "Custom",
            MODULE.DEFAULT_BASE_URL,
            "secret",
        )
        self.assertIn("model_context_window = 500000", text)
        self.assertIn("model_auto_compact_token_limit = 430000", text)
        self.assertIn('model_auto_compact_token_limit_scope = "total"', text)
        preamble, provider = text.split("[model_providers.custom]", 1)
        self.assertIn("model_context_window", preamble)
        self.assertNotIn("model_context_window", provider)

    def test_posix_rejects_wsl_profile_for_win11_script(self):
        if MODULE.os.name == "nt":
            self.skipTest("POSIX boundary test")
        with self.assertRaises(SystemExit):
            MODULE.validate_win11_target_paths(
                Path("/home/alex_mercer/.codex"),
                Path("/home/alex_mercer/.cc-switch/cc-switch.db"),
            )

    def test_posix_rejects_drvfs_profile_for_win11_script(self):
        if MODULE.os.name == "nt":
            self.skipTest("POSIX boundary test")
        with self.assertRaises(SystemExit):
            MODULE.validate_win11_target_paths(
                Path("/mnt/c/Users/Alex Mercer/.codex"),
                Path("/mnt/c/Users/Alex Mercer/.cc-switch/cc-switch.db"),
            )

    def test_rejects_mismatched_windows_profiles(self):
        if MODULE.os.name == "nt":
            self.skipTest("POSIX boundary test")
        with self.assertRaises(SystemExit):
            MODULE.validate_win11_target_paths(
                Path("/mnt/c/Users/Alex Mercer/.codex"),
                Path("/mnt/c/Users/Other/.cc-switch/cc-switch.db"),
            )


if __name__ == "__main__":
    unittest.main()
