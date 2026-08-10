from __future__ import annotations

import unittest
from unittest import mock

from linear_workflow_runtime.metadata import version_metadata


class VersionMetadataTests(unittest.TestCase):
    def test_reports_versions_from_runtime_and_canonical_schemas(self) -> None:
        self.assertEqual(
            {"workflow_version": "0.4.0", "schema_version": 1},
            version_metadata(),
        )

    @mock.patch("linear_workflow_runtime.metadata.load_schema")
    def test_rejects_disagreeing_canonical_schema_versions(self, load_schema: mock.Mock) -> None:
        load_schema.side_effect = [
            {"properties": {"schema_version": {"enum": [1]}}},
            {"properties": {"schema_version": {"enum": [2]}}},
            {"properties": {"schema_version": {"enum": [1]}}},
            {"properties": {"schema_version": {"enum": [1]}}},
            {"properties": {"schema_version": {"enum": [1]}}},
        ]

        with self.assertRaisesRegex(RuntimeError, "canonical schema versions disagree"):
            version_metadata()

    @mock.patch("linear_workflow_runtime.metadata.load_schema")
    def test_rejects_missing_single_integer_version(self, load_schema: mock.Mock) -> None:
        load_schema.return_value = {
            "properties": {"schema_version": {"enum": [1, 2]}}
        }

        with self.assertRaisesRegex(RuntimeError, "exactly one integer schema_version"):
            version_metadata()

    @mock.patch("linear_workflow_runtime.metadata.load_schema")
    def test_rejects_contract_set_without_a_schema_version(self, load_schema: mock.Mock) -> None:
        load_schema.return_value = {"properties": {}}

        with self.assertRaisesRegex(RuntimeError, "do not declare a schema_version"):
            version_metadata()


if __name__ == "__main__":
    unittest.main()
