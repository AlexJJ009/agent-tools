"""Portable source archives exclude private state in checkouts and extracted sources."""
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PortablePackageTests(unittest.TestCase):
    def test_source_inventory_keeps_current_entrypoints_and_excludes_private_files(self):
        for git_checkout in (True, False):
            with self.subTest(git_checkout=git_checkout), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'agent-tools'
                (source / 'scripts').mkdir(parents=True)
                shutil.copy2(ROOT / 'scripts/pack.sh', source / 'scripts/pack.sh')
                (source / '.gitignore').write_text('ignored-private.txt\ndocs/_local/\n')
                public = ('scripts/install.sh', 'scripts/sync_agent_context.py',
                          '.agents/skills/build-eval/SKILL.md', '.claude/skills/public/SKILL.md')
                for name in public:
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('public source')
                if git_checkout:
                    subprocess.run(['git', 'init', '-q', str(source)], check=True)
                    subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
                    # Include uncommitted, unignored new sources, including moved entrypoints.
                    (source / 'scripts/new-source.py').write_text('new public source')
                private = ('docs/_local/evidence.txt', 'agent_context_sync.config.json',
                           'config/codex-fleet.targets.json', '.env', '.env.production',
                           '.codex/auth.json', '.claude/worktrees/private/secret.txt',
                           'logs/local.log', '__pycache__/cached.pyc', 'credential.pem',
                           'config/auth.json', 'tasks.sqlite3-wal', 'vendor/.git/private')
                for name in private:
                    path = source / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text('PRIVATE_SENTINEL')
                if git_checkout:
                    (source / 'ignored-private.txt').write_text('PRIVATE_SENTINEL')
                if not git_checkout:
                    (source / '.git').mkdir()
                    (source / '.git/private').write_text('PRIVATE_SENTINEL')
                output = source / 'portable.tar.gz'
                subprocess.run(['bash', str(source / 'scripts/pack.sh'), str(output)],
                               check=True, capture_output=True, env=os.environ, timeout=30)
                with tarfile.open(output) as archive:
                    names = archive.getnames()
                    self.assertTrue(all(f'agent-tools/{name}' in names for name in public))
                    if git_checkout:
                        self.assertIn('agent-tools/scripts/new-source.py', names)
                    self.assertFalse(any('/.git/' in name or name.endswith('/portable.tar.gz') for name in names))
                    for name in private:
                        self.assertNotIn(f'agent-tools/{name}', names)
                    for member in archive.getmembers():
                        if member.isfile():
                            self.assertNotIn(b'PRIVATE_SENTINEL', archive.extractfile(member).read())


if __name__ == '__main__':
    unittest.main()
