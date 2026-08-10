from __future__ import annotations

import json
import os
import re
from importlib import resources
from pathlib import Path
from typing import Any


SHA = re.compile(r"[0-9a-f]{40}")
RUN_URL = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[1-9][0-9]*/job/[1-9][0-9]*"
)


def pilot_evidence_path() -> Path:
    override = os.environ.get("GOAL_PLAN_PILOT_EVIDENCE")
    if override:
        return Path(override)
    return Path(resources.files("goal_plan_runtime").joinpath("pilot-evidence.json"))


def validate_pilot_evidence(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["pilot evidence must be a JSON object"]
    errors: list[str] = []
    expected = {
        "schema_version": 1,
        "linear_issue": "DRAGAI-61",
        "linear_issue_status": "Done",
        "pilot_batch": "DRAGAI-80",
        "pilot_batch_status": "Done",
        "repository_full_name": "AlexJJ009/agent-tools",
        "claude_code_runtime_validation": "deferred",
        "native_win11_runtime_validation": "deferred",
    }
    for field, wanted in expected.items():
        if value.get(field) != wanted:
            errors.append(f"{field} must equal {wanted!r}")
    merged_sha = value.get("merged_main_sha")
    if not isinstance(merged_sha, str) or not SHA.fullmatch(merged_sha):
        errors.append("merged_main_sha must be a full lowercase Git SHA")

    check = value.get("required_check")
    if not isinstance(check, dict):
        errors.append("required_check must be an object")
    else:
        if check.get("name") != "linear-workflow-runtime":
            errors.append("required_check.name must be 'linear-workflow-runtime'")
        if check.get("status") != "success":
            errors.append("required_check.status must be 'success'")
        if check.get("sha") != merged_sha:
            errors.append("required_check.sha must match merged_main_sha")
        run_url = check.get("run_url")
        if not isinstance(run_url, str) or not RUN_URL.fullmatch(run_url):
            errors.append("required_check.run_url must identify one GitHub Actions job")

    ruleset = value.get("ruleset")
    if not isinstance(ruleset, dict):
        errors.append("ruleset must be an object")
    else:
        if type(ruleset.get("id")) is not int or ruleset["id"] <= 0:
            errors.append("ruleset.id must be a positive integer")
        if ruleset.get("enforcement") != "active":
            errors.append("ruleset.enforcement must be 'active'")
        if ruleset.get("bypass_actors") != []:
            errors.append("ruleset.bypass_actors must be empty")
    return errors


def load_pilot_evidence(path: Path | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    source = path or pilot_evidence_path()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"cannot read valid pilot evidence at {source}: {exc}"]
    errors = validate_pilot_evidence(value)
    return value if isinstance(value, dict) else None, errors


def deprecation_enabled(path: Path | None = None) -> bool:
    _, errors = load_pilot_evidence(path)
    return not errors
