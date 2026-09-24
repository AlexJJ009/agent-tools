"""Executable contracts for the teaching reconstruction artifact validator.

These tests were written red before the production validator existed. The
historical red run is retained under ``docs/teaching-skills-suite/evidence``;
the tests continue to exercise production behavior without reimplementing it.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# teaching-gate: fast


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "teaching"
VALIDATOR = (
    ROOT
    / "skills"
    / "teaching-reconstruction"
    / "scripts"
    / "validate_teaching_artifact.py"
)


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_mutated_fixture(base_name: str, old: str, new: str) -> subprocess.CompletedProcess[str]:
    source = (FIXTURES / base_name).read_text(encoding="utf-8")
    if old not in source:
        raise AssertionError(f"mutation source not found in {base_name}: {old!r}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / base_name
        path.write_text(source.replace(old, new, 1), encoding="utf-8")
        return run_validator(str(path))


class TeachingValidatorSelfTest(unittest.TestCase):
    def test_self_test_contract_is_green(self) -> None:
        result = run_validator("--self-test")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("SELF_TEST_PASS", result.stdout)

    def test_self_test_goes_red_when_named_rule_is_disabled(self) -> None:
        """Mutation-integrity contract for future production self-tests.

        The production validator must expose a test-only way to disable a named
        rule, or an equivalent mutation hook, so reviewers can prove self-test
        fixtures fail for the intended branch instead of only exercising happy
        paths. This test intentionally names one concrete rule to avoid a vague
        "mutation testing exists" assertion.
        """

        result = run_validator("--self-test", "--self-test-disable-rule", "cycle")
        self.assertNotEqual(result.returncode, 0, "self-test stayed green with cycle rule disabled")
        self.assertIn("MUTATION_CAUGHT", result.stderr + result.stdout)
        self.assertIn("cycle", result.stderr + result.stdout)


class TeachingStructureTests(unittest.TestCase):
    def test_good_guided_session_passes(self) -> None:
        result = run_validator(str(FIXTURES / "good_guided_session.md"))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("VALID", result.stdout)

    def test_good_artifact_passes(self) -> None:
        result = run_validator(str(FIXTURES / "good_artifact.md"))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("VALID", result.stdout)

    def test_good_provisional_anchors_pass_with_explicit_downgrade_signal(self) -> None:
        result = run_validator(str(FIXTURES / "good_provisional_anchors.md"))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("VALID", result.stdout)
        self.assertIn("PROVISIONAL_ANCHOR", result.stdout)

    def assert_fixture_fails(self, fixture_name: str, expected_code: str) -> None:
        result = run_validator(str(FIXTURES / fixture_name))
        self.assertNotEqual(result.returncode, 0, f"{fixture_name} unexpectedly passed")
        combined = result.stderr + result.stdout
        self.assertIn(expected_code, combined)

    def test_rejects_manifest_inside_zotlit_managed_region(self) -> None:
        self.assert_fixture_fails("bad_managed_region_marker.md", "MANAGED_REGION")

    def test_rejects_teaching_heading_inside_zotlit_managed_region(self) -> None:
        self.assert_fixture_fails("bad_managed_region_heading.md", "MANAGED_REGION_HEADING")

    def test_rejects_missing_version_marker(self) -> None:
        self.assert_fixture_fails("bad_missing_version_marker.md", "VERSION_MARKER_MISSING")

    def test_rejects_wrong_version_marker(self) -> None:
        self.assert_fixture_fails("bad_wrong_version_marker.md", "VERSION_MARKER_WRONG")

    def test_rejects_duplicate_version_marker(self) -> None:
        self.assert_fixture_fails("bad_duplicate_version_marker.md", "VERSION_MARKER_DUPLICATE")

    def test_rejects_invalid_manifest_json(self) -> None:
        self.assert_fixture_fails("bad_manifest_json.md", "MANIFEST_JSON")

    def test_rejects_duplicate_manifest_blocks(self) -> None:
        self.assert_fixture_fails("bad_duplicate_manifest.md", "MANIFEST_DUPLICATE")

    def test_rejects_missing_guided_core_fields(self) -> None:
        self.assert_fixture_fails("bad_missing_guided_core.md", "MISSING_GUIDED_CORE")

    def test_all_durable_modes_require_core_fields(self) -> None:
        result = run_mutated_fixture(
            "good_artifact.md",
            '  "goal": {"target_ability":',
            '  "goal_removed": {"target_ability":',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISSING_GUIDED_CORE", result.stderr + result.stdout)

    def test_rejects_missing_top_level_manifest_fields(self) -> None:
        result = run_mutated_fixture(
            "good_artifact.md",
            '  "review_queue": [',
            '  "review_cards": [',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISSING_MANIFEST_FIELD", result.stderr + result.stdout)

    def test_rejects_unknown_modes(self) -> None:
        result = run_mutated_fixture("good_guided_session.md", '"mode": "guided"', '"mode": "lecture"')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ILLEGAL_MODE", result.stderr + result.stdout)

    def test_rejects_cycles(self) -> None:
        self.assert_fixture_fails("bad_cycle.md", "CYCLE")

    def test_rejects_duplicate_kc_ids(self) -> None:
        self.assert_fixture_fails("bad_duplicate_kc.md", "DUPLICATE_KC")

    def test_rejects_missing_core_kc_fields(self) -> None:
        self.assert_fixture_fails("bad_missing_core_field.md", "MISSING_CORE_FIELD")

    def test_rejects_missing_prerequisites(self) -> None:
        self.assert_fixture_fails("bad_missing_prereq.md", "MISSING_PREREQUISITE")

    def test_rejects_missing_edge_witnesses(self) -> None:
        self.assert_fixture_fails("bad_missing_witness.md", "MISSING_WITNESS")

    def test_rejects_missing_learning_checks(self) -> None:
        self.assert_fixture_fails("bad_missing_check.md", "MISSING_CHECK")

    def test_rejects_illegal_frontier_nodes(self) -> None:
        self.assert_fixture_fails("bad_illegal_frontier.md", "ILLEGAL_FRONTIER")

    def test_callable_is_not_an_unfinished_frontier_state(self) -> None:
        result = run_mutated_fixture("bad_illegal_frontier.md", '"state": "mastered"', '"state": "callable"')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ILLEGAL_FRONTIER", result.stderr + result.stdout)

    def test_rejects_duplicate_frontier_nodes(self) -> None:
        result = run_mutated_fixture(
            "good_artifact.md",
            '"frontier": ["kc.artifact"]',
            '"frontier": ["kc.artifact", "kc.artifact"]',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DUPLICATE_FRONTIER", result.stderr + result.stdout)

    def test_rejects_illegal_edge_types(self) -> None:
        self.assert_fixture_fails("bad_illegal_edge_type.md", "ILLEGAL_EDGE_TYPE")

    def test_rejects_prerequisite_without_teaching_edge(self) -> None:
        self.assert_fixture_fails("bad_missing_teaching_edge.md", "MISSING_TEACHING_EDGE")


class TeachingEvidenceTests(unittest.TestCase):
    def assert_fixture_fails(self, fixture_name: str, expected_code: str) -> None:
        result = run_validator(str(FIXTURES / fixture_name))
        self.assertNotEqual(result.returncode, 0, f"{fixture_name} unexpectedly passed")
        self.assertIn(expected_code, result.stderr + result.stdout)

    def test_rejects_unknown_evidence_layer(self) -> None:
        self.assert_fixture_fails("bad_evidence_layer.md", "EVIDENCE_LAYER")

    def test_accepts_every_frozen_evidence_layer(self) -> None:
        source = (FIXTURES / "good_guided_session.md").read_text(encoding="utf-8")
        for layer in (
            "source_fact",
            "runtime_fact",
            "inference",
            "design_mapping",
            "teaching_reconstruction",
            "advice",
        ):
            with self.subTest(layer=layer):
                replaced = source.replace('"layer": "source_fact"', f'"layer": "{layer}"', 1)
                import tempfile

                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "layer.md"
                    path.write_text(replaced, encoding="utf-8")
                    result = run_validator(str(path))
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rejects_missing_common_evidence_fields(self) -> None:
        self.assert_fixture_fails("bad_missing_evidence_common.md", "EVIDENCE_CORE")

    def test_rejects_verified_paper_without_pdf_and_page_locator(self) -> None:
        self.assert_fixture_fails(
            "bad_missing_verified_paper_locator.md",
            "PAPER_LOCATOR",
        )

    def test_rejects_nonpositive_verified_paper_page(self) -> None:
        result = run_mutated_fixture("good_guided_session.md", '"page": 3', '"page": 0')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PAPER_LOCATOR", result.stderr + result.stdout)

    def test_rejects_verified_code_without_immutable_revision(self) -> None:
        self.assert_fixture_fails("bad_code_revision.md", "CODE_REVISION")

    def test_rejects_verified_log_without_artifact_hash(self) -> None:
        self.assert_fixture_fails("bad_log_artifact.md", "LOG_ARTIFACT")

    def test_verified_log_accepts_artifact_id_instead_of_run_id(self) -> None:
        result = run_mutated_fixture(
            "good_artifact.md",
            '"run_id": "run-good-artifact"',
            '"artifact_id": "artifact-good-artifact"',
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rejects_verified_web_without_durable_snapshot(self) -> None:
        self.assert_fixture_fails("bad_web_snapshot.md", "WEB_SNAPSHOT")

    def test_provisional_anchor_still_requires_mutable_identity(self) -> None:
        result = run_mutated_fixture(
            "good_provisional_anchors.md",
            '"locator": {"zotero_item_key": "ABCD1234"}',
            '"locator": {}',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PROVISIONAL_LOCATOR", result.stderr + result.stdout)

    def test_rejects_status_outside_verified_or_provisional(self) -> None:
        result = run_mutated_fixture(
            "good_provisional_anchors.md",
            '"status": "provisional"',
            '"status": "pending"',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EVIDENCE_STATUS", result.stderr + result.stdout)


class TeachingLearningCheckTests(unittest.TestCase):
    def test_artifact_mode_requires_transfer_and_audit_checks(self) -> None:
        result = run_validator(str(FIXTURES / "bad_artifact_transfer.md"))
        self.assertNotEqual(result.returncode, 0, "artifact fixture unexpectedly passed")
        self.assertIn("ARTIFACT_TRANSFER", result.stderr + result.stdout)

    def test_artifact_mode_also_requires_reconstruction_and_retrieval(self) -> None:
        result = run_mutated_fixture(
            "good_artifact.md",
            '"type": "reconstruction"',
            '"type": "near_transfer"',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ARTIFACT_TRANSFER", result.stderr + result.stdout)

    def test_rejects_unknown_learning_check_types(self) -> None:
        result = run_mutated_fixture(
            "good_guided_session.md",
            '"type": "reconstruction"',
            '"type": "recognition_only"',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHECK_TYPE", result.stderr + result.stdout)


class TeachingReviewQueueTests(unittest.TestCase):
    def test_rejects_orphaned_review_queue_cards(self) -> None:
        result = run_validator(str(FIXTURES / "bad_review_queue_orphan.md"))
        self.assertNotEqual(result.returncode, 0, "review queue fixture unexpectedly passed")
        self.assertIn("REVIEW_QUEUE_ORPHAN", result.stderr + result.stdout)

    def test_rejects_duplicate_review_queue_cards(self) -> None:
        result = run_validator(str(FIXTURES / "bad_duplicate_review_card.md"))
        self.assertNotEqual(result.returncode, 0, "duplicate review-card fixture unexpectedly passed")
        self.assertIn("REVIEW_QUEUE_DUPLICATE", result.stderr + result.stdout)

    def test_rejects_incomplete_or_non_wikilink_review_cards(self) -> None:
        result = run_validator(str(FIXTURES / "bad_review_queue_fields.md"))
        self.assertNotEqual(result.returncode, 0, "bad review-card fields unexpectedly passed")
        self.assertIn("REVIEW_QUEUE_FIELDS", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
