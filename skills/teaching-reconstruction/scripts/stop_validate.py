#!/usr/bin/env python3
"""Codex Stop hook wrapper for teaching reconstruction validation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_teaching_artifact as validator  # noqa: E402


def _json_stdout(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _transcript_artifacts(payload: dict[str, Any]) -> list[Path]:
    transcript_raw = payload.get("transcript_path")
    if not isinstance(transcript_raw, str):
        return []
    try:
        lines = Path(transcript_raw).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    cwd = Path(str(payload.get("cwd") or ".")).resolve()
    candidates: list[Path] = []
    for line in lines:
        try:
            record: Any = json.loads(line)
        except json.JSONDecodeError:
            record = line
        for value in _strings(record):
            raw_candidates = re.findall(r"/[^\r\n\"'<>]*?\.md\b", value)
            raw_candidates += re.findall(r"(?:^|[\s:])([A-Za-z0-9_./-]+\.md)\b", value)
            for raw in raw_candidates:
                path = Path(raw.strip())
                path = path.resolve() if path.is_absolute() else (cwd / path).resolve()
                try:
                    path.relative_to(cwd)
                except ValueError:
                    continue
                if path.is_file() and path not in candidates:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    if validator.ANY_MARKER_RE.search(text) or "```json teaching-manifest" in text:
                        candidates.append(path)
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", action="append", default=[])
    args = parser.parse_args(argv)

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        payload = {}

    if payload.get("stop_hook_active") is True:
        return _json_stdout({})

    artifacts: list[Path] = []
    cwd = Path(str(payload.get("cwd") or ".")).resolve()
    for raw in args.artifact:
        path = Path(raw)
        path = path.resolve() if path.is_absolute() else (cwd / path).resolve()
        if path not in artifacts:
            artifacts.append(path)
    if not artifacts:
        artifacts = _transcript_artifacts(payload)

    if not artifacts:
        return _json_stdout({})

    errors: set[str] = set()
    for artifact in artifacts:
        result = validator.validate_file(artifact)
        errors.update(result.errors)
    if not errors:
        return _json_stdout({})

    reason = " ".join(sorted(errors))
    return _json_stdout({"decision": "block", "reason": reason})


if __name__ == "__main__":
    raise SystemExit(main())
