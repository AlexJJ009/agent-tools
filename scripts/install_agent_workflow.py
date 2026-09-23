#!/usr/bin/env python3
"""Install/check the local Linux/WSL agent workflow suite without changing Codex config."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
MARKER = ".agent-workflow-managed.json"
SUITE = "agent-workflow"
SKILLS = (
    "intent-to-contract",
    "infra-verification",
    "cleaner",
    "acceptance-gate",
    "reviewer-brief",
)
REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/licenses/spec-kit-MIT.txt",
    "references/licenses/superpowers-MIT.txt",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): sha256(p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts and p.name != MARKER and p.suffix != ".pyc"
    }


def runtime_files(root: Path) -> dict[str, str]:
    package = root / "agent_workflow"
    if not package.is_dir():
        raise RuntimeError(f"missing runtime package: {package}")
    return files(package)


def reject_parent_escape(path: Path, home: Path) -> None:
    parent = path.parent.resolve()
    if not parent.is_relative_to(home):
        raise RuntimeError(f"target directory escapes the current Unix profile: {parent}")


def run_target_guard(home: Path) -> None:
    guard = [
        sys.executable,
        str(ROOT / "scripts/codex_target_guard.py"),
        "--platform",
        "auto",
        "--codex-home",
        str(home / ".codex"),
        "--cc-switch-db",
        str(home / ".cc-switch/cc-switch.db"),
        "--path-only",
        "--allow-missing-config",
        "--allow-missing-cc-switch",
        "--skip-cc-switch-read-check",
        "--json",
    ]
    result = subprocess.run(guard, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("target guard rejected installation: " + result.stdout + result.stderr)


def expected_launcher(runtime_target: Path) -> str:
    return (
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        f"PYTHONPATH={shlex.quote(str(runtime_target))} exec {shlex.quote(sys.executable)} -P -m agent_workflow.cli \"$@\"\n"
    )


def prior_expected_launchers(runtime_target: Path) -> set[str]:
    return {
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        f"PYTHONPATH={json.dumps(str(runtime_target))} exec {json.dumps(sys.executable)} -m agent_workflow.cli \"$@\"\n"
    }


def managed_launcher_contents(runtime_target: Path) -> set[str]:
    return {expected_launcher(runtime_target), *prior_expected_launchers(runtime_target)}


def validate_sources() -> dict[str, dict[str, str]]:
    source_hashes: dict[str, dict[str, str]] = {}
    canonical = ROOT / "skills/work-report/references/writing-contract.md"
    packaged = ROOT / "skills/reviewer-brief/references/writing-contract.md"
    if not packaged.is_file():
        raise RuntimeError("missing generated reviewer-brief writing contract")
    if canonical.is_file() and packaged.read_bytes() != canonical.read_bytes():
        raise RuntimeError("generated writing contract differs; run work-report/scripts/sync_writing_contract.py --write")
    for skill in SKILLS:
        source = ROOT / "skills" / skill
        if not source.is_dir():
            raise RuntimeError(f"missing skill source: {source}")
        for rel in REQUIRED_SKILL_FILES:
            if not (source / rel).is_file():
                raise RuntimeError(f"missing skill source: {skill}/{rel}")
        source_hashes[f"skills/{skill}"] = files(source)
    source_hashes["runtime/agent_workflow"] = runtime_files(ROOT)
    return source_hashes


def load_marker(path: Path) -> dict[str, object] | None:
    marker = path / MARKER
    if not marker.is_file():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"invalid managed marker at {marker}: {exc}") from exc
    if data.get("suite") != SUITE:
        raise RuntimeError(f"managed marker at {marker} does not belong to {SUITE}")
    return data


def reject_collisions(home: Path, runtime_target: Path, launcher: Path, *, check: bool) -> None:
    for skill in SKILLS:
        legacy = home / ".codex/skills" / skill
        target = home / ".agents/skills" / skill
        if legacy.exists() or legacy.is_symlink():
            raise RuntimeError(f"duplicate legacy skill location exists: {legacy}; resolve explicitly")
        reject_parent_escape(target, home)
        if target.exists() or target.is_symlink():
            if target.is_symlink() or load_marker(target) is None:
                raise RuntimeError(f"unmanaged skill exists: {target}")
    reject_parent_escape(runtime_target, home)
    reject_parent_escape(launcher, home)
    if runtime_target.exists() or runtime_target.is_symlink():
        if runtime_target.is_symlink() or load_marker(runtime_target) is None:
            raise RuntimeError(f"unmanaged runtime exists: {runtime_target}")
    marker = load_marker(runtime_target) if runtime_target.is_dir() else None
    if launcher.exists() or launcher.is_symlink():
        if launcher.is_symlink():
            raise RuntimeError(f"unmanaged launcher symlink exists: {launcher}")
        if marker is None and not check:
            raise RuntimeError(f"unmanaged launcher exists: {launcher}")
        if marker is not None and launcher.read_text(encoding="utf-8") not in managed_launcher_contents(runtime_target):
            raise RuntimeError(f"managed launcher was modified: {launcher}")


def verify_installed(home: Path, expected: dict[str, dict[str, str]], runtime_target: Path, launcher: Path) -> None:
    for skill in SKILLS:
        target = home / ".agents/skills" / skill
        if not target.is_dir():
            raise RuntimeError(f"installed skill missing: {target}")
        actual = files(target)
        if actual != expected[f"skills/{skill}"]:
            raise RuntimeError(f"installed skill differs from source: {skill}")
        marker = load_marker(target)
        if marker is None or marker.get("files") != expected[f"skills/{skill}"]:
            raise RuntimeError(f"installed marker differs from source: {skill}")
    package = runtime_target / "agent_workflow"
    if not package.is_dir() or files(package) != expected["runtime/agent_workflow"]:
        raise RuntimeError("installed runtime differs from source or is missing")
    marker = load_marker(runtime_target)
    if marker is None or marker.get("files") != expected["runtime/agent_workflow"]:
        raise RuntimeError("runtime marker differs from source")
    if not launcher.is_file() or launcher.read_text(encoding="utf-8") != expected_launcher(runtime_target):
        raise RuntimeError("launcher is missing or differs from managed content")
    run = subprocess.run([str(launcher), "--help"], cwd=str(runtime_target), capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError("installed runtime cannot start: " + run.stderr)


def write_marker(path: Path, payload: dict[str, object]) -> None:
    (path / MARKER).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_skill(source: Path, staged_parent: Path, skill: str, expected: dict[str, str]) -> Path:
    staged = staged_parent / skill
    shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", MARKER))
    canonical = ROOT / "skills/work-report/references/writing-contract.md"
    if skill == "reviewer-brief" and canonical.is_file():
        shutil.copyfile(canonical, staged / "references/writing-contract.md")
    write_marker(staged, {"suite": SUITE, "kind": "skill", "skill": skill, "source": str(source), "files": expected})
    return staged


def copy_runtime(staged_parent: Path, expected: dict[str, str]) -> Path:
    staged = staged_parent / "agent-workflow"
    staged.mkdir()
    shutil.copytree(ROOT / "agent_workflow", staged / "agent_workflow", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    write_marker(staged, {"suite": SUITE, "kind": "runtime", "source": str(ROOT / "agent_workflow"), "files": expected})
    return staged


def replace_tree(staged: Path, target: Path, backup_root: Path) -> Path | None:
    old = None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup_root.mkdir(parents=True, exist_ok=True)
        old = backup_root / (target.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        target.rename(old)
    try:
        staged.rename(target)
    except OSError:
        if old is not None and not target.exists():
            old.rename(target)
        raise
    return old


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="read-only source/install consistency check")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required (the launcher uses Python's -P option)")
    if platform.system() != "Linux":
        parser.error("this installer supports the current Linux/WSL user only")
    home = Path.home().resolve()
    runtime_target = home / ".local/share/agent-workflow"
    launcher = home / ".local/bin/agent-workflow"
    state = home / ".local/state/agent-workflow"
    published: list[tuple[Path, Path | None]] = []
    old_launcher: bytes | None = None
    old_launcher_mode: int | None = None
    launcher_written = False
    try:
        run_target_guard(home)
        expected = validate_sources()
        reject_collisions(home, runtime_target, launcher, check=args.check)
        reject_parent_escape(state, home)
        if state.is_symlink():
            raise RuntimeError(f"state directory must not be a symlink: {state}")
        reject_parent_escape(state / "install-backups" / "entry", home)
        if args.check:
            verify_installed(home, expected, runtime_target, launcher)
            print(json.dumps({"status": "pass", "runtime": str(runtime_target), "launcher": str(launcher), "skills": list(SKILLS)}))
            return 0
        state.mkdir(parents=True, exist_ok=True)
        state.chmod(0o700)
        with tempfile.TemporaryDirectory(prefix="install-", dir=state) as temporary:
            temp = Path(temporary)
            staged_runtime = copy_runtime(temp, expected["runtime/agent_workflow"])
            staged_skills = [
                copy_skill(ROOT / "skills" / skill, temp, skill, expected[f"skills/{skill}"])
                for skill in SKILLS
            ]
            env = os.environ.copy()
            env["PYTHONPATH"] = str(staged_runtime)
            run = subprocess.run([sys.executable, "-P", "-m", "agent_workflow.cli", "--help"], cwd=str(staged_runtime), env=env, capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError("runtime preflight failed: " + run.stderr)
            backup_root = state / "install-backups"
            published.append((runtime_target, replace_tree(staged_runtime, runtime_target, backup_root)))
            for staged, skill in zip(staged_skills, SKILLS):
                target = home / ".agents/skills" / skill
                published.append((target, replace_tree(staged, target, backup_root)))
        launcher.parent.mkdir(parents=True, exist_ok=True)
        if launcher.exists():
            old_launcher = launcher.read_bytes()
            old_launcher_mode = launcher.stat().st_mode
        launcher.write_text(expected_launcher(runtime_target), encoding="utf-8")
        launcher.chmod(0o755)
        launcher_written = True
        verify_installed(home, expected, runtime_target, launcher)
        print(json.dumps({"status": "installed", "runtime": str(runtime_target), "launcher": str(launcher), "skills": list(SKILLS)}))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        for target, old in reversed(published):
            try:
                if target.exists():
                    rejected = state / ("rejected-" + target.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
                    target.rename(rejected)
                if old is not None and not target.exists():
                    old.rename(target)
            except OSError as rollback_error:
                exc = RuntimeError(f"{exc}; rollback incomplete: {rollback_error}")
        try:
            if old_launcher is not None:
                launcher.write_bytes(old_launcher)
                if old_launcher_mode is not None:
                    launcher.chmod(old_launcher_mode)
            elif launcher_written and launcher.exists():
                launcher.unlink()
        except OSError as rollback_error:
            exc = RuntimeError(f"{exc}; launcher rollback incomplete: {rollback_error}")
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
