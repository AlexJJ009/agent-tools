from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "linear_workflow/scripts/validate_repo_adoption.py"


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_repo_adoption", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateAdoptionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_validator()
        cls.workflow = (REPO_ROOT / ".github/workflows/linear-workflow-runtime.yml").read_text(encoding="utf-8")
        cls.action = (REPO_ROOT / ".github/actions/linear-workflow-pr-check/action.yml").read_text(encoding="utf-8")

    def test_repository_adoption_contract_is_current(self) -> None:
        self.assertEqual([], self.validator.validate_repository(REPO_ROOT))

    def test_feature_branch_push_cannot_duplicate_pr_full_ci(self) -> None:
        broken = self.workflow.replace("      - main\n    paths:", "      - main\n      - feature\n    paths:")
        self.assertTrue(any("push branches" in error for error in self.validator.validate_workflow_text(broken)))

    def test_gate_owned_path_deletion_is_observed(self) -> None:
        broken = self.workflow.replace("      - linear_workflow/**\n", "", 1)
        self.assertTrue(any("pull_request paths" in error for error in self.validator.validate_workflow_text(broken)))

    def test_base_validator_fetch_or_archive_deletion_is_observed(self) -> None:
        for marker in ("git cat-file -e", "git archive", "pr-check --input"):
            with self.subTest(marker=marker):
                broken = self.action.replace(marker, "removed-command")
                self.assertTrue(self.validator.validate_action_text(broken))


if __name__ == "__main__":
    unittest.main()
