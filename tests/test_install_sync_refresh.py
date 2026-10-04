"""The context-sync refresh command must not churn a repo that ships the tool."""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(copy):
    spec = importlib.util.spec_from_file_location("sync_copy", copy)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


class RefreshCommandTests(unittest.TestCase):
    def test_installed_copy_keeps_relative_command_for_repo_shipping_the_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            install, repo, other = (Path(tmp) / n for n in ("lib", "repo", "other"))
            for d in (install, repo, other):
                d.mkdir()
                (d / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts" / "sync_agent_context.py", install / "scripts/sync_agent_context.py")
            (repo / "scripts/sync_agent_context.py").write_text("# shipped copy\n")
            tool = load(install / "scripts/sync_agent_context.py")
            self.assertIn(" scripts/sync_agent_context.py sync .", tool.refresh_command_for(repo))
            self.assertIn(str(install / "scripts/sync_agent_context.py"), tool.refresh_command_for(other))


if __name__ == "__main__":
    unittest.main()
