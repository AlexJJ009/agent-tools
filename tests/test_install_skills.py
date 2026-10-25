"""Discovery links for the plain learning skills, in temporary profiles."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import install_skills as skills  # noqa: E402


class LinkSkillsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.install = self.home / '.local/lib/agent-tools'
        self.base = self.home / '.agents/skills'
        for name in skills.KEPT:
            self.write(self.install / 'skills' / name / 'SKILL.md', f'# {name}\n')

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_fresh_link_is_idempotent_and_points_into_install_root(self):
        first = skills.link_skills(self.home, self.base, self.install)
        self.assertEqual(sorted(first['linked']), sorted(skills.KEPT))
        for name in skills.KEPT:
            self.assertEqual(os.readlink(self.base / name), str(self.install / 'skills' / name))
        second = skills.link_skills(self.home, self.base, self.install)
        self.assertEqual((second['linked'], second['removed'], second['preserved']), ([], [], []))
        self.assertEqual(skills.check_links(self.home, self.base, self.install), [])

    def test_old_bundle_link_is_replaced_retired_link_removed_foreign_entries_kept(self):
        bundle = self.home / '.local/share/agent-tools/learning-workflow/skills'
        self.write(bundle / 'academic-writing/SKILL.md', 'old')
        self.base.mkdir(parents=True)
        (self.base / 'academic-writing').symlink_to(bundle / 'academic-writing')
        (self.base / 'knowledge-deposition-doc').symlink_to(self.home / 'gone-bundle/knowledge-deposition-doc')
        foreign = self.home / 'mine/evidence-anchor'
        self.write(foreign / 'SKILL.md', 'mine')
        (self.base / 'evidence-anchor').symlink_to(foreign)
        self.write(self.base / 'retrieval-practice/SKILL.md', 'a real directory')
        self.write(self.base / 'cleaner/SKILL.md', 'a real retired directory')
        unrelated = self.home / 'elsewhere/work-report'
        self.write(unrelated / 'SKILL.md', 'foreign link target')
        (self.base / 'work-report').symlink_to(unrelated)
        result = skills.link_skills(self.home, self.base, self.install)
        self.assertEqual(os.readlink(self.base / 'academic-writing'), str(self.install / 'skills/academic-writing'))
        self.assertFalse((self.base / 'knowledge-deposition-doc').is_symlink())
        self.assertEqual(sorted(result['preserved']), ['evidence-anchor', 'retrieval-practice'])
        self.assertEqual(os.readlink(self.base / 'evidence-anchor'), str(foreign))
        self.assertEqual((self.base / 'retrieval-practice/SKILL.md').read_text(), 'a real directory')
        self.assertTrue((self.base / 'cleaner/SKILL.md').is_file())  # copies are the operator's to remove
        self.assertTrue((self.base / 'work-report').is_symlink())

    def test_prune_retired_covers_the_codex_skills_directory(self):
        codex = self.home / '.codex/skills'
        codex.mkdir(parents=True)
        (codex / 'codex-win11-patch-safety').symlink_to(self.install / 'skills/codex-win11-patch-safety')
        (codex / 'manage-worktrees').symlink_to(self.install / 'skills/manage-worktrees')
        self.assertEqual(skills.prune_retired(self.home, codex, self.install), ['codex-win11-patch-safety'])
        self.assertTrue((codex / 'manage-worktrees').is_symlink())

    def test_missing_source_is_refused_before_any_write(self):
        (self.install / 'skills/task-routing/SKILL.md').unlink()
        with self.assertRaisesRegex(ValueError, 'skill source missing'):
            skills.link_skills(self.home, self.base, self.install)
        self.assertFalse(self.base.exists())

    def test_target_directory_outside_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as other, self.assertRaisesRegex(ValueError, 'escapes profile'):
            skills.link_skills(self.home, Path(other) / 'skills', self.install)

    def test_check_reports_changed_link(self):
        skills.link_skills(self.home, self.base, self.install)
        (self.base / 'task-routing').unlink()
        (self.base / 'task-routing').symlink_to(self.home)
        self.assertEqual(skills.check_links(self.home, self.base, self.install), ['task-routing'])


if __name__ == '__main__':
    unittest.main()
