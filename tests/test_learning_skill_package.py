import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCRIPT = ROOT / "project_adapters/read_papers/read-paper/scripts/resolve_project_config.py"
SYNC_SCRIPT = ROOT / "skills/work-report/scripts/sync_writing_contract.py"
RESOLVER = ROOT / "project_adapters/read_papers/read-paper/scripts/resolve_zotero_paper.py"

spec = importlib.util.spec_from_file_location("read_papers_config", CONFIG_SCRIPT)
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)


class LearningSkillPackageTests(unittest.TestCase):
    def test_project_config_resolves_relative_paths_from_config_not_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "project/read-paper-adapter.json"
            config.parent.mkdir()
            config.write_text(json.dumps({
                "read_papers_root": ".", "zotero_data_dir": "../Zotero/dataStorage",
                "zotero_api_url": "http://127.0.0.1:23119", "import_arxiv_script": "scripts/import_arxiv_to_zotero.py",
            }))
            result = config_module.load_config(config)
            self.assertEqual(result["read_papers_root"], str(config.parent.resolve()))
            self.assertEqual(result["zotero_data_dir"], str((root / "Zotero/dataStorage").resolve()))
            self.assertEqual(result["import_arxiv_script"], str((config.parent / "scripts/import_arxiv_to_zotero.py").resolve()))
            config.write_text('{}')
            with self.assertRaises(ValueError):
                config_module.load_config(config)

    def test_zotero_resolver_migration_preserves_source_bytes(self):
        self.assertEqual(hashlib.sha256(RESOLVER.read_bytes()).hexdigest(),
                         "d68b93e8fbaa70915aa99a2128f162c7ae5e352556213b8ced91bce512d95203")

    def test_contract_sync_detects_drift_and_restores_both_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            script = repo / "skills/work-report/scripts/sync_writing_contract.py"
            script.parent.mkdir(parents=True)
            shutil.copy2(SYNC_SCRIPT, script)
            source = repo / "shared/writing/reader-facing-contract.md"
            source.parent.mkdir(parents=True)
            source.write_text("W1 through W9 fixture\n")
            install = repo / "scripts/install_agent_workflow.py"
            install.parent.mkdir()
            install.write_text("# fixture\n")
            def run(flag):
                return subprocess.run([sys.executable, str(script), flag], capture_output=True, text=True)
            self.assertNotEqual(run("--check").returncode, 0)
            self.assertEqual(run("--write").returncode, 0)
            self.assertEqual(run("--check").returncode, 0)
            target = repo / "skills/reviewer-brief/references/writing-contract.md"
            target.write_text("drift\n")
            self.assertNotEqual(run("--check").returncode, 0)
            self.assertEqual(run("--write").returncode, 0)
            self.assertEqual(target.read_bytes(), source.read_bytes())
