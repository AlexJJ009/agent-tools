from __future__ import annotations

import contextlib
import io
import json
import unittest

from linear_workflow_runtime.cli import build_parser, main


class VersionCliTests(unittest.TestCase):
    def test_version_json_reports_exact_metadata_contract(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = main(["version", "--json"])

        self.assertEqual(0, exit_code)
        self.assertEqual(
            {"workflow_version": "0.4.0", "schema_version": 1},
            json.loads(output.getvalue()),
        )
        self.assertEqual(
            '{"workflow_version":"0.4.0","schema_version":1}\n',
            output.getvalue(),
        )

    def test_legacy_version_flag_is_unchanged(self) -> None:
        output = io.StringIO()

        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(0, raised.exception.code)
        self.assertEqual("0.4.0\n", output.getvalue())

    def test_help_discovers_version_command(self) -> None:
        help_text = build_parser().format_help()

        self.assertIn("version", help_text)

    def test_version_subcommand_requires_json_mode(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["version"])

        self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
