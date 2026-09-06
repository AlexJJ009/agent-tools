import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_work_report_hooks.py"
spec = importlib.util.spec_from_file_location("install_work_report_hooks", SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class WorkReportHookInstallTests(unittest.TestCase):
    maxDiff = 4000

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.python = self.base / "python3"
        self.python.write_text("#!/bin/sh\n", encoding="utf-8")
        self.runtime = self.home / ".agents" / "skills" / "work-report" / "scripts" / "report_runtime.py"
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_text("runtime\n", encoding="utf-8")
        self.calls = []
        self.guard_ok = True

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        self.assertIn("codex_target_guard.py", args[1])
        self.assertIn("--path-only", args)
        code = 0 if self.guard_ok else 1
        return SimpleNamespace(returncode=code, stdout="{}", stderr="guard refused" if code else "")

    def invoke(self, args=()):
        with patch.object(installer, "ROOT", self.repo), patch.object(Path, "home", return_value=self.home), \
             patch.object(installer.platform, "system", return_value="Linux"), \
             patch.object(installer.shutil, "which", return_value=str(self.python)), \
             patch.object(installer.subprocess, "run", side_effect=self.run_command), \
             contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
            rc = installer.main(list(args))
            return rc, stdout.getvalue(), stderr.getvalue()

    def hooks_path(self):
        return self.home / ".codex" / "hooks.json"

    def hooks_data(self):
        return json.loads(self.hooks_path().read_text(encoding="utf-8"))

    def test_changed_managed_options_are_detected_and_repaired(self):
        self.assertEqual(self.invoke()[0], 0)
        data = self.hooks_data()
        data["hooks"]["Stop"][0]["hooks"][0]["timeout"] = 1
        data["hooks"]["Stop"][0]["hooks"][0]["additionalContextLimit"] = 5000
        self.hooks_path().write_text(json.dumps(data))
        self.assertEqual(self.invoke(["--check"])[0], 1)
        self.assertEqual(self.invoke()[0], 0)
        self.assertEqual(self.invoke(["--check"])[0], 0)
        handler = self.hooks_data()["hooks"]["Stop"][0]["hooks"][0]
        self.assertEqual(handler["timeout"], 30)
        self.assertNotIn("additionalContextLimit", handler)

    def is_installed_group(self, group, event):
        with patch.object(installer.shutil, "which", return_value=str(self.python)):
            return installer.is_same_group(group, event, self.home)

    def foreign_group(self):
        return {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": '"/usr/bin/python3" "/tmp/foreign.py" hook',
                    "timeout": 9,
                    "statusMessage": "foreign",
                }
            ],
        }

    def similar_foreign_group(self):
        return {
            "hooks": [
                {
                    "type": "command",
                    "command": f'{json.dumps(str(self.python.resolve()))} {json.dumps(str(self.runtime.resolve()))} hook --foreign',
                    "timeout": 30,
                    "statusMessage": "work-report-v2 extra",
                    "additionalContextLimit": 5000,
                }
            ],
        }

    def test_guard_failure_writes_nothing(self):
        self.guard_ok = False
        rc, _out, _err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertFalse(self.hooks_path().exists())
        self.assertEqual(len(self.calls), 1)

    def test_install_merges_foreign_hooks_and_check_reports_native_review(self):
        path = self.hooks_path()
        path.parent.mkdir(parents=True)
        original = {
            "description": "mine",
            "hooks": {
                "PostToolUse": [self.foreign_group()],
                "Stop": [self.similar_foreign_group()],
            },
        }
        path.write_text(json.dumps(original), encoding="utf-8")

        rc, out, err = self.invoke()
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["trust_status"], "not_checked_by_installer")
        self.assertEqual(payload["groups_added"], 5)
        self.assertTrue(Path(payload["backup"]).is_file())

        data = self.hooks_data()
        self.assertEqual(data["description"], "mine")
        self.assertEqual(data["hooks"]["PostToolUse"][0], original["hooks"]["PostToolUse"][0])
        self.assertEqual(data["hooks"]["Stop"][0], original["hooks"]["Stop"][0])
        for event in installer.EVENTS:
            self.assertTrue(any(self.is_installed_group(group, event) for group in data["hooks"][event]))

        rc, check_out, check_err = self.invoke(["--check"])
        self.assertEqual(rc, 0, check_err)
        check = json.loads(check_out)
        self.assertEqual(check["events_checked"], 5)
        self.assertEqual(check["trust_status"], "not_checked_by_installer")

    def test_duplicate_install_is_idempotent(self):
        self.assertEqual(self.invoke()[0], 0)
        first = self.hooks_data()
        self.assertEqual(self.invoke()[0], 0)
        second = self.hooks_data()
        self.assertEqual(first, second)
        payload = json.loads(self.invoke()[1])
        self.assertEqual(payload["groups_added"], 0)

    def test_remove_preserves_foreign_and_similar_groups(self):
        self.assertEqual(self.invoke()[0], 0)
        data = self.hooks_data()
        data["hooks"]["Stop"].insert(0, self.similar_foreign_group())
        data["hooks"]["PostToolUse"].insert(0, self.foreign_group())
        self.hooks_path().write_text(json.dumps(data), encoding="utf-8")

        rc, out, err = self.invoke(["--remove"])
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["groups_removed"], 5)
        self.assertTrue(Path(payload["backup"]).is_file())

        remaining = self.hooks_data()["hooks"]
        self.assertEqual(remaining["Stop"], [self.similar_foreign_group()])
        self.assertEqual(remaining["PostToolUse"], [self.foreign_group()])
        for event in ("SessionStart", "UserPromptSubmit", "Interrupt"):
            self.assertNotIn(event, remaining)

    def test_remove_recognizes_exact_runtime_command_with_different_python(self):
        path = self.hooks_path()
        path.parent.mkdir(parents=True)
        old_python = self.base / "old" / "python3"
        old_group = {
            "hooks": [
                {
                    "type": "command",
                    "command": f'{json.dumps(str(old_python))} {json.dumps(str(self.runtime.resolve()))} hook',
                    "timeout": 99,
                    "statusMessage": "work-report-v2",
                }
            ],
        }
        path.write_text(json.dumps({"hooks": {"Stop": [old_group]}}), encoding="utf-8")
        rc, out, err = self.invoke(["--remove"])
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(out)["groups_removed"], 1)
        self.assertEqual(self.hooks_data()["hooks"], {})

    def test_malformed_json_and_nonobject_are_preserved_and_fail(self):
        path = self.hooks_path()
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "{broken")
        self.assertIn("invalid hooks JSON preserved", json.loads(err)["error"])

        path.write_text("[]", encoding="utf-8")
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "[]")
        self.assertIn("top-level value must be an object", json.loads(err)["error"])

    def test_foreign_event_shape_is_preserved_and_fails(self):
        path = self.hooks_path()
        path.parent.mkdir(parents=True)
        data = {"hooks": {"Stop": {"hooks": []}, "UserPromptSubmit": [self.foreign_group()]}}
        path.write_text(json.dumps(data), encoding="utf-8")
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), data)
        self.assertIn("hooks.Stop must be a list", json.loads(err)["error"])

    def test_check_is_read_only_and_requires_installed_runtime(self):
        rc, _out, err = self.invoke(["--check"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.calls)
        self.assertFalse(self.hooks_path().exists())
        self.assertIn("hooks file is missing", json.loads(err)["error"])

        self.assertEqual(self.invoke()[0], 0)
        self.runtime.unlink()
        rc, _out, err = self.invoke(["--check"])
        self.assertEqual(rc, 1)
        self.assertFalse(self.calls[-1][1].endswith("missing"))
        self.assertIn("installed report runtime is missing", json.loads(err)["error"])


if __name__ == "__main__":
    unittest.main()
