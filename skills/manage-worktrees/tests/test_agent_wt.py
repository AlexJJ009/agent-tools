import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path


SKILL_ROOT = Path(__file__).parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "agent_wt.py"
SPEC = importlib.util.spec_from_file_location("agent_wt", SCRIPT)
assert SPEC and SPEC.loader
agent_wt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent_wt
SPEC.loader.exec_module(agent_wt)


def run(argv, cwd, env=None, check=True):
    completed = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        raise AssertionError(
            f"command failed: {argv}\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return completed


class AgentWtTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "code" / "demo"
        self.repo.mkdir(parents=True)
        run(["git", "init", "-b", "main"], self.repo)
        run(["git", "config", "user.name", "Test User"], self.repo)
        run(["git", "config", "user.email", "test@example.invalid"], self.repo)
        (self.repo / "README.md").write_text("demo\n", encoding="utf-8")
        run(["git", "add", "README.md"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)
        self.env = os.environ.copy()
        self.env["AGENT_WT_STATE_HOME"] = str(self.base / "state")

    def cli(self, *args, cwd=None, check=True):
        completed = run(
            [sys.executable, str(SCRIPT), "-C", str(cwd or self.repo), *args],
            cwd or self.repo,
            env=self.env,
            check=check,
        )
        if "--json" in args and completed.stdout:
            return completed, json.loads(completed.stdout)
        return completed, None

    def assert_contract(self, payload, command):
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["command"], command)

    def test_parse_worktrees_accepts_legacy_newline_porcelain(self):
        raw = (
            "worktree /srv/code\n"
            "HEAD 0123456789abcdef\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree /srv/review tree\n"
            "HEAD fedcba9876543210\n"
            "detached\n"
        )
        self.assertEqual(
            agent_wt.parse_worktrees(raw),
            [
                {
                    "path": "/srv/code",
                    "head": "0123456789abcdef",
                    "branch_ref": "refs/heads/main",
                    "branch": "main",
                },
                {
                    "path": "/srv/review tree",
                    "head": "fedcba9876543210",
                    "detached": True,
                },
            ],
        )

    def test_list_worktrees_falls_back_when_git_lacks_z(self):
        legacy = "worktree /srv/code\nHEAD abcdef\nbranch refs/heads/main\n\n"
        unsupported = SimpleNamespace(returncode=129, stdout="", stderr="unknown switch `z'")
        supported = SimpleNamespace(returncode=0, stdout=legacy, stderr="")
        with mock.patch.object(agent_wt, "git", side_effect=[unsupported, supported]) as git_mock:
            records = agent_wt.list_worktrees(Path("/srv/code"))
        self.assertEqual(records[0]["branch"], "main")
        self.assertEqual(git_mock.call_count, 2)

    def test_decide_defaults_to_branch_for_clean_single_task(self):
        _completed, payload = self.cli("decide", "--json")
        self.assert_contract(payload, "decide")
        self.assertEqual(payload["recommendation"], "branch")

    def test_decide_uses_worktree_for_dirty_or_parallel_context(self):
        (self.repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        _completed, payload = self.cli("decide", "--json")
        self.assertEqual(payload["recommendation"], "worktree")
        self.assertIn("uncommitted", " ".join(payload["reasons"]))

        (self.repo / "scratch.txt").unlink()
        _completed, payload = self.cli("decide", "--parallel", "--json")
        self.assertEqual(payload["recommendation"], "worktree")

    def test_decide_returns_unsupported_guidance_without_mutation_for_permission_boundary(self):
        before = run(["git", "worktree", "list", "--porcelain"], self.repo).stdout
        _completed, payload = self.cli("decide", "--untrusted-users", "--json")
        after = run(["git", "worktree", "list", "--porcelain"], self.repo).stdout
        self.assertEqual(payload["recommendation"], "unsupported")
        self.assertIn("v1 does not create", payload["guidance"])
        self.assertEqual(after, before)

    def test_inspect_detects_root_lockfiles_and_setup(self):
        (self.repo / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
        (self.repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
        _completed, payload = self.cli("inspect", "--json")
        self.assertIn("pnpm", payload["project"]["detected"])
        self.assertEqual(payload["project"]["setup"][0]["argv"][:2], ["pnpm", "install"])
        self.assertIsNotNone(payload["project"]["lock_hash"])

    def test_create_dry_run_uses_external_same_parent_layout(self):
        completed, payload = self.cli(
            "create", "codex/feature-one", "--dry-run", "--min-free-gib", "0", "--json"
        )
        self.assertEqual(completed.returncode, 0)
        self.assert_contract(payload, "create")
        target = Path(payload["worktree_path"])
        self.assertEqual(target, (self.repo.parent / "_worktrees" / "demo" / "codex-feature-one").resolve())
        self.assertFalse(target.exists())
        self.assertFalse(agent_wt.is_within(target, self.repo))

    def test_path_policy_precedence_is_cli_repository_user_then_sibling(self):
        user_policy = self.base / "user-policy.json"
        user_root = self.base / "user-root"
        user_policy.write_text(json.dumps({"worktree_root": str(user_root)}), encoding="utf-8")
        self.env["AGENT_WT_CONFIG"] = str(user_policy)

        _completed, payload = self.cli(
            "create", "codex/user-policy", "--dry-run", "--min-free-gib", "0", "--json"
        )
        self.assertEqual(payload["path_policy_source"], "user_or_machine")
        self.assertEqual(Path(payload["workspace_root"]), user_root.resolve())

        repo_root = self.base / "repo-root"
        (self.repo / ".agent-wt.json").write_text(
            json.dumps({"worktree_root": str(repo_root)}), encoding="utf-8"
        )
        _completed, payload = self.cli(
            "create", "codex/repo-policy", "--dry-run", "--min-free-gib", "0", "--json"
        )
        self.assertEqual(payload["path_policy_source"], "repository")
        self.assertEqual(Path(payload["workspace_root"]), repo_root.resolve())

        cli_root = self.base / "cli-root"
        _completed, payload = self.cli(
            "create", "codex/cli-policy", "--root", str(cli_root),
            "--dry-run", "--min-free-gib", "0", "--json"
        )
        self.assertEqual(payload["path_policy_source"], "cli")
        self.assertEqual(Path(payload["workspace_root"]), cli_root.resolve())

    def test_create_registers_worktree_and_artifact_root(self):
        completed, payload = self.cli(
            "create", "codex/feature-two", "--task", "T-42", "--min-free-gib", "0", "--json"
        )
        self.assertEqual(completed.returncode, 0)
        target = Path(payload["worktree_path"])
        self.assertTrue(target.is_dir())
        self.assertTrue(Path(payload["artifact_root"]).is_dir())
        self.assertTrue(Path(payload["registry_path"]).is_file())

        branch = run(["git", "branch", "--show-current"], target).stdout.strip()
        self.assertEqual(branch, "codex/feature-two")
        _completed, listing = self.cli("list", "--all", "--json")
        self.assertEqual(listing["worktrees"][0]["task"], "T-42")

        doctor_completed, doctor = self.cli("doctor", str(target), "--min-free-gib", "0", "--json")
        self.assertEqual(doctor_completed.returncode, 0)
        self.assertEqual(doctor["status"], "healthy")
        self.assertTrue(doctor["repo"]["linked_worktree"])

    def test_create_refuses_target_inside_repository(self):
        completed, payload = self.cli(
            "create",
            "codex/unsafe",
            "--root",
            str(self.repo / ".worktrees"),
            "--min-free-gib",
            "0",
            "--json",
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error_code"], "target_inside_repository")

    def test_create_reports_actionable_base_and_target_collision_codes(self):
        completed, payload = self.cli(
            "create", "codex/missing-base", "--base", "does-not-exist", "--json", check=False
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error_code"], "base_not_found")

        target_root = self.base / "chosen"
        target = target_root / "demo" / "codex-target-exists"
        target.mkdir(parents=True)
        completed, payload = self.cli(
            "create", "codex/target-exists", "--root", str(target_root), "--json", check=False
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error_code"], "target_exists")

    def test_existing_branch_must_equal_exact_requested_base(self):
        run(["git", "branch", "codex/existing"], self.repo)
        (self.repo / "second").write_text("second\n", encoding="utf-8")
        run(["git", "add", "second"], self.repo)
        run(["git", "commit", "-m", "second"], self.repo)
        completed, payload = self.cli(
            "create", "codex/existing", "--base", "HEAD", "--json", check=False
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error_code"], "branch_base_mismatch")

    def test_create_plans_but_does_not_run_setup_by_default(self):
        (self.repo / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
        (self.repo / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
        run(["git", "add", "package.json", "package-lock.json"], self.repo)
        run(["git", "commit", "-m", "add node project"], self.repo)
        _completed, payload = self.cli(
            "create", "codex/node", "--min-free-gib", "0", "--json"
        )
        self.assertEqual(payload["setup_results"][0]["status"], "planned")
        self.assertFalse((Path(payload["worktree_path"]) / "node_modules").exists())

    def test_adapter_guidance_separates_shared_cache_and_writable_state(self):
        (self.repo / "package.json").write_text('{"name":"demo"}\n', encoding="utf-8")
        (self.repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")
        (self.repo / "compose.yml").write_text("services: {}\n", encoding="utf-8")
        _completed, payload = self.cli(
            "create", "codex/adapters", "--dry-run", "--min-free-gib", "0", "--json"
        )
        by_name = {item["adapter"]: item for item in payload["adapter_guidance"]}
        self.assertIn("node_modules", by_name["node"]["isolated"])
        self.assertIn(".venv", by_name["uv"]["isolated"])
        self.assertIn("Compose", by_name["docker"]["isolated"])
        self.assertIn("checkpoints", by_name["ml_artifacts"]["isolated"])
        for key in ("NPM_CONFIG_CACHE", "PNPM_STORE_DIR", "PIP_CACHE_DIR", "UV_CACHE_DIR",
                    "CONDA_PKGS_DIRS", "GOMODCACHE", "GOCACHE", "CARGO_HOME", "HF_HOME",
                    "COMPOSE_PROJECT_NAME", "AGENT_WT_ARTIFACT_ROOT"):
            self.assertIn(key, payload["environment"])

    def test_doctor_warns_about_large_source_tree_artifact(self):
        artifact = self.repo / "wandb"
        artifact.mkdir()
        (artifact / "run.bin").write_bytes(b"x" * (2 * 1024 * 1024))
        completed, payload = self.cli(
            "doctor", "--artifact-warning-mib", "1", "--min-free-gib", "0", "--json", check=False
        )
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(payload["status"], "warning")
        self.assertIn("wandb", " ".join(payload["warnings"]))

    def test_doctor_reports_bounded_lower_bound_scan(self):
        dependency = self.repo / "node_modules" / "pkg"
        dependency.mkdir(parents=True)
        (dependency / "value.bin").write_bytes(b"x" * 1024)
        completed, payload = self.cli(
            "doctor", "--scan-files", "1", "--scan-seconds", "60",
            "--min-free-gib", "0", "--json", check=False
        )
        self.assertEqual(completed.returncode, 1)
        self.assertTrue(payload["scan"]["truncated"])
        self.assertIn("lower bounds", payload["scan"]["size_semantics"])
        self.assertIn("lower bounds", " ".join(payload["warnings"]))

    @unittest.skipIf(os.name == "nt", "ordinary Win11 users cannot create directory symlinks")
    def test_doctor_warns_for_symlinked_conda_environment(self):
        environment = self.base / "shared-env"
        (environment / "conda-meta").mkdir(parents=True)
        (self.repo / "training-env").symlink_to(environment, target_is_directory=True)
        completed, payload = self.cli(
            "doctor", "--min-free-gib", "0", "--json", check=False
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("Conda environment", " ".join(payload["warnings"]))

    def test_cli_has_no_remove_command(self):
        completed = run(
            [sys.executable, str(SCRIPT), "-C", str(self.repo), "remove"],
            self.repo,
            env=self.env,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("invalid choice", completed.stderr)

    def test_cli_has_only_five_commands_and_no_dependency_execution_flag(self):
        help_result = run([sys.executable, str(SCRIPT), "--help"], self.repo, env=self.env)
        for command in ("inspect", "decide", "create", "list", "doctor"):
            self.assertIn(command, help_result.stdout)
        for excluded in ("remove", "prune", "merge", "push", "delete-branch"):
            self.assertNotIn(f"  {excluded}", help_result.stdout)
        create_help = run(
            [sys.executable, str(SCRIPT), "create", "--help"], self.repo, env=self.env
        )
        self.assertNotIn("--setup", create_help.stdout)

    def test_windows_state_path_and_override_contract(self):
        home = Path("C:/Users/Alex")
        state = agent_wt.default_state_home(
            platform_name="nt",
            environ={"LOCALAPPDATA": "C:/Users/Alex/AppData/Local"},
            home=home,
        )
        self.assertEqual(str(state).replace("\\", "/"), "C:/Users/Alex/AppData/Local/agent-wt/state")
        override = self.base / "override-state"
        self.env["AGENT_WT_STATE_HOME"] = str(override)
        _completed, payload = self.cli("list", "--all", "--json")
        self.assertEqual(Path(payload["registry_path"]), (override / "registry.json").resolve())

    def test_windows_path_containment_is_case_insensitive_and_drive_aware(self):
        self.assertTrue(agent_wt.is_within(
            Path("C:/Code/Repo/child"), Path("c:/code/repo"), platform_name="nt"
        ))
        self.assertFalse(agent_wt.is_within(
            Path("D:/Code/Repo"), Path("C:/Code/Repo"), platform_name="nt"
        ))

    def test_allocated_size_has_portable_fallback(self):
        value, kind = agent_wt.stat_allocated_bytes(SimpleNamespace(st_size=1234))
        self.assertEqual((value, kind), (1234, "apparent_fallback"))
        value, kind = agent_wt.stat_allocated_bytes(SimpleNamespace(st_size=9999, st_blocks=4))
        self.assertEqual((value, kind), (2048, "allocated"))

    def test_registry_lock_fails_closed_and_atomic_replace_leaves_valid_json(self):
        state = self.base / "locking-state"
        state.mkdir()
        with agent_wt.registry_lock(state):
            with self.assertRaises(agent_wt.AgentWtError) as raised:
                with agent_wt.registry_lock(state, timeout_seconds=0):
                    pass
            self.assertEqual(raised.exception.code, "registry_lock_timeout")
        with mock.patch.dict(os.environ, {"AGENT_WT_STATE_HOME": str(state)}):
            path = agent_wt.save_registry({"version": 1, "worktrees": [{"branch": "one"}]})
            agent_wt.save_registry({"version": 1, "worktrees": [{"branch": "two"}]})
        self.assertEqual(json.loads(path.read_text())["worktrees"][0]["branch"], "two")
        self.assertEqual(list(state.glob("tmp*")), [])

    def test_subprocess_arguments_remain_an_argv_vector(self):
        completed = subprocess.CompletedProcess([], 0, "ok", "")
        with mock.patch.object(agent_wt.subprocess, "run", return_value=completed) as called:
            agent_wt.run(["git", "show", "branch with spaces"], cwd=self.repo)
        self.assertEqual(called.call_args.args[0], ["git", "show", "branch with spaces"])


if __name__ == "__main__":
    unittest.main()
