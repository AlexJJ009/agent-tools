"""Red contracts for the Codex Stop hook teaching-artifact wrapper."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# teaching-gate: fast


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "teaching"
STOP_WRAPPER = (
    ROOT / "skills" / "teaching-reconstruction" / "scripts" / "stop_validate.py"
)


def run_stop_hook(
    artifact: Path,
    *,
    stop_hook_active: bool,
    explicit_artifact: bool = True,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        transcript = Path(tmp) / "transcript.jsonl"
        transcript.write_text(
            json.dumps(
                {
                    "role": "assistant",
                    "content": f"wrote durable teaching artifact: {artifact}",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        payload = {
            "hook_event_name": "Stop",
            "session_id": "teaching-stop-test",
            "transcript_path": str(transcript),
            "cwd": str(ROOT),
            "stop_hook_active": stop_hook_active,
        }
        command = [sys.executable, str(STOP_WRAPPER)]
        if explicit_artifact:
            command.extend(("--artifact", str(artifact)))
        return subprocess.run(
            command,
            cwd=ROOT,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )


def parse_json_stdout(result: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - assertion helper
        raise AssertionError(f"stdout is not valid JSON: {result.stdout!r}") from exc


class TeachingStopHookTests(unittest.TestCase):
    def test_invalid_artifact_blocks_on_first_stop_pass(self) -> None:
        result = run_stop_hook(FIXTURES / "bad_cycle.md", stop_hook_active=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = parse_json_stdout(result)
        self.assertEqual(payload.get("decision"), "block")
        self.assertIn("CYCLE", payload.get("reason", ""))

    def test_active_stop_pass_does_not_request_another_continuation(self) -> None:
        result = run_stop_hook(FIXTURES / "bad_cycle.md", stop_hook_active=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = parse_json_stdout(result)
        self.assertEqual(payload, {}, "active Stop pass must emit the official no-op JSON object")

    def test_corrected_artifact_is_non_blocking_json(self) -> None:
        result = run_stop_hook(FIXTURES / "good_guided_session.md", stop_hook_active=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = parse_json_stdout(result)
        self.assertEqual(payload, {})

    def test_corrected_compiled_artifact_is_non_blocking_json(self) -> None:
        result = run_stop_hook(FIXTURES / "good_artifact.md", stop_hook_active=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = parse_json_stdout(result)
        self.assertEqual(payload, {})

    def test_managed_region_heading_blocks_on_first_stop_pass(self) -> None:
        result = run_stop_hook(FIXTURES / "bad_managed_region_heading.md", stop_hook_active=False)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = parse_json_stdout(result)
        self.assertEqual(payload.get("decision"), "block")
        self.assertIn("MANAGED_REGION_HEADING", payload.get("reason", ""))

    def test_project_hook_can_infer_artifact_from_transcript(self) -> None:
        result = run_stop_hook(
            FIXTURES / "bad_cycle.md",
            stop_hook_active=False,
            explicit_artifact=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = parse_json_stdout(result)
        self.assertEqual(payload.get("decision"), "block")
        self.assertIn("CYCLE", payload.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
