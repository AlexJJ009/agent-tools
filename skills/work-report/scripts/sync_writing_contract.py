#!/usr/bin/env python3
"""Generate or check the independent reviewer-brief packaging view."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1] / "references/writing-contract.md"
    target = source.parents[2] / "reviewer-brief/references/writing-contract.md"
    if args.write:
        if not (source.parents[3] / "scripts/install_agent_workflow.py").is_file():
            parser.exit(1, "Regeneration is a repository packaging step; do not mutate installed skills\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    if not target.is_file() or target.read_bytes() != source.read_bytes():
        parser.exit(1, "Generated reviewer-brief writing contract differs from its canonical source\n")
    print("Shared writing contract copies match")


if __name__ == "__main__":
    main()
