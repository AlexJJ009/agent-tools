#!/usr/bin/env python3
"""Codex Stop hook wrapper for teaching reconstruction validation."""

from __future__ import annotations

import argparse
import json
import hashlib
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import validate_teaching_artifact as validator  # noqa: E402


def _json_stdout(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0


def _bound_artifacts(payload, state_root):
    """Read the exact session/workspace binding, never historical transcript paths."""
    session=payload.get("session_id")
    if not isinstance(session,str) or not session:
        return []
    cwd=Path(str(payload.get("cwd") or ".")).resolve()
    for workspace in (cwd,*cwd.parents):
        identity=hashlib.sha256((session+"\n"+str(workspace)).encode()).hexdigest()
        path=state_root/(identity+".json")
        if not path.is_file():
            continue
        binding=json.loads(path.read_text())
        delivery=binding.get("teaching_delivery")
        if not delivery:
            return []
        if binding["session_id"]!=session or binding["workspace"]!=str(workspace):
            raise ValueError("teaching binding session/workspace mismatch")
        record=json.loads((Path(binding["record"])/"routing.json").read_text())
        if delivery["route_revision"]!=record["route_revision"]:
            return []
        return [Path(p) for p in delivery["artifacts"]]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--state-root",type=Path,default=Path.home()/".local/state/learning-workflow/hooks")
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
        try:
            artifacts = _bound_artifacts(payload,args.state_root)
        except (OSError,ValueError,KeyError,TypeError) as exc:
            return _json_stdout({"decision":"block","reason":"Current teaching binding unavailable: "+str(exc)})

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
