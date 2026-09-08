import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install_work_report_schedule.py"
spec = importlib.util.spec_from_file_location("install_work_report_schedule", SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class WorkReportScheduleInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.task = self.base / "task%dir"
        self.task.mkdir()
        self.runtime = self.home / ".agents" / "skills" / "work-report" / "scripts" / "report_runtime.py"
        self.scheduler = self.home / ".agents" / "skills" / "work-report" / "scripts" / "report_scheduler.py"
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_text("runtime", encoding="utf-8")
        self.scheduler.write_text("scheduler", encoding="utf-8")
        self.codex = self.base / "codex"
        self.codex.write_text("codex", encoding="utf-8")
        self.python = self.base / "python3"
        self.python.write_text("python", encoding="utf-8")
        self.cron = ["MAILTO=alex@example.invalid", "5 * * * * /foreign/job # keep"]
        self.interval = 60
        self.guard_ok = True
        self.crontab_read_error = None
        self.crontab_write_error = None
        self.calls = []

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        if len(args) > 1 and "codex_target_guard.py" in args[1]:
            code = 0 if self.guard_ok else 1
            return SimpleNamespace(returncode=code, stdout="{}", stderr="guard refused" if code else "")
        if args[:2] == ["crontab", "-l"]:
            if self.crontab_read_error:
                return SimpleNamespace(returncode=1, stdout="", stderr=self.crontab_read_error)
            return SimpleNamespace(returncode=0, stdout="\n".join(self.cron) + "\n", stderr="")
        if args[:2] in (["crontab", "--help"], ["crontab", "-h"]):
            return SimpleNamespace(returncode=0, stdout="usage: crontab [-T file]", stderr="")
        if args[:2] in (["crontab", "-T"], ["crontab", "-n"]):
            content = Path(args[2]).read_text(encoding="utf-8")
            for line in content.splitlines():
                if line and len(line.split()) < 6 and "=" not in line:
                    return SimpleNamespace(returncode=1, stdout="", stderr="bad minute")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:1] == ["crontab"]:
            if self.crontab_write_error:
                return SimpleNamespace(returncode=1, stdout="", stderr=self.crontab_write_error)
            self.cron = Path(args[1]).read_text(encoding="utf-8").splitlines()
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if len(args) >= 4 and args[2:4] == ["status", "--task-dir"]:
            manifest = {
                "schema_version": "work-report.runtime/2",
                "task_dir": str(self.task),
                "interval_seconds": self.interval,
                "periodic": {"last_ack": {"delivery": "ok"}} if self.interval else None,
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps({"status": "pass", "manifest": manifest}), stderr="")
        raise AssertionError(f"unexpected command: {args}")

    def invoke(self, args=()):
        def which(name):
            if name == "codex":
                return str(self.codex)
            if name == "python3":
                return str(self.python)
            return None

        with patch.object(installer, "ROOT", self.base), patch.object(Path, "home", return_value=self.home), \
             patch.object(installer.platform, "system", return_value="Linux"), \
             patch.object(installer.shutil, "which", side_effect=which), \
             patch.object(installer.os, "getuid", return_value=1000), \
             patch.object(installer.subprocess, "run", side_effect=self.run_command), \
             contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            rc = installer.main(["--task-dir", str(self.task), *args])
            return rc, out.getvalue(), err.getvalue()

    def test_install_registers_cron_and_metadata_preserving_foreign_entries(self):
        rc, out, err = self.invoke()
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["crontab_registered"])
        self.assertTrue(payload["runtime_delivered"])
        self.assertEqual(self.cron[0], "MAILTO=alex@example.invalid")
        self.assertEqual(self.cron[1], "5 * * * * /foreign/job # keep")
        self.assertIn(payload["marker"], self.cron[2])
        self.assertTrue(self.cron[2].startswith("* * * * * "))
        self.assertIn(r"task\%dir", self.cron[2])
        meta = json.loads((self.task / "scheduler.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["schema_version"], "work-report.scheduler/1")
        self.assertEqual(meta["codex_bin"], str(self.codex.resolve()))
        self.assertEqual(meta["python_bin"], str(self.python.resolve()))
        self.assertEqual(meta["codex_home"], str((self.home / ".codex").resolve()))
        self.assertEqual(meta["uid"], 1000)

    def test_check_reports_registered_without_rewriting_cron(self):
        self.assertEqual(self.invoke()[0], 0)
        calls_before = len(self.calls)
        rc, out, err = self.invoke(["--check"])
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["crontab_registered"])
        self.assertTrue(payload["has_interval"])
        self.assertEqual(len([c for c in self.calls[calls_before:] if c[:1] == ["crontab"] and c != ["crontab", "-l"]]), 0)

    def test_check_fails_when_managed_line_differs_from_metadata(self):
        self.assertEqual(self.invoke()[0], 0)
        self.cron[-1] = self.cron[-1].replace("--task-dir", "--wrong-task-dir")
        rc, _out, err = self.invoke(["--check"])
        self.assertEqual(rc, 1)
        self.assertIn("managed cron line is missing or differs", json.loads(err)["error"])

    def test_long_path_stays_in_metadata_not_cron_command(self):
        long_path = ":".join(["/long/runtime/tool/directory"] * 100)
        with patch.dict(installer.os.environ, {"PATH": long_path}):
            self.assertEqual(self.invoke()[0], 0)
        self.assertLess(len(self.cron[-1]), 1000)
        self.assertNotIn(long_path, self.cron[-1])
        self.assertEqual(json.loads((self.task / "scheduler.json").read_text())["path"], long_path)

    def test_remove_only_exact_task_marker(self):
        self.assertEqual(self.invoke()[0], 0)
        self.cron.append("* * * * /other # work-report-v2-schedule:not-this-task")
        self.cron.append("* * * * * /contains-marker work-report-v2-schedule:" + installer.task_hash(self.task) + " # unrelated")
        rc, out, err = self.invoke(["--remove"])
        self.assertEqual(rc, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["entries_removed"], 1)
        self.assertEqual(
            self.cron,
            [
                "MAILTO=alex@example.invalid",
                "5 * * * * /foreign/job # keep",
                "* * * * /other # work-report-v2-schedule:not-this-task",
                "* * * * * /contains-marker work-report-v2-schedule:" + installer.task_hash(self.task) + " # unrelated",
            ],
        )

    def test_guard_failure_and_missing_interval_do_not_write_cron(self):
        self.guard_ok = False
        before = list(self.cron)
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(self.cron, before)
        self.assertIn("target guard rejected", json.loads(err)["error"])

        self.guard_ok = True
        self.interval = None
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(self.cron, before)
        self.assertIn("no confirmed periodic interval", json.loads(err)["error"])

    def test_crontab_permission_error_preserves_entries(self):
        before = list(self.cron)
        self.crontab_read_error = "permission denied"
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(self.cron, before)
        self.assertIn("cannot read crontab", json.loads(err)["error"])

    def test_crontab_write_failure_is_reported(self):
        before = list(self.cron)
        self.crontab_write_error = "write refused"
        rc, _out, err = self.invoke()
        self.assertEqual(rc, 1)
        self.assertEqual(self.cron, before)
        self.assertIn("cannot write crontab", json.loads(err)["error"])

    def test_malformed_managed_cron_line_is_rejected(self):
        with self.assertRaises(installer.ScheduleError):
            installer.validate_cron_line("* * * * /bad # " + installer.marker(self.task))


if __name__ == "__main__":
    unittest.main()
