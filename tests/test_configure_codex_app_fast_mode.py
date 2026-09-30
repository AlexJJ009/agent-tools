import importlib.util
import tomllib
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
            config.parent.mkdir()
            config.write_text('[projects."/fixture"]\ntrust_level = "trusted"\n')
            MODULE.patch_config(config, "priority", "true")
            first = config.read_bytes()
            MODULE.patch_config(config, "priority", "true")
            self.assertEqual(config.read_bytes(), first)
            data = tomllib.loads(config.read_text())
            self.assertEqual(data["model_context_window"], 500000)
            self.assertEqual(data["model_auto_compact_token_limit"], 430000)
            self.assertEqual(data["model_auto_compact_token_limit_scope"], "total")
            self.assertEqual(data["service_tier"], "priority")
            self.assertTrue(data["features"]["fast_mode"])
            self.assertEqual(data["projects"], {"/fixture": {"trust_level": "trusted"}})


if __name__ == "__main__":
    unittest.main()
