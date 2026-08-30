import importlib.util
import json
import sqlite3
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
    def test_default_base_url_uses_official_chatgpt_backend(self):
        self.assertEqual(MODULE.DEFAULT_BASE_URL, "https://chatgpt.com/backend-api/codex")
        self.assertEqual(MODULE.DEFAULT_CC_SWITCH_PROVIDER, "codex-official")

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
                model="gpt-5.5",
                reasoning_effort="high",
                service_tier="priority",
                stream_idle_timeout_ms=1800000,
                stream_max_retries=20,
                model_context_window=500000,
                model_auto_compact_token_limit=430000,
                model_auto_compact_token_limit_scope="total",
                approval_policy="on-request",
                sandbox_mode="workspace-write",
                approvals_reviewer="guardian_subagent",
            )
            text = (codex_home / "config.toml").read_text(encoding="utf-8")
            preamble, provider = text.split("[model_providers.custom]", 1)
            self.assertNotIn("stream_idle_timeout_ms", preamble)
            self.assertNotIn("stream_max_retries", preamble)
            self.assertIn("stream_idle_timeout_ms = 1800000", provider)
            self.assertIn("stream_max_retries = 20", provider)
            self.assertIn("model_context_window = 500000", preamble)
            self.assertIn("model_auto_compact_token_limit = 430000", preamble)
            self.assertIn('model_auto_compact_token_limit_scope = "total"', preamble)
            self.assertNotIn("experimental_bearer_token", text)
            self.assertIn('base_url = "https://chatgpt.com/backend-api/codex"', provider)

    def test_cc_switch_provider_config_preserves_context_defaults(self):
        text = MODULE.cc_switch_provider_config(
            "custom", "OpenAI Official", MODULE.DEFAULT_BASE_URL, 500000, 430000, "total"
        )
        self.assertIn("model_context_window = 500000", text)
        self.assertIn("model_auto_compact_token_limit = 430000", text)
        self.assertIn('model_auto_compact_token_limit_scope = "total"', text)
        self.assertNotIn("experimental_bearer_token", text)

    def test_load_chatgpt_auth_rejects_placeholder_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / ".codex"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text(
                '{"auth_mode":"chatgpt","OPENAI_API_KEY":null,"tokens":{"access_token":"placeholder"}}',
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                MODULE.load_chatgpt_auth(codex_home)

    def test_enforce_cc_switch_makes_official_provider_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "cc-switch.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE providers (id TEXT, app_type TEXT, name TEXT, category TEXT, "
                "is_current INTEGER, settings_config TEXT, updated_at INTEGER)"
            )
            conn.execute(
                "INSERT INTO providers VALUES ('codex-official','codex','OpenAI Official','custom',0,'{}',0)"
            )
            conn.execute(
                "INSERT INTO providers VALUES ('custom','codex','relay','custom',1,'{}',0)"
            )
            conn.commit()
            conn.close()
            auth = {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {"access_token": "real-token", "account_id": "account"},
            }
            MODULE.enforce_cc_switch_official_chatgpt(
                db, "codex-official", "custom", MODULE.DEFAULT_BASE_URL, auth, 500000, 430000, "total"
            )
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT id,is_current,settings_config FROM providers WHERE app_type='codex' ORDER BY id"
            ).fetchall()
            conn.close()
            self.assertEqual([(row[0], row[1]) for row in rows], [("codex-official", 1), ("custom", 0)])
            settings = json.loads(rows[0][2])
            self.assertEqual(settings["auth"]["tokens"]["access_token"], "real-token")
            self.assertIn(MODULE.DEFAULT_BASE_URL, settings["config"])
            self.assertNotIn("experimental_bearer_token", settings["config"])

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
