import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "codex_target_guard.py"
SPEC = importlib.util.spec_from_file_location("codex_target_guard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


VALID_CONFIG = '''model_provider = "custom"
approval_policy = "on-request"

[model_providers.custom]
base_url = "http://15.204.46.107:8080"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = true
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
'''


class CodexTargetGuardTests(unittest.TestCase):
    def unix_paths(self, root):
        home = root / "alice"
        return home, home / ".codex", home / ".cc-switch" / "cc-switch.db"

    def test_linux_accepts_one_unix_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, codex_home, db = self.unix_paths(Path(tmp))
            self.assertEqual(
                MODULE.validate_paths(
                    "linux",
                    codex_home,
                    db,
                    "alice",
                    actual_platform="linux",
                    actual_user="alice",
                    home_dir=home,
                ),
                "linux",
            )

    def test_linux_rejects_windows_profile(self):
        with self.assertRaisesRegex(MODULE.GateFailure, "Windows /mnt"):
            MODULE.validate_paths(
                "linux",
                Path("/mnt/c/Users/Alice/.codex"),
                Path("/mnt/c/Users/Alice/.cc-switch/cc-switch.db"),
                "alice",
                actual_platform="linux",
                actual_user="alice",
                home_dir=Path("/home/alice"),
            )

    def test_win11_rejects_posix_execution_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, codex_home, db = self.unix_paths(Path(tmp))
            with self.assertRaisesRegex(MODULE.GateFailure, "platform mismatch"):
                MODULE.validate_paths(
                    "win11",
                    codex_home,
                    db,
                    "alice",
                    actual_platform="linux",
                    actual_user="alice",
                    home_dir=home,
                )

    def test_wsl_rejects_windows_common_config_pollution(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(
                'model_catalog_json = "C:\\\\Users\\\\Alice\\\\Downloads\\\\model-catalog.json"\n' + VALID_CONFIG,
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.GateFailure, "Windows path pollution"):
                MODULE.validate_config_contract(
                    config,
                    "wsl",
                    "http://15.204.46.107:8080",
                    allow_missing=False,
                )

    def test_provider_contract_accepts_only_provider_scoped_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(VALID_CONFIG, encoding="utf-8")
            report = MODULE.validate_config_contract(
                config,
                "linux",
                "http://15.204.46.107:8080",
                allow_missing=False,
            )
            self.assertEqual(report["status"] if "status" in report else report["config"], "valid")

    def test_provider_contract_rejects_top_level_stream_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text("stream_max_retries = 20\n" + VALID_CONFIG, encoding="utf-8")
            with self.assertRaisesRegex(MODULE.GateFailure, "provider-scoped"):
                MODULE.validate_config_contract(config, "linux", None, allow_missing=False)


if __name__ == "__main__":
    unittest.main()
