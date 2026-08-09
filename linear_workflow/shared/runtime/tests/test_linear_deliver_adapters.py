from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = RUNTIME_ROOT.parents[1]
REPO_ROOT = WORKFLOW_ROOT.parent
ASSEMBLER_PATH = WORKFLOW_ROOT / "scripts" / "assemble_adapters.py"
INVENTORY_PATH = WORKFLOW_ROOT / "shared" / "delivery-adapter-inventory.json"


def load_assembler():
    spec = importlib.util.spec_from_file_location("assemble_adapters", ASSEMBLER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LinearDeliverAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
        self.source = (REPO_ROOT / self.inventory["canonical_skill_source"]).read_text(
            encoding="utf-8"
        )

    def test_all_generated_adapters_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ASSEMBLER_PATH), "--check"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_clients_share_one_delivery_contract(self) -> None:
        for relative in self.inventory["generated_skills"]:
            with self.subTest(path=relative):
                self.assertEqual(self.source, (REPO_ROOT / relative).read_text(encoding="utf-8"))
        self.assertNotIn("| High |", self.source)
        self.assertNotIn("risk:high", self.source)

    def test_command_references_and_stop_boundaries_are_present(self) -> None:
        self.assertIn(self.inventory["required_command"], self.source)
        for marker in self.inventory["required_stop_markers"]:
            self.assertIn(marker, self.source)
        for reference in self.inventory["shared_references"]:
            self.assertIn(reference, self.source)
            self.assertTrue((REPO_ROOT / reference).is_file(), reference)

    def test_stop_guard_deletion_is_observed(self) -> None:
        assembler = load_assembler()
        marker = self.inventory["required_stop_markers"][0]
        with self.assertRaisesRegex(ValueError, "missing stop marker"):
            assembler.validate_skill_source(self.source.replace(marker, ""), self.inventory)

    def test_both_clients_report_shared_version_and_identity(self) -> None:
        version = (WORKFLOW_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        metadata = [
            json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
            for relative in self.inventory["generated_metadata"]
            if relative.endswith("references/contract.json")
        ]
        self.assertEqual(3, len(metadata))
        self.assertTrue(all(item == metadata[0] for item in metadata))
        self.assertEqual(version, metadata[0]["workflow_version"])
        self.assertEqual(1, metadata[0]["schema_version"])
        for relative in self.inventory["generated_commands"]:
            self.assertIn("$linear-deliver", (REPO_ROOT / relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
