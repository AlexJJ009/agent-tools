from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from linear_workflow_runtime.contracts import load_json, validate_schema
from linear_workflow_runtime.validators import (
    BATCH_BLOCKING_RULES,
    PLAN_BLOCKING_RULES,
    validate_batch,
    validate_plan,
    _path_allowed,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _set_pointer(value: Any, pointer: str, replacement: Any) -> None:
    parts = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
    target = value
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    final = parts[-1]
    if isinstance(target, list):
        target[int(final)] = replacement
    else:
        target[final] = replacement


def load_bad_case(path: Path) -> tuple[dict[str, Any], str]:
    case = json.loads(path.read_text(encoding="utf-8"))
    value = load_json(FIXTURES / case["base"])
    value = copy.deepcopy(value)
    for pointer, replacement in case["set"].items():
        _set_pointer(value, pointer, replacement)
    return value, case["expected_rule"]


class PlanningValidatorTests(unittest.TestCase):
    def test_good_plan_passes(self) -> None:
        self.assertEqual([], validate_plan(load_json(FIXTURES / "good/prd.json")))

    def test_every_planning_guard_has_a_known_bad_fixture(self) -> None:
        observed = set()
        for path in sorted((FIXTURES / "bad").glob("plan-*.json")):
            value, expected = load_bad_case(path)
            rules = {error.rule_id for error in validate_plan(value)}
            self.assertIn(expected, rules, path.name)
            observed.add(expected)
        self.assertEqual(PLAN_BLOCKING_RULES, observed)

    def test_missing_destination_is_rejected_by_schema(self) -> None:
        issue = load_json(FIXTURES / "good/issue.json")
        del issue["destination"]
        self.assertTrue(validate_schema(issue, "issue"))


class BatchValidatorTests(unittest.TestCase):
    def test_good_standard_and_fast_batches_pass(self) -> None:
        for name in ("batch.json", "batch-fast.json"):
            with self.subTest(name=name):
                self.assertEqual([], validate_batch(load_json(FIXTURES / "good" / name)))

    def test_every_batch_guard_has_a_known_bad_fixture(self) -> None:
        observed = set()
        for path in sorted((FIXTURES / "bad").glob("batch-*.json")):
            value, expected = load_bad_case(path)
            rules = {error.rule_id for error in validate_batch(value)}
            self.assertIn(expected, rules, path.name)
            observed.add(expected)
        self.assertEqual(BATCH_BLOCKING_RULES, observed)

    def test_short_sha_and_repo_abbreviation_fail_schema(self) -> None:
        batch = load_json(FIXTURES / "good/batch.json")
        batch["work_references"][0]["base_sha"] = "abc123"
        batch["work_references"][0]["repository_full_name"] = "AT"
        self.assertTrue(validate_schema(batch, "batch"))

    def test_scope_prefix_does_not_match_sibling_name(self) -> None:
        self.assertTrue(_path_allowed("linear_workflow/VERSION", ["linear_workflow/"]))
        self.assertFalse(_path_allowed("linear_workflow_evil/VERSION", ["linear_workflow/"]))

    def test_fast_branch_uses_issue_id_and_batch_branch_uses_batch_id(self) -> None:
        fast = load_json(FIXTURES / "good/batch-fast.json")
        standard = load_json(FIXTURES / "good/batch.json")
        self.assertEqual([], validate_batch(fast))
        self.assertEqual([], validate_batch(standard))
        fast["work_references"][0]["working_branch"] = "linear/dragai-62-wrong"
        standard["work_references"][0]["working_branch"] = "linear/dragai-67-wrong"
        self.assertIn("LW-BAT-002", {error.rule_id for error in validate_batch(fast)})
        self.assertIn("LW-BAT-002", {error.rule_id for error in validate_batch(standard)})


if __name__ == "__main__":
    unittest.main()
