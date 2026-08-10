import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "codex_fleet_guard.py"
SPEC = importlib.util.spec_from_file_location("codex_fleet_guard", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TARGET = {
    "id": "ovh-109",
    "platform": "linux",
    "transport": "ssh",
    "ssh_alias": "ovh-109",
    "expected_user": "ubuntu",
    "codex_home": "/home/ubuntu/.codex",
    "cc_switch_db": "/home/ubuntu/.cc-switch/cc-switch.db",
    "cc_switch_bin": "/home/ubuntu/.local/bin/cc-switch",
}


class CodexFleetGuardTests(unittest.TestCase):
    def test_path_only_is_forwarded_for_skill_scoped_preflight(self):
        target = {
            "id": "server",
            "platform": "linux",
            "transport": "ssh",
            "ssh_alias": "server",
            "expected_user": "root",
            "codex_home": "/root/.codex",
            "cc_switch_db": "/root/.cc-switch/cc-switch.db",
        }
        args = MODULE.guard_args(target, None, path_only=True)
        self.assertIn("--path-only", args)
        self.assertIn("--allow-missing-config", args)
        self.assertIn("--skip-cc-switch-read-check", args)

    def test_ssh_transport_is_batch_only_without_tty(self):
        command = MODULE.ssh_base(TARGET)
        self.assertIn("BatchMode=yes", command)
        self.assertIn("RequestTTY=no", command)
        self.assertNotIn("-t", command)
        self.assertNotIn("-tt", command)

    def test_manifest_requires_safe_target_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "fleet.json"
            invalid = dict(TARGET)
            invalid["id"] = "ovh-109; rm -rf /"
            manifest.write_text(json.dumps({"targets": [invalid]}), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.FleetFailure, "unsafe target id"):
                MODULE.load_manifest(manifest)

    def test_wrong_platform_canary_is_opposite(self):
        self.assertEqual(MODULE.opposite_platform("linux"), "win11")
        self.assertEqual(MODULE.opposite_platform("win11"), "linux")

    def test_remote_command_uses_home_expansion_only_on_remote_side(self):
        command = MODULE.remote_helper_relative_path()
        self.assertFalse(command.startswith("/mnt/"))
        self.assertFalse(command.startswith("C:"))

    def test_remote_guard_uses_batch_ssh_and_remote_home(self):
        captured = []
        original = MODULE.run
        try:
            def fake_run(command, check=True):
                captured.append(command)
                return MODULE.subprocess.CompletedProcess(command, 0, "{}", "")

            MODULE.run = fake_run
            MODULE.run_guard(TARGET, "http://15.204.46.107:8080")
        finally:
            MODULE.run = original
        self.assertIn("BatchMode=yes", captured[0])
        self.assertIn("RequestTTY=no", captured[0])
        self.assertIn('"$HOME/.local/lib/agent-tools/codex_target_guard.py"', captured[0][-1])


if __name__ == "__main__":
    unittest.main()
