import json
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

    def test_default_paths_are_not_machine_specific(self):
        settings = load_settings(Path("/tmp/proxy-relay-example/settings.json"))
        combined = "\n".join(str(value) for value in settings.values())
        self.assertNotIn("C:/" + "Apps" + "External", combined)
        self.assertNotIn("Alex Mercer", combined)


if __name__ == "__main__":
    unittest.main()
