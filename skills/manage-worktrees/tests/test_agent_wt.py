import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
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

    def test_decide_defaults_to_branch_for_clean_single_task(self):
        _completed, payload = self.cli("decide", "--json")
        self.assertEqual(payload["recommendation"], "branch")

    def test_decide_uses_worktree_for_dirty_or_parallel_context(self):
        (self.repo / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        _completed, payload = self.cli("decide", "--json")
        self.assertEqual(payload["recommendation"], "worktree")
        self.assertIn("uncommitted", " ".join(payload["reasons"]))

        (self.repo / "scratch.txt").unlink()
        _completed, payload = self.cli("decide", "--parallel", "--json")
        self.assertEqual(payload["recommendation"], "worktree")

    def test_decide_rejects_worktree_as_untrusted_user_boundary(self):
        _completed, payload = self.cli("decide", "--untrusted-users", "--json")
        self.assertEqual(payload["recommendation"], "separate-clone")

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
        target = Path(payload["worktree_path"])
        self.assertEqual(target, self.repo.parent / "_worktrees" / "demo" / "codex-feature-one")
        self.assertFalse(target.exists())
        self.assertFalse(agent_wt.is_within(target, self.repo))

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
        self.assertIn("inside repository", payload["error"])

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

    def test_cli_has_no_remove_command(self):
        completed = run(
            [sys.executable, str(SCRIPT), "-C", str(self.repo), "remove"],
            self.repo,
            env=self.env,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("invalid choice", completed.stderr)


if __name__ == "__main__":
    unittest.main()
