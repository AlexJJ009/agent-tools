import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TEST_DIR.parent
SCHEDULER = SKILL_ROOT / "scripts" / "report_scheduler.py"
spec = importlib.util.spec_from_file_location("report_scheduler", SCHEDULER)
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


class ReportSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.task = self.root / "task"
        self.task.mkdir()
        self.runtime = self.root / "report_runtime.py"
        self.codex = self.root / "codex"
        self.codex_calls = self.root / "codex.calls"
        self.write_runtime()
        self.write_codex(0)
        self.manifest = {
            "schema_version": "work-report.runtime/2",
            "task_dir": str(self.task),
            "workspace": str(self.root),
            "request": str(self.root / "request.md"),
            "request_sha256": "abc",
            "interval_seconds": 60,
            "cancelled_at": None,
            "periodic": {"id": "p1", "kind": "progress", "cutoff": "2026-09-06T00:00:00Z", "attempts": 0, "state": "pending", "lease": None, "failures": []},
            "final": None,
        }
        (self.root / "request.md").write_text("request", encoding="utf-8")
        self.save_manifest()
        (self.task / "scheduler.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.scheduler/1",
                    "task_dir": str(self.task),
                    "task_dir_sha256": scheduler.task_hash(self.task),
                    "codex_bin": str(self.codex),
                    "codex_home": str(self.root / ".codex"),
                    "path": os.environ.get("PATH", ""),
                    "scheduler": str(SCHEDULER),
                    "runtime": str(self.runtime),
                    "uid": 1000,
                }
            ),
            encoding="utf-8",
        )

    def save_manifest(self):
        (self.task / "reporting.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def write_runtime(self):
        self.runtime.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json, sys
                from pathlib import Path
                args = sys.argv[1:]
                task = Path(args[args.index("--task-dir") + 1])
                path = task / "reporting.json"
                data = json.loads(path.read_text())
                def save():
                    path.write_text(json.dumps(data))
                if args[0] == "status":
                    print(json.dumps({"status":"pass","manifest":data}))
                elif args[0] == "tick":
                    if data.get("cancelled_at"):
                        print(json.dumps({"action":"complete"}))
                    elif data["periodic"].get("state") == "failed":
                        print(json.dumps({"action":"failed","obligation":data["periodic"]}))
                        sys.exit(1)
                    elif data["periodic"].get("lease"):
                        print(json.dumps({"action":"pending","obligation":data["periodic"]}))
                    else:
                        print(json.dumps({"action":"report_due","obligation":data["periodic"]}))
                elif args[0] == "claim":
                    owner = args[args.index("--owner") + 1]
                    if data["periodic"].get("lease"):
                        print(json.dumps({"status":"pending","lease":data["periodic"]["lease"]}))
                    else:
                        data["periodic"]["lease"] = {"owner": owner}
                        save()
                        print(json.dumps({"status":"claimed","obligation":data["periodic"]}))
                elif args[0] == "release":
                    success = "--success" in args
                    if success and (task / "delivery.ok").exists():
                        data["periodic"]["state"] = "satisfied"
                        data["periodic"]["last_ack"] = {"delivery":"ok"}
                        data["periodic"]["lease"] = None
                        save()
                        print(json.dumps({"status":"released","result":"success"}))
                    else:
                        data["periodic"]["attempts"] = int(data["periodic"].get("attempts",0)) + 1
                        data["periodic"]["lease"] = None
                        if data["periodic"]["attempts"] >= 2:
                            data["periodic"]["state"] = "failed"
                        save()
                        print(json.dumps({"status":"released","result":"error"}))
                """
            ),
            encoding="utf-8",
        )
        self.runtime.chmod(0o755)

    def write_codex(self, rc, create_delivery=False):
        marker = "Path.cwd().joinpath('delivery.ok').write_text('ok')" if create_delivery else ""
        self.codex.write_text(
            textwrap.dedent(
                f"""\
                #!/usr/bin/env python3
                import sys
                from pathlib import Path
                Path({str(self.codex_calls)!r}).write_text('called\\n', encoding='utf-8')
                {marker}
                sys.exit({rc})
                """
            ),
            encoding="utf-8",
        )
        self.codex.chmod(0o755)

    def write_codex_body(self, body):
        self.codex.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        self.codex.chmod(0o755)

    def run_scheduler(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = scheduler.main(["--task-dir", str(self.task), "--timeout", "5"])
            return rc, json.loads(out.getvalue())

    def process_exists(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def wait_until_gone(self, pid, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if not self.process_exists(pid):
                return True
            time.sleep(0.05)
        return not self.process_exists(pid)

    def test_codex_success_without_delivery_fails(self):
        rc, data = self.run_scheduler()
        self.assertEqual(rc, 1)
        self.assertEqual(data["action"], "failed")
        self.assertTrue(Path(data["snapshot"]).is_file())
        self.assertTrue(self.codex_calls.is_file())

    def test_failed_dispatch_writes_snapshot_and_runtime_caps_retries(self):
        self.write_codex(2)
        first, _ = self.run_scheduler()
        second, data = self.run_scheduler()
        third, final = self.run_scheduler()
        self.assertEqual((first, second, third), (1, 1, 1))
        self.assertEqual(data["action"], "failed")
        self.assertEqual(final["runtime"]["action"], "failed")
        manifest = json.loads((self.task / "reporting.json").read_text())
        self.assertEqual(manifest["periodic"]["state"], "failed")
        self.assertEqual(manifest["periodic"]["attempts"], 2)

    def test_existing_lease_prevents_second_launch(self):
        self.manifest["periodic"]["lease"] = {"owner": "other"}
        self.save_manifest()
        rc, data = self.run_scheduler()
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "pending")
        self.assertFalse(self.codex_calls.exists())

    def test_valid_delivery_releases_success(self):
        self.write_codex(0, create_delivery=True)
        rc, data = self.run_scheduler()
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "delivered")
        manifest = json.loads((self.task / "reporting.json").read_text())
        self.assertEqual(manifest["periodic"]["state"], "satisfied")

    def test_optional_tick_positional_is_supported(self):
        rc, data = self.run_scheduler()
        self.assertEqual(rc, 1)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc2 = scheduler.main(["tick", "--task-dir", str(self.task), "--timeout", "5"])
        self.assertEqual(rc2, 1)
        self.assertEqual(json.loads(out.getvalue())["action"], data["action"])

    def test_symlink_task_dir_is_rejected_before_resolve(self):
        link = self.root / "task-link"
        link.symlink_to(self.task, target_is_directory=True)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = scheduler.main(["--task-dir", str(link), "--timeout", "5"])
        self.assertEqual(rc, 1)
        self.assertIn("symlinks", json.loads(out.getvalue())["reason"])

    def test_cancelled_runner_releases_error_and_kills_descendant(self):
        child_pid = self.root / "child.pid"
        self.write_codex_body(
            textwrap.dedent(
                f"""\
                import json, subprocess, time
                from pathlib import Path
                task = Path({str(self.task)!r})
                child = subprocess.Popen(['sleep', '30'])
                Path({str(child_pid)!r}).write_text(str(child.pid), encoding='utf-8')
                data = json.loads((task / 'reporting.json').read_text())
                data['cancelled_at'] = '2026-09-06T00:00:01Z'
                (task / 'reporting.json').write_text(json.dumps(data))
                child.wait()
                """
            )
        )
        rc, data = self.run_scheduler()
        self.assertEqual(rc, 1)
        self.assertEqual(data["reason"], "scheduler_cancelled")
        pid = int(child_pid.read_text())
        self.assertTrue(self.wait_until_gone(pid))
        manifest = json.loads((self.task / "reporting.json").read_text())
        self.assertEqual(manifest["periodic"]["attempts"], 1)
        self.assertIsNone(manifest["periodic"]["lease"])

    def test_timeout_kills_descendant(self):
        child_pid = self.root / "timeout-child.pid"
        self.write_codex_body(
            textwrap.dedent(
                f"""\
                import subprocess
                from pathlib import Path
                child = subprocess.Popen(['sleep', '30'])
                Path({str(child_pid)!r}).write_text(str(child.pid), encoding='utf-8')
                child.wait()
                """
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = scheduler.main(["--task-dir", str(self.task), "--timeout", "1"])
        data = json.loads(out.getvalue())
        self.assertEqual(rc, 1)
        self.assertEqual(data["reason"], "codex_timeout")
        pid = int(child_pid.read_text())
        self.assertTrue(self.wait_until_gone(pid))

    def test_timeout_bounds_are_enforced(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = scheduler.main(["--task-dir", str(self.task), "--timeout", "0"])
        self.assertEqual(rc, 1)
        self.assertIn("timeout must be between", json.loads(out.getvalue())["reason"])


if __name__ == "__main__":
    unittest.main()
