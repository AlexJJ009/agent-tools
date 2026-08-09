from __future__ import annotations

import copy
import unittest
from pathlib import Path

from linear_workflow_runtime.contracts import load_json
from linear_workflow_runtime.delivery import (
    CandidateBinding,
    DeliveryAdmissionError,
    topological_issue_order,
)


FIXTURES = Path(__file__).parent / "fixtures"


def issue(issue_id: str, dependencies: list[str]) -> dict[str, object]:
    value = load_json(FIXTURES / "good/issue.json")
    value.update(
        {
            "id": issue_id,
            "title": issue_id,
            "github_issue": f"AlexJJ009/agent-tools#{72 if issue_id.endswith('72') else 73}",
            "dependencies": dependencies,
        }
    )
    return value


def batch() -> dict[str, object]:
    value = load_json(FIXTURES / "good/batch.json")
    value.update(
        {
            "id": "DRAGAI-64",
            "risk_profile": "high",
            "included_issues": ["DRAGAI-72", "DRAGAI-73"],
            "work_references": [
                {
                    "repository_full_name": "AlexJJ009/agent-tools",
                    "base_branch": "main",
                    "base_sha": "1" * 40,
                    "working_branch": "linear/dragai-64-delivery-review-gate",
                    "candidate_sha": None,
                    "github_pull_request": None,
                }
            ],
        }
    )
    return value


class DeliveryRuntimeTests(unittest.TestCase):
    def test_ready_batch_runs_multiple_issues_in_dag_order(self) -> None:
        ordered = topological_issue_order(
            batch(),
            [
                issue("DRAGAI-73", ["DRAGAI-69", "DRAGAI-72"]),
                issue("DRAGAI-72", ["DRAGAI-68", "DRAGAI-71"]),
            ],
            completed_external_dependencies={"DRAGAI-68", "DRAGAI-69", "DRAGAI-71"},
        )
        self.assertEqual(("DRAGAI-72", "DRAGAI-73"), ordered)

    def test_project_context_cannot_bypass_ready_admission(self) -> None:
        value = batch()
        value["status"] = "In Progress"
        with self.assertRaisesRegex(DeliveryAdmissionError, "only a Ready Batch"):
            topological_issue_order(value, [issue("DRAGAI-72", []), issue("DRAGAI-73", [])])

    def test_unknown_or_duplicate_batch_member_fails_closed(self) -> None:
        with self.assertRaisesRegex(DeliveryAdmissionError, "identity mismatch"):
            topological_issue_order(batch(), [issue("DRAGAI-72", [])])
        with self.assertRaisesRegex(DeliveryAdmissionError, "duplicate Issue ID"):
            topological_issue_order(
                batch(),
                [issue("DRAGAI-72", []), issue("DRAGAI-72", [])],
            )

    def test_incomplete_external_dependency_and_cycle_fail_closed(self) -> None:
        with self.assertRaisesRegex(DeliveryAdmissionError, "incomplete external dependency"):
            topological_issue_order(
                batch(),
                [issue("DRAGAI-72", ["DRAGAI-68"]), issue("DRAGAI-73", ["DRAGAI-72"])],
            )
        with self.assertRaisesRegex(DeliveryAdmissionError, "contains a cycle"):
            topological_issue_order(
                batch(),
                [issue("DRAGAI-72", ["DRAGAI-73"]), issue("DRAGAI-73", ["DRAGAI-72"])],
            )

    def test_candidate_change_invalidates_ci_and_review(self) -> None:
        binding = CandidateBinding(
            batch_id="DRAGAI-64",
            issue_ids=("DRAGAI-72", "DRAGAI-73"),
            repository_full_name="AlexJJ009/agent-tools",
            branch="linear/dragai-64-delivery-review-gate",
            base_sha="1" * 40,
        )
        first = binding.bind_candidate("2" * 40)
        complete = first.record_full_ci("2" * 40).record_review("2" * 40)
        self.assertTrue(complete.candidate_gate_complete)
        changed = complete.bind_candidate("3" * 40)
        self.assertFalse(changed.candidate_gate_complete)
        self.assertIsNone(changed.full_ci_sha)
        self.assertIsNone(changed.review_sha)
        with self.assertRaisesRegex(ValueError, "not bound"):
            changed.record_review("2" * 40)


if __name__ == "__main__":
    unittest.main()
