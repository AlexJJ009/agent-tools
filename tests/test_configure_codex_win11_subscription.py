import importlib.util
import contextlib
import io
import os
import tomllib
from unittest.mock import patch
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
            data = tomllib.loads((codex_home / "config.toml").read_text())
            self.assertNotIn("stream_idle_timeout_ms", data)
            self.assertNotIn("stream_max_retries", data)
            self.assertEqual(data["model_context_window"], 500000)
            self.assertEqual(data["model_auto_compact_token_limit"], 430000)
            self.assertEqual(data["model_auto_compact_token_limit_scope"], "total")
            self.assertEqual(data["model_providers"]["custom"]["stream_idle_timeout_ms"], 1800000)
            self.assertEqual(data["model_providers"]["custom"]["stream_max_retries"], 20)
            self.assertFalse(data["features"]["memories"])

    def test_cc_switch_provider_config_includes_context_defaults(self):
        text = MODULE.cc_switch_provider_config(
            "custom",
            "Custom",
            MODULE.DEFAULT_BASE_URL,
            "secret",
        )
        data = tomllib.loads(text)
        self.assertEqual(data["model_context_window"], 500000)
        self.assertEqual(data["model_auto_compact_token_limit"], 430000)
        self.assertEqual(data["model_auto_compact_token_limit_scope"], "total")
        self.assertFalse(data["features"]["memories"])
        self.assertFalse(data["memories"]["generate_memories"])
        self.assertFalse(data["memories"]["use_memories"])
        provider = data["model_providers"]["custom"]
        self.assertNotIn("model_context_window", provider)
        self.assertEqual(provider["base_url"], MODULE.DEFAULT_BASE_URL)
        self.assertEqual(provider["experimental_bearer_token"], "secret")
        self.assertTrue(provider["supports_websockets"])

    def test_profile_mismatch_is_rejected_after_native_platform_check(self):
        # Simulate only host identity. Execute the real shared path guard; this is
        # not a native Windows installer acceptance test.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "Alice"
            other = Path(tmp) / "Bob"
            guard_globals = MODULE.validate_write_target.__globals__
            with patch.dict(guard_globals, {"detected_platform": lambda: "win11"}), \
                 patch.dict(os.environ, {"USERPROFILE": str(home)}):
                MODULE.validate_win11_target_paths(home / ".codex", home / ".cc-switch/cc-switch.db")
                with contextlib.redirect_stderr(io.StringIO()) as error:
                    with self.assertRaises(SystemExit) as refused:
                        MODULE.validate_win11_target_paths(home / ".codex", other / ".cc-switch/cc-switch.db")
                self.assertEqual(refused.exception.code, 2)
                self.assertIn("different profiles", error.getvalue())
                self.assertNotIn("platform mismatch", error.getvalue())
                self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
