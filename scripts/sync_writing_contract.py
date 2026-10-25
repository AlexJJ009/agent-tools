#!/usr/bin/env python3
"""Generate or check the independently packaged copy of the reader-facing contract."""

import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "shared/writing/reader-facing-contract.md"
TARGETS = (REPO / "skills/academic-writing/references/writing-contract.md",)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not SOURCE.is_file():
        parser.exit(1, "Regeneration requires the repository source\n")
    expected = SOURCE.read_bytes()
    if args.write:
        for target in TARGETS:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(expected)
    drift = [str(t.relative_to(REPO)) for t in TARGETS if not t.is_file() or t.read_bytes() != expected]
    if drift:
        parser.exit(1, "Generated writing contracts differ from canonical source: " + ", ".join(drift) + "\n")
    print("Shared writing contract copies match")


if __name__ == "__main__":
    main()
