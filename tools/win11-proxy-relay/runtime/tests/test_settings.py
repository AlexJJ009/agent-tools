import json
import importlib.util
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

RUNTIME_DIR = Path(__file__).resolve().parents[1]
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from settings import load_settings


class SettingsTests(unittest.TestCase):
    def test_relative_paths_resolve_from_settings_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings_path = root / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "v2rayn_dir": "vendor/v2rayN",
                        "state_dir": "state",
                        "ssh_config": "state/ssh_config",
                        "ssh_identity_file": "state/id_ed25519",
                        "ssh_known_hosts": "state/known_hosts",
                        "main_controller_ports": [18001],
                    }
                ),
                encoding="utf-8",
            )
            settings = load_settings(settings_path)
        self.assertEqual(settings["v2rayn_dir"], str(root / "vendor" / "v2rayN"))
        self.assertEqual(settings["state_dir"], str(root / "state"))
        self.assertEqual(settings["ssh_config"], str(root / "state" / "ssh_config"))
        self.assertEqual(settings["ssh_identity_file"], str(root / "state" / "id_ed25519"))
        self.assertEqual(settings["ssh_known_hosts"], str(root / "state" / "known_hosts"))
        self.assertEqual(settings["main_controller_ports"], [18001])

    def test_default_paths_follow_relocated_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "relocated install"
            runtime = root / "runtime"
            runtime.mkdir(parents=True)
            module_path = runtime / "settings.py"
            shutil.copy2(RUNTIME_DIR / "settings.py", module_path)
            spec = importlib.util.spec_from_file_location("relocated_relay_settings", module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            settings = module.load_settings()
            self.assertEqual(Path(settings["v2rayn_dir"]), root / "v2rayN-windows-64")
            self.assertEqual(Path(settings["state_dir"]), root / "state")
            self.assertEqual(Path(settings["core_exe"]),
                             root / "v2rayN-windows-64/bin/sing_box/sing-box.exe")
            self.assertFalse((root / "state").exists(), "reading defaults must not create runtime state")


if __name__ == "__main__":
    unittest.main()
