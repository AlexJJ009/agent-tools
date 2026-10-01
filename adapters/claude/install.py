"""Claude discovery and context views; shared packages remain authoritative."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from scripts import install_agent_workflow as workflow
from scripts import install_learning_workflow as learning
from adapters.claude import hooks

ROOT = Path(__file__).resolve().parents[2]
STATE = ".local/state/agent-tools/claude/install.json"
CONTEXT = ".local/share/agent-tools/claude/context.md"
RULE = ".claude/rules/agent-tools.md"
NATIVE = ".local/share/agent-tools/claude/native_hook.py"


def native_source() -> bytes:
    return (ROOT / "adapters/claude/native_hook.py").read_bytes()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=".agent-tools-", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_target(path: Path, home: Path) -> None:
    if not path.parent.resolve().is_relative_to(home):
        raise ValueError(f"destination escapes profile: {path}")


def read_settings(home: Path) -> dict:
    path = home / ".claude/settings.json"
    safe_target(path, home)
    if path.is_symlink():
        raise ValueError(f"settings symlink preserved: {path}")
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("settings must be a JSON object")
    return data


def skill_sources(home: Path) -> dict[str, Path]:
    bundle = home / ".local/share/agent-tools/learning-workflow"
    sources = {name: home / ".agents/skills" / name for name in workflow.SKILLS}
    sources.update({name: bundle / "skills" / name for name in learning.SKILLS})
    sources["work-report"] = home / ".agents/skills/work-report"
    for name, source in sources.items():
        if not (source / "SKILL.md").is_file():
            raise ValueError(f"shared skill missing: {name}; run with --install-packages")
    for path in [home / ".local/share/agent-workflow/agent_workflow/hooks.py",
                 bundle / "bin/learning-workflow-hook",
                 sources["work-report"] / "scripts/report_runtime.py"]:
        if not path.is_file():
            raise ValueError(f"shared hook runtime missing: {path}")
    return sources


def context(home: Path, core_source: Path | None = None) -> str:
    contract = home / ".local/share/agent-tools/learning-workflow/shared/writing/reader-facing-contract.md"
    if not contract.is_file():
        raise ValueError(f"shared writing contract missing: {contract}")
    core_import = ""
    if core_source is not None:
        core_source = core_source.resolve()
        if not core_source.is_file():
            raise ValueError(f"Agent Core Claude context missing: {core_source}")
        if (home / ".claude/CLAUDE.md").resolve() != core_source:
            # Preserve the user's global file; Claude expands native imports
            # from the separate managed rules view instead.
            core_import = f"@{core_source.as_posix()}\n\n"
    return ("# Agent Tools — Claude Code adapter\n\n"
            + core_import
            + "Use the installed Agent Tools skills when the current request matches their descriptions. "
            "Their shared source and runtime are authoritative; Claude discovery links are views.\n\n"
            + learning.writing_entry(home, home / ".local/share/agent-tools/learning-workflow")
            + "\nNative hooks supply the actual session_id and workspace. Use those values when binding "
            "a task or route, and reuse the existing process record on resume. "
            "Do not create a separate Claude copy of task state.\n")


def prepare_packages(home: Path) -> None:
    for script, installed in [
        ("install_agent_workflow.py", home / ".local/share/agent-workflow"),
        ("install_work_report.py", home / ".agents/skills/work-report"),
        ("install_learning_workflow.py", home / ".local/state/learning-workflow/install.json"),
    ]:
        # Existing learning candidates have their own upgrade/rollback contract.
        # Check them, rather than silently replacing their installation state.
        args = [sys.executable, str(ROOT / "scripts" / script)]
        if script == "install_learning_workflow.py" and installed.exists():
            args.append("--check")
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def install_cli() -> None:
    # A PATH entry can be a broken npm shim. Prefer the native user launcher;
    # bootstrap with the official installer when it is absent or unusable.
    binary = Path.home() / ".local/bin/claude"
    try:
        usable = binary.is_file() and subprocess.run([str(binary), "--version"], capture_output=True).returncode == 0
    except OSError:
        usable = False
    if usable:
        subprocess.run([str(binary), "install", "latest"], check=True)
    else:
        with tempfile.TemporaryDirectory(prefix="agent-tools-claude-") as tmp:
            script = Path(tmp) / "install.sh"
            subprocess.run(["curl", "-fsSL", "--connect-timeout", "20", "--max-time", "120",
                            "https://claude.ai/install.sh", "-o", str(script)], check=True)
            subprocess.run(["bash", str(script), "latest"], check=True)
    subprocess.run([str(Path.home() / ".local/bin/claude"), "--version"], check=True)


def load_state(home: Path) -> dict | None:
    path = home / STATE
    safe_target(path, home)
    if path.is_symlink():
        raise ValueError("adapter manifest symlink preserved")
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("home") != str(home):
        raise ValueError("invalid Claude adapter manifest")
    if (not isinstance(data.get("links"), dict) or not isinstance(data.get("context"), str)
            or not isinstance(data.get("native_sha256"), str) or not isinstance(data.get("managed_hooks"), dict)):
        raise ValueError("incomplete Claude adapter manifest")
    return data


def check(home: Path, *, current_source: bool = True) -> dict:
    state = load_state(home)
    if state is None:
        raise ValueError("Claude adapter is not installed")
    skill_sources(home)
    for raw, entry in state["links"].items():
        path = home / raw
        safe_target(path, home)
        if not path.is_symlink() or os.readlink(path) != entry["target"]:
            raise ValueError(f"managed Claude link missing or changed: {path}")
    generated = home / CONTEXT
    safe_target(generated, home)
    if not isinstance(state.get("core_source"), str):
        raise ValueError("Claude adapter manifest is missing its Agent Core source")
    if not Path(state["core_source"]).is_file():
        raise ValueError(f"Agent Core Claude context missing: {state['core_source']}")
    if generated.is_symlink() or generated.read_text() != state["context"]:
        raise ValueError("managed Claude context missing or changed")
    native = home / NATIVE
    safe_target(native, home)
    if native.is_symlink() or not native.is_file() or hashlib.sha256(native.read_bytes()).hexdigest() != state["native_sha256"]:
        raise ValueError("managed native hook adapter missing or changed")
    hooks.check(read_settings(home), home, state["managed_hooks"])
    if current_source:
        if generated.read_text() != context(home, Path(state["core_source"])) or native.read_bytes() != native_source():
            raise ValueError("Claude adapter source updated; rerun installation to refresh managed views")
        hooks.check(read_settings(home), home)
    if read_settings(home).get("disableAllHooks"):
        raise ValueError("Claude hooks are disabled")
    return {"status": "checked", "skills": sum(raw.startswith(".claude/skills/") for raw in state["links"]),
            "settings": str(home / ".claude/settings.json")}


def install(home: Path, core: Path, legacy_roots: list[Path]) -> dict:
    state = load_state(home)
    if state is not None:
        return refresh(home, state)
    sources = skill_sources(home)
    core_source = (core / "adapters/claude/CLAUDE.md").resolve()
    core_view = home / ".claude/CLAUDE.md"
    if not core_source.is_file():
        raise ValueError(f"Agent Core Claude context missing: {core_source}")
    settings = read_settings(home)
    if settings.get("disableAllHooks"):
        raise ValueError("Claude hooks are disabled; preserve this setting and resolve it explicitly")
    merged = hooks.merge_install(settings, home)
    links = {f".claude/skills/{name}": source for name, source in sources.items()}
    links[RULE] = home / CONTEXT
    if not core_view.exists():
        links[".claude/CLAUDE.md"] = core_source
    plan = {}
    for raw, target in links.items():
        path = home / raw
        safe_target(path, home)
        prior = None
        if path.exists() or path.is_symlink():
            if not path.is_symlink():
                raise ValueError(f"unmanaged Claude file/directory preserved: {path}")
            prior = os.readlink(path)
            if path.resolve() != target.resolve():
                if not any(path.resolve() == (root / path.name).resolve() for root in legacy_roots):
                    raise ValueError(f"foreign Claude link preserved: {path}; specify its exact --legacy-skill-root")
        plan[raw] = {"target": str(target), "prior": prior}
    generated = home / CONTEXT
    safe_target(generated, home)
    if generated.exists() or generated.is_symlink():
        raise ValueError(f"unmanaged context preserved: {generated}")
    native = home / NATIVE
    safe_target(native, home)
    if native.exists() or native.is_symlink():
        raise ValueError(f"unmanaged native hook adapter preserved: {native}")
    state_path = home / STATE
    settings_path = home / ".claude/settings.json"
    backup_path = state_path.parent / "settings-before.json"
    safe_target(backup_path, home)
    if backup_path.is_symlink():
        raise ValueError(f"settings backup symlink preserved: {backup_path}")
    before_settings = settings_path.read_bytes() if settings_path.exists() else None
    before_backup = backup_path.read_bytes() if backup_path.exists() else None
    changed = []
    try:
        for raw, entry in plan.items():
            path = home / raw
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink() and os.readlink(path) == entry["target"]:
                continue
            # Track before replacing a legacy link, including failed creation.
            changed.append(raw)
            if path.is_symlink():
                path.unlink()
            path.symlink_to(entry["target"], target_is_directory=raw.startswith(".claude/skills/"))
        atomic_write(generated, context(home, core_source).encode())
        atomic_write(native, native_source())
        if before_settings is not None:
            # May contain credentials: private backup, never print its contents.
            atomic_write(backup_path, before_settings)
        atomic_write(settings_path, (json.dumps(merged, indent=2) + "\n").encode())
        payload = {"schema_version": 1, "home": str(home), "links": plan, "core_source": str(core_source),
                   "context": generated.read_text(), "native_sha256": hashlib.sha256(native_source()).hexdigest(),
                   "managed_hooks": hooks.hook_groups(home)}
        atomic_write(state_path, (json.dumps(payload, indent=2) + "\n").encode())
        return {**check(home), "status": "installed"}
    except Exception:
        for raw in reversed(changed):
            path = home / raw
            path.unlink(missing_ok=True)
            if plan[raw]["prior"] is not None:
                path.symlink_to(plan[raw]["prior"])
        generated.unlink(missing_ok=True)
        native.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
        if before_backup is None:
            backup_path.unlink(missing_ok=True)
        else:
            atomic_write(backup_path, before_backup)
        if before_settings is None:
            settings_path.unlink(missing_ok=True)
        else:
            atomic_write(settings_path, before_settings)
        raise


def refresh(home: Path, state: dict) -> dict:
    check(home, current_source=False)  # validate published bytes before upgrade
    expected_context = context(home, Path(state["core_source"]))
    expected_native = native_source()
    expected_hooks = hooks.hook_groups(home)
    if (state["context"] == expected_context and state["native_sha256"] == hashlib.sha256(expected_native).hexdigest()
            and state["managed_hooks"] == expected_hooks):
        return check(home)
    settings = hooks.merge_install(hooks.remove_owned(read_settings(home), home, state["managed_hooks"]), home)
    paths = [home / CONTEXT, home / NATIVE, home / ".claude/settings.json", home / STATE]
    before = {path: path.read_bytes() for path in paths}
    updated = dict(state, context=expected_context, native_sha256=hashlib.sha256(expected_native).hexdigest(), managed_hooks=expected_hooks)
    try:
        for path, data in zip(paths, [expected_context.encode(), expected_native,
                                   (json.dumps(settings, indent=2) + "\n").encode(),
                                   (json.dumps(updated, indent=2) + "\n").encode()]):
            atomic_write(path, data)
        return {**check(home), "status": "updated"}
    except Exception:
        for path, data in before.items():
            atomic_write(path, data)
        raise


def remove(home: Path) -> dict:
    check(home, current_source=False)  # refuse user drift; source upgrades do not prevent removal
    state = load_state(home)
    settings_path = home / ".claude/settings.json"
    cleaned = hooks.remove_owned(read_settings(home), home, state["managed_hooks"])
    before = {path: path.read_bytes() for path in [settings_path, home / CONTEXT, home / NATIVE, home / STATE]}
    changed = []
    try:
        atomic_write(settings_path, (json.dumps(cleaned, indent=2) + "\n").encode())
        for raw, entry in state["links"].items():
            path = home / raw
            changed.append(raw)
            path.unlink()
            if entry["prior"] is not None:
                path.symlink_to(entry["prior"])
        (home / CONTEXT).unlink()
        (home / NATIVE).unlink()
        (home / STATE).unlink()
    except Exception:
        for raw in reversed(changed):
            path = home / raw
            path.unlink(missing_ok=True)
            path.symlink_to(state["links"][raw]["target"])
        for path, data in before.items():
            atomic_write(path, data)
        raise
    return {"status": "removed", "shared_packages": "preserved"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--remove", action="store_true")
    parser.add_argument("--install-cli", action="store_true", help="install/update official native latest CLI")
    parser.add_argument("--install-packages", action="store_true", help="prepare missing shared packages; check existing packages")
    parser.add_argument("--agent-core-home", type=Path, default=Path(os.environ.get("AGENT_CORE_HOME", Path.home() / "agent-core")))
    parser.add_argument("--legacy-skill-root", type=Path, action="append", default=[], help="exact old skills directory whose symlinks may be migrated")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("this adapter supports Linux/WSL Unix profiles only")
    if (args.check or args.remove) and (args.install_cli or args.install_packages):
        parser.error("check/remove cannot install CLI or shared packages")
    home = Path.home().resolve()
    try:
        workflow.run_target_guard(home)
        if args.check:
            result = check(home)
        elif args.remove:
            result = remove(home)
        else:
            if args.install_cli:
                install_cli()
            if args.install_packages:
                prepare_packages(home)
            result = install(home, args.agent_core_home.resolve(), [p.resolve() for p in args.legacy_skill_root])
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1
