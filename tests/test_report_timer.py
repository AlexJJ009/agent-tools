import contextlib
import datetime as dt
import fcntl
import importlib.util
import io
import json
import subprocess
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TIMER_PATH = ROOT / "skills" / "work-report" / "scripts" / "report_timer.py"
spec = importlib.util.spec_from_file_location("report_timer", TIMER_PATH)
timer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timer)


THREAD = "12345678-1234-1234-1234-123456789abc"


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ReportTimerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.state_dir = self.root / "state"
        self.state_dir.mkdir()
        self.codex = self.root / "codex"
        self.codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.codex.chmod(0o755)

    def parse_one(self, output):
        return json.loads(output.getvalue())

    def run_timer(self, argv, clock=None, queue_runner=None):
        args = timer.build_parser().parse_args(argv)
        clock = clock or FakeClock()
        queue_runner = queue_runner or (
            lambda cmd, cwd, timeout: subprocess.CompletedProcess(
                cmd,
                0,
                f"Queued message 01a07bd4-a82e-7b72-b438-354f29644a19 for thread {THREAD}.\n",
                "",
            )
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = timer.run_command(args, clock=clock.time, sleeper=clock.sleep, queue_runner=queue_runner)
        return rc, self.parse_one(out), clock

    def test_after_waits_until_due_and_queues_thread_message(self):
        calls = []

        def runner(cmd, cwd, timeout):
            calls.append((cmd, cwd, timeout))
            return subprocess.CompletedProcess(cmd, 0, '{"queue_id":"qid-1"}', "")

        rc, data, clock = self.run_timer(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--after",
                "2.5",
                "--codex",
                str(self.codex),
            ],
            queue_runner=runner,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "queued")
        self.assertEqual(data["queue"]["queue_id"], "qid-1")
        self.assertEqual(clock.sleeps, [1.0, 1.0, 0.5])
        self.assertEqual(calls[0][0][:4], [str(self.codex), "queue", "--thread", THREAD])
        self.assertIn("临时 work-report", calls[0][0][-1])

    def test_at_requires_timezone_and_schedules_absolute_due(self):
        naive = timer.build_parser().parse_args(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--at",
                "2026-09-07T09:00:00",
                "--codex",
                str(self.codex),
            ]
        )
        with self.assertRaises(timer.TimerError):
            timer.validate_run_args(naive, lambda: 0.0)

        aware_time = dt.datetime.fromtimestamp(1003.0, tz=dt.timezone.utc).isoformat()
        rc, data, clock = self.run_timer(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--at",
                aware_time,
                "--codex",
                str(self.codex),
            ],
            clock=FakeClock(1000.0),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "queued")
        self.assertEqual(clock.sleeps, [1.0, 1.0, 1.0])

    def test_stop_marker_exits_before_queue(self):
        clock = FakeClock()
        calls = []

        def sleeper(seconds):
            clock.sleeps.append(seconds)
            timer.atomic_write_json(self.state_dir / "timer_stop.json", {"schema_version": timer.SCHEMA})
            clock.now += seconds

        args = timer.build_parser().parse_args(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--after",
                "10",
                "--codex",
                str(self.codex),
            ]
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = timer.run_command(
                args,
                clock=clock.time,
                sleeper=sleeper,
                queue_runner=lambda cmd, cwd, timeout: calls.append(cmd),
            )
        data = self.parse_one(out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "stopped")
        self.assertEqual(calls, [])

    def test_existing_stop_marker_is_respected(self):
        timer.atomic_write_json(self.state_dir / "timer_stop.json", {"schema_version": timer.SCHEMA})
        calls = []
        rc, data, _ = self.run_timer(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--after",
                "1",
                "--codex",
                str(self.codex),
            ],
            queue_runner=lambda cmd, cwd, timeout: calls.append(cmd),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "stopped")
        self.assertEqual(calls, [])
        self.assertTrue((self.state_dir / "timer_stop.json").exists())

    def test_duplicate_lock_prevents_second_timer(self):
        lock_path = self.state_dir / "timer.lock"
        with lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = timer.main(
                    [
                        "run",
                        "--workspace",
                        str(self.workspace),
                        "--state-dir",
                        str(self.state_dir),
                        "--thread",
                        THREAD,
                        "--after",
                        "1",
                        "--codex",
                        str(self.codex),
                    ]
                )
        data = self.parse_one(out)
        self.assertEqual(rc, 2)
        self.assertEqual(data["code"], "already_running")

    def test_queue_failure_is_recorded_without_retrying_same_due_time(self):
        calls = []

        def runner(cmd, cwd, timeout):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 7, "prompt should not be logged", "bad")

        rc, data, _ = self.run_timer(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--after",
                "1",
                "--codex",
                str(self.codex),
            ],
            queue_runner=runner,
        )
        self.assertEqual(rc, 1)
        self.assertEqual(data["action"], "failed")
        self.assertEqual(data["queue"]["status"], "uncertain_failure")
        self.assertEqual(len(calls), 1)
        events = (self.state_dir / "timer_events.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("prompt should not be logged", events)

    def test_real_codex_queue_text_output_is_parsed_and_thread_checked(self):
        output = f"Queued message 01a07bd4-a82e-7b72-b438-354f29644a19 for thread {THREAD}.\n"
        self.assertEqual(timer.parse_queue_id(output, THREAD), "01a07bd4-a82e-7b72-b438-354f29644a19")
        self.assertIsNone(timer.parse_queue_id(output, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"))

    def test_queue_success_without_id_is_uncertain_not_confirmed_sent(self):
        rc, data, _ = self.run_timer(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--after",
                "1",
                "--codex",
                str(self.codex),
            ],
            queue_runner=lambda cmd, cwd, timeout: subprocess.CompletedProcess(cmd, 0, "ok\n", ""),
        )
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "uncertain")
        self.assertEqual(data["state"]["status"], "uncertain")

    def test_invalid_run_args_fail_before_state_dir_mutation(self):
        args = timer.build_parser().parse_args(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                "not-a-uuid",
                "--after",
                "1",
                "--codex",
                str(self.codex),
            ]
        )
        with self.assertRaises(timer.TimerError):
            timer.run_command(args, clock=FakeClock().time, sleeper=FakeClock().sleep)
        self.assertEqual(list(self.state_dir.iterdir()), [])

    def test_nan_and_inf_schedules_fail_before_state_dir_mutation(self):
        for flag, value in [("--after", "nan"), ("--every", "inf")]:
            with self.subTest(flag=flag):
                args = timer.build_parser().parse_args(
                    [
                        "run",
                        "--workspace",
                        str(self.workspace),
                        "--state-dir",
                        str(self.state_dir),
                        "--thread",
                        THREAD,
                        flag,
                        value,
                        "--codex",
                        str(self.codex),
                    ]
                )
                with self.assertRaises(timer.TimerError):
                    timer.run_command(args, clock=FakeClock().time, sleeper=FakeClock().sleep)
                self.assertEqual(list(self.state_dir.iterdir()), [])

    def test_every_coalesces_missed_intervals_instead_of_bursting(self):
        calls = []

        def runner(cmd, cwd, timeout):
            calls.append(cmd)
            clock.now += 5.0
            if len(calls) == 1:
                return subprocess.CompletedProcess(cmd, 0, '{"queue_id":"qid-1"}', "")
            timer.atomic_write_json(self.state_dir / "timer_stop.json", {"schema_version": timer.SCHEMA})
            return subprocess.CompletedProcess(cmd, 0, '{"queue_id":"qid-2"}', "")

        clock = FakeClock(1000.0)
        args = timer.build_parser().parse_args(
            [
                "run",
                "--workspace",
                str(self.workspace),
                "--state-dir",
                str(self.state_dir),
                "--thread",
                THREAD,
                "--every",
                "2",
                "--codex",
                str(self.codex),
            ]
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = timer.run_command(args, clock=clock.time, sleeper=clock.sleep, queue_runner=runner)
        data = self.parse_one(out)
        self.assertEqual(rc, 0)
        self.assertEqual(data["action"], "stopped")
        self.assertEqual(len(calls), 2)
        due_events = [
            json.loads(line)["due_at"]
            for line in (self.state_dir / "timer_events.jsonl").read_text(encoding="utf-8").splitlines()
            if json.loads(line)["event"] == "queue_result"
        ]
        self.assertEqual(due_events, ["1970-01-01T00:16:42Z", "1970-01-01T00:16:48Z"])

    def test_status_and_stop_use_existing_state_dir(self):
        with contextlib.redirect_stdout(io.StringIO()) as stop_out:
            stop_rc = timer.main(["stop", "--state-dir", str(self.state_dir)])
        self.assertEqual(stop_rc, 0)
        self.assertEqual(self.parse_one(stop_out)["action"], "stop_requested")

        with contextlib.redirect_stdout(io.StringIO()) as status_out:
            status_rc = timer.main(["status", "--state-dir", str(self.state_dir)])
        status = self.parse_one(status_out)
        self.assertEqual(status_rc, 0)
        self.assertTrue(status["stop_requested"])


if __name__ == "__main__":
    unittest.main()
