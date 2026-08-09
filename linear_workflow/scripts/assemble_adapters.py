#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


WORKFLOW_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKFLOW_ROOT.parent
INVENTORY_PATH = WORKFLOW_ROOT / "shared" / "adapter-inventory.json"


def load_inventory() -> dict[str, object]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def validate_skill_source(source: str, inventory: dict[str, object]) -> None:
    for marker in inventory["required_stop_markers"]:
        if marker not in source:
            raise ValueError(f"canonical skill source is missing stop marker: {marker}")
    if inventory["required_command"] not in source:
        raise ValueError("canonical skill source is missing the required validator command")
    for reference in inventory["shared_references"]:
        if reference not in source:
            raise ValueError(f"canonical skill source is missing shared reference: {reference}")


def _openai_yaml() -> str:
    return '''interface:
  display_name: "Linear Plan"
  short_description: "Plan Linear projects with shared contracts"
  default_prompt: "Use $linear-plan to prepare an approval-bound Linear planning preview."
'''


def _command() -> str:
    return '''---
description: Prepare or revise a Linear PRD, DAG, and Delivery Batch preview without entering Delivery.
argument-hint: [Linear Issue or Project ID]
---

Use `$linear-plan` for the supplied Linear Issue or Project. Read the shared contract and candidate repositories, present the complete approval-bound preview, apply only the exact approved preview, and stop before Delivery.
'''


def _plugin(version: str) -> str:
    value = {
        "name": "linear-workflow",
        "version": version,
        "description": "Plan Linear-first software delivery with shared deterministic contracts.",
        "author": {"name": "Local developer"},
        "skills": "./skills/",
        "interface": {
            "displayName": "Linear Workflow",
            "shortDescription": "Plan Linear-first delivery batches.",
            "longDescription": "Linear Plan reads Linear and candidate repositories, builds an approval-bound planning preview, and applies it through the shared runtime without entering Delivery.",
            "developerName": "Local developer",
            "category": "Developer Tools",
            "capabilities": ["Interactive", "Read", "Write"],
            "defaultPrompt": "Use /linear-plan to prepare a reviewed Linear planning preview.",
        },
    }
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _contract_metadata(version: str) -> str:
    return json.dumps(
        {
            "workflow_version": version,
            "schema_version": 1,
            "canonical_contract": "linear_workflow/shared/",
        },
        indent=2,
    ) + "\n"


def render_targets() -> dict[Path, str]:
    inventory = load_inventory()
    source_path = REPO_ROOT / inventory["canonical_skill_source"]
    source = source_path.read_text(encoding="utf-8")
    validate_skill_source(source, inventory)
    version = (REPO_ROOT / inventory["workflow_version_source"]).read_text(
        encoding="utf-8"
    ).strip()
    rendered: dict[Path, str] = {}
    for path in inventory["generated_skills"]:
        rendered[REPO_ROOT / path] = source
    for path in inventory["generated_metadata"]:
        target = REPO_ROOT / path
        if target.name == "plugin.json":
            rendered[target] = _plugin(version)
        elif target.name == "contract.json":
            rendered[target] = _contract_metadata(version)
        else:
            rendered[target] = _openai_yaml()
    for path in inventory["generated_commands"]:
        rendered[REPO_ROOT / path] = _command()
    return rendered


def assemble(*, check: bool) -> list[str]:
    drift: list[str] = []
    for path, expected in render_targets().items():
        if path.is_file() and path.read_text(encoding="utf-8") == expected:
            continue
        drift.append(path.relative_to(REPO_ROOT).as_posix())
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    return drift


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble generated Linear Workflow adapters")
    parser.add_argument("--check", action="store_true", help="report drift without writing")
    args = parser.parse_args(argv)
    try:
        drift = assemble(check=args.check)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"adapter assembly failed: {error}", file=sys.stderr)
        return 2
    if drift:
        action = "drift" if args.check else "generated"
        for path in drift:
            print(f"{action}: {path}")
        return 1 if args.check else 0
    print("adapter assembly: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
