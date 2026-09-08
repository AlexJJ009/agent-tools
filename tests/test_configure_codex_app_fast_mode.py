import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "configure_codex_app_fast_mode.py"
SPEC = importlib.util.spec_from_file_location("configure_codex_app_fast_mode", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ConfigureCodexAppFastModeTests(unittest.TestCase):
    def test_patch_config_sets_context_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".codex" / "config.toml"
            MODULE.patch_config(config, "priority", "true")

            text = config.read_text(encoding="utf-8")
            preamble, features = text.split("[features]", 1)
            self.assertIn("model_context_window = 500000", preamble)
            self.assertIn("model_auto_compact_token_limit = 430000", preamble)
            self.assertIn('model_auto_compact_token_limit_scope = "total"', preamble)
            self.assertIn('service_tier = "priority"', preamble)
            self.assertIn("fast_mode = true", features)


if __name__ == "__main__":
    unittest.main()
