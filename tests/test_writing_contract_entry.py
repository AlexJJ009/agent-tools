"""A real generated Codex entry resolves and preserves existing instructions."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('writing_installer', ROOT / 'scripts/install_learning_workflow.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class WritingEntryTests(unittest.TestCase):
    def test_generated_entry_materializes_adapter_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            source = home / 'adapter.md'
            source.write_text('Original adapter instructions.\n')
            path = home / '.codex/AGENTS.md'
            path.parent.mkdir()
            path.symlink_to(source)
            bundle = home / 'bundle with spaces'
            contract = bundle / 'shared/writing/reader-facing-contract.md'
            contract.parent.mkdir(parents=True)
            contract.write_text('Real reader contract.')
            entry = installer.install_writing_entry(home, bundle)
            self.assertFalse(path.is_symlink())
            self.assertEqual(source.read_text(), 'Original adapter instructions.\n')
            self.assertIn(str(contract), path.read_text())
            self.assertEqual(path.read_text().count(installer.WRITING_START), 1)
            installer.remove_writing_entry(home, entry)
            self.assertTrue(path.is_symlink())
            self.assertEqual(path.resolve(), source)

    def test_rollback_keeps_later_user_edits_and_rejects_modified_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            entry = installer.install_writing_entry(home, home / 'bundle')
            path = home / '.codex/AGENTS.md'
            path.write_text(path.read_text() + '\nLater user instruction.\n')
            installer.remove_writing_entry(home, entry)
            self.assertIn('Later user instruction.', path.read_text())
            self.assertNotIn(installer.WRITING_START, path.read_text())
            entry = installer.install_writing_entry(home, home / 'bundle')
            path.write_text(path.read_text().replace('For all reader-facing', 'For some reader-facing'))
            with self.assertRaises(installer.InstallError):
                installer.remove_writing_entry(home, entry)
