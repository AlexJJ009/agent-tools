"""Isolated profile tests for the bounded learning workflow installer."""

from __future__ import annotations

import importlib.util
import json
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
                     self.repo / "skills/work-report/references/writing-contract.md"):
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
        bundle = self.home / ".local/share/agent-tools/learning-workflow"
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

    def test_unrecognized_link_is_preserved_before_writes(self) -> None:
        link = self.home / ".agents/skills/teaching-reconstruction"
        link.unlink()
        link.symlink_to(self.base / "foreign")
        with self.assertRaisesRegex(installer.InstallError, "unmanaged target preserved"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=False)
        self.assertEqual(link.readlink(), self.base / "foreign")
        self.assertFalse((self.home / ".local/share/agent-tools/learning-workflow").exists())

    def test_changed_payload_blocks_rollback(self) -> None:
        installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=False)
        bundle = self.home / ".local/share/agent-tools/learning-workflow"
        (bundle / "skills/task-routing/SKILL.md").write_text("later user edit\n")
        with self.assertRaisesRegex(installer.InstallError, "bundle changed"):
            installer.rollback(self.home)
        self.assertTrue(bundle.exists())

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
        old_adapter = self.papers / ".claude/skills/read-paper"
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
        for base in (self.home / ".codex/skills", self.home / ".claude/skills"):
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
        self.assertEqual(launcher.resolve(), self.home / ".local/share/agent-tools/learning-workflow/bin/learning-workflow")
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
        self.assertFalse((self.home / ".local/share/agent-tools/learning-workflow").exists())

    def test_partial_bundle_copy_is_removed(self) -> None:
        bundle = self.home / ".local/share/agent-tools/learning-workflow"
        original = shutil.copytree

        def fail_bundle_copy(src: Path, dst: Path, *args: object, **kwargs: object) -> Path:
            if Path(dst) == bundle:
                bundle.mkdir(parents=True)
                (bundle / "partial").write_text("incomplete")
                raise OSError("injected copy failure")
            return original(src, dst, *args, **kwargs)

        with patch.object(installer.shutil, "copytree", fail_bundle_copy):
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
        self.assertFalse((self.home / ".local/share/agent-tools/learning-workflow").exists())
        self.assertEqual((self.home / ".agents/skills/teaching-reconstruction").resolve(),
                         self.old / "skills/teaching-reconstruction")

    def test_target_guard_rejects_cross_platform_config_before_writes(self) -> None:
        (self.home / ".codex/config.toml").write_text('note = "C:\\\\Users\\\\other"\n')
        with self.assertRaisesRegex(installer.InstallError, "target guard rejected"):
            installer.install(self.home, legacy_root=self.old, read_papers_root=None, with_hooks=False)
        self.assertFalse((self.home / ".local/share/agent-tools/learning-workflow").exists())


if __name__ == "__main__":
    unittest.main()
