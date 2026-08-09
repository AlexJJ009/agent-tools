from __future__ import annotations

import importlib.util
import json
import re
import tomllib
import unittest
from pathlib import Path

from linear_workflow_runtime import __version__
from linear_workflow_runtime.contracts import SCHEMA_NAMES, load_json, load_schema, validate_schema


RUNTIME_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = RUNTIME_ROOT.parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


class VersionContractTests(unittest.TestCase):
    def test_all_version_sources_match(self) -> None:
        version_file = (WORKFLOW_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        metadata = tomllib.loads((RUNTIME_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(version_file, metadata["project"]["version"])
        self.assertEqual(version_file, __version__)


class SchemaContractTests(unittest.TestCase):
    def test_all_canonical_schemas_load(self) -> None:
        for name in SCHEMA_NAMES:
            with self.subTest(name=name):
                schema = load_schema(name)
                self.assertEqual(schema["type"], "object")
                self.assertTrue(schema["required"])

    def test_known_good_contracts_load(self) -> None:
        for name in ("prd", "issue", "batch", "evidence"):
            with self.subTest(name=name):
                value = load_json(FIXTURES / "good" / f"{name}.json")
                self.assertEqual([], validate_schema(value, name))

    def test_schema_rejects_ambiguous_work_references(self) -> None:
        issue = load_json(FIXTURES / "good" / "issue.json")
        for field, bad in (
            ("repository_full_name", "AT"),
            ("repository_full_name", "agent-tools"),
            ("github_issue", "#3"),
        ):
            with self.subTest(field=field, bad=bad):
                changed = dict(issue)
                changed[field] = bad
                self.assertTrue(validate_schema(changed, "issue"))
        batch = load_json(FIXTURES / "good" / "batch.json")
        changed = json.loads(json.dumps(batch))
        changed["work_references"][0]["base_sha"] = "1234abcd"
        self.assertTrue(validate_schema(changed, "batch"))

    def test_schema_guard_canary_observes_pattern_deletion(self) -> None:
        schema = load_schema("issue")
        original = schema["properties"]["repository_full_name"].pop("pattern")
        try:
            self.assertNotIn("pattern", schema["properties"]["repository_full_name"])
            self.assertIsNotNone(re.fullmatch(original, "AlexJJ009/agent-tools"))
            self.assertIsNone(re.fullmatch(original, "AT"))
        finally:
            schema["properties"]["repository_full_name"]["pattern"] = original


if __name__ == "__main__":
    unittest.main()
