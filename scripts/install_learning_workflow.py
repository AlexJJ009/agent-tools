#!/usr/bin/env python3
"""Install, check, or roll back one local learning workflow candidate.

Run this on the target Linux/WSL profile. The installer copies the runtime and
skills, never runs the repository's broad install.sh, and does not establish
that a host has trusted or invoked the optional hooks.
"""

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
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    "teaching-reconstruction", "teaching-dag-builder", "evidence-anchor",
    "retrieval-practice", "learning-artifact-compiler", "academic-writing", "task-routing",
)
OLD_SKILLS = SKILLS[:5]
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")
MARKER = "learning-workflow/1"


class InstallError(RuntimeError):
    pass


def digest(path: Path) -> str:
    if path.is_symlink():
        return "link:" + os.readlink(path)
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    values = []
    for child in sorted(path.rglob("*")):
        if "__pycache__" in child.parts or child.suffix == ".pyc":
            continue
        if child.is_file() or child.is_symlink():
            values.append((child.relative_to(path).as_posix(), digest(child)))
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def target_guard(home: Path) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "scripts/codex_target_guard.py"),
               "--platform", "auto", "--codex-home", str(home / ".codex"),
               "--cc-switch-db", str(home / ".cc-switch/cc-switch.db"),
               "--path-only", "--allow-missing-config", "--allow-missing-cc-switch",
               "--skip-cc-switch-read-check", "--json"]
    env = dict(os.environ, HOME=str(home))
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    if result.returncode:
        raise InstallError("target guard rejected profile: " + result.stderr.strip())
    return json.loads(result.stdout)


def source_files() -> list[tuple[Path, Path]]:
    sources = [(ROOT / "learning_workflow", Path("learning_workflow")),
               (ROOT / "project_adapters/read_papers", Path("project_adapters/read_papers"))]
    sources += [(ROOT / "skills" / name, Path("skills") / name) for name in SKILLS]
    sources.append((ROOT / "skills/work-report/references/writing-contract.md",
                    Path("skills/work-report/references/writing-contract.md")))
    sources.append((ROOT / "shared/writing/reader-facing-contract.md",
                    Path("shared/writing/reader-facing-contract.md")))
    for source, _ in sources:
        if not source.exists():
            raise InstallError(f"missing source: {source}")
    if (ROOT / "skills/work-report/references/writing-contract.md").read_bytes() != (ROOT / "shared/writing/reader-facing-contract.md").read_bytes():
        raise InstallError("generated writing contract differs from canonical source")
    return sources


def link_plan(home: Path, bundle: Path, read_papers_root: Path | None) -> dict[Path, Path]:
    links = {home / ".local/bin/learning-workflow": bundle / "bin/learning-workflow"}
    for name in SKILLS:
        for base in (home / ".agents/skills", home / ".claude/skills"):
            links[base / name] = bundle / "skills" / name
    if read_papers_root is not None:
        if not read_papers_root.is_dir():
            raise InstallError(f"ReadPapers project does not exist: {read_papers_root}")
        adapter = bundle / "project_adapters/read_papers/read-paper"
        for base in (read_papers_root / ".agents/skills", read_papers_root / ".claude/skills"):
            links[base / "read-paper"] = adapter
    return links


def old_global_paper_links(home: Path, exact_source: Path | None) -> dict[Path, str]:
    """Inventory only the three known user-level aliases, never project skills."""
    removed = {}
    for base in (home / ".agents/skills", home / ".codex/skills", home / ".claude/skills"):
        path = base / "read-paper"
        if not path.exists() and not path.is_symlink():
            continue
        if not path.is_symlink() or exact_source is None or path.resolve(strict=False) != exact_source:
            raise InstallError(f"global read-paper target is occupied or differs from the explicit legacy source: {path}")
        removed[path] = os.readlink(path)
    return removed


def legacy_target(path: Path, home: Path, legacy_root: Path | None) -> bool:
    if not path.is_symlink():
        return False
    name = path.name
    if name not in OLD_SKILLS or legacy_root is None:
        return False
    if path.parent not in (home / ".agents/skills", home / ".claude/skills"):
        return False
    return path.resolve(strict=False) == (legacy_root / "skills" / name).resolve(strict=False)


def managed_group(event: str, bundle: Path, home: Path) -> dict[str, Any]:
    command = shlex.join([sys.executable, str(bundle / "bin/learning-workflow-hook"),
                          "--state-root", str(home / ".local/state/learning-workflow/hooks")])
    handler = {"type": "command", "command": command, "timeout": 30,
               "statusMessage": MARKER}
    group: dict[str, Any] = {"hooks": [handler]}
    if event == "SessionStart":
        group["matcher"] = "startup|resume|clear|compact"
    elif event in ("PreToolUse", "PostToolUse"):
        group["matcher"] = ".*"
    return group


