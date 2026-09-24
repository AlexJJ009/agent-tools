"""Verify frozen acceptance inputs; never read candidate-generated state."""

import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--trusted-sha256", required=True,
                        help="Digest recorded outside the mutable baseline directory")
    args = parser.parse_args()
    failures = []
    if sha(args.manifest) != args.trusted_sha256:
        failures.append({"path": str(args.manifest), "reason": "manifest differs from independently recorded digest"})
    manifest = json.loads(args.manifest.read_text())
    root = args.root or Path(manifest["repository_root"])
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.is_file() or sha(path) != entry["sha256"]:
            failures.append({"path": entry["path"], "reason": "missing or changed frozen file"})
    for entry in manifest["source_snapshots"]:
        path = args.manifest.parent / entry["snapshot"]
        if not path.is_file() or sha(path) != entry["sha256"]:
            failures.append({"path": entry["snapshot"], "reason": "missing or changed source snapshot"})
    print(json.dumps({"kind": "baseline_integrity", "pass": not failures,
                      "candidate_evaluated": False, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
