#!/usr/bin/env python3
"""Build the public Win11 proxy relay ZIP from an explicit allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
DIST = ROOT / "dist"
PACKAGE_NAME = "win11-proxy-relay.zip"

ROOT_FILES = (
    "install.ps1",
    "control.ps1",
    "relay.cmd",
    "README.md",
    "tests/check-install.ps1",
)

RUNTIME_FILES = (
    "ai-fallback.py",
    "build-configs.py",
    "enter-supervised-job.ps1",
    "feitu-node-policy.json",
    "phai-reverse-proxy.ps1",
    "probe.py",
    "quality-manager.py",
    "run-server-proxy.ps1",
    "settings.ps1",
    "settings.py",
    "show-quality.py",
    "v2rayn-dashboard.html",
    "tests/test_probe.py",
    "tests/test_quality_manager.py",
    "tests/test_settings.py",
)

FORBIDDEN_PARTS = {
    "__pycache__",
    "state",
    "backup",
    "dist",
}
FORBIDDEN_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".db",
}
FORBIDDEN_NAMES = {
    "server-config.json",
    "normal-template.json",
    "tun-template.json",
    "normal-runtime.json",
    "tun-runtime.json",
    "node-labels.json",
    "quality-manager-state.json",
    "quality-manager-state-status.json",
    "ai-fallback-state.json",
    "ai-fallback-state-status.json",
    "server-cache.db",
    "known_hosts",
    "ssh_config",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_public_path(relative: Path) -> None:
    parts = set(relative.parts)
    if parts & FORBIDDEN_PARTS:
        raise ValueError(f"forbidden package path: {relative}")
    if relative.name in FORBIDDEN_NAMES:
        raise ValueError(f"forbidden package file: {relative}")
    if relative.suffix.lower() in FORBIDDEN_SUFFIXES:
        raise ValueError(f"forbidden package suffix: {relative}")


def collect_files() -> list[tuple[Path, Path]]:
    files: list[tuple[Path, Path]] = []
    missing_required: list[str] = []
    for name in ROOT_FILES:
        source = ROOT / name
        if not source.exists():
            missing_required.append(name)
            continue
        archive = Path(name)
        assert_public_path(archive)
        files.append((source, archive))

    for name in RUNTIME_FILES:
        source = ROOT / "runtime" / name
        if not source.exists():
            missing_required.append(f"runtime/{name}")
            continue
        archive = Path("runtime") / name
        assert_public_path(archive)
        files.append((source, archive))

    guard = REPO_ROOT / "scripts" / "codex_target_guard.py"
    if not guard.exists():
        missing_required.append("scripts/codex_target_guard.py")
    else:
        files.append((guard, Path("support") / "codex_target_guard.py"))

    if missing_required:
        raise FileNotFoundError("missing required package inputs: " + ", ".join(missing_required))
    return sorted(files, key=lambda item: item[1].as_posix())


def build(out: Path) -> dict[str, object]:
    files = collect_files()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    manifest_entries = []
    for source, archive in files:
        manifest_entries.append(
            {
                "path": archive.as_posix(),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
            }
        )

    manifest = {
        "package": out.name,
        "schema": 1,
        "files": manifest_entries,
    }

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
        for source, archive in files:
            package.write(source, archive.as_posix())
        package.writestr("SHA256SUMS.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    manifest["zip_sha256"] = sha256(out)
    manifest_path = out.with_suffix(".SHA256SUMS.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build the public Win11 proxy relay package.")
    parser.add_argument("--out", default=str(DIST / PACKAGE_NAME), help="Output ZIP path.")
    args = parser.parse_args(argv)
    manifest = build(Path(args.out))
    print(json.dumps({"zip": args.out, "zip_sha256": manifest["zip_sha256"], "files": len(manifest["files"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
