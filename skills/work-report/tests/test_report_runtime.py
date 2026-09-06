import json
import multiprocessing
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import datetime as dt
from pathlib import Path


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

    def sha(self, text):
        import hashlib

        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def file_sha(self, path):
        import hashlib

        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

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

    def test_prompt_candidate_blocks_stop_until_judge_decision_clears_it(self):
        text = "Please send an end report."
        repo, task_dir, request = self.make_repo_task(request_text=text)
        prompt_event = json.dumps(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(repo),
                "session_id": self.session_id,
                "turn_id": "t1",
                "prompt": "After this work is complete, send a report.",
            }
        )
        prompt = self.data(self.run_cli("hook", input=prompt_event, cwd=repo))
        self.assertIn("hookSpecificOutput", prompt)
        stop_event = json.dumps({"hook_event_name": "Stop", "cwd": str(repo), "session_id": self.session_id})
        stop = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(stop["decision"], "block")
        decision = self.decision(self.root / "none.json", text, verdict="none")
        cleared = self.data(self.register(repo, task_dir, request, decision))
        self.assertEqual(cleared["status"], "ignored")
        stop2 = self.data(self.run_cli("hook", input=stop_event, cwd=repo))
        self.assertEqual(stop2, {})

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
