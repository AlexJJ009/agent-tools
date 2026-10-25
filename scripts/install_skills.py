#!/usr/bin/env python3
"""Link the plain Agent Tools learning and writing skills into a client skills directory.

The skills are ordinary directories shipped in the install root
(~/.local/lib/agent-tools/skills/<name>); they carry no runtime, hooks or state.
This installer only creates discovery symlinks. It replaces links left by earlier
releases (bundle or data-root locations), removes such links for retired skill
names, and preserves everything else. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import install_layout as layout  # noqa: E402

KEPT = ("academic-writing", "teaching-reconstruction", "evidence-anchor", "retrieval-practice",
        "teaching-dag-builder", "learning-artifact-compiler", "task-routing")
# Skills removed by ADR 0012; only discovery symlinks that point at agent-tools locations are removed.
RETIRED = ("intent-to-contract", "acceptance-gate", "infra-verification", "reviewer-brief", "cleaner",
           "work-report", "knowledge-deposition-doc", "codex-win11-patch-safety")


def run_target_guard(home: Path) -> None:
    guard = [sys.executable, str(ROOT / "scripts/codex_target_guard.py"), "--platform", "auto",
             "--codex-home", str(home / ".codex"), "--cc-switch-db", str(home / ".cc-switch/cc-switch.db"),
             "--path-only", "--allow-missing-config", "--allow-missing-cc-switch",
             "--skip-cc-switch-read-check", "--json"]
    result = subprocess.run(guard, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("target guard rejected installation: " + result.stdout + result.stderr)


def source_dir(install: Path, name: str) -> Path:
    path = install / "skills" / name
    if not (path / "SKILL.md").is_file():
        raise ValueError(f"skill source missing: {path}; run scripts/install.sh to install the software copy")
    return path


def owned_roots(home: Path, install: Path) -> tuple[Path, ...]:
    """Locations whose symlink targets earlier releases created and this installer may replace."""
    return (install, home / layout.LEGACY_DATA_LAYOUT, home / ".local/share/agent-workflow", home / ".agents/skills")


def _target(link: Path) -> Path:
    return Path(os.path.abspath(link.parent / os.readlink(link)))


def _owned(link: Path, roots: tuple[Path, ...]) -> bool:
    target = _target(link)
    return not target.exists() or any(target == root or target.is_relative_to(root) for root in roots)


def link_skills(home: Path, base: Path, install: Path) -> dict[str, list[str]]:
    """Make base/<kept> point at the install root and drop owned links to retired skills."""
    home, base, install = Path(home), Path(base), Path(install)
    if not base.resolve(strict=False).is_relative_to(home.resolve()):
        raise ValueError(f"skills directory escapes profile: {base}")
    roots = owned_roots(home, install)
    targets = {name: source_dir(install, name) for name in KEPT}  # refuse before any write
    result: dict[str, list[str]] = {"linked": [], "unchanged": [], "removed": [], "preserved": []}
    for name, target in targets.items():
        link = base / name
        if link.is_symlink() and _target(link) == target:
            result["unchanged"].append(name)
        elif link.is_symlink() and _owned(link, roots):
            link.unlink()
            link.symlink_to(target, target_is_directory=True)
            result["linked"].append(name)
        elif link.exists() or link.is_symlink():
            result["preserved"].append(name)
        else:
            base.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
            result["linked"].append(name)
    result["removed"] = prune_retired(home, base, install)
    return result


def prune_retired(home: Path, base: Path, install: Path) -> list[str]:
    """Remove discovery symlinks for retired skills that point at agent-tools locations."""
    roots = owned_roots(Path(home), Path(install))
    removed = []
    for name in RETIRED:
        link = Path(base) / name
        if link.is_symlink() and _owned(link, roots):
            link.unlink()
            removed.append(name)
    return removed


def check_links(home: Path, base: Path, install: Path) -> list[str]:
    """Names whose link is missing or does not point at the install root."""
    return [name for name in KEPT
            if not (Path(base) / name).is_symlink() or _target(Path(base) / name) != source_dir(install, name)]


def remove_links(base: Path, install: Path) -> list[str]:
    removed = []
    for name in KEPT:
        link = Path(base) / name
        if link.is_symlink() and _target(link) == Path(install) / "skills" / name:
            link.unlink()
            removed.append(name)
    return removed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only: verify the links in ~/.agents/skills")
    args = parser.parse_args(argv)
    home = Path.home().resolve()
    base = home / ".agents/skills"
    try:
        install = layout.install_root(home)
        if args.check:
            drift = check_links(home, base, install)
            print(json.dumps({"status": "drift" if drift else "pass", "skills_dir": str(base), "drift": drift}))
            return 1 if drift else 0
        run_target_guard(home)
        result = link_skills(home, base, install)
        result["removed"] += prune_retired(home, home / ".codex/skills", install)
        print(json.dumps({"status": "installed", "skills_dir": str(base), **result}))
        if result["preserved"]:
            print("preserved existing entries: " + ", ".join(result["preserved"]), file=sys.stderr)
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
