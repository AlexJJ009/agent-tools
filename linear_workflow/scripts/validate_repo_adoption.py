#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/linear-workflow-runtime.yml"
ACTION = REPO_ROOT / ".github/actions/linear-workflow-pr-check/action.yml"
CONFIG = REPO_ROOT / ".linear-workflow.yml"
REQUIRED_PATHS = {
    ".github/workflows/linear-workflow-runtime.yml",
    ".github/actions/linear-workflow-pr-check/**",
    ".github/pull_request_template.md",
    ".linear-workflow.yml",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "linear_workflow/**",
}


def _event_block(text: str, event: str) -> str:
    match = re.search(
        rf"^  {re.escape(event)}:\s*\n(.*?)(?=^  [a-z_]+:\s*$|^permissions:)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def validate_workflow_text(text: str) -> list[str]:
    errors: list[str] = []
    pull_request = _event_block(text, "pull_request")
    push = _event_block(text, "push")
    if not pull_request:
        errors.append("pull_request trigger is missing")
    if not push:
        errors.append("main push trigger is missing")
    if "  workflow_dispatch:" not in text:
        errors.append("workflow_dispatch trigger is missing")
    branch_match = re.search(r"^    branches:\s*\n(.*?)(?=^    [a-z_]+:)", push, re.MULTILINE | re.DOTALL)
    branches = re.findall(r"^      - (.+)$", branch_match.group(1), re.MULTILINE) if branch_match else []
    if branches != ["main"]:
        errors.append(f"push branches must be exactly ['main'], got {branches!r}")
    for name, block in (("pull_request", pull_request), ("push", push)):
        paths_match = re.search(r"^    paths:\s*\n(.*)$", block, re.MULTILINE | re.DOTALL)
        paths = set(re.findall(r"^      - (.+)$", paths_match.group(1), re.MULTILINE)) if paths_match else set()
        missing = sorted(REQUIRED_PATHS - paths)
        if missing:
            errors.append(f"{name} paths are missing {missing!r}")
    if not re.search(r"^permissions:\s*\n  contents: read\s*$", text, re.MULTILINE):
        errors.append("workflow permissions must be contents: read")
    if "name: linear-workflow-runtime" not in text:
        errors.append("authoritative check name is missing")
    for command in (
        "pip wheel --no-deps",
        "pip check",
        "unittest discover -s linear_workflow/shared/runtime/tests",
        "assemble_adapters.py --check",
        "validate_repo_adoption.py",
        "compileall",
        "git diff --check",
    ):
        if command not in text:
            errors.append(f"workflow command is missing: {command}")
    return errors


def validate_action_text(text: str) -> list[str]:
    required = (
        "LINEAR_WORKFLOW_BASE_SHA",
        "^[0-9a-f]{40}$",
        "git cat-file -e",
        "git fetch --no-tags origin",
        "git archive",
        "linear_workflow/shared/runtime",
        "linear_workflow/shared/gate-policy.json",
        "pr-check --input",
        "set -euo pipefail",
    )
    return [f"base-validator action is missing: {item}" for item in required if item not in text]


def validate_repository(root: Path = REPO_ROOT) -> list[str]:
    errors = validate_workflow_text((root / WORKFLOW.relative_to(REPO_ROOT)).read_text(encoding="utf-8"))
    errors.extend(validate_action_text((root / ACTION.relative_to(REPO_ROOT)).read_text(encoding="utf-8")))
    version = (root / "linear_workflow/VERSION").read_text(encoding="utf-8").strip()
    config = (root / CONFIG.relative_to(REPO_ROOT)).read_text(encoding="utf-8")
    for line in (
        f"workflow_version: {version}",
        "repository_full_name: AlexJJ009/agent-tools",
        "base_branch: main",
        "required_check: linear-workflow-runtime",
        "merge_authority: human",
    ):
        if line not in config:
            errors.append(f"adoption config is missing: {line}")
    for inventory_name in ("adapter-inventory.json", "delivery-adapter-inventory.json"):
        inventory = json.loads((root / "linear_workflow/shared" / inventory_name).read_text(encoding="utf-8"))
        source = (root / inventory["canonical_skill_source"]).read_text(encoding="utf-8")
        expected_name = inventory["adapter"]
        if f"name: {expected_name}" not in source:
            errors.append(f"canonical adapter identity is wrong: {expected_name}")
        for relative in inventory["generated_skills"]:
            if (root / relative).read_text(encoding="utf-8") != source:
                errors.append(f"generated adapter drift: {relative}")
        for relative in inventory["generated_metadata"]:
            if relative.endswith("contract.json"):
                metadata = json.loads((root / relative).read_text(encoding="utf-8"))
                if metadata.get("workflow_version") != version or metadata.get("schema_version") != 1:
                    errors.append(f"generated contract version drift: {relative}")
    plugin = json.loads((root / "linear_workflow/codex/plugins/linear-workflow/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if plugin.get("version") != version or plugin.get("skills") != "./skills/":
        errors.append("plugin manifest version or skills root is invalid")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    claude = (root / "CLAUDE.md").read_text(encoding="utf-8")
    marker = "Only an explicitly dispatched Ready Batch authorizes implementation"
    if marker not in agents or marker not in claude:
        errors.append("AGENTS/CLAUDE Delivery entrypoint is missing or out of sync")
    pr_template = (root / ".github/pull_request_template.md").read_text(encoding="utf-8")
    for marker in ("Repository: `AlexJJ009/agent-tools`", "Base SHA", "Candidate SHA", "Unresolved prior findings", "New findings"):
        if marker not in pr_template:
            errors.append(f"PR template is missing: {marker}")
    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        for error in errors:
            print(f"repo-adoption: {error}", file=sys.stderr)
        return 1
    print("repo-adoption: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
