import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import datetime as dt
import importlib.util
from pathlib import Path
from types import SimpleNamespace


TEST_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TEST_DIR.parent
REPO_ROOT = SKILL_ROOT.parent.parent
RUNTIME = SKILL_ROOT / "scripts" / "report_runtime.py"


def claim_worker(runtime, task_dir, owner, env, queue):
    proc = subprocess.run(
        [sys.executable, str(runtime), "claim", "--task-dir", str(task_dir), "--owner", owner, "--kind", "progress"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    queue.put((proc.returncode, proc.stdout, proc.stderr))


class ReportRuntimeTests(unittest.TestCase):
    maxDiff = 4000

    def git_env(self, extra=None):
        env = {
            **os.environ,
            "GIT_CEILING_DIRECTORIES": str(Path(tempfile.gettempdir()).resolve()),
            "WORK_REPORT_UV": str(self.fake_uv),
        }
        if extra:
            env.update(extra)
        return env

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo_counter = 0
        self.session_id = "11111111-2222-4333-8444-555555555555"
        self.fake_uv = self.root / "uv"
        self.fake_uv.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import sys
                from pathlib import Path

                args = sys.argv[1:]
                if args[:2] != ["run", "--script"]:
                    sys.exit(3)
                tool = args[2]
                rest = args[3:]
                if "--verify-only" not in rest:
                    sys.exit(4)
                report = Path(rest[rest.index("--report") + 1])
                delivery = json.loads((report.parent / "delivery.json").read_text())
                import hashlib
                actual = hashlib.sha256(report.read_bytes()).hexdigest()
                expected = delivery.get("expected_report_sha")
                if expected:
                    ok = actual == expected
                else:
                    ok = True
                invalidate_if_exists = delivery.get("invalidate_if_exists")
                if invalidate_if_exists and Path(invalidate_if_exists).exists():
                    ok = False
                status = "pass" if delivery.get("verify_ok", True) and ok else "fail"
                artifact_digest = actual
                task = rest[rest.index("--task") + 1]
                print(json.dumps({
                    "status": status,
                    "artifact_digest": artifact_digest,
                    "task_id": task,
                    "report_id": report.parent.name,
                }))
                sys.exit(0 if status == "pass" else 1)
                """
            ),
            encoding="utf-8",
        )
        self.fake_uv.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, input=None, cwd=None, env=None):
        return subprocess.run(
            [sys.executable, str(RUNTIME), *map(str, args)],
            input=input,
            cwd=str(cwd or REPO_ROOT),
            env=self.git_env(env),
            text=True,
            capture_output=True,
            check=False,
        )

    def data(self, proc):
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"bad JSON rc={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}\n{exc}")

    def git(self, repo, *args):
        proc = subprocess.run(["git", *args], cwd=str(repo), env=self.git_env(), text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def make_repo_task(self, *, ignored=True, request_text="Please send an end report and periodic report."):
        self.repo_counter += 1
        repo = self.root / f"repo-{self.repo_counter}"
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "runtime@example.invalid")
        self.git(repo, "config", "user.name", "Runtime Tests")
        (repo / "README.md").write_text("repo\n", encoding="utf-8")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-m", "initial")
        if ignored:
            exclude = repo / ".git" / "info" / "exclude"
            exclude.write_text(exclude.read_text(encoding="utf-8") + "\n/docs/work-reports/\n", encoding="utf-8")
        request = repo / "request.md"
        request.write_text(request_text, encoding="utf-8")
        task_dir = repo / "docs" / "work-reports" / "20260906T000000Z-runtime-12345678"
        report_dir = task_dir / "20260906T000001Z-progress-abcdef"
        report_dir.mkdir(parents=True)
        context = {
            "schema_version": "work-report.context/1",
            "task_id": task_dir.name,
            "report_id": report_dir.name,
            "kind": "progress",
            "workspace": str(repo.resolve()),
            "output_root": str((repo / "docs" / "work-reports").resolve()),
            "generated_at": "2026-09-06T00:00:01Z",
            "window_start": "2026-09-06T00:00:01Z",
            "window_end": "2026-09-06T00:00:01Z",
            "request": {
                "path": str(request.resolve()),
                "sha256": self.sha(request_text),
                "text": request_text,
            },
            "state": {"path": str((task_dir / "working-state.md").resolve()), "sha256": self.sha("state"), "text": "state"},
            "git": {"head": "", "status": ""},
            "initial_work_inventory": {"status": "unavailable"},
        }
        (report_dir / "context.json").write_text(json.dumps(context), encoding="utf-8")
        return repo.resolve(), task_dir.resolve(), request.resolve()

    def make_additional_task(self, repo, request, request_text, *, task_id, report_id):
        task_dir = repo / "docs" / "work-reports" / task_id
        report_dir = task_dir / report_id
        report_dir.mkdir(parents=True)
        context = {
            "schema_version": "work-report.context/1",
            "task_id": task_dir.name,
            "report_id": report_dir.name,
            "kind": "progress",
            "workspace": str(repo.resolve()),
            "output_root": str((repo / "docs" / "work-reports").resolve()),
            "generated_at": "2026-09-06T00:00:01Z",
            "window_start": "2026-09-06T00:00:01Z",
            "window_end": "2026-09-06T00:00:01Z",
            "request": {
                "path": str(request.resolve()),
                "sha256": self.sha(request_text),
                "text": request_text,
            },
            "state": {"path": str((task_dir / "working-state.md").resolve()), "sha256": self.sha("state"), "text": "state"},
            "git": {"head": "", "status": ""},
            "initial_work_inventory": {"status": "unavailable"},
        }
        (report_dir / "context.json").write_text(json.dumps(context), encoding="utf-8")
        return task_dir.resolve()

    def sha(self, text):
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def file_sha(self, path):
        import hashlib

        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def load_runtime_module(self):
        name = f"report_runtime_under_test_{self.repo_counter}"
        spec = importlib.util.spec_from_file_location(name, RUNTIME)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)
        return module

    def write_delivery(
        self,
        task_dir,
        request_text,
        *,
        kind="progress",
        report_id="20260906T000008Z-progress-acdc01",
        report_text="fresh progress report",
        generated_at="2099-01-01T00:00:00Z",
        delivered_at="2099-01-01T00:00:01Z",
        extra_delivery=None,
    ):
        report_dir = task_dir / report_id
        report_dir.mkdir()
        report = report_dir / "report.md"
        report.write_text(report_text, encoding="utf-8")
        (report_dir / "context.json").write_text(
            json.dumps({"schema_version": "work-report.context/1", "generated_at": generated_at}),
            encoding="utf-8",
        )
        delivery = {
            "schema_version": "work-report.delivery/1",
            "status": "pass",
            "task_id": task_dir.name,
            "report_id": report_dir.name,
            "report": str(report.resolve()),
            "artifact_digest": self.file_sha(report),
            "delivered_at": delivered_at,
            "kind": kind,
            "request_sha256": self.sha(request_text),
        }
        if extra_delivery:
            delivery.update(extra_delivery)
        (report_dir / "delivery.json").write_text(
            json.dumps(delivery),
            encoding="utf-8",
        )
        return report_dir

    def decision(self, path, request_text, **overrides):
        data = {
            "schema_version": "work-report.intent/1",
            "request_sha256": self.sha(request_text),
            "reviewer_id": "judge",
            "verdict": "confirmed",
            "on_end": True,
            "interval_seconds": None,
            "evidence_quotes": ["end report"],
            "reason": "explicit report request",
        }
        data.update(overrides)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def register(self, repo, task_dir, request, decision):
        return self.run_cli(
            "register",
            "--task-dir",
            task_dir,
            "--request",
            request,
            "--decision",
            decision,
            "--session-id",
            self.session_id,
            "--workspace",
            repo,
        )

    def test_register_ignores_none_and_rejects_missing_git_ignore(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(ignored=True, request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        decision = self.decision(self.root / "decision.json", text, verdict="none")
        proc = self.register(repo, task_dir, request, decision)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(self.data(proc)["status"], "ignored")
        self.assertFalse((task_dir / "reporting.json").exists())

        repo2, task_dir2, request2 = self.make_repo_task(ignored=False, request_text=text)
        proc2 = self.register(repo2, task_dir2, request2, self.decision(self.root / "decision2.json", text))
        self.assertNotEqual(proc2.returncode, 0)
        self.assertEqual(self.data(proc2)["issues"][0]["code"], "git_ignore_missing")

    def test_register_rejects_intent_digest_quote_and_trigger_mismatches(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        bad = self.decision(self.root / "bad.json", text, request_sha256="0" * 64)
        self.assertEqual(self.data(self.register(repo, task_dir, request, bad))["issues"][0]["code"], "decision_digest_mismatch")
        bad = self.decision(self.root / "bad2.json", text, evidence_quotes=["not present"])
        self.assertEqual(self.data(self.register(repo, task_dir, request, bad))["issues"][0]["code"], "decision_quote_missing")
        bad = self.decision(self.root / "bad3.json", text, on_end=False, interval_seconds=None)
        self.assertEqual(self.data(self.register(repo, task_dir, request, bad))["issues"][0]["code"], "decision_trigger_missing")

    def test_register_accepts_standalone_interim_resume_intent(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        result = self.data(self.register(repo, task_dir, request, decision))
        self.assertEqual(result["status"], "registered")
        self.assertIn("new progress report batch", result["next_step"])
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertTrue(manifest["resume_after_report"])
        self.assertIsNone(manifest["final"])
        self.assertIsNone(manifest["periodic"])
        self.assertIsNotNone(manifest["interim"])
        self.assertEqual(manifest["interim"]["kind"], "progress")

    def test_resume_after_report_must_be_boolean(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report="yes",
            evidence_quotes=["interim report", "continue"],
        )
        self.assertEqual(
            self.data(self.register(repo, task_dir, request, decision))["issues"][0]["code"],
            "decision_resume_after_report_invalid",
        )

    def test_register_rejects_placeholder_session_id(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        proc = self.run_cli(
            "register",
            "--task-dir",
            task_dir,
            "--request",
            request,
            "--decision",
            self.decision(self.root / "decision.json", text),
            "--session-id",
            "current-codex-session",
            "--workspace",
            repo,
        )
        self.assertEqual(self.data(proc)["issues"][0]["code"], "session_id_invalid")

    def test_register_rejects_matching_pending_from_other_session(self):
        text = "Please send an end report after completion."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        other_session = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": other_session,
                "prompt": text,
            }
        )
        self.run_cli("hook", input=event, cwd=repo)
        proc = self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text))
        self.assertEqual(self.data(proc)["issues"][0]["code"], "pending_session_mismatch")

    def test_register_confirmed_preserves_crlf_request_hash_for_context_match(self):
        text = "Please send an end report.\r\nKeep the original task evidence."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        proc = self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        result = self.data(proc)
        self.assertEqual(result["status"], "registered")
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["request_sha256"], self.sha(text))

    def test_stop_blocks_until_fresh_verified_final_delivery(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.assertEqual(self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text)).returncode, 0)
        event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id, "stop_hook_active": True})
        first = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertEqual(first["decision"], "block")
        self.assertEqual(json.loads((task_dir / "reporting.json").read_text())["final"]["attempts"], 1)

        old_dir = task_dir / "20260906T000002Z-final-badbad"
        old_dir.mkdir()
        (old_dir / "context.json").write_text(
            json.dumps({"schema_version": "work-report.context/1", "generated_at": "2020-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        (old_dir / "report.md").write_text("old", encoding="utf-8")
        (old_dir / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.delivery/1",
                    "status": "pass",
                    "task_id": task_dir.name,
                    "report_id": old_dir.name,
                    "report": str((old_dir / "report.md").resolve()),
                    "artifact_digest": self.file_sha(old_dir / "report.md"),
                    "delivered_at": "2026-09-06T00:10:00Z",
                    "kind": "final",
                    "request_sha256": self.sha(text),
                }
            ),
            encoding="utf-8",
        )
        second = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertEqual(second["decision"], "block")

        fresh_dir = task_dir / "20260906T000003Z-final-cafeba"
        fresh_dir.mkdir()
        (fresh_dir / "context.json").write_text(
            json.dumps({"schema_version": "work-report.context/1", "generated_at": "2099-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        (fresh_dir / "report.md").write_text("fresh", encoding="utf-8")
        (fresh_dir / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.delivery/1",
                    "status": "pass",
                    "task_id": task_dir.name,
                    "report_id": fresh_dir.name,
                    "report": str((fresh_dir / "report.md").resolve()),
                    "artifact_digest": self.file_sha(fresh_dir / "report.md"),
                    "delivered_at": "2099-01-01T00:00:01Z",
                    "kind": "final",
                    "request_sha256": self.sha(text),
                }
            ),
            encoding="utf-8",
        )
        final = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertEqual(final, {})

    def test_status_cache_does_not_close_and_stop_revalidates_before_closing(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text))
        report_dir = task_dir / "20260906T000004Z-final-feed01"
        report_dir.mkdir()
        report = report_dir / "report.md"
        report.write_text("fresh", encoding="utf-8")
        (report_dir / "context.json").write_text(
            json.dumps({"schema_version": "work-report.context/1", "generated_at": "2099-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        (report_dir / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.delivery/1",
                    "status": "pass",
                    "task_id": task_dir.name,
                    "report_id": report_dir.name,
                    "report": str(report.resolve()),
                    "artifact_digest": self.file_sha(report),
                    "delivered_at": "2099-01-01T00:00:01Z",
                    "kind": "final",
                    "request_sha256": self.sha(text),
                    "expected_report_sha": self.file_sha(report),
                }
            ),
            encoding="utf-8",
        )
        event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        status = self.data(self.run_cli("status", "--task-dir", task_dir))
        self.assertEqual(status["manifest"]["final"]["state"], "pending")
        report.write_text("changed after delivery", encoding="utf-8")
        blocked = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertEqual(blocked["decision"], "block")
        (report_dir / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.delivery/1",
                    "status": "pass",
                    "task_id": task_dir.name,
                    "report_id": report_dir.name,
                    "report": str(report.resolve()),
                    "artifact_digest": self.file_sha(report),
                    "delivered_at": "2099-01-01T00:00:02Z",
                    "kind": "final",
                    "request_sha256": self.sha(text),
                    "expected_report_sha": self.file_sha(report),
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(self.data(self.run_cli("hook", input=event, cwd=repo)), {})
        closed = json.loads((task_dir / "reporting.json").read_text())
        self.assertIsNotNone(closed["closed_at"])
        report.write_text("later Q&A should not reopen old end report", encoding="utf-8")
        self.assertEqual(self.data(self.run_cli("hook", input=event, cwd=repo)), {})
        self.assertEqual(self.data(self.run_cli("tick", "--task-dir", task_dir))["action"], "complete")

    def test_old_delivery_digest_rejected_even_when_current_finalizer_passes(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text))
        report_dir = task_dir / "20260906T000006Z-final-feed02"
        report_dir.mkdir()
        report = report_dir / "report.md"
        report.write_text("old digest material", encoding="utf-8")
        old_digest = self.file_sha(report)
        report.write_text("new valid report material", encoding="utf-8")
        (report_dir / "context.json").write_text(
            json.dumps({"schema_version": "work-report.context/1", "generated_at": "2099-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        (report_dir / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.delivery/1",
                    "status": "pass",
                    "task_id": task_dir.name,
                    "report_id": report_dir.name,
                    "report": str(report.resolve()),
                    "artifact_digest": old_digest,
                    "delivered_at": "2099-01-01T00:00:01Z",
                    "kind": "final",
                    "request_sha256": self.sha(text),
                }
            ),
            encoding="utf-8",
        )
        event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        blocked = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertEqual(blocked["decision"], "block")

    def test_stop_records_visible_failure_after_two_continuations(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.assertEqual(self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text)).returncode, 0)
        event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        self.run_cli("hook", input=event, cwd=repo)
        self.run_cli("hook", input=event, cwd=repo)
        third = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertIn("systemMessage", third)
        self.assertEqual(self.data(self.run_cli("hook", input=event, cwd=repo)), {})
        self.assertTrue((task_dir / "reporting.failure.json").exists())

    def test_interrupt_cancels_obligation(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text))
        event = json.dumps({"hook_event_name": "Interrupt", "cwd": str(repo), "session_id": self.session_id})
        self.assertEqual(self.run_cli("hook", input=event, cwd=repo).returncode, 0)
        stop = self.data(self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo))
        self.assertEqual(stop, {})

    def test_interim_resume_blocks_until_report_then_nudges_once(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        missing = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(missing["decision"], "block")
        self.assertIn("progress", missing["reason"])

        self.write_delivery(
            task_dir,
            text,
            report_id="20260906T000009Z-progress-acdc02",
            generated_at="2020-01-01T00:00:00Z",
            delivered_at="2020-01-01T00:00:01Z",
        )
        stale = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(stale["decision"], "block")
        self.assertIn("work-report obligation is due", stale["reason"])

        self.write_delivery(task_dir, text, report_id="20260906T000010Z-progress-acdc03")
        nudge = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(nudge["decision"], "block")
        self.assertIn("Continue the original task", nudge["reason"])
        self.assertIn("one-shot", nudge["reason"])
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertIsNotNone(manifest["closed_at"])
        self.assertIsNone(manifest["final"])
        self.assertEqual(manifest["interim"]["state"], "complete")
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "issued")

        report = Path(manifest["interim"]["last_ack"]["report"])
        report.write_text("edited after consumed interim receipt", encoding="utf-8")
        status = self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]
        self.assertEqual(status["interim"]["state"], "complete")
        self.assertEqual(self.data(self.run_cli("hook", input=stop_event, cwd=repo)), {})

    def test_interim_resume_does_not_nudge_after_non_report_post_tool_use(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["interim"]["cutoff"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.write_delivery(
            task_dir,
            text,
            report_id="20260906T000011Z-progress-acdc04",
            generated_at="2000-01-01T00:00:01Z",
            delivered_at="2000-01-01T00:00:02Z",
        )
        self.assertIsNotNone(self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]["interim"]["last_ack"])
        post_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "touch actual-task-file"},
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=post_tool, cwd=repo)), {})
        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop, {})
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "observed")
        self.assertEqual(manifest["interim"]["state"], "complete")
        self.assertIsNotNone(manifest["closed_at"])

    def test_cached_interim_ack_consumes_before_non_report_change_revalidation(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        cited_file = repo / "calculator.py"
        self.write_delivery(
            task_dir,
            text,
            report_id="20260906T000015Z-progress-acdc10",
            extra_delivery={"invalidate_if_exists": str(cited_file)},
        )
        status = self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]
        self.assertIsNotNone(status["interim"]["last_ack"])
        self.assertEqual(status["interim"]["state"], "pending")

        cited_file.write_text("changed by resumed task action\n", encoding="utf-8")
        post_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "edit calculator.py"},
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=post_tool, cwd=repo)), {})
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "observed")
        self.assertEqual(manifest["interim"]["state"], "complete")

        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop, {})
        status_after_change = self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]
        self.assertEqual(status_after_change["interim"]["state"], "complete")

    def test_cached_interim_ack_is_not_consumed_after_report_tampering(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        report_dir = self.write_delivery(task_dir, text, report_id="20260906T000017Z-progress-acdc12")
        delivery_path = report_dir / "delivery.json"
        delivery = json.loads(delivery_path.read_text())
        delivery["expected_report_sha"] = delivery["artifact_digest"]
        delivery_path.write_text(json.dumps(delivery), encoding="utf-8")
        self.assertIsNotNone(self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]["interim"]["last_ack"])

        (report_dir / "report.md").write_text("tampered report", encoding="utf-8")
        post_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "edit calculator.py"},
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=post_tool, cwd=repo)), {})
        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop["decision"], "block")
        self.assertIn("work-report obligation is due", stop["reason"])
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "pending")
        self.assertIsNone(manifest["interim"]["last_ack"])

    def test_cached_interim_ack_is_not_consumed_after_delivery_tampering(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        report_dir = self.write_delivery(task_dir, text, report_id="20260906T000018Z-progress-acdc13")
        self.assertIsNotNone(self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]["interim"]["last_ack"])

        delivery_path = report_dir / "delivery.json"
        delivery = json.loads(delivery_path.read_text())
        delivery["artifact_digest"] = "0" * 64
        delivery_path.write_text(json.dumps(delivery), encoding="utf-8")
        post_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "edit calculator.py"},
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=post_tool, cwd=repo)), {})
        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop["decision"], "block")
        self.assertIn("work-report obligation is due", stop["reason"])
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "pending")
        self.assertIsNone(manifest["interim"]["last_ack"])

    def test_unverified_stale_interim_receipt_is_not_consumed_by_non_report_tool_use(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        self.write_delivery(
            task_dir,
            text,
            report_id="20260906T000016Z-progress-acdc11",
            generated_at="2020-01-01T00:00:00Z",
            delivered_at="2020-01-01T00:00:01Z",
        )
        post_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "edit calculator.py"},
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=post_tool, cwd=repo)), {})
        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop["decision"], "block")
        self.assertIn("work-report obligation is due", stop["reason"])
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "pending")
        self.assertIsNone(manifest["interim"]["last_ack"])

    def test_report_related_post_tool_use_does_not_satisfy_interim_resume(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["interim"]["cutoff"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.write_delivery(
            task_dir,
            text,
            report_id="20260906T000012Z-progress-acdc05",
            generated_at="2000-01-01T00:00:01Z",
            delivered_at="2000-01-01T00:00:02Z",
        )
        report_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "uv run --script skills/work-report/scripts/report_tool.py finalize"},
            }
        )
        notice = self.data(self.run_cli("hook", input=report_tool, cwd=repo))
        self.assertIn("hookSpecificOutput", notice)
        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop["decision"], "block")
        self.assertIn("Continue the original task", stop["reason"])

    def test_report_related_post_tool_use_emits_interim_delivery_notice_once(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        report_dir = self.write_delivery(task_dir, text, report_id="20260906T000019Z-progress-acdc14")
        report_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "uv run --script skills/work-report/scripts/report_tool.py finalize"},
            }
        )
        first = self.data(self.run_cli("hook", input=report_tool, cwd=repo))
        notice = first["hookSpecificOutput"]["additionalContext"]
        self.assertIn(str((report_dir / "report.md").resolve()), notice)
        self.assertIn("share this report.md link before any non-report business action", notice)
        self.assertIn("Do not defer the report path to the final reply", notice)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertIsNotNone(manifest["resume_after_report_gate"]["delivery_notice_at"])

        second = self.data(self.run_cli("hook", input=report_tool, cwd=repo))
        self.assertEqual(second, {})

    def test_report_related_post_tool_use_does_not_emit_notice_for_final_only(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.register(repo, task_dir, request, self.decision(self.root / "decision.json", text))
        self.write_delivery(
            task_dir,
            text,
            kind="final",
            report_id="20260906T000020Z-final-acdc15",
            report_text="fresh final report",
        )
        report_tool = json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "tool_name": "shell",
                "tool_input": {"cmd": "uv run --script skills/work-report/scripts/report_tool.py finalize"},
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=report_tool, cwd=repo)), {})

    def test_stop_prioritizes_newer_interim_manifest_over_older_final_manifest(self):
        final_text = "Please send an end report."
        repo, final_task_dir, final_request = self.make_repo_task(request_text=final_text)
        final_decision = self.decision(self.root / "final.json", final_text)
        self.assertEqual(self.data(self.register(repo, final_task_dir, final_request, final_decision))["status"], "registered")

        interim_text = "Please make an interim report, then continue the task."
        interim_request = repo / "interim-request.md"
        interim_request.write_text(interim_text, encoding="utf-8")
        interim_task_dir = self.make_additional_task(
            repo,
            interim_request,
            interim_text,
            task_id="20260906T000100Z-runtime-87654321",
            report_id="20260906T000101Z-progress-acdc08",
        )
        interim_decision = self.decision(
            self.root / "interim.json",
            interim_text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.assertEqual(self.data(self.register(repo, interim_task_dir, interim_request, interim_decision))["status"], "registered")

        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        first = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(first["decision"], "block")
        self.assertIn("progress", first["reason"])
        self.assertIn(str(interim_task_dir), first["reason"])
        self.assertNotIn(str(final_task_dir), first["reason"])
        self.assertEqual(json.loads((final_task_dir / "reporting.json").read_text())["final"]["attempts"], 0)

        self.write_delivery(
            interim_task_dir,
            interim_text,
            report_id="20260906T000102Z-progress-acdc09",
        )
        second = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(second["decision"], "block")
        self.assertIn("Continue the original task", second["reason"])
        self.assertIn(str(interim_task_dir), second["reason"])
        self.assertEqual(json.loads((final_task_dir / "reporting.json").read_text())["final"]["attempts"], 0)

        third = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(third["decision"], "block")
        self.assertIn("final", third["reason"])
        self.assertIn(str(final_task_dir), third["reason"])
        final_manifest = json.loads((final_task_dir / "reporting.json").read_text())
        interim_manifest = json.loads((interim_task_dir / "reporting.json").read_text())
        self.assertEqual(final_manifest["final"]["attempts"], 1)
        self.assertEqual(interim_manifest["interim"]["state"], "complete")

    def test_interrupt_cancels_interim_resume_obligation(self):
        text = "Please make an interim report, then continue the task."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        self.register(repo, task_dir, request, decision)
        self.write_delivery(task_dir, text, report_id="20260906T000013Z-progress-acdc06")
        interrupt = json.dumps({"hook_event_name": "Interrupt", "cwd": str(repo), "session_id": self.session_id})
        self.assertEqual(self.data(self.run_cli("hook", input=interrupt, cwd=repo)), {})
        stop = self.data(
            self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)
        )
        self.assertEqual(stop, {})
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["interim"]["state"], "cancelled")
        self.assertEqual(manifest["resume_after_report_gate"]["state"], "cancelled")

    def test_prompt_candidate_blocks_stop_until_judge_decision_clears_it(self):
        text = "After this work is complete, send a report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        prompt = self.data(self.run_cli("hook", input=prompt_event, cwd=repo))
        self.assertIn("hookSpecificOutput", prompt)
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        stop = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(stop["decision"], "block")
        decision = self.decision(self.root / "none.json", text, verdict="none", evidence_quotes=["send a report"])
        cleared = self.data(
            self.run_cli(
                "register",
                "--request",
                request,
                "--decision",
                decision,
                "--session-id",
                self.session_id,
                "--workspace",
                repo,
            )
        )
        self.assertEqual(cleared["status"], "ignored")
        resolution = json.loads(Path(cleared["resolution"]).read_text())
        self.assertEqual(resolution["decision"]["verdict"], "none")
        self.assertFalse(resolution["auto_enforced"])
        stop2 = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(stop2, {})

    def test_ordinary_stop_without_pending_does_not_create_pending_lock_artifacts(self):
        self.repo_counter += 1
        repo = self.root / f"clean-repo-{self.repo_counter}"
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "runtime@example.invalid")
        self.git(repo, "config", "user.name", "Runtime Tests")
        (repo / "README.md").write_text("repo\n", encoding="utf-8")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-m", "initial")
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        self.assertEqual(self.data(self.run_cli("hook", input=stop_event, cwd=repo)), {})
        self.assertFalse((repo / "docs").exists())

    def test_nonconfirmed_register_without_pending_has_no_lock_artifacts(self):
        self.repo_counter += 1
        repo = self.root / f"no-pending-repo-{self.repo_counter}"
        repo.mkdir()
        self.git(repo, "init")
        self.git(repo, "config", "user.email", "runtime@example.invalid")
        self.git(repo, "config", "user.name", "Runtime Tests")
        (repo / "README.md").write_text("repo\n", encoding="utf-8")
        self.git(repo, "add", "README.md")
        self.git(repo, "commit", "-m", "initial")
        text = "After this, no report needed."
        request = repo / "request.md"
        request.write_text(text, encoding="utf-8")
        decision = self.decision(self.root / "no-pending-none.json", text, verdict="none", evidence_quotes=["no report needed"])
        proc = self.run_cli(
            "register",
            "--request",
            request,
            "--decision",
            decision,
            "--session-id",
            self.session_id,
            "--workspace",
            repo,
        )
        self.assertEqual(self.data(proc)["issues"][0]["code"], "pending_missing")
        self.assertFalse((repo / "docs").exists())

    def test_prompt_candidate_needs_clarification_clears_without_task_dir(self):
        text = "After this work is complete, send a report."
        repo, _task_dir, request = self.make_repo_task(request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        decision = self.decision(
            self.root / "needs_clarification.json",
            text,
            verdict="needs_clarification",
            evidence_quotes=["send a report"],
        )
        cleared = self.data(
            self.run_cli(
                "register",
                "--request",
                request,
                "--decision",
                decision,
                "--session-id",
                self.session_id,
                "--workspace",
                repo,
            )
        )
        self.assertEqual(cleared["status"], "ignored")
        self.assertFalse((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json").exists())

    def test_deferred_milestone_resolution_is_recorded_without_scheduling(self):
        text = "完整矩阵结束后给我一份报告。"
        repo, _task_dir, request = self.make_repo_task(request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        decision = self.decision(
            self.root / "deferred.json",
            text,
            verdict="deferred",
            on_end=False,
            interval_seconds=None,
            evidence_quotes=["完整矩阵结束后"],
            reason="explicit future milestone, but no runtime milestone scheduler exists",
        )
        result = self.data(
            self.run_cli(
                "register",
                "--request",
                request,
                "--decision",
                decision,
                "--session-id",
                self.session_id,
                "--workspace",
                repo,
            )
        )
        self.assertEqual(result["status"], "deferred")
        self.assertFalse(result["scheduled"])
        self.assertFalse(result["auto_enforced"])
        deferred_resolution_path = Path(result["resolution"])
        resolution = json.loads(deferred_resolution_path.read_text())
        self.assertEqual(resolution["decision"]["verdict"], "deferred")
        self.assertEqual(resolution["decision"]["evidence_quotes"], ["完整矩阵结束后"])
        self.assertNotIn("resume_after_report", resolution["decision"])
        self.assertFalse((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json").exists())
        self.assertEqual(
            self.data(self.run_cli("hook", input=json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id}), cwd=repo)),
            {},
        )

        followup = "After this, no report needed for this ordinary follow-up."
        request.write_text(followup, encoding="utf-8")
        followup_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t2",
                "prompt": followup,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=followup_event, cwd=repo)))
        followup_decision = self.decision(
            self.root / "followup-none.json",
            followup,
            verdict="none",
            evidence_quotes=["no report needed"],
        )
        followup_result = self.data(
            self.run_cli(
                "register",
                "--request",
                request,
                "--decision",
                followup_decision,
                "--session-id",
                self.session_id,
                "--workspace",
                repo,
            )
        )
        self.assertEqual(followup_result["status"], "ignored")
        followup_resolution_path = Path(followup_result["resolution"])
        self.assertNotEqual(deferred_resolution_path, followup_resolution_path)
        self.assertTrue(deferred_resolution_path.exists())
        self.assertTrue(followup_resolution_path.exists())

    def test_late_new_pending_survives_old_nonconfirmed_resolution_clear(self):
        text = "After this work is complete, send a report."
        new_text = "After the follow-up, send a report."
        repo, _task_dir, request = self.make_repo_task(request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        decision = self.decision(self.root / "none-race.json", text, verdict="none", evidence_quotes=["send a report"])
        runtime = self.load_runtime_module()
        original_write_resolution = runtime.write_pending_resolution

        def write_resolution_then_new_pending(workspace_root, session_id, pending, raw_decision):
            path = original_write_resolution(workspace_root, session_id, pending, raw_decision)
            runtime.atomic_write_json(
                runtime.pending_path(workspace_root, session_id),
                {
                    "schema_version": "work-report.pending/1",
                    "session_id": session_id,
                    "turn_id": "t2",
                    "workspace": str(workspace_root),
                    "created_at": runtime.iso_now(),
                    "request_sha256": self.sha(new_text),
                    "prompt": new_text,
                    "state": "needs_intent_judge",
                    "attempts": 0,
                    "reason": "new same-session candidate arrived during old resolution",
                },
            )
            return path

        runtime.write_pending_resolution = write_resolution_then_new_pending
        old_env = os.environ.copy()
        os.environ.update(self.git_env())
        try:
            rc, result = runtime.cmd_register(
                SimpleNamespace(
                    task_dir=None,
                    request=str(request),
                    decision=str(decision),
                    session_id=self.session_id,
                    workspace=str(repo),
                )
            )
        finally:
            os.environ.clear()
            os.environ.update(old_env)
        self.assertEqual(rc, 0)
        self.assertEqual(result["status"], "ignored")
        self.assertTrue(Path(result["resolution"]).exists())
        current_pending = json.loads((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json").read_text())
        self.assertEqual(current_pending["request_sha256"], self.sha(new_text))
        self.assertEqual(current_pending["prompt"], new_text)

    def test_nonconfirmed_register_rejects_same_session_pending_hash_mismatch(self):
        text = "After this work is complete, send a report."
        other_text = "Please send an end report."
        repo, _task_dir, request = self.make_repo_task(request_text=other_text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        decision = self.decision(self.root / "none-mismatch.json", other_text, verdict="none")
        proc = self.run_cli(
            "register",
            "--request",
            request,
            "--decision",
            decision,
            "--session-id",
            self.session_id,
            "--workspace",
            repo,
        )
        self.assertEqual(self.data(proc)["issues"][0]["code"], "pending_request_mismatch")
        self.assertTrue((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json").exists())

    def test_confirmed_register_failure_records_one_time_pending_diagnostic(self):
        text = "After this work is complete, send a report."
        repo, _task_dir, request = self.make_repo_task(request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        decision = self.decision(self.root / "confirmed.json", text, evidence_quotes=["send a report"])
        external_repo = self.root / "external-repo"
        external_repo.mkdir()
        self.git(external_repo, "init")
        self.git(external_repo, "config", "user.email", "runtime@example.invalid")
        self.git(external_repo, "config", "user.name", "Runtime Tests")
        (external_repo / "README.md").write_text("external\n", encoding="utf-8")
        self.git(external_repo, "add", "README.md")
        self.git(external_repo, "commit", "-m", "initial")
        external_task_dir = external_repo / "docs" / "work-reports" / "20260906T000000Z-runtime-abcdef"
        external_task_dir.mkdir(parents=True)
        proc = self.run_cli(
            "register",
            "--task-dir",
            external_task_dir,
            "--request",
            request,
            "--decision",
            decision,
            "--session-id",
            self.session_id,
            "--workspace",
            repo,
        )
        self.assertEqual(self.data(proc)["issues"][0]["code"], "task_dir_git_mismatch")
        pending_path = repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json"
        pending = json.loads(pending_path.read_text())
        self.assertEqual(pending["state"], "register_failed")
        self.assertEqual(pending["last_register_error"]["verdict"], "confirmed")
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        first = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertIn("systemMessage", first)
        self.assertIn("Judge result was recorded", first["systemMessage"])
        self.assertIn("no report obligation was registered or satisfied", first["systemMessage"])
        retry = self.run_cli(
            "register",
            "--task-dir",
            external_task_dir,
            "--request",
            request,
            "--decision",
            decision,
            "--session-id",
            self.session_id,
            "--workspace",
            repo,
        )
        self.assertEqual(self.data(retry)["issues"][0]["code"], "task_dir_git_mismatch")
        self.assertEqual(self.data(self.run_cli("hook", input=stop_event, cwd=repo)), {})
        changed = self.run_cli(
            "register",
            "--request",
            request,
            "--decision",
            decision,
            "--session-id",
            self.session_id,
            "--workspace",
            repo,
        )
        self.assertEqual(self.data(changed)["issues"][0]["code"], "task_dir_required")
        changed_notice = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertIn("systemMessage", changed_notice)
        self.assertIn("task_dir_required", changed_notice["systemMessage"])

    def test_manifest_conflict_records_one_time_pending_diagnostic(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        self.assertEqual(self.register(repo, task_dir, request, self.decision(self.root / "initial.json", text)).returncode, 0)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": text,
            }
        )
        self.assertIn("hookSpecificOutput", self.data(self.run_cli("hook", input=prompt_event, cwd=repo)))
        different = self.decision(
            self.root / "different.json",
            text,
            on_end=True,
            interval_seconds=60,
            evidence_quotes=["end report"],
        )
        proc = self.register(repo, task_dir, request, different)
        self.assertEqual(self.data(proc)["issues"][0]["code"], "manifest_conflict")
        pending = json.loads((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json").read_text())
        self.assertEqual(pending["state"], "register_failed")
        self.assertEqual(pending["last_register_error"]["code"], "manifest_conflict")
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        notice = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertIn("systemMessage", notice)
        self.assertIn("manifest_conflict", notice["systemMessage"])

    def test_prompt_candidate_matches_interim_continue_terms(self):
        repo, _, _ = self.make_repo_task(request_text="irrelevant")
        examples = [
            "Give me an interim work-report and continue afterwards.",
            "临时汇报一下，之后继续做。",
            "中途抽检报告一下，然后继续。",
        ]
        for idx, prompt in enumerate(examples):
            event = json.dumps(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "cwd": str(repo),
                    "session_id": f"11111111-2222-4333-8444-55555555555{idx}",
                    "turn_id": f"t{idx}",
                    "prompt": prompt,
                }
            )
            output = self.data(self.run_cli("hook", input=event, cwd=repo))
            self.assertIn("hookSpecificOutput", output, prompt)

    def test_prompt_candidate_caps_then_fails_open_visibly(self):
        repo, _, _ = self.make_repo_task(request_text="irrelevant")
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "prompt": "After this work is complete, send a report.",
            }
        )
        self.run_cli("hook", input=prompt_event, cwd=repo)
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        self.assertEqual(self.data(self.run_cli("hook", input=stop_event, cwd=repo))["decision"], "block")
        self.assertEqual(self.data(self.run_cli("hook", input=stop_event, cwd=repo))["decision"], "block")
        third = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertIn("systemMessage", third)
        self.assertEqual(self.data(self.run_cli("hook", input=stop_event, cwd=repo)), {})
        self.assertTrue((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.failure.json").exists())

    def test_subagent_hook_payload_is_ignored(self):
        repo, _, _ = self.make_repo_task(request_text="irrelevant")
        event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "agent_id": "judge-agent",
                "prompt": "After this work is complete, send a report.",
            }
        )
        self.assertEqual(self.data(self.run_cli("hook", input=event, cwd=repo)), {})
        self.assertFalse((repo / "docs" / "work-reports" / ".pending" / f"{self.session_id}.json").exists())

    def test_periodic_tick_and_claim_are_bounded(self):
        text = "Please send periodic report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=60,
            evidence_quotes=["periodic report"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["next_due_at"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        due = self.data(self.run_cli("tick", "--task-dir", task_dir))
        self.assertEqual(due["action"], "report_due")
        claimed = self.data(self.run_cli("claim", "--task-dir", task_dir, "--owner", "a", "--kind", "progress"))
        self.assertEqual(claimed["status"], "claimed")
        pending = self.data(self.run_cli("claim", "--task-dir", task_dir, "--owner", "b", "--kind", "progress"))
        self.assertEqual(pending["status"], "pending")
        self.run_cli("release", "--task-dir", task_dir, "--owner", "a", "--kind", "progress", "--error", "failed once")
        claimed2 = self.data(self.run_cli("claim", "--task-dir", task_dir, "--owner", "b", "--kind", "progress"))
        self.assertEqual(claimed2["status"], "claimed")

    def test_periodic_release_advances_future_due_and_status_preserves_ack(self):
        text = "Please send periodic report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=60,
            evidence_quotes=["periodic report"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["next_due_at"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.data(self.run_cli("tick", "--task-dir", task_dir))["action"], "report_due")
        self.assertEqual(self.data(self.run_cli("claim", "--task-dir", task_dir, "--owner", "scheduler", "--kind", "progress"))["status"], "claimed")

        report_dir = task_dir / "20260906T000007Z-progress-c0ffee"
        report_dir.mkdir()
        report = report_dir / "report.md"
        report.write_text("periodic report after a long run", encoding="utf-8")
        (report_dir / "context.json").write_text(
            json.dumps({"schema_version": "work-report.context/1", "generated_at": "2099-01-01T00:00:00Z"}),
            encoding="utf-8",
        )
        (report_dir / "delivery.json").write_text(
            json.dumps(
                {
                    "schema_version": "work-report.delivery/1",
                    "status": "pass",
                    "task_id": task_dir.name,
                    "report_id": report_dir.name,
                    "report": str(report.resolve()),
                    "artifact_digest": self.file_sha(report),
                    "delivered_at": "2099-01-01T00:00:01Z",
                    "kind": "progress",
                    "request_sha256": self.sha(text),
                }
            ),
            encoding="utf-8",
        )
        released = self.data(
            self.run_cli("release", "--task-dir", task_dir, "--owner", "scheduler", "--kind", "progress", "--success")
        )
        self.assertEqual(released["result"], "success")
        first = self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]
        second = self.data(self.run_cli("status", "--task-dir", task_dir))["manifest"]
        self.assertEqual(first["periodic"]["state"], "satisfied")
        self.assertEqual(second["periodic"]["state"], "satisfied")
        self.assertIsNotNone(second["periodic"]["last_ack"])
        next_due = dt.datetime.fromisoformat(second["next_due_at"].replace("Z", "+00:00"))
        self.assertGreater(next_due, dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30))
        self.assertEqual(self.data(self.run_cli("tick", "--task-dir", task_dir))["action"], "idle")

    def test_stop_blocks_due_periodic_obligation(self):
        text = "Please send periodic report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=60,
            evidence_quotes=["periodic report"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["next_due_at"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        blocked = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertEqual(blocked["decision"], "block")
        self.assertIn("progress", blocked["reason"])

    def test_register_same_intent_is_idempotent(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(self.root / "decision.json", text)
        first = self.data(self.register(repo, task_dir, request, decision))
        before = json.loads((task_dir / "reporting.json").read_text())["registered_at"]
        second = self.data(self.register(repo, task_dir, request, decision))
        after = json.loads((task_dir / "reporting.json").read_text())["registered_at"]
        self.assertEqual(first["status"], "registered")
        self.assertTrue(second["idempotent"])
        self.assertEqual(before, after)

    def test_register_rejects_different_manifest_in_existing_task_dir(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        final_decision = self.decision(self.root / "final.json", text)
        self.assertEqual(self.data(self.register(repo, task_dir, request, final_decision))["status"], "registered")
        before = json.loads((task_dir / "reporting.json").read_text())

        interim_text = "Please make an interim report, then continue the task."
        request.write_text(interim_text, encoding="utf-8")
        report_dir = task_dir / "20260906T000014Z-progress-acdc07"
        report_dir.mkdir()
        context = json.loads(next(task_dir.glob("*/context.json")).read_text())
        context["report_id"] = report_dir.name
        context["request"]["sha256"] = self.sha(interim_text)
        context["request"]["text"] = interim_text
        (report_dir / "context.json").write_text(json.dumps(context), encoding="utf-8")
        interim_decision = self.decision(
            self.root / "interim.json",
            interim_text,
            on_end=False,
            interval_seconds=None,
            resume_after_report=True,
            evidence_quotes=["interim report", "continue"],
        )
        conflict = self.data(self.register(repo, task_dir, request, interim_decision))
        self.assertEqual(conflict["issues"][0]["code"], "manifest_conflict")
        after = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(after["request_sha256"], before["request_sha256"])
        self.assertIsNotNone(after["final"])

    def test_register_uses_context_matching_current_request(self):
        old_text = "Please send an end report."
        new_text = "Please send an end report after the updated task."
        repo, task_dir, request = self.make_repo_task(request_text=old_text)
        request.write_text(new_text, encoding="utf-8")
        report_dir = task_dir / "20260906T000005Z-progress-bb0011"
        report_dir.mkdir()
        context = json.loads(next(task_dir.glob("*/context.json")).read_text())
        context["report_id"] = report_dir.name
        context["request"]["sha256"] = self.sha(new_text)
        context["request"]["text"] = new_text
        (report_dir / "context.json").write_text(json.dumps(context), encoding="utf-8")
        decision = self.decision(self.root / "decision.json", new_text, evidence_quotes=["end report"])
        result = self.data(self.register(repo, task_dir, request, decision))
        self.assertEqual(result["status"], "registered")

    def test_stop_skips_duplicate_prompt_while_scheduler_lease_active(self):
        text = "Please send periodic report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=60,
            evidence_quotes=["periodic report"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["next_due_at"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.run_cli("tick", "--task-dir", task_dir)
        self.assertEqual(self.data(self.run_cli("claim", "--task-dir", task_dir, "--owner", "scheduler", "--kind", "progress"))["status"], "claimed")
        event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        self.assertEqual(self.data(self.run_cli("hook", input=event, cwd=repo)), {})

    def test_post_tool_use_due_prompt_claims_main_lease(self):
        text = "Please send periodic report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=60,
            evidence_quotes=["periodic report"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["next_due_at"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        event = json.dumps({"hook_event_name": "PostToolUse", "cwd": str(repo), "session_id": self.session_id, "turn_id": "t1"})
        output = self.data(self.run_cli("hook", input=event, cwd=repo))
        self.assertIn("hookSpecificOutput", output)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        self.assertEqual(manifest["periodic"]["lease"]["owner"], f"main:{self.session_id}:t1")
        scheduler = self.data(self.run_cli("claim", "--task-dir", task_dir, "--owner", "scheduler", "--kind", "progress"))
        self.assertEqual(scheduler["status"], "pending")

    def test_concurrent_claims_produce_single_lease(self):
        text = "Please send periodic report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        decision = self.decision(
            self.root / "decision.json",
            text,
            on_end=False,
            interval_seconds=60,
            evidence_quotes=["periodic report"],
        )
        self.register(repo, task_dir, request, decision)
        manifest = json.loads((task_dir / "reporting.json").read_text())
        manifest["next_due_at"] = "2000-01-01T00:00:00Z"
        (task_dir / "reporting.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.data(self.run_cli("tick", "--task-dir", task_dir))["action"], "report_due")

        queue = multiprocessing.Queue()
        env = self.git_env()
        procs = [
            multiprocessing.Process(target=claim_worker, args=(RUNTIME, task_dir, f"owner-{idx}", env, queue))
            for idx in range(6)
        ]
        for proc in procs:
            proc.start()
        for proc in procs:
            proc.join(10)
            self.assertFalse(proc.is_alive())
        results = [json.loads(queue.get()[1]) for _ in procs]
        self.assertEqual(sum(1 for item in results if item.get("status") == "claimed"), 1, results)
        self.assertEqual(sum(1 for item in results if item.get("status") == "pending"), 5, results)


if __name__ == "__main__":
    unittest.main()
