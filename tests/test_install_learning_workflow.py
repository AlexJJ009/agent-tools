"""Isolated profile tests for the bounded learning workflow installer."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/install_learning_workflow.py"
SPEC = importlib.util.spec_from_file_location("install_learning_workflow", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "profile"
        self.home.mkdir()
        self.repo = self.base / "source"
        self.repo.mkdir()
        (self.repo / "scripts").mkdir()
        shutil.copy2(SCRIPT.parent / "codex_target_guard.py", self.repo / "scripts/codex_target_guard.py")
        package = self.repo / "learning_workflow"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "__main__.py").write_text("print('learning workflow help')\n")
        (package / "hooks.py").write_text("print('{}')\n")
        for name in installer.SKILLS:
            path = self.repo / "skills" / name
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
        contract = "W1: readable writing.\n"
        for path in (self.repo / "shared/writing/reader-facing-contract.md",
                     self.repo / "skills/work-report/references/writing-contract.md",
                     self.repo / "skills/academic-writing/references/writing-contract.md"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contract)
        adapter = self.repo / "project_adapters/read_papers"
        (adapter / "read-paper").mkdir(parents=True)
        (adapter / "config.example.json").write_text("{}\n")
        (adapter / "read-paper/SKILL.md").write_text("read paper\n")
        self.patch_root = patch.object(installer, "ROOT", self.repo)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        self.old = self.base / "old-suite"
        for name in installer.OLD_SKILLS:
            target = self.old / "skills" / name
            target.mkdir(parents=True)
            for location in (self.home / ".agents/skills", self.home / ".claude/skills"):
                location.mkdir(parents=True, exist_ok=True)
                (location / name).symlink_to(target, target_is_directory=True)
        self.foreign = {"description": "kept", "custom": {"new": 1}, "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": "echo foreign"}]}]}}
        path = self.home / ".codex/hooks.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self.foreign))
        self.papers = self.base / "ReadPapers"
        self.papers.mkdir()

    def test_install_relocation_and_scoped_rollback(self) -> None:
        report = installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                                   with_hooks=True)
        self.assertEqual(report["status"], "installed")
        self.assertEqual(installer.check(self.home)["status"], "pass")
        bundle = self.home / ".local/lib/agent-tools/learning-workflow"
        self.assertEqual((bundle / "shared/writing/reader-facing-contract.md").read_text(),
                         (bundle / "skills/work-report/references/writing-contract.md").read_text())
        self.assertTrue((self.papers / ".agents/skills/read-paper").is_symlink())
        self.assertTrue((self.papers / ".agents/skills/read-paper/../config.example.json").is_file())
        # The installed commands and skills continue to resolve after checkout relocation.
        self.repo.rename(self.base / "moved-source")
        installer.ROOT = self.base / "moved-source"
        self.assertEqual(installer.check(self.home)["status"], "pass")
        hooks_path = self.home / ".codex/hooks.json"
        data = json.loads(hooks_path.read_text())
        data["custom"]["later"] = True
        data["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "echo later"}]})
        hooks_path.write_text(json.dumps(data))
        self.assertEqual(installer.rollback(self.home)["status"], "rolled_back")
        after = json.loads(hooks_path.read_text())
        self.assertEqual(after["description"], "kept")
        self.assertTrue(after["custom"]["later"])
        self.assertEqual(len(after["hooks"]["Stop"]), 2)
        self.assertEqual(after["hooks"]["Stop"][0], self.foreign["hooks"]["Stop"][0])
        for name in installer.OLD_SKILLS:
            self.assertEqual((self.home / ".agents/skills" / name).resolve(), self.old / "skills" / name)
        self.assertFalse((self.home / ".agents/skills/academic-writing").exists())
        self.assertFalse((self.papers / ".agents/skills/read-paper").exists())

    def test_legacy_teaching_double_registration_migrates_and_restores(self):
        from learning_workflow import hook_registration as reg
        directory=self.papers/'.codex'; directory.mkdir()
        handler={'type':'command','command':'/usr/bin/env python3 .codex/teaching_stop_filter.py'}
        groups=[{'hooks':[handler]}]
        (directory/'hooks.json').write_text(json.dumps({'hooks':{'Stop':groups}}))
        (directory/'config.toml').write_text('[features]\nhooks = true\n[hooks]\nStop = '+reg.inline(groups)+'\n')
        installer.install(self.home,legacy_root=self.old,read_papers_root=self.papers,with_hooks=True)
        self.assertEqual(reg.prepare(self.home,self.papers),[])
        self.assertEqual(installer.check(self.home)['status'],'pass')
        installer.rollback(self.home)
        self.assertEqual(len(reg.prepare(self.home,self.papers)),2)

    def test_actual_cli_from_unrelated_cwd_with_global_legacy_hooks(self):
        from learning_workflow import hook_registration as reg
        isolated_home=self.base/'cli-profile'; directory=isolated_home/'.codex'; directory.mkdir(parents=True)
        handler={'type':'command','command':'python3 .codex/teaching_stop_filter.py'}
        groups=[{'hooks':[handler]}]
        (directory/'hooks.json').write_text(json.dumps({'hooks':{'Stop':groups}}))
        (directory/'config.toml').write_text('[hooks]\nStop = '+reg.inline(groups)+'\n')
        env=dict(os.environ,HOME=str(isolated_home))
        env.pop('PYTHONPATH',None)
        for flags in (['--with-hooks'],['--check'],['--rollback']):
            run=subprocess.run([sys.executable,str(SCRIPT),*flags],cwd=self.base,env=env,
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr+run.stdout)
        self.assertEqual(len(reg.prepare(isolated_home)),2)

    def test_unrecognized_link_is_preserved_before_writes(self) -> None:
        link = self.home / ".agents/skills/teaching-reconstruction"
        link.unlink()
        link.symlink_to(self.base / "foreign")
        with self.assertRaisesRegex(installer.InstallError, "unmanaged target preserved"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=False)
        self.assertEqual(link.readlink(), self.base / "foreign")
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_changed_payload_blocks_rollback(self) -> None:
        installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=False)
        bundle = self.home / ".local/lib/agent-tools/learning-workflow"
        (bundle / "skills/task-routing/SKILL.md").write_text("later user edit\n")
        with self.assertRaisesRegex(installer.InstallError, "bundle changed"):
            installer.rollback(self.home)
        self.assertTrue(bundle.exists())

    def test_core_learning_alias_migrates_relocates_and_rolls_back(self) -> None:
        source = self.base / "agent-core/skills/knowledge-deposition-doc"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("legacy teaching rules\n")
        alias = self.home / ".codex/skills/knowledge-deposition-doc"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(os.path.relpath(source, alias.parent))
        claude_alias = self.home / ".claude/skills/knowledge-deposition-doc"
        claude_alias.symlink_to(os.path.relpath(source, claude_alias.parent))
        original = os.readlink(alias)
        installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                          legacy_knowledge_source=source, with_hooks=False)
        bundle = self.home / ".local/lib/agent-tools/learning-workflow"
        self.assertEqual(alias.resolve(), bundle / "skills/knowledge-deposition-doc")
        self.assertFalse((self.home / ".agents/skills/knowledge-deposition-doc").exists())
        self.assertEqual(os.readlink(claude_alias), original)
        self.assertEqual((source / "SKILL.md").read_text(), "legacy teaching rules\n")
        self.repo.rename(self.base / "moved-source")
        installer.ROOT = self.base / "moved-source"
        self.assertEqual(installer.check(self.home)["status"], "pass")
        self.assertTrue((alias / "SKILL.md").is_file())
        installer.rollback(self.home)
        self.assertEqual(os.readlink(alias), original)
        self.assertEqual(os.readlink(claude_alias), original)

    def test_core_alias_replacement_requires_exact_explicit_source(self) -> None:
        source = self.base / "agent-core/skills/knowledge-deposition-doc"
        source.mkdir(parents=True)
        alias = self.home / ".codex/skills/knowledge-deposition-doc"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(source)
        for supplied in (None, self.base / "another-core/skills/knowledge-deposition-doc"):
            with self.subTest(source=supplied):
                with self.assertRaisesRegex(installer.InstallError, "unmanaged target preserved"):
                    installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                                      legacy_knowledge_source=supplied, with_hooks=False)
                self.assertEqual(alias.resolve(), source)
                self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_duplicate_core_alias_is_preserved_before_install(self) -> None:
        alias = self.home / ".agents/skills/knowledge-deposition-doc"
        alias.mkdir()
        (alias / "SKILL.md").write_text("user-owned rules\n")
        with self.assertRaisesRegex(installer.InstallError, "duplicate knowledge-deposition-doc"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                              with_hooks=False)
        self.assertEqual((alias / "SKILL.md").read_text(), "user-owned rules\n")
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_check_detects_new_duplicate_without_removing_it(self) -> None:
        installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                          with_hooks=False)
        alias = self.home / ".agents/skills/knowledge-deposition-doc"
        alias.symlink_to(self.base / "stale-core-source")
        with self.assertRaisesRegex(installer.InstallError, "duplicate knowledge-deposition-doc"):
            installer.check(self.home)
        self.assertTrue(alias.is_symlink())
        installer.rollback(self.home)
        self.assertTrue(alias.is_symlink())

    def test_changed_managed_hook_blocks_rollback_without_removing_settings(self) -> None:
        installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=True)
        path = self.home / ".codex/hooks.json"
        data = json.loads(path.read_text())
        data["hooks"]["Stop"][-1]["hooks"][0]["timeout"] = 45
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(installer.InstallError, "managed hook changed"):
            installer.rollback(self.home)
        self.assertEqual(json.loads(path.read_text()), data)
        self.assertTrue((self.home / ".agents/skills/teaching-reconstruction").is_symlink())

    def test_existing_project_adapter_directory_is_restored_byte_for_byte(self) -> None:
        old_adapter = self.papers / ".agents/skills/read-paper"
        old_adapter.mkdir(parents=True)
        (old_adapter / "SKILL.md").write_bytes(b"legacy read paper\n")
        (old_adapter / "private-note.txt").write_bytes(b"keep exactly\x00\n")
        before = installer.digest(old_adapter)
        installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                          legacy_read_paper_dir=old_adapter, with_hooks=False)
        self.assertTrue(old_adapter.is_symlink())
        self.assertEqual(installer.rollback(self.home)["status"], "rolled_back")
        self.assertTrue(old_adapter.is_dir())
        self.assertFalse(old_adapter.is_symlink())
        self.assertEqual(installer.digest(old_adapter), before)

    def test_launcher_and_exact_global_read_paper_links_are_managed(self) -> None:
        source = self.base / "old-read-paper"
        source.mkdir()
        (source / "SKILL.md").write_text("old broad scope\n")
        aliases = []
        for base in (self.home / ".codex/skills", self.home / ".agents/skills"):
            base.mkdir(parents=True, exist_ok=True)
            alias = base / "read-paper"
            alias.symlink_to(source, target_is_directory=True)
            aliases.append(alias)
        with self.assertRaisesRegex(installer.InstallError, "explicit legacy source"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                              with_hooks=False)
        with self.assertRaisesRegex(installer.InstallError, "requires an explicit ReadPapers"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                              legacy_global_read_paper_source=source, with_hooks=False)
        report = installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                                   legacy_global_read_paper_source=source, with_hooks=False)
        self.assertEqual(report["global_read_paper_aliases_deactivated"], 2)
        launcher = self.home / ".local/bin/learning-workflow"
        self.assertTrue(launcher.is_symlink())
        self.assertEqual(launcher.resolve(), self.home / ".local/lib/agent-tools/learning-workflow/bin/learning-workflow")
        self.assertTrue(all(not alias.exists() for alias in aliases))
        self.assertEqual(installer.check(self.home)["status"], "pass")
        installer.rollback(self.home)
        self.assertFalse(launcher.exists())
        self.assertTrue(all(alias.is_symlink() and alias.resolve() == source for alias in aliases))

    def test_check_fails_when_requested_hooks_are_missing(self) -> None:
        installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=True)
        path = self.home / ".codex/hooks.json"
        data = json.loads(path.read_text())
        data["hooks"]["Stop"] = self.foreign["hooks"]["Stop"]
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(installer.InstallError, "hook groups are missing"):
            installer.check(self.home)

    def test_failed_new_symlink_restores_old_link(self) -> None:
        old_link = self.home / ".agents/skills/teaching-reconstruction"
        old_text = old_link.readlink()
        original = Path.symlink_to
        failed = False

        def fail_once(path: Path, target: Path, target_is_directory: bool = False) -> None:
            nonlocal failed
            if path == old_link and not failed and "learning-workflow" in str(target):
                failed = True
                raise OSError("injected symlink failure")
            original(path, target, target_is_directory=target_is_directory)

        with patch.object(Path, "symlink_to", fail_once):
            with self.assertRaisesRegex(OSError, "injected symlink failure"):
                installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                                  with_hooks=False)
        self.assertTrue(failed)
        self.assertTrue(old_link.is_symlink())
        self.assertEqual(old_link.readlink(), old_text)
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_partial_bundle_copy_is_removed(self) -> None:
        bundle = self.home / ".local/lib/agent-tools/learning-workflow"
        original = installer.layout.sync_tree

        def fail_bundle_copy(dst: Path, *args: object, **kwargs: object) -> dict:
            if Path(dst) == bundle:
                bundle.mkdir(parents=True)
                (bundle / "partial").write_text("incomplete")
                raise OSError("injected copy failure")
            return original(dst, *args, **kwargs)

        with patch.object(installer.layout, "sync_tree", fail_bundle_copy):
            with self.assertRaisesRegex(OSError, "injected copy failure"):
                installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                                  with_hooks=False)
        self.assertFalse(bundle.exists())
        self.assertTrue((self.home / ".agents/skills/teaching-reconstruction").is_symlink())

    def test_manifest_write_failure_removes_only_new_hook_groups(self) -> None:
        manifest = self.home / ".local/state/learning-workflow/install.json"
        original = installer.atomic_json

        def fail_manifest(path: Path, value: dict) -> None:
            if path == manifest:
                raise OSError("injected manifest write failure")
            original(path, value)

        with patch.object(installer, "atomic_json", fail_manifest):
            with self.assertRaisesRegex(OSError, "injected manifest write failure"):
                installer.install(self.home, legacy_root=self.old, read_papers_root=None,
                                  with_hooks=True)
        self.assertEqual(json.loads((self.home / ".codex/hooks.json").read_text()), self.foreign)
        self.assertFalse(manifest.exists())
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())
        self.assertEqual((self.home / ".agents/skills/teaching-reconstruction").resolve(),
                         self.old / "skills/teaching-reconstruction")

    def test_codex_only_preserves_shared_claude_roots(self) -> None:
        shared = self.base / "shared-claude"
        (shared / "skills/read-paper").mkdir(parents=True)
        (shared / "skills/read-paper/SKILL.md").write_text("unrelated shared adapter\n")
        (self.papers / ".claude").symlink_to(shared, target_is_directory=True)
        global_source = self.base / "old-read-paper"
        global_source.mkdir()
        (global_source / "SKILL.md").write_text("old broad scope\n")
        (self.home / ".codex/skills").mkdir(parents=True)
        (self.home / ".codex/skills/read-paper").symlink_to(global_source)
        # A foreign Claude alias must not even be considered for replacement.
        (self.home / ".claude/skills/read-paper").symlink_to(shared / "skills/read-paper")
        before_shared = installer.digest(shared)
        before_claude = installer.digest(self.home / ".claude")
        report = installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                                   legacy_global_read_paper_source=global_source, with_hooks=False)
        self.assertEqual(report["client"], "codex")
        self.assertTrue((self.papers / ".agents/skills/read-paper/SKILL.md").is_file())
        self.assertFalse((self.home / ".codex/skills/read-paper").exists())
        self.assertEqual(installer.digest(shared), before_shared)
        self.assertEqual(installer.digest(self.home / ".claude"), before_claude)
        self.assertEqual(installer.check(self.home)["status"], "pass")
        installer.rollback(self.home)
        self.assertEqual(installer.digest(shared), before_shared)
        self.assertEqual(installer.digest(self.home / ".claude"), before_claude)
        self.assertEqual((self.home / ".codex/skills/read-paper").resolve(), global_source)

    def test_codex_alias_into_claude_is_rejected_before_writes(self) -> None:
        # A parent inside the allowed project can still belong to another client.
        claude = self.papers / ".claude"
        claude.mkdir()
        (self.papers / ".agents").symlink_to(claude, target_is_directory=True)
        before = installer.digest(claude)
        with self.assertRaisesRegex(installer.InstallError, "Claude-owned"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers, with_hooks=False)
        self.assertEqual(installer.digest(claude), before)
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_shared_agents_parent_is_still_rejected_before_writes(self) -> None:
        shared = self.base / "foreign-agents"
        shared.mkdir()
        (self.papers / ".agents").symlink_to(shared, target_is_directory=True)
        with self.assertRaisesRegex(installer.InstallError, "skill destination escapes"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers, with_hooks=False)
        self.assertEqual(list(shared.iterdir()), [])
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_codex_alias_into_renamed_claude_root_is_rejected(self) -> None:
        shared = self.papers / "shared-client-state"
        shared.mkdir()
        (self.papers / ".claude").symlink_to(shared)
        (self.papers / ".agents").symlink_to(shared)
        with self.assertRaisesRegex(installer.InstallError, "Claude-owned"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers, with_hooks=False)
        self.assertEqual(list(shared.iterdir()), [])

    def make_project_bridge(self) -> tuple[Path, Path]:
        source = self.base / "shared-project-skills"
        for name in ("read-paper", "other-skill"):
            (source / name).mkdir(parents=True)
            (source / name / "SKILL.md").write_text(name)
        bridge = self.papers / ".codex/skills"
        bridge.parent.mkdir()
        bridge.symlink_to(source, target_is_directory=True)
        return bridge, source

    def test_project_bridge_split_and_exact_rollback(self) -> None:
        bridge, source = self.make_project_bridge()
        before = installer.digest(source)
        with self.assertRaisesRegex(installer.InstallError, "exact --legacy-project"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers, with_hooks=False)
        installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                          legacy_project_skills_source=source, with_hooks=False)
        self.assertFalse(bridge.is_symlink())
        self.assertFalse((bridge / "read-paper").exists())
        self.assertEqual((bridge / "other-skill").readlink(), source / "other-skill")
        self.assertEqual(installer.check(self.home)["status"], "pass")
        # An empty added directory must block rollback before any managed removal.
        (bridge / "later-user-content").mkdir()
        with self.assertRaisesRegex(installer.InstallError, "bridge changed"):
            installer.rollback(self.home)
        self.assertTrue((self.papers / ".agents/skills/read-paper").is_symlink())
        (bridge / "later-user-content").rmdir()
        installer.rollback(self.home)
        self.assertEqual(bridge.readlink(), source)
        self.assertEqual(installer.digest(source), before)

    def test_manifest_failure_restores_split_project_bridge(self) -> None:
        bridge, source = self.make_project_bridge()
        original = installer.atomic_json
        def fail_manifest(path: Path, value: dict) -> None:
            if path.name == "install.json":
                raise OSError("injected manifest failure after bridge split")
            original(path, value)
        with patch.object(installer, "atomic_json", fail_manifest):
            with self.assertRaisesRegex(OSError, "after bridge split"):
                installer.install(self.home, legacy_root=self.old, read_papers_root=self.papers,
                                  legacy_project_skills_source=source, with_hooks=False)
        self.assertEqual(bridge.readlink(), source)
        self.assertFalse((self.papers / ".agents/skills/read-paper").exists())
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())

    def test_target_guard_rejects_cross_platform_config_before_writes(self) -> None:
        (self.home / ".codex/config.toml").write_text('note = "C:\\\\Users\\\\other"\n')
        with self.assertRaisesRegex(installer.InstallError, "target guard rejected"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=False)
        self.assertFalse((self.home / ".local/lib/agent-tools/learning-workflow").exists())


if __name__ == "__main__":
    unittest.main()
