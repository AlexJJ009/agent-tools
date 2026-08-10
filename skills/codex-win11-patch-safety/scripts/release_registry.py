#!/usr/bin/env python3
"""Manage human-reviewed, version-specific Codex patch release recipes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_ledger(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def find_release(index_path: Path, package_version: str, source_hash: str) -> dict | None:
    index = load_json(index_path)
    matches = [
        item
        for item in index.get("releases", [])
        if str(item.get("packageVersion")) == package_version
        and str(item.get("sourceAsarSha256", "")).lower() == source_hash.lower()
    ]
    if len(matches) > 1:
        raise ValueError("release registry contains duplicate exact matches")
    return matches[0] if matches else None


def within(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_release_entry(index_path: Path, entry: dict) -> tuple[Path, dict, Path]:
    release_root = index_path.parent.resolve()
    recipe_path = (release_root / str(entry.get("recipe", ""))).resolve()
    if not within(release_root, recipe_path):
        raise ValueError("release recipe escapes the releases directory")
    recipe = load_json(recipe_path)
    application = recipe.get("application", {})
    comparisons = {
        "releaseId": (entry.get("releaseId"), recipe.get("releaseId")),
        "status": (entry.get("status"), recipe.get("status")),
        "packageVersion": (entry.get("packageVersion"), application.get("packageVersion")),
        "sourceAsarSha256": (
            str(entry.get("sourceAsarSha256", "")).lower(),
            str(application.get("sourceAsarSha256", "")).lower(),
        ),
    }
    inconsistent = [name for name, (left, right) in comparisons.items() if left != right]
    if inconsistent:
        raise ValueError("release index/recipe mismatch: " + ", ".join(inconsistent))
    patcher = (recipe_path.parent / str(recipe.get("patcher", {}).get("entrypoint", ""))).resolve()
    if not within(recipe_path.parent, patcher):
        raise ValueError("release patcher escapes its release directory")
    if not patcher.is_file():
        raise ValueError("release patcher is missing")
    expected_hash = recipe.get("patcher", {}).get("sha256")
    if expected_hash and sha256(patcher) != expected_hash:
        raise ValueError("release patcher hash does not match recipe")
    for companion in recipe.get("patcher", {}).get("companionScripts", []):
        companion_path = (recipe_path.parent / str(companion.get("entrypoint", ""))).resolve()
        if not within(recipe_path.parent, companion_path):
            raise ValueError("release companion script escapes its release directory")
        if not companion_path.is_file():
            raise ValueError("release companion script is missing")
        companion_hash = str(companion.get("sha256", ""))
        if not companion_hash or sha256(companion_path) != companion_hash:
            raise ValueError("release companion script hash does not match recipe")
    for artifact in recipe.get("patcher", {}).get("artifacts", []):
        artifact_path = (recipe_path.parent / str(artifact.get("path", ""))).resolve()
        if not within(recipe_path.parent, artifact_path):
            raise ValueError("release artifact escapes its release directory")
        if not artifact_path.is_file():
            raise ValueError("release artifact is missing")
        artifact_hash = str(artifact.get("sha256", ""))
        if not artifact_hash or sha256(artifact_path) != artifact_hash:
            raise ValueError("release artifact hash does not match recipe")
        if artifact.get("requiredWhileConfigured") and (
            not artifact.get("configKey") or not artifact.get("targetPath")
        ):
            raise ValueError("required config artifact lacks configKey/targetPath")
    if entry.get("status") == "verified" and not recipe.get("verificationEvidence"):
        raise ValueError("verified release lacks promotion evidence")
    return recipe_path, recipe, patcher


def command_select(args: argparse.Namespace) -> int:
    detect = load_json(args.detect)
    package_version = str(detect.get("packageVersion", ""))
    source_hash = str(detect.get("sourceAsarSha256", ""))
    if not package_version or not source_hash:
        result = {"ok": False, "status": "ERROR", "failures": ["detect report lacks packageVersion/sourceAsarSha256"]}
        print(json.dumps(result, indent=2))
        return 2
    match = find_release(args.index, package_version, source_hash)
    if not match:
        result = {
            "ok": False,
            "status": "UNKNOWN",
            "packageVersion": package_version,
            "sourceAsarSha256": source_hash,
            "action": "probe and record a candidate; do not reuse a nearby release",
        }
        print(json.dumps(result, indent=2))
        return 3
    recipe_path, recipe, patcher = validate_release_entry(args.index, match)
    result = {
        "ok": match.get("status") == "verified",
        "status": str(match.get("status", "unknown")).upper(),
        "releaseId": match.get("releaseId"),
        "recipe": str(recipe_path),
        "patcher": str(patcher),
        "activationAllowed": match.get("status") == "verified",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 4


def safe_version(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", value).strip(".-")
    if not cleaned:
        raise ValueError("packageVersion cannot form a safe directory name")
    return cleaned


def command_record_candidate(args: argparse.Namespace) -> int:
    detect = load_json(args.detect)
    version = safe_version(str(detect.get("packageVersion", "")))
    source_hash = str(detect.get("sourceAsarSha256", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        raise ValueError("detect report sourceAsarSha256 is not a SHA256")
    if find_release(args.index, version, source_hash):
        raise ValueError("an exact release already exists; never overwrite it")
    release_id = f"openai-codex-{version}-{source_hash[:12]}"
    release_dir = args.index.parent / version
    if release_dir.exists():
        release_dir = args.index.parent / f"{version}-{source_hash[:12]}"
    release_dir.mkdir(parents=True, exist_ok=False)
    patcher_name = args.patcher.name
    shutil.copy2(args.patcher, release_dir / patcher_name)
    recipe = {
        "schemaVersion": 1,
        "releaseId": release_id,
        "status": "candidate",
        "application": {
            "packageName": "OpenAI.Codex",
            "packageVersion": version,
            "packageFullName": detect.get("packageFullName"),
            "sourceAsarSha256": source_hash,
        },
        "patcher": {
            "kind": "feature-signature-javascript",
            "entrypoint": patcher_name,
            "sha256": sha256(release_dir / patcher_name),
        },
        "verification": {"requiredSemanticGates": ["userConfiguration", "sshConnections", "projectMemoryAndPlanning", "ccSwitch"]},
        "provenance": {
            "createdBy": args.author,
            "candidateReason": args.reason,
            "detectReportSha256": sha256(args.detect),
            "promotionRequirements": ["human review", "release verdict PASS", "postflight four-gate PASS"],
        },
    }
    atomic_json(release_dir / "recipe.json", recipe)
    index = load_json(args.index)
    index.setdefault("releases", []).append(
        {
            "releaseId": release_id,
            "packageVersion": version,
            "sourceAsarSha256": source_hash,
            "status": "candidate",
            "recipe": (release_dir / "recipe.json").relative_to(args.index.parent).as_posix(),
        }
    )
    atomic_json(args.index, index)
    append_ledger(args.ledger, {"event": "candidate-recorded", "releaseId": release_id, "author": args.author, "reason": args.reason})
    print(json.dumps({"ok": True, "status": "CANDIDATE", "releaseId": release_id, "recipe": str(release_dir / "recipe.json")}, indent=2))
    return 0


def all_four_gates_pass(report: dict) -> bool:
    categories = report.get("categories", {})
    required = {"userConfiguration", "sshConnections", "projectMemoryAndPlanning", "ccSwitch"}
    return report.get("ok") is True and required <= set(categories) and all(categories[name].get("ok") is True for name in required)


def command_promote(args: argparse.Namespace) -> int:
    verdict = load_json(args.verdict)
    postflight = load_json(args.postflight)
    approval = load_json(args.approval)
    if verdict.get("status") != "PASS":
        raise ValueError("release verdict is not PASS")
    if not all_four_gates_pass(postflight):
        raise ValueError("postflight does not contain four PASS semantic gates")
    index = load_json(args.index)
    matches = [item for item in index.get("releases", []) if item.get("releaseId") == args.release_id]
    if len(matches) != 1:
        raise ValueError("releaseId is missing or duplicated")
    item = matches[0]
    if item.get("status") != "candidate":
        raise ValueError("only a candidate may be promoted")
    recipe_path, recipe, patcher_path = validate_release_entry(args.index, item)
    application = recipe.get("application", {})
    source = verdict.get("source", {})
    if str(source.get("packageFullName")) != str(application.get("packageFullName")):
        raise ValueError("release verdict package identity does not match the candidate recipe")
    if str(source.get("sourceAsarSha256", "")).lower() != str(application.get("sourceAsarSha256", "")).lower():
        raise ValueError("release verdict source ASAR does not match the candidate recipe")
    expected_patcher_hash = recipe.get("patcher", {}).get("sha256")
    if expected_patcher_hash and (not patcher_path.exists() or sha256(patcher_path) != expected_patcher_hash):
        raise ValueError("candidate patcher changed after it was recorded")
    release_binding = verdict.get("release", {})
    if release_binding.get("releaseId") != args.release_id:
        raise ValueError("release verdict is bound to a different releaseId")
    if release_binding.get("recipeSha256") != sha256(recipe_path):
        raise ValueError("release verdict is bound to a different recipe")
    if expected_patcher_hash and release_binding.get("patcherSha256") != expected_patcher_hash:
        raise ValueError("release verdict is bound to a different patcher")
    required_reports = set(recipe.get("verification", {}).get("requiredReports", []))
    verdict_reports = set(release_binding.get("requiredReports", []))
    if required_reports != verdict_reports:
        raise ValueError("release verdict did not enforce the recipe requiredReports")
    verification = recipe.get("verification", {})
    required_check_ids = set(verification.get("requiredCheckIds", []))
    required_check_ids.update(verification.get("requiredWireCases", []))
    required_check_ids.update(verification.get("requiredPluginChecks", []))
    verdict_check_ids = set(release_binding.get("requiredCheckIds", []))
    if required_check_ids != verdict_check_ids:
        raise ValueError("release verdict did not enforce the recipe required semantic check IDs")
    observed_check_ids = {
        str(check_id)
        for check in verdict.get("checks", [])
        if check.get("ok") is True
        for check_id in check.get("checkIds", [])
    }
    if not required_check_ids.issubset(observed_check_ids):
        raise ValueError("release verdict required semantic check IDs lack bound PASS report evidence")
    reviewer = str(approval.get("reviewer", "")).strip()
    reason = str(approval.get("reason", "")).strip()
    declaration = approval.get("humanApproval") is True
    if len(reviewer) < 2 or len(reason) < 10 or not declaration:
        raise ValueError("approval must contain reviewer, concrete reason, and humanApproval=true")
    expected_approval = {
        "releaseId": args.release_id,
        "recipeSha256": sha256(recipe_path),
        "verdictSha256": sha256(args.verdict),
        "postflightSha256": sha256(args.postflight),
    }
    mismatched = [key for key, value in expected_approval.items() if approval.get(key) != value]
    if mismatched:
        raise ValueError("approval evidence binding mismatch: " + ", ".join(mismatched))
    recipe["status"] = "verified"
    recipe["verificationEvidence"] = {
        "releaseVerdictSha256": sha256(args.verdict),
        "postflightSha256": sha256(args.postflight),
        "approvalSha256": sha256(args.approval),
        "reviewer": reviewer,
        "reason": reason,
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    item["status"] = "verified"
    atomic_json(recipe_path, recipe)
    atomic_json(args.index, index)
    append_ledger(args.ledger, {"event": "candidate-promoted", "releaseId": args.release_id, "reviewer": reviewer, "reason": reason, "approvalSha256": sha256(args.approval)})
    print(json.dumps({"ok": True, "status": "VERIFIED", "releaseId": args.release_id}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--detect", type=Path, required=True)
    candidate = sub.add_parser("record-candidate")
    candidate.add_argument("--detect", type=Path, required=True)
    candidate.add_argument("--patcher", type=Path, required=True)
    candidate.add_argument("--author", required=True)
    candidate.add_argument("--reason", required=True)
    candidate.add_argument("--ledger", type=Path, required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--release-id", required=True)
    promote.add_argument("--verdict", type=Path, required=True)
    promote.add_argument("--postflight", type=Path, required=True)
    promote.add_argument("--approval", type=Path, required=True)
    promote.add_argument("--ledger", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "select":
            return command_select(args)
        if args.command == "record-candidate":
            return command_record_candidate(args)
        return command_promote(args)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"ok": False, "status": "ERROR", "error": str(error)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
