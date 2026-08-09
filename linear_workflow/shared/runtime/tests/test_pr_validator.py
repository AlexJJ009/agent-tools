from __future__ import annotations

import unittest
from pathlib import Path

from linear_workflow_runtime.contracts import load_json
from linear_workflow_runtime.validators import (
    PR_BLOCKING_RULES,
    _path_matches_prefix,
    load_gate_policy,
    validate_pr,
)
from test_planning_batch_validators import load_bad_case


FIXTURES = Path(__file__).parent / "fixtures"


class PullRequestValidatorTests(unittest.TestCase):
    def test_good_current_candidate_evidence_passes(self) -> None:
        self.assertEqual([], validate_pr(load_json(FIXTURES / "good/evidence.json")))

    def test_every_pr_guard_has_a_known_bad_fixture(self) -> None:
        observed = set()
        for path in sorted((FIXTURES / "bad").glob("pr-*.json")):
            value, expected = load_bad_case(path)
            rules = {error.rule_id for error in validate_pr(value)}
            self.assertIn(expected, rules, path.name)
            observed.add(expected)
        self.assertEqual(PR_BLOCKING_RULES, observed)

    def test_review_required_paths_have_one_machine_readable_source(self) -> None:
        policy = load_gate_policy()
        self.assertEqual(1, policy["schema_version"])
        self.assertEqual(len(policy["review_required_paths"]), len(set(policy["review_required_paths"])))
        self.assertIn("linear_workflow/shared/runtime/", policy["review_required_paths"])

    def test_review_path_prefix_does_not_match_sibling_name(self) -> None:
        prefixes = ["linear_workflow/shared/runtime/"]
        self.assertTrue(_path_matches_prefix("linear_workflow/shared/runtime/pyproject.toml", prefixes))
        self.assertFalse(_path_matches_prefix("linear_workflow/shared/runtime_evil/file", prefixes))

    def test_duplicate_issue_identity_fails_closed(self) -> None:
        evidence = load_json(FIXTURES / "good/evidence.json")
        evidence["linear_issues"][2] = evidence["linear_issues"][1]
        rules = {error.rule_id for error in validate_pr(evidence)}
        self.assertIn("LW-SCHEMA", rules)

    def test_stale_gate_self_test_fails_closed(self) -> None:
        evidence = load_json(FIXTURES / "good/evidence.json")
        evidence["gate_self_test"]["sha"] = "3" * 40
        rules = {error.rule_id for error in validate_pr(evidence)}
        self.assertIn("LW-PR-014", rules)


if __name__ == "__main__":
    unittest.main()
