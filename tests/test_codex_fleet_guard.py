import importlib.util
import contextlib
import io
from types import SimpleNamespace
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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



    def test_manifest_requires_safe_target_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "fleet.json"
            invalid = dict(TARGET)
            invalid["id"] = "ovh-109; rm -rf /"
            manifest.write_text(json.dumps({"targets": [invalid]}), encoding="utf-8")
            with self.assertRaisesRegex(MODULE.FleetFailure, "unsafe target id"):
                MODULE.load_manifest(manifest)

    def test_manifest_rejects_profile_escape_before_remote_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "fleet.json"
            for codex_home in ("/etc/.codex", "/.codex", "relative/.codex", "/tmp/not-codex"):
                invalid = dict(TARGET, codex_home=codex_home)
                manifest.write_text(json.dumps({"targets": [invalid]}), encoding="utf-8")
                with self.assertRaisesRegex(MODULE.FleetFailure, "invalid Unix profile paths"):
                    MODULE.load_manifest(manifest)




    def test_sync_uses_profile_home_when_ssh_starts_elsewhere(self):
        target = dict(TARGET, codex_home="/data_storage/yl_test/lgx/home/.codex")
        calls = []

        def fake_run(command, *, check=True, input_text=None):
            calls.append(command)
            if input_text is not None:
                self.assertIn("def validate_paths", input_text)
                return subprocess.CompletedProcess(command, 0, '{"status":"PASS"}', "")
            if command[0] == "scp":
                return subprocess.CompletedProcess(command, 0, "", "")
            if "sha256sum" in command[-1]:
                return subprocess.CompletedProcess(command, 0, MODULE.sha256(MODULE.REMOTE_HELPER) + "  helper\n", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        with mock.patch.object(MODULE, "run", side_effect=fake_run):
            MODULE.sync_target(target)
        scp_command = next(command for command in calls if command[0] == "scp")
        profile_helper = "/data_storage/yl_test/lgx/home/.local/lib/agent-tools/codex_target_guard.py"
        self.assertEqual(scp_command[-1], f"ovh-109:{profile_helper}.tmp")
        self.assertIn(str(Path(profile_helper).parent), calls[1][-1])
        self.assertIn(f"{profile_helper}.tmp", calls[-1][-1])
        self.assertIn(profile_helper, calls[-1][-1])
        with mock.patch.object(MODULE, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "{}", "")
            MODULE.run_guard(target, None)
        self.assertIn(profile_helper, run.call_args.args[0][-1])

    def test_sync_refuses_guard_failure_before_writing(self):
        with mock.patch.object(MODULE, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 2, "", "profile mismatch")
            with self.assertRaisesRegex(MODULE.FleetFailure, "profile mismatch"):
                MODULE.sync_target(TARGET)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["input_text"], MODULE.REMOTE_HELPER.read_text())
    def test_remote_dispatch_preserves_profile_arguments_and_batch_transport(self):
        for path_only in (False, True):
            with self.subTest(path_only=path_only), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                home = str(root / "operator profile")
                # The generated remote shell command runs locally against a harmless
                # executable. A JSON/double-quoted filename would expand $() in sh;
                # shlex.split alone cannot detect that error.
                recorder = root / "python $(touch quote-expanded)"
                recorder.write_text(f"#!{sys.executable}\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n")
                recorder.chmod(0o755)
                endpoint = "https://relay.example.invalid/$(touch endpoint-expanded)"
                target = dict(TARGET, codex_home=home + "/.codex",
                              cc_switch_db=home + "/.cc-switch/cc-switch.db", python_bin=str(recorder))
                with mock.patch.object(MODULE, "run") as run:
                    run.return_value = subprocess.CompletedProcess([], 0, '{"status":"PASS"}', "")
                    MODULE.run_guard(target, endpoint, path_only=path_only)
                command = run.call_args.args[0]
                self.assertIn("BatchMode=yes", command)
                self.assertIn("RequestTTY=no", command)
                self.assertNotIn("-t", command)
                self.assertNotIn("-tt", command)
                result = subprocess.run(["sh", "-c", command[-1]], cwd=root,
                                        text=True, capture_output=True, timeout=5)
                self.assertFalse((root / "quote-expanded").exists(), "interpreter path triggered shell substitution")
                self.assertFalse((root / "endpoint-expanded").exists(), "argument triggered shell substitution")
                self.assertEqual(result.returncode, 0, result.stderr)
                remote = json.loads(result.stdout)
                self.assertEqual(remote[0], home + "/.local/lib/agent-tools/codex_target_guard.py")
                self.assertEqual(remote[remote.index("--codex-home") + 1], target["codex_home"])
                self.assertEqual(remote[remote.index("--cc-switch-db") + 1], target["cc_switch_db"])
                self.assertEqual(remote[remote.index("--expect-base-url") + 1], endpoint)
                for flag in ("--path-only", "--allow-missing-config", "--skip-cc-switch-read-check"):
                    self.assertEqual(flag in remote, path_only)

    def test_preflight_canary_actually_dispatches_opposite_platform_and_rejects_false_green(self):
        args = SimpleNamespace(command="preflight", manifest=Path("unused"), target=[],
                               expect_base_url=None, path_only=True, canary_reject=True)
        for canary_rc in (2, 0):
            with self.subTest(canary_rc=canary_rc):
                responses = [subprocess.CompletedProcess([], 0, '{"status":"PASS"}', ""),
                             subprocess.CompletedProcess([], canary_rc, "{}", "")]
                with mock.patch.object(MODULE, "parse_args", return_value=args), \
                     mock.patch.object(MODULE, "load_manifest", return_value=[TARGET]), \
                     mock.patch.object(MODULE, "run_guard", side_effect=responses) as guard, \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    result = MODULE.main()
                self.assertEqual(result, 0 if canary_rc else 2)
                self.assertEqual(guard.call_args_list[1], mock.call(TARGET, None, "win11", path_only=True))


if __name__ == "__main__":
    unittest.main()
