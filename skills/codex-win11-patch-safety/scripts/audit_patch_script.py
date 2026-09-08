#!/usr/bin/env python3
"""Statically reject Codex patch scripts that violate the Win11 safety contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROFILE_OVERRIDES = ("--user-data-dir", "--profile-directory")
DESTRUCTIVE = re.compile(r"(?i)(remove-item|rm\s+-rf|rmtree|unlink|delete|robocopy[^\n]*/mir)")
PROTECTED = re.compile(
    r"(?i)(\\?\.codex|\\?\.ssh|\\?\.cc-switch|appdata[\\/]roaming[\\/]codex|program files[\\/]windowsapps)"
)


def audit(paths: list[Path]) -> dict:
    findings: list[dict] = []
    for path in paths:
        text = path.read_text("utf-8-sig")
        lowered = text.lower()
        for token in PROFILE_OVERRIDES:
            if token in lowered:
                findings.append({"file": str(path), "rule": "profile_override", "token": token})
        lines = text.splitlines()
        for index, line in enumerate(lines, start=1):
            if DESTRUCTIVE.search(line) and PROTECTED.search(line):
                findings.append(
                    {"file": str(path), "line": index, "rule": "destructive_protected_path", "text": line.strip()}
                )
            if DESTRUCTIVE.search(line) and "windowsapps" in line.lower():
                findings.append(
                    {"file": str(path), "line": index, "rule": "write_windowsapps", "text": line.strip()}
                )
    return {"ok": not findings, "files": [str(path) for path in paths], "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    result = audit(args.paths)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
