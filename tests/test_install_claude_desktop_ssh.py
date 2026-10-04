"""configure_claude_desktop_ssh runs in a fake root with a stubbed root runner."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, name):
    return re.search(rf"^{name}\(\) {{\n.*?^}}\n", source, re.S | re.M).group()


class ClaudeDesktopSshTests(unittest.TestCase):
    def run_step(self, root, path):
        source = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
        script = "\n".join([
            "set -euo pipefail",
            'run_script_as_root_if_available() { local -a a=(); while [[ $1 != -- ]]; do a+=("$1"); shift; done; shift; bash -s -- "${a[@]}" "$@"; }',
            function(source, "resolve_existing_path"),
            function(source, "configure_claude_desktop_ssh"),
            "INSTALL_CLAUDE_DESKTOP_SSH=1",
            "configure_claude_desktop_ssh",
            'printf "STATUS=%s\\n" "$CLAUDE_DESKTOP_SSH_STATUS"',
        ])
        env = dict(os.environ, AGENT_TOOLS_TEST_ROOT=str(root), PATH=path)
        return subprocess.run(["bash", "-c", script], env=env, text=True, capture_output=True)

    def test_claude_found_through_managed_link_keeps_its_real_target(self):
        # The step refuses /tmp targets, so stage outside /tmp.
        with tempfile.TemporaryDirectory(dir=Path.home()) as tmp:
            root = Path(tmp) / "root"
            real = Path(tmp) / "home/.local/share/claude/versions/2.1.287"
            real.parent.mkdir(parents=True)
            real.write_text("#!/bin/sh\necho ok\n")
            real.chmod(0o755)
            bin_dir = root / "usr/local/bin"
            bin_dir.mkdir(parents=True)
            (bin_dir / "claude").symlink_to(real)
            result = self.run_step(root, f"{bin_dir}:/usr/bin:/bin")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            link = bin_dir / "claude"
            self.assertTrue(link.is_symlink())
            self.assertEqual(Path(os.path.realpath(link)), real.resolve())
            self.assertTrue(os.access(link, os.X_OK))
            self.assertIn("STATUS=", result.stdout)
            self.assertNotIn("skipped", result.stdout)


if __name__ == "__main__":
    unittest.main()
