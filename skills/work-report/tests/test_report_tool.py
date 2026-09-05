import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

import yaml


TEST_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TEST_DIR.parent
REPO_ROOT = SKILL_ROOT.parent.parent
DEFAULT_TOOL = SKILL_ROOT / "scripts" / "report_tool.py"
FIXTURES = TEST_DIR / "fixtures"


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c63000100000500010d0a2db400000000"
    "49454e44ae426082"
)


@dataclass
class ReportCase:
    workspace: Path
    task_dir: Path
    report: Path
    context: Path
    task_id: str
    report_id: str
    output_root: Path
    tool: Path
    skill_root: Path


class ReportToolTests(unittest.TestCase):
    maxDiff = 4000

    def isolated_git_env(self):
        # TMPDIR may itself live inside a developer's Git checkout. Fixture
        # repositories remain discoverable, but their ancestors must not be.
        return {**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(tempfile.gettempdir()).resolve())}

    def run_cli(self, *args, tool=DEFAULT_TOOL, cwd=None):
        return subprocess.run(
            [sys.executable, str(tool), *map(str, args)],
            cwd=str(cwd or REPO_ROOT),
            env=self.isolated_git_env(),
            text=True,
            capture_output=True,
            check=False,
        )

    def json_stdout(self, proc):
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"stdout was not JSON, exit={proc.returncode}\n"
                f"stdout={proc.stdout!r}\nstderr={proc.stderr!r}\n{exc}"
            )

    def assert_pass(self, proc):
        data = self.json_stdout(proc)
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout}\nstderr={proc.stderr}")
        self.assertEqual(data.get("status"), "pass", data)
        return data

    def assert_fail(self, proc):
        data = self.json_stdout(proc)
        self.assertNotEqual(proc.returncode, 0, data)
        self.assertEqual(data.get("status"), "fail", data)
        self.assertTrue(data.get("issues"), data)
        return data

    def git(self, repo, *args, check=True):
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            env=self.isolated_git_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        if check and proc.returncode != 0:
            self.fail(f"git {' '.join(args)} failed\n{proc.stdout}\n{proc.stderr}")
        return proc

    def init_git_repo(self, path):
        path.mkdir(parents=True, exist_ok=True)
        self.git(path, "init")
        self.git(path, "config", "user.email", "report-tests@example.invalid")
        self.git(path, "config", "user.name", "Report Tool Tests")
        (path / "README.md").write_text("fixture repo\n", encoding="utf-8")
        self.git(path, "add", "README.md")
        self.git(path, "commit", "-m", "initial")

    def load_rubric(self, skill_root=SKILL_ROOT):
        with self.rubric_path(skill_root).open(encoding="utf-8") as handle:
            rubric = yaml.safe_load(handle)
        self.assertIsInstance(rubric, dict)
        return rubric

    def rubric_path(self, skill_root=SKILL_ROOT):
        candidates = [skill_root / "references" / "rubric.yaml", skill_root / "rubric.yaml"]
        for path in candidates:
            if path.exists():
                return path
        self.fail(f"rubric.yaml not found under {skill_root}")

    def section_defs(self, skill_root=SKILL_ROOT):
        sections = self.load_rubric(skill_root).get("sections")
        self.assertIsInstance(sections, list)
        return [(str(item["id"]), str(item["title"])) for item in sections]

    def criteria_ids(self, skill_root=SKILL_ROOT):
        criteria = self.load_rubric(skill_root).get("criteria")
        self.assertIsInstance(criteria, list)
        return [str(item["id"]) for item in criteria]

    def make_workspace(self, root, git=False):
        workspace = Path(root) / "workspace"
        workspace.mkdir()
        if git:
            self.init_git_repo(workspace)
        return workspace

    def init_report(self, workspace, *, tool=DEFAULT_TOOL, title="case", output_root=None, state_text=None):
        request = workspace / "request.md"
        request.write_text("Original request: build a factual work report.\n", encoding="utf-8")
        args = ["init", "--workspace", workspace, "--title", title, "--request", request]
        if output_root is not None:
            args.extend(["--output-root", output_root])
        state_path = None
        if state_text is not None:
            state_path = workspace / "state.md"
            state_path.write_text(state_text, encoding="utf-8")
            args.extend(["--state", state_path])
        proc = self.run_cli(*args, tool=tool)
        data = self.assert_pass(proc)
        report = self.find_report_path(data)
        if report is None:
            search_root = Path(output_root) if output_root is not None else workspace / "docs" / "work-reports"
            reports = sorted(search_root.glob("*/**/report.md"))
            self.assertEqual(len(reports), 1, data)
            report = reports[0]
        context = report.parent / "context.json"
        with context.open(encoding="utf-8") as handle:
            context_data = json.load(handle)
        return ReportCase(
            workspace=workspace,
            task_dir=report.parent.parent,
            report=report,
            context=context,
            task_id=context_data["task_id"],
            report_id=context_data["report_id"],
            output_root=Path(context_data["output_root"]),
            tool=Path(tool),
            skill_root=Path(tool).parent.parent,
        )

    def find_report_path(self, data):
        stack = [data]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
            elif isinstance(value, str) and value.endswith("report.md"):
                path = Path(value)
                if path.exists():
                    return path
        return None

    def frontmatter(self, case):
        with case.context.open(encoding="utf-8") as handle:
            context = json.load(handle)
        keys = [
            "task_id",
            "report_id",
            "kind",
            "workspace",
            "generated_at",
            "window_start",
            "window_end",
        ]
        lines = ["---"]
        lines.extend(f"{key}: {json.dumps(context[key])}" for key in keys)
        lines.append("---")
        return "\n".join(lines) + "\n\n"

    def body_with_sections(self, case, *, visual="table", section_overrides=None, local_link=True):
        section_overrides = section_overrides or {}
        parts = []
        evidence = case.report.parent / "evidence.txt"
        evidence.write_text("The CLI completed and the checked files are local.\n", encoding="utf-8")
        image_md = ""
        if visual == "image":
            assets = case.report.parent / "assets"
            assets.mkdir(exist_ok=True)
            (assets / "diagram.png").write_bytes(PNG_1X1)
            image_md = "\n![workflow](assets/diagram.png)\n"
        table = ""
        if visual == "table":
            table = (
                "\n| Check | Evidence | Result |\n"
                "| --- | --- | --- |\n"
                "| CLI report gate | [local evidence](evidence.txt) | passed |\n"
            )
        elif visual == "empty_table":
            table = "\n| Check | Evidence |\n| --- | --- |\n"
        elif visual == "code_table":
            table = "\n```markdown\n| Check | Result |\n| --- | --- |\n| hidden | passed |\n```\n"
        elif visual == "mermaid":
            table = "\n```mermaid\ngraph TD\n  A[Start] --> B[Done]\n```\n"
        elif visual == "missing_image":
            image_md = "\n![missing](assets/missing.png)\n"
        elif visual == "outside_image":
            outside = case.report.parent / "diagram.png"
            outside.write_bytes(PNG_1X1)
            image_md = "\n![outside](diagram.png)\n"

        for section_id, title in self.section_defs(case.skill_root):
            content = section_overrides.get(section_id)
            if content is None:
                content = (
                    f"This section records concrete facts for {section_id}. "
                    "The work stayed inside the requested report skill tests."
                )
            parts.append(f"## {title}\n\n{content}\n")
        if local_link:
            parts.append("The main local evidence is [available here](evidence.txt).\n")
        parts.append(table)
        parts.append(image_md)
        return "\n".join(parts)

    def write_report(self, case, body):
        case.report.write_text(self.frontmatter(case) + body, encoding="utf-8")

    def write_fixture_report(self, case, name, *, create_evidence=True):
        if create_evidence:
            (case.report.parent / "evidence.txt").write_text(
                "Fixture evidence created by the unit test beside report.md.\n",
                encoding="utf-8",
            )
        self.write_report(case, (FIXTURES / name).read_text(encoding="utf-8"))

    def check_report(self, case, *, task_id=None, workspace=None):
        return self.run_cli(
            "check",
            "--report",
            case.report,
            "--task",
            task_id or case.task_id,
            "--workspace",
            workspace or case.workspace,
            tool=case.tool,
        )

    def checks_json(self, case):
        with (case.report.parent / "checks.json").open(encoding="utf-8") as handle:
            return json.load(handle)

    def write_review(self, case, *, verdict="pass", scope_status="within_scope", criteria=None, findings=None):
        digest = self.checks_json(case)["artifact_digest"]
        if criteria is None:
            criteria = [
                {
                    "id": criterion_id,
                    "status": "pass",
                    "reason": "The report gives a concrete, reviewable account.",
                    "evidence": ["report.md"],
                }
                for criterion_id in self.criteria_ids(case.skill_root)
            ]
        review = {
            "schema_version": "work-report.review/1",
            "artifact_digest": digest,
            "rubric_version": "1.0.0",
            "reviewer_id": "unit-test-judge",
            "verdict": verdict,
            "criteria": criteria,
            "findings": findings or [],
            "scope_assessment": {
                "status": scope_status,
                "reason": "The reviewer explicitly assessed the task boundary.",
                "evidence": ["report.md"],
            },
        }
        (case.report.parent / "review.json").write_text(json.dumps(review, indent=2), encoding="utf-8")
        return review

    def finalize(self, case):
        return self.run_cli(
            "finalize",
            "--report",
            case.report,
            "--task",
            case.task_id,
            "--workspace",
            case.workspace,
            tool=case.tool,
        )

    def checked_case(self, tmp, *, visual="table", body=None, tool=DEFAULT_TOOL):
        case = self.init_report(self.make_workspace(tmp), tool=tool)
        self.write_report(case, body if body is not None else self.body_with_sections(case, visual=visual))
        self.assert_pass(self.check_report(case))
        return case

    def copy_skill(self, tmp):
        copied = Path(tmp) / "skill-copy"
        shutil.copytree(
            SKILL_ROOT,
            copied,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
        )
        return copied, copied / "scripts" / "report_tool.py"

    def test_init_creates_context_and_preserves_initial_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp, git=True)
            case = self.init_report(workspace, state_text="Initial state text.\n")
            context = json.loads(case.context.read_text(encoding="utf-8"))
            self.assertEqual(context["request"]["text"], "Original request: build a factual work report.\n")
            self.assertEqual(context["state"]["text"], "Initial state text.\n")
            self.assertEqual(Path(context["workspace"]), workspace.resolve())
            self.assertEqual(Path(context["state"]["path"]), (workspace / "state.md").resolve())
            self.assertFalse((case.task_dir / "working-state.md").exists())

    def test_init_creates_working_state_when_no_state_file_is_supplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp)
            case = self.init_report(workspace)
            context = json.loads(case.context.read_text(encoding="utf-8"))
            self.assertEqual(Path(context["state"]["path"]), (case.task_dir / "working-state.md").resolve())
            self.assertIn(case.task_id, context["state"]["text"])
            self.assertTrue((case.task_dir / "working-state.md").exists())

    def test_sufficient_fixture_passes_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_fixture_report(case, "sufficient-scoped-report.md")
            result = self.assert_pass(self.check_report(case))
            self.assertEqual(result["task_id"], case.task_id)
            self.assertEqual(result["report_id"], case.report_id)

    def test_fixture_bodies_do_not_show_test_answer_keys(self):
        forbidden = ["expected", "verdict", "expected judge", "judge reading"]
        report_names = [
            "empty-but-formatted.md",
            "hidden-drift.md",
            "honest-drift.md",
            "sufficient-scoped-report.md",
            "wrong-evidence.md",
            "context.json",
            "source.md",
        ]
        for name in report_names:
            text = (FIXTURES / name).read_text(encoding="utf-8").lower()
            for marker in forbidden:
                self.assertNotIn(marker, text, name)

    def test_honest_drift_can_finalize_when_judge_discloses_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_fixture_report(case, "honest-drift.md")
            self.assert_pass(self.check_report(case))
            self.write_review(case, scope_status="drift_disclosed")
            final = self.assert_pass(self.finalize(case))
            self.assertEqual(final.get("review_origin"), "not_independently_verified_by_script")

    def test_empty_but_formatted_fixture_fails_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_fixture_report(case, "empty-but-formatted.md", create_evidence=False)
            self.assert_fail(self.check_report(case))

    def test_absent_report_file_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            missing = case.report
            missing.unlink()
            proc = self.run_cli("check", "--report", missing, "--task", case.task_id, "--workspace", case.workspace)
            self.assertNotEqual(proc.returncode, 0)
            data = self.json_stdout(proc)
            self.assertEqual(data.get("status"), "fail")

    def test_wrong_task_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case))
            self.assert_fail(self.check_report(case, task_id="20260905T000000Z-other-12345678"))

    def test_wrong_workspace_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            other = Path(tmp) / "other"
            other.mkdir()
            self.write_report(case, self.body_with_sections(case))
            self.assert_fail(self.check_report(case, workspace=other))

    def test_malformed_context_workspace_or_output_root_list_returns_validation_json(self):
        for field in ["workspace", "output_root"]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                case = self.init_report(self.make_workspace(tmp))
                self.write_report(case, self.body_with_sections(case))
                context = json.loads(case.context.read_text(encoding="utf-8"))
                context[field] = [context[field]]
                case.context.write_text(json.dumps(context, indent=2), encoding="utf-8")
                proc = self.check_report(case)
                data = self.json_stdout(proc)
                self.assertEqual(proc.returncode, 1, data)
                self.assertEqual(data.get("status"), "fail", data)
                self.assertTrue(data.get("issues"), data)

    def test_headings_inside_code_fence_do_not_satisfy_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            fake = "```markdown\n" + "\n".join(f"## {title}\nfilled" for _, title in self.section_defs(case.skill_root)) + "\n```\n"
            self.write_report(case, fake + "\n| A | B |\n| --- | --- |\n| 1 | 2 |\n")
            self.assert_fail(self.check_report(case))

    def test_placeholder_content_fails_until_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            first_id = self.section_defs(case.skill_root)[0][0]
            body = self.body_with_sections(case, section_overrides={first_id: "TODO"})
            self.write_report(case, body)
            self.assert_fail(self.check_report(case))

    def test_empty_required_section_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            first_id = self.section_defs(case.skill_root)[0][0]
            body = self.body_with_sections(case, section_overrides={first_id: "   \n"})
            self.write_report(case, body)
            self.assert_fail(self.check_report(case))

    def test_report_without_table_or_image_fails_visual_requirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case, visual=None))
            self.assert_fail(self.check_report(case))

    def test_empty_table_does_not_count_as_visual(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case, visual="empty_table"))
            self.assert_fail(self.check_report(case))

    def test_table_inside_code_fence_does_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case, visual="code_table"))
            self.assert_fail(self.check_report(case))

    def test_mermaid_only_is_not_a_verified_visual(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case, visual="mermaid"))
            result = self.assert_fail(self.check_report(case))
            codes = {issue.get("code") for issue in result.get("issues", [])}
            self.assertIn("visual_unverified", codes)

    def test_missing_local_image_fails_even_with_full_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case, visual="missing_image"))
            self.assert_fail(self.check_report(case))

    def test_missing_local_link_fails_even_when_table_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_fixture_report(case, "wrong-evidence.md", create_evidence=False)
            self.assert_fail(self.check_report(case))

    def test_image_must_stay_inside_assets_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case, visual="outside_image"))
            self.assert_fail(self.check_report(case))

    def test_symlink_output_root_is_rejected_before_init_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp)
            real_out = Path(tmp) / "real-output"
            real_out.mkdir()
            linked_out = Path(tmp) / "linked-output"
            linked_out.symlink_to(real_out, target_is_directory=True)
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli(
                "init",
                "--workspace",
                workspace,
                "--title",
                "symlink-out",
                "--request",
                request,
                "--output-root",
                linked_out,
            )
            self.assert_fail(proc)
            self.assertEqual([], list(real_out.rglob("report.md")))

    def test_symlink_report_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case))
            real_report = case.report.with_name("real-report.md")
            case.report.rename(real_report)
            case.report.symlink_to(real_report)
            self.assert_fail(self.check_report(case))

    def test_symlink_context_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_report(case, self.body_with_sections(case))
            real_context = case.context.with_name("real-context.json")
            case.context.rename(real_context)
            case.context.symlink_to(real_context)
            self.assert_fail(self.check_report(case))

    def test_missing_rubric_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_root, tool = self.copy_skill(tmp)
            self.rubric_path(copied_root).unlink()
            workspace = self.make_workspace(tmp)
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli("init", "--workspace", workspace, "--title", "no-rubric", "--request", request, tool=tool)
            self.assert_fail(proc)

    def test_missing_report_template_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_root, tool = self.copy_skill(tmp)
            (copied_root / "assets" / "report.md").unlink()
            workspace = self.make_workspace(tmp)
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli("init", "--workspace", workspace, "--title", "no-template", "--request", request, tool=tool)
            self.assert_fail(proc)

    def test_request_and_state_files_are_not_reread_during_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp)
            case = self.init_report(workspace, state_text="State at init.\n")
            (workspace / "request.md").write_text("Changed request after init.\n", encoding="utf-8")
            (workspace / "state.md").write_text("Changed state after init.\n", encoding="utf-8")
            self.write_report(case, self.body_with_sections(case))
            self.assert_pass(self.check_report(case))
            context = json.loads(case.context.read_text(encoding="utf-8"))
            self.assertEqual(context["request"]["text"], "Original request: build a factual work report.\n")
            self.assertEqual(context["state"]["text"], "State at init.\n")

    def test_init_rejects_tracked_default_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp, git=True)
            tracked = workspace / "docs" / "work-reports" / "tracked.txt"
            tracked.parent.mkdir(parents=True)
            tracked.write_text("tracked report output\n", encoding="utf-8")
            self.git(workspace, "add", "docs/work-reports/tracked.txt")
            self.git(workspace, "commit", "-m", "track report output")
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli("init", "--workspace", workspace, "--title", "tracked", "--request", request)
            self.assert_fail(proc)

    def test_init_rejects_staged_default_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp, git=True)
            staged = workspace / "docs" / "work-reports" / "staged.txt"
            staged.parent.mkdir(parents=True)
            staged.write_text("staged report output\n", encoding="utf-8")
            self.git(workspace, "add", "docs/work-reports/staged.txt")
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli("init", "--workspace", workspace, "--title", "staged", "--request", request)
            self.assert_fail(proc)

    def test_external_output_root_in_other_repo_must_not_be_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp, git=True)
            external = Path(tmp) / "external"
            self.init_git_repo(external)
            out = external / "reports"
            out.mkdir()
            (out / "kept.txt").write_text("tracked elsewhere\n", encoding="utf-8")
            self.git(external, "add", "reports/kept.txt")
            self.git(external, "commit", "-m", "track external reports")
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli(
                "init",
                "--workspace",
                workspace,
                "--title",
                "external",
                "--request",
                request,
                "--output-root",
                out,
            )
            self.assert_fail(proc)

    def test_external_output_root_passes_when_already_ignored_and_untracked_without_editing_external_ignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp, git=True)
            external = Path(tmp) / "external"
            self.init_git_repo(external)
            out = external / "reports"
            out.mkdir()
            exclude = external / ".git" / "info" / "exclude"
            original_exclude = exclude.read_text(encoding="utf-8")
            if original_exclude and not original_exclude.endswith("\n"):
                original_exclude += "\n"
            original_exclude += "/reports/\n"
            exclude.write_text(original_exclude, encoding="utf-8")
            case = self.init_report(workspace, output_root=out)
            self.assertEqual(exclude.read_text(encoding="utf-8"), original_exclude)
            self.write_report(case, self.body_with_sections(case))
            self.assert_pass(self.check_report(case))
            self.assertEqual(exclude.read_text(encoding="utf-8"), original_exclude)

    def test_linked_git_worktree_uses_worktree_git_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "main"
            self.init_git_repo(main)
            linked = Path(tmp) / "linked"
            self.git(main, "worktree", "add", str(linked), "HEAD")
            case = self.init_report(linked)
            self.write_report(case, self.body_with_sections(case))
            self.assert_pass(self.check_report(case))

    def test_finalize_fails_when_report_changes_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            self.write_review(case)
            case.report.write_text(case.report.read_text(encoding="utf-8") + "\nLate mutation.\n", encoding="utf-8")
            self.assert_fail(self.finalize(case))

    def test_finalize_fails_when_asset_changes_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp, visual="image")
            self.write_review(case)
            (case.report.parent / "assets" / "diagram.png").write_bytes(PNG_1X1 + b"changed")
            self.assert_fail(self.finalize(case))

    def test_finalize_fails_when_cited_evidence_changes_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            self.write_review(case)
            (case.report.parent / "evidence.txt").write_text("changed evidence\n", encoding="utf-8")
            self.assert_fail(self.finalize(case))

    def test_finalize_fails_when_rubric_changes_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_root, tool = self.copy_skill(tmp)
            case = self.checked_case(tmp, tool=tool)
            self.write_review(case)
            rubric = self.rubric_path(copied_root)
            rubric.write_text(rubric.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
            self.assert_fail(self.finalize(case))

    def test_finalize_fails_when_report_tool_changes_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            copied_root, tool = self.copy_skill(tmp)
            case = self.checked_case(tmp, tool=tool)
            self.write_review(case)
            tool.write_text(tool.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_duplicate_review_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            ids = self.criteria_ids(case.skill_root)
            criteria = [
                {"id": ids[0], "status": "pass", "reason": "first", "evidence": ["report.md"]},
                {"id": ids[0], "status": "pass", "reason": "duplicate", "evidence": ["report.md"]},
            ] + [
                {"id": criterion_id, "status": "pass", "reason": "ok", "evidence": ["report.md"]}
                for criterion_id in ids[1:]
            ]
            self.write_review(case, criteria=criteria)
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_missing_review_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            criteria = [
                {"id": criterion_id, "status": "pass", "reason": "ok", "evidence": ["report.md"]}
                for criterion_id in self.criteria_ids(case.skill_root)[:-1]
            ]
            self.write_review(case, criteria=criteria)
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_unknown_review_criteria(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            criteria = [
                {"id": criterion_id, "status": "pass", "reason": "ok", "evidence": ["report.md"]}
                for criterion_id in self.criteria_ids(case.skill_root)
            ]
            criteria[-1]["id"] = "not-in-rubric"
            self.write_review(case, criteria=criteria)
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_not_applicable_for_mandatory_criterion(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            criteria = [
                {"id": criterion_id, "status": "pass", "reason": "ok", "evidence": ["report.md"]}
                for criterion_id in self.criteria_ids(case.skill_root)
            ]
            mandatory = next(item for item in criteria if item["id"] != "decisions")
            mandatory["status"] = "not_applicable"
            self.write_review(case, criteria=criteria)
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_nonstring_review_criterion_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            criteria = [
                {"id": criterion_id, "status": "pass", "reason": "ok", "evidence": ["report.md"]}
                for criterion_id in self.criteria_ids(case.skill_root)
            ]
            criteria[0]["id"] = 123
            self.write_review(case, criteria=criteria)
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_unknown_scope_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            self.write_review(case, scope_status="looks_fine")
            self.assert_fail(self.finalize(case))

    def test_finalize_rejects_malformed_finding_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            self.write_review(
                case,
                findings=[
                    {
                        "criterion_id": self.criteria_ids(case.skill_root)[0],
                        "severity": "risk",
                        "report_location": "",
                        "evidence": "report.md",
                        "message": "",
                        "required_change": "",
                    }
                ],
            )
            self.assert_fail(self.finalize(case))

    def test_blocked_review_cannot_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.checked_case(tmp)
            self.write_review(
                case,
                verdict="blocked",
                findings=[
                    {
                        "criterion_id": self.criteria_ids(case.skill_root)[0],
                        "severity": "blocker",
                        "report_location": "report.md",
                        "evidence": ["report.md"],
                        "message": "The reviewer could not validate the report.",
                        "required_change": "Resolve the blocking review finding.",
                    }
                ],
            )
            self.assert_fail(self.finalize(case))

    def test_hidden_drift_review_cannot_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = self.init_report(self.make_workspace(tmp))
            self.write_fixture_report(case, "hidden-drift.md")
            self.assert_pass(self.check_report(case))
            self.write_review(case, scope_status="drift_undisclosed")
            self.assert_fail(self.finalize(case))

    def test_invalid_timestamp_window_does_not_write_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp)
            output_root = Path(tmp) / "reports"
            request = workspace / "request.md"
            request.write_text("request\n", encoding="utf-8")
            proc = self.run_cli(
                "init",
                "--workspace",
                workspace,
                "--title",
                "bad-window",
                "--request",
                request,
                "--output-root",
                output_root,
                "--window-start",
                "2026-09-05T10:00:00Z",
                "--window-end",
                "2026-09-05T09:00:00Z",
            )
            self.assert_fail(proc)
            self.assertEqual([], list(output_root.rglob("report.md")) if output_root.exists() else [])

    def test_check_outside_tool_task_does_not_write_checks_next_to_arbitrary_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = self.make_workspace(tmp)
            arbitrary = Path(tmp) / "arbitrary"
            arbitrary.mkdir()
            report = arbitrary / "report.md"
            report.write_text("---\ntask_id: wrong\n---\n\n# outside\n", encoding="utf-8")
            proc = self.run_cli(
                "check",
                "--report",
                report,
                "--task",
                "20260905T000000Z-task-12345678",
                "--workspace",
                workspace,
            )
            self.assert_fail(proc)
            self.assertFalse((arbitrary / "checks.json").exists())


if __name__ == "__main__":
    unittest.main()
