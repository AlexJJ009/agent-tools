import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install_agent_workflow.py"
spec = importlib.util.spec_from_file_location("install_agent_workflow", SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class AgentWorkflowInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.repo = self.base / "repo"
        self.skills = (
            "intent-to-contract",
            "infra-verification",
            "cleaner",
            "acceptance-gate",
            "reviewer-brief",
        )
        for skill in self.skills:
            root = self.repo / "skills" / skill
            (root / "agents").mkdir(parents=True)
            (root / "templates").mkdir()
            (root / "references/licenses").mkdir(parents=True)
            (root / "SKILL.md").write_text(f"---\nname: {skill}\ndescription: fixture\n---\n", encoding="utf-8")
            (root / "agents/openai.yaml").write_text("interface:\n  display_name: fixture\n", encoding="utf-8")
            (root / "templates/template.txt").write_text(skill, encoding="utf-8")
            (root / "references/licenses/spec-kit-MIT.txt").write_text("spec license", encoding="utf-8")
            (root / "references/licenses/superpowers-MIT.txt").write_text("superpowers license", encoding="utf-8")
        runtime = self.repo / "agent_workflow"
        runtime.mkdir()
        (runtime / "__init__.py").write_text("", encoding="utf-8")
        (runtime / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts/codex_target_guard.py").write_text("# fixture\n", encoding="utf-8")
        self.calls = []
        self.guard_ok = True
        self.runtime_ok = True
        self.installed_launcher_ok = True

    def run_command(self, args, **kwargs):
        self.calls.append((args, kwargs))
        text = " ".join(str(arg) for arg in args)
        if "codex_target_guard.py" in text:
            code = 0 if self.guard_ok else 1
            return SimpleNamespace(returncode=code, stdout="{}", stderr="guard refused" if code else "")
        if "-m agent_workflow.cli" in text:
            code = 0 if self.runtime_ok else 1
            return SimpleNamespace(returncode=code, stdout="help", stderr="runtime refused" if code else "")
        if args and str(args[0]).endswith("/agent-workflow"):
            code = 0 if self.installed_launcher_ok else 1
            return SimpleNamespace(returncode=code, stdout="help", stderr="launcher refused" if code else "")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def install(self, args=()):
        with patch.object(installer, "ROOT", self.repo), patch.object(Path, "home", return_value=self.home), \
             patch.object(installer.platform, "system", return_value="Linux"), \
             patch.object(installer.subprocess, "run", side_effect=self.run_command), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return installer.main(list(args))

    def test_guard_failure_writes_nothing(self):
        self.guard_ok = False
        self.assertEqual(self.install(), 1)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.home / ".local").exists())

    def test_missing_runtime_refuses_install(self):
        (self.repo / "agent_workflow").rename(self.repo / "agent_workflow.missing")
        self.assertEqual(self.install(), 1)
        self.assertFalse((self.home / ".agents").exists())

    def test_runtime_preflight_failure_writes_nothing(self):
        self.runtime_ok = False
        self.assertEqual(self.install(), 1)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.home / ".local/bin/agent-workflow").exists())

    def test_install_and_check_readback(self):
        self.assertEqual(self.install(), 0)
        for skill in self.skills:
            target = self.home / ".agents/skills" / skill
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertEqual(installer.files(target), installer.files(self.repo / "skills" / skill))
        self.assertTrue((self.home / ".local/share/agent-workflow/agent_workflow/cli.py").is_file())
        self.assertTrue((self.home / ".local/bin/agent-workflow").is_file())
        self.assertEqual(self.install(["--check"]), 0)
        (self.home / ".agents/skills/cleaner/SKILL.md").write_text("changed", encoding="utf-8")
        self.assertEqual(self.install(["--check"]), 1)

    def test_runtime_help_uses_safe_path_and_installed_cwd(self):
        self.assertEqual(self.install(), 0)
        preflight = [call for call in self.calls if "-m agent_workflow.cli" in " ".join(str(x) for x in call[0])]
        self.assertTrue(any("-P" in call[0] and call[1].get("cwd", "").endswith("/agent-workflow") for call in preflight))
        launcher_calls = [call for call in self.calls if call[0] and str(call[0][0]).endswith("/agent-workflow")]
        self.assertTrue(any(call[1].get("cwd") == str(self.home / ".local/share/agent-workflow") for call in launcher_calls))
        launcher_text = (self.home / ".local/bin/agent-workflow").read_text(encoding="utf-8")
        self.assertIn(" -P -m agent_workflow.cli", launcher_text)

    def test_unmanaged_skill_is_preserved(self):
        target = self.home / ".agents/skills/cleaner"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("personal", encoding="utf-8")
        self.assertEqual(self.install(), 1)
        self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), "personal")

    def test_duplicate_codex_skill_is_rejected(self):
        duplicate = self.home / ".codex/skills/acceptance-gate"
        duplicate.mkdir(parents=True)
        (duplicate / "SKILL.md").write_text("legacy", encoding="utf-8")
        self.assertEqual(self.install(), 1)
        self.assertEqual((duplicate / "SKILL.md").read_text(encoding="utf-8"), "legacy")

    def test_unmanaged_runtime_is_preserved(self):
        runtime = self.home / ".local/share/agent-workflow"
        runtime.mkdir(parents=True)
        (runtime / "personal.txt").write_text("keep", encoding="utf-8")
        self.assertEqual(self.install(), 1)
        self.assertEqual((runtime / "personal.txt").read_text(encoding="utf-8"), "keep")

    def test_modified_managed_launcher_is_rejected_before_overwrite(self):
        self.assertEqual(self.install(), 0)
        launcher = self.home / ".local/bin/agent-workflow"
        launcher.write_text("#!/usr/bin/env sh\nexec /bin/false\n", encoding="utf-8")
        self.assertEqual(self.install(), 1)
        self.assertEqual(launcher.read_text(encoding="utf-8"), "#!/usr/bin/env sh\nexec /bin/false\n")

    def test_prior_managed_launcher_can_be_upgraded(self):
        self.assertEqual(self.install(), 0)
        runtime = self.home / ".local/share/agent-workflow"
        launcher = self.home / ".local/bin/agent-workflow"
        prior = next(iter(installer.prior_expected_launchers(runtime)))
        launcher.write_text(prior, encoding="utf-8")
        self.assertEqual(self.install(), 0)
        self.assertEqual(launcher.read_text(encoding="utf-8"), installer.expected_launcher(runtime))

    def test_failed_final_launcher_validation_restores_previous_install(self):
        self.assertEqual(self.install(), 0)
        runtime = self.home / ".local/share/agent-workflow"
        before_runtime = installer.files(runtime / "agent_workflow")
        launcher = self.home / ".local/bin/agent-workflow"
        before_launcher = launcher.read_text(encoding="utf-8")
        (self.repo / "agent_workflow/cli.py").write_text("changed runtime\n", encoding="utf-8")
        self.installed_launcher_ok = False
        self.assertEqual(self.install(), 1)
        self.assertEqual(installer.files(runtime / "agent_workflow"), before_runtime)
        self.assertEqual(launcher.read_text(encoding="utf-8"), before_launcher)

    def test_failed_first_final_validation_removes_new_launcher(self):
        self.installed_launcher_ok = False
        self.assertEqual(self.install(), 1)
        self.assertFalse((self.home / ".local/bin/agent-workflow").exists())
        self.assertFalse((self.home / ".agents/skills/cleaner").exists())

    def test_symlink_parent_outside_profile_is_rejected(self):
        external = self.base / "external"
        external.mkdir()
        (self.home / ".agents").symlink_to(external, target_is_directory=True)
        self.assertEqual(self.install(), 1)
        self.assertEqual(list(external.iterdir()), [])

    def test_check_only_does_not_create_missing_install(self):
        self.assertEqual(self.install(["--check"]), 1)
        self.assertFalse((self.home / ".agents").exists())


if __name__ == "__main__":
    unittest.main()
