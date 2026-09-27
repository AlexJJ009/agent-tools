#!/usr/bin/env python3
"""Generate or check independently packaged copies of the reader-facing contract."""

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[3]
    source = repo / "shared/writing/reader-facing-contract.md"
    targets = (
        repo / "skills/work-report/references/writing-contract.md",
        repo / "skills/reviewer-brief/references/writing-contract.md",
    )
    if not (repo / "scripts/install_agent_workflow.py").is_file() or not source.is_file():
        parser.exit(1, "Regeneration requires the repository source and packaging scripts\n")
    expected = source.read_bytes()
    if args.write:
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(expected)
    drift = [str(target.relative_to(repo)) for target in targets if not target.is_file() or target.read_bytes() != expected]
    if drift:
        parser.exit(1, "Generated writing contracts differ from canonical source: " + ", ".join(drift) + "\n")
    print("Shared writing contract copies match")


if __name__ == "__main__":
    main()
