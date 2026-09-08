#!/usr/bin/env python3
"""Create and verify hash-bound PASS/RED/ERROR verdicts for a patched Codex build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
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
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def artifact_record(path: Path) -> dict:
    return {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": sha256(path)}


def passed_check_ids(payload: dict) -> set[str]:
    passed = {str(item) for item in payload.get("checkIds", []) if isinstance(item, str)}
    checks = payload.get("checks", {})
    if isinstance(checks, dict):
        for name, value in checks.items():
            if value is True or isinstance(value, dict) and value.get("ok") is True:
                passed.add(str(name))
    elif isinstance(checks, list):
        for item in checks:
            if isinstance(item, str):
                passed.add(item)
            elif isinstance(item, dict) and item.get("ok") is True and item.get("id"):
                passed.add(str(item["id"]))
    return passed


def build_verdict(
    recipe_path: Path,
    detect_path: Path,
    snapshot_manifest: Path,
    source_asar: Path,
    candidate_asar: Path,
    candidate_executable: Path,
    check_paths: list[Path],
) -> dict:
    errors: list[str] = []
    red: list[str] = []
    checks: list[dict] = []
    observed_check_ids: set[str] = set()
    try:
        recipe = load_json(recipe_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        recipe = {}
        errors.append(f"recipe unreadable: {error}")
    try:
        detect = load_json(detect_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        detect = {}
        errors.append(f"detect report unreadable: {error}")
    for required in ("packageFullName", "sourceAsarSha256"):
        if not detect.get(required):
            errors.append(f"detect report missing {required}")
    for path in check_paths:
        try:
            payload = load_json(path)
            report_check_ids = passed_check_ids(payload)
            observed_check_ids.update(report_check_ids)
            item = {
                "name": path.stem,
                "report": artifact_record(path),
                "ok": payload.get("ok") is True,
                "checkIds": sorted(report_check_ids),
            }
            checks.append(item)
            if payload.get("ok") is not True:
                red.append(f"check is not PASS: {path.name}")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            errors.append(f"check report unreadable: {path}: {error}")
    supplied_reports = {Path(item["report"]["path"]).name for item in checks}
    required_reports = set(recipe.get("verification", {}).get("requiredReports", []))
    missing_reports = sorted(required_reports - supplied_reports)
    if missing_reports:
        errors.append("required check reports were not supplied: " + ", ".join(missing_reports))
    verification = recipe.get("verification", {})
    required_check_ids = set(verification.get("requiredCheckIds", []))
    required_check_ids.update(verification.get("requiredWireCases", []))
    required_check_ids.update(verification.get("requiredPluginChecks", []))
    missing_check_ids = sorted(required_check_ids - observed_check_ids)
    if missing_check_ids:
        errors.append("required semantic check IDs were not supplied: " + ", ".join(missing_check_ids))
    artifacts: dict[str, dict] = {}
    for name, path in (
        ("recipe", recipe_path),
        ("detectReport", detect_path),
        ("snapshotManifest", snapshot_manifest),
        ("sourceAsar", source_asar),
        ("candidateAsar", candidate_asar),
        ("candidateExecutable", candidate_executable),
    ):
        try:
            artifacts[name] = artifact_record(path)
        except OSError as error:
            errors.append(f"required artifact unreadable: {path}: {error}")
    source_record = artifacts.get("sourceAsar", {})
    if source_record and detect.get("sourceAsarSha256"):
        if str(source_record.get("sha256", "")).lower() != str(detect["sourceAsarSha256"]).lower():
            red.append("source app.asar hash no longer matches the detection report")
    recipe_application = recipe.get("application", {})
    if recipe:
        if str(recipe_application.get("packageFullName")) != str(detect.get("packageFullName")):
            red.append("recipe package identity does not match the detection report")
        if str(recipe_application.get("sourceAsarSha256", "")).lower() != str(detect.get("sourceAsarSha256", "")).lower():
            red.append("recipe source ASAR does not match the detection report")
        patcher_path = recipe_path.parent / str(recipe.get("patcher", {}).get("entrypoint", ""))
        try:
            artifacts["patcher"] = artifact_record(patcher_path)
            expected = recipe.get("patcher", {}).get("sha256")
            if expected and artifacts["patcher"]["sha256"] != expected:
                red.append("patcher hash does not match the recipe")
        except OSError as error:
            errors.append(f"recipe patcher unreadable: {error}")
    if errors:
        status = "ERROR"
    elif red:
        status = "RED"
    else:
        status = "PASS"
    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "release": {
            "releaseId": recipe.get("releaseId"),
            "recipeSha256": artifacts.get("recipe", {}).get("sha256"),
            "patcherSha256": artifacts.get("patcher", {}).get("sha256"),
            "requiredReports": sorted(required_reports),
            "requiredCheckIds": sorted(required_check_ids),
        },
        "source": {
            "packageFullName": detect.get("packageFullName"),
            "packageVersion": detect.get("packageVersion"),
            "sourceAsarSha256": detect.get("sourceAsarSha256"),
        },
        "artifacts": artifacts,
        "checks": checks,
        "redReasons": red,
        "errorReasons": errors,
    }


def append_ledger(path: Path, verdict_path: Path, verdict: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": verdict["createdAt"],
        "status": verdict["status"],
        "packageFullName": verdict["source"].get("packageFullName"),
        "sourceAsarSha256": verdict["source"].get("sourceAsarSha256"),
        "candidateAsarSha256": verdict.get("artifacts", {}).get("candidateAsar", {}).get("sha256"),
        "snapshotManifestSha256": verdict.get("artifacts", {}).get("snapshotManifest", {}).get("sha256"),
        "verdictPath": str(verdict_path.resolve()),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def verify_verdict(path: Path) -> dict:
    try:
        verdict = load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return {"ok": False, "failures": [f"verdict unreadable: {error}"]}
    failures: list[str] = []
    if verdict.get("status") != "PASS":
        failures.append(f"verdict status is not PASS: {verdict.get('status')}")
    for name, artifact in verdict.get("artifacts", {}).items():
        candidate = Path(str(artifact.get("path", "")))
        if not candidate.exists():
            failures.append(f"bound artifact disappeared: {name}")
            continue
        if candidate.stat().st_size != artifact.get("size") or sha256(candidate) != artifact.get("sha256"):
            failures.append(f"bound artifact changed: {name}")
    for check in verdict.get("checks", []):
        if check.get("ok") is not True:
            failures.append(f"bound check was not PASS: {check.get('name')}")
        report = check.get("report", {})
        candidate = Path(str(report.get("path", "")))
        if not candidate.exists() or sha256(candidate) != report.get("sha256"):
            failures.append(f"bound check report changed: {check.get('name')}")
    required_check_ids = set(verdict.get("release", {}).get("requiredCheckIds", []))
    observed_check_ids = {
        str(check_id)
        for check in verdict.get("checks", [])
        if check.get("ok") is True
        for check_id in check.get("checkIds", [])
    }
    missing_check_ids = sorted(required_check_ids - observed_check_ids)
    if missing_check_ids:
        failures.append("bound PASS reports lack required semantic check IDs: " + ", ".join(missing_check_ids))
    return {"ok": not failures, "status": verdict.get("status"), "failures": sorted(set(failures))}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue")
    issue.add_argument("--recipe", type=Path, required=True)
    issue.add_argument("--detect", type=Path, required=True)
    issue.add_argument("--snapshot-manifest", type=Path, required=True)
    issue.add_argument("--source-asar", type=Path, required=True)
    issue.add_argument("--candidate-asar", type=Path, required=True)
    issue.add_argument("--candidate-executable", type=Path, required=True)
    issue.add_argument("--check", type=Path, action="append", required=True)
    issue.add_argument("--output", type=Path, required=True)
    issue.add_argument("--ledger", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--verdict", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "issue":
        verdict = build_verdict(
            args.recipe,
            args.detect,
            args.snapshot_manifest,
            args.source_asar,
            args.candidate_asar,
            args.candidate_executable,
            args.check,
        )
        atomic_json(args.output, verdict)
        append_ledger(args.ledger, args.output, verdict)
        result = verdict
        exit_code = 0 if verdict["status"] == "PASS" else 2
    else:
        result = verify_verdict(args.verdict)
        exit_code = 0 if result["ok"] else 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