def load_hooks(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise InstallError(f"hooks target is a symlink; preserve it: {path}")
    if not path.exists():
        return {"hooks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError(f"invalid hooks JSON preserved: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise InstallError("invalid hooks JSON preserved: expected an object with hooks object")
    data.setdefault("hooks", {})
    for event in EVENTS:
        if event in data["hooks"] and not isinstance(data["hooks"][event], list):
            raise InstallError(f"invalid hooks JSON preserved: hooks.{event} must be a list")
    return data


def update_hooks(data: dict[str, Any], bundle: Path, home: Path, *, remove: bool) -> bool:
    changed = False
    for event in EVENTS:
        expected = managed_group(event, bundle, home)
        groups = data["hooks"].get(event, [])
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if (isinstance(handlers, list) and any(isinstance(handler, dict)
                and handler.get("statusMessage") == MARKER for handler in handlers)
                    and group != expected):
                raise InstallError(f"managed hook changed or conflicts in {event}; preserve it")
        if remove:
            kept = [group for group in groups if group != expected]
            if len(kept) != len(groups):
                changed = True
                if kept:
                    data["hooks"][event] = kept
                else:
                    data["hooks"].pop(event, None)
        elif expected not in groups:
            data["hooks"].setdefault(event, []).append(expected)
            changed = True
    return changed


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".learning-workflow-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def copy_payload(bundle: Path) -> None:
    for source, relative in source_files():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, target)
    bindir = bundle / "bin"
    bindir.mkdir()
    for name, module in (("learning-workflow", "learning_workflow"),
                         ("learning-workflow-hook", "learning_workflow.hooks")):
        (bindir / name).write_text(
            "#!/usr/bin/env python3\nimport runpy, sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            f"runpy.run_module({module!r}, run_name='__main__')\n", encoding="utf-8")
        (bindir / name).chmod(0o755)


def install(home: Path, *, legacy_root: Path | None, read_papers_root: Path | None,
            legacy_read_paper_dir: Path | None = None,
            legacy_global_read_paper_source: Path | None = None,
            with_hooks: bool) -> dict[str, Any]:
    guard = target_guard(home)
    sources = source_files()
    bundle = home / ".local/share/agent-tools/learning-workflow"
    state = home / ".local/state/learning-workflow/install.json"
    legacy_backup = home / ".local/state/learning-workflow/legacy-read-paper"
    links = link_plan(home, bundle, read_papers_root)
    global_paper_links = old_global_paper_links(home, legacy_global_read_paper_source)
    if global_paper_links and read_papers_root is None:
        raise InstallError("deactivating global read-paper aliases requires an explicit ReadPapers project adapter target")
    if legacy_read_paper_dir is not None and (read_papers_root is None or legacy_read_paper_dir not in links):
        raise InstallError("legacy ReadPapers adapter path must be one of the selected project's skill targets")
    for path in (bundle, state, legacy_backup, home / ".codex/hooks.json"):
        if not path.parent.resolve(strict=False).is_relative_to(home):
            raise InstallError(f"profile destination escapes its root: {path}")
    for path in links:
        root = read_papers_root if read_papers_root and path.is_relative_to(read_papers_root) else home
        if not path.parent.resolve(strict=False).is_relative_to(root):
            raise InstallError(f"skill destination escapes its root: {path}")
    for path in global_paper_links:
        if not path.parent.resolve(strict=False).is_relative_to(home):
            raise InstallError(f"global read-paper alias escapes profile: {path}")
    if state.exists() or bundle.exists() or bundle.is_symlink():
        raise InstallError("candidate is already installed; check or roll back before reinstalling")
    if legacy_backup.exists() or legacy_backup.is_symlink():
        raise InstallError(f"legacy adapter backup already exists: {legacy_backup}")
    previous = {}
    for path, target in links.items():
        if path.is_symlink() and path.resolve(strict=False) == target:
            raise InstallError(f"untracked candidate link exists: {path}")
        if path.exists() or path.is_symlink():
            if legacy_target(path, home, legacy_root):
                previous[str(path)] = {"kind": "symlink", "target": os.readlink(path)}
            elif (legacy_read_paper_dir is not None and path == legacy_read_paper_dir
                  and read_papers_root is not None and path.name == "read-paper"
                  and path.parent in (read_papers_root / ".agents/skills", read_papers_root / ".claude/skills")
                  and path.is_dir() and not path.is_symlink()):
                previous[str(path)] = {"kind": "directory", "backup": str(legacy_backup),
                                       "digest": digest(path)}
            else:
                raise InstallError(f"unmanaged target preserved: {path}")
        else:
            previous[str(path)] = {"kind": "absent"}
    hooks_path = home / ".codex/hooks.json"
    hooks_preexisting = hooks_path.exists()
    hook_data = load_hooks(hooks_path) if with_hooks else None
    if hook_data is not None:
        update_hooks(json.loads(json.dumps(hook_data)), bundle, home, remove=False)
    with tempfile.TemporaryDirectory(prefix="learning-workflow-stage-") as temporary:
        staged = Path(temporary) / "learning-workflow"
        staged.mkdir()
        copy_payload(staged)
        payload_digest = digest(staged)
        # Check the staged launchers before writing any profile entry.
        run = subprocess.run([sys.executable, str(staged / "bin/learning-workflow"), "--help"],
                             capture_output=True, text=True)
        if run.returncode:
            raise InstallError("staged runtime cannot start: " + run.stderr.strip())
        bundle.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(staged, bundle, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        except Exception:
            if bundle.is_dir():
                shutil.rmtree(bundle)
            raise
    try:
        for path, target in links.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                path.unlink()
            elif path.is_dir() and previous[str(path)]["kind"] == "directory":
                legacy_backup.parent.mkdir(parents=True, exist_ok=True)
                path.rename(legacy_backup)
            path.symlink_to(target, target_is_directory=path.name != "learning-workflow")
        for path in global_paper_links:
            path.unlink()
        if with_hooks and hook_data is not None:
            if update_hooks(hook_data, bundle, home, remove=False):
                atomic_json(hooks_path, hook_data)
        manifest = {"schema_version": MARKER, "bundle": str(bundle), "bundle_digest": payload_digest,
                    "source_digest": {str(relative): digest(source) for source, relative in sources},
                    "links": {str(path): {**prior, "installed_target": str(links[path])}
                              for path, prior in ((Path(k), v) for k, v in previous.items())},
                    "deactivated_global_read_paper": {str(path): target for path, target in global_paper_links.items()},
                    "read_papers_root": str(read_papers_root) if read_papers_root else None,
                    "hooks_installed": with_hooks, "hooks_preexisting": hooks_preexisting,
                    "guard": guard}
        atomic_json(state, manifest)
    except Exception:
        # The manifest has not yet been published. Restore only links this call replaced.
        for raw, prior in previous.items():
            path = Path(raw)
            if path.is_symlink() and path.resolve(strict=False) == links[path]:
                path.unlink()
            if prior["kind"] == "symlink" and not path.exists() and not path.is_symlink():
                path.symlink_to(prior["target"])
            if prior["kind"] == "directory" and not path.exists() and Path(prior["backup"]).exists():
                Path(prior["backup"]).rename(path)
        for path, target in global_paper_links.items():
            if not path.exists() and not path.is_symlink():
                path.symlink_to(target, target_is_directory=True)
        if with_hooks and hooks_path.exists():
            current = load_hooks(hooks_path)
            if update_hooks(current, bundle, home, remove=True):
                if not hooks_preexisting and current == {"hooks": {}}:
                    hooks_path.unlink()
                else:
                    atomic_json(hooks_path, current)
        shutil.rmtree(bundle)
        raise
    return {"status": "installed", "bundle": str(bundle), "skills": list(SKILLS),
            "read_papers_scope": str(read_papers_root) if read_papers_root else None,
            "global_read_paper_aliases_deactivated": len(global_paper_links),
            "launcher": str(home / ".local/bin/learning-workflow"),
            "hooks_configured": with_hooks, "hook_trust": "not_verified", "source_items": len(sources)}


def installed_manifest(home: Path) -> tuple[Path, dict[str, Any]]:
    path = home / ".local/state/learning-workflow/install.json"
    if not path.is_file():
        raise InstallError("no managed learning workflow installation")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != MARKER or data.get("bundle") != str(home / ".local/share/agent-tools/learning-workflow"):
        raise InstallError("invalid managed install manifest")
    return path, data


def check(home: Path) -> dict[str, Any]:
    guard = target_guard(home)
    _, manifest = installed_manifest(home)
    bundle = Path(manifest["bundle"])
    if not bundle.is_dir() or digest(bundle) != manifest["bundle_digest"]:
        raise InstallError("installed bundle is missing or changed")
    for raw, entry in manifest["links"].items():
        path = Path(raw)
        if not path.is_symlink() or path.resolve(strict=False) != Path(entry["installed_target"]):
            raise InstallError(f"managed skill link is missing or changed: {path}")
    for raw in manifest.get("deactivated_global_read_paper", {}):
        path = Path(raw)
        if path.exists() or path.is_symlink():
            raise InstallError(f"deactivated global read-paper alias was recreated: {path}")
    run = subprocess.run([sys.executable, str(bundle / "bin/learning-workflow"), "--help"],
                         capture_output=True, text=True)
    if run.returncode:
        raise InstallError("installed runtime cannot start: " + run.stderr.strip())
    hooks_present = False
    if manifest["hooks_installed"]:
        data = load_hooks(home / ".codex/hooks.json")
        hooks_present = all(managed_group(event, bundle, home) in data["hooks"].get(event, []) for event in EVENTS)
        if not hooks_present:
            raise InstallError("requested managed hook groups are missing or changed")
    return {"status": "pass", "bundle": str(bundle), "links_checked": len(manifest["links"]),
            "global_read_paper_aliases_deactivated": len(manifest.get("deactivated_global_read_paper", {})),
            "hooks_configured": hooks_present, "hook_trust": "not_verified", "guard": guard}


def rollback(home: Path) -> dict[str, Any]:
    target_guard(home)
    state, manifest = installed_manifest(home)
    bundle = Path(manifest["bundle"])
    if not bundle.is_dir() or digest(bundle) != manifest["bundle_digest"]:
        raise InstallError("installed bundle changed; preserve it and resolve manually")
    for raw, prior in manifest["links"].items():
        path = Path(raw)
        root = Path(manifest["read_papers_root"]) if manifest["read_papers_root"] and path.is_relative_to(Path(manifest["read_papers_root"])) else home
        if not path.parent.resolve(strict=False).is_relative_to(root):
            raise InstallError(f"skill destination escapes its root: {path}")
        if not path.is_symlink() or path.resolve(strict=False) != Path(prior["installed_target"]):
            raise InstallError(f"managed link changed; preserve it and resolve manually: {path}")
        if prior["kind"] == "directory":
            backup = Path(prior["backup"])
            if not backup.is_dir() or digest(backup) != prior["digest"]:
                raise InstallError(f"legacy adapter backup changed; preserve it: {backup}")
    for raw in manifest.get("deactivated_global_read_paper", {}):
        path = Path(raw)
        if path.exists() or path.is_symlink():
            raise InstallError(f"deactivated global read-paper alias was replaced; preserve it: {path}")
    hooks_path = home / ".codex/hooks.json"
    hook_data = load_hooks(hooks_path) if manifest["hooks_installed"] else None
    if hook_data is not None:
        update_hooks(json.loads(json.dumps(hook_data)), bundle, home, remove=True)
    if hook_data is not None and update_hooks(hook_data, bundle, home, remove=True):
        if not manifest.get("hooks_preexisting") and hook_data == {"hooks": {}}:
            hooks_path.unlink()
        else:
            atomic_json(hooks_path, hook_data)
    for raw, prior in manifest["links"].items():
        path = Path(raw)
        path.unlink()
        if prior["kind"] == "symlink":
            path.symlink_to(prior["target"])
        elif prior["kind"] == "directory":
            Path(prior["backup"]).rename(path)
    for raw, target in manifest.get("deactivated_global_read_paper", {}).items():
        Path(raw).symlink_to(target, target_is_directory=True)
    shutil.rmtree(bundle)
    state.unlink()
    return {"status": "rolled_back", "links_restored": len(manifest["links"]),
            "global_read_paper_aliases_restored": len(manifest.get("deactivated_global_read_paper", {})),
            "hooks_removed": bool(manifest["hooks_installed"]), "foreign_settings_preserved": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--legacy-root", type=Path, help="exact old teaching suite checkout whose five skill links may be replaced")
    parser.add_argument("--read-papers-root", type=Path, help="explicit local ReadPapers project for its read-paper adapter")
    parser.add_argument("--legacy-read-paper-dir", type=Path,
                        help="exact existing ReadPapers read-paper skill directory to back up and replace")
    parser.add_argument("--legacy-global-read-paper-source", type=Path,
                        help="exact old source of matching user-level read-paper symlinks to deactivate")
    parser.add_argument("--with-hooks", action="store_true", help="merge bounded Codex hook definitions; trust remains unverified")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("this installer supports Linux/WSL current user profiles only")
    home = Path.home().resolve()
    try:
        if args.check:
            report = check(home)
        elif args.rollback:
            report = rollback(home)
        else:
            report = install(home, legacy_root=args.legacy_root.resolve() if args.legacy_root else None,
                             read_papers_root=args.read_papers_root.resolve() if args.read_papers_root else None,
                             legacy_read_paper_dir=args.legacy_read_paper_dir.resolve() if args.legacy_read_paper_dir else None,
                             legacy_global_read_paper_source=args.legacy_global_read_paper_source.resolve() if args.legacy_global_read_paper_source else None,
                             with_hooks=args.with_hooks)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0
    except (InstallError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
