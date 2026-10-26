"""Claude discovery links and context view for the plain Agent Tools skills.

The adapter registers no hooks. It links the kept skills from the install root into
~/.claude/skills, writes the generated context view that ~/.claude/CLAUDE.md can
import, disables automatic memory, and removes hook entries written by earlier
releases. Shared sources stay authoritative; everything here is a view.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import install_layout as layout  # noqa: E402
from scripts import install_skills as skills  # noqa: E402

RULE = ".claude/rules/agent-tools.md"
OLD_STATE = ".local/state/agent-tools/claude/install.json"  # manifest written by releases that registered hooks
LEGACY_VIEWS = layout.LEGACY_DATA_LAYOUT + "/claude"  # earlier releases wrote views into the data root


def view_root(home: Path) -> Path:
    """The one location of the generated Claude view: inside the software install root."""
    return layout.install_root(home) / "claude"


def context_path(home: Path) -> Path:
    return view_root(home) / "context.md"


def contract_path(home: Path) -> Path:
    return layout.install_root(home) / "shared/writing/reader-facing-contract.md"


def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=".agent-tools-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.chmod(raw, mode)
        os.replace(raw, path)
    finally:
        if os.path.exists(raw):
            os.unlink(raw)


def safe_target(path: Path, home: Path) -> None:
    if not path.parent.resolve().is_relative_to(home):
        raise ValueError(f"destination escapes profile: {path}")


def read_settings(home: Path) -> dict:
    path = home / ".claude/settings.json"
    safe_target(path, home)
    if path.is_symlink():
        raise ValueError(f"settings symlink preserved: {path}")
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise ValueError("settings must be a JSON object with an object-valued hooks entry")
    return data


def _retired_hook(handler: object) -> bool:
    """A command written by the retired hook adapter: `<python> <...>/claude/native_hook.py -- ...`."""
    if not isinstance(handler, dict) or handler.get("type") != "command" or not isinstance(handler.get("command"), str):
        return False
    try:
        tokens = shlex.split(handler["command"])
    except ValueError:
        return False
    script = Path(tokens[1]) if len(tokens) > 1 else None
    return script is not None and script.name == "native_hook.py" and script.parent.name == "claude"


def strip_retired_hooks(settings: dict) -> dict:
    """Copy of settings without retired agent-tools hook handlers; foreign hooks stay, even in mixed groups."""
    hooks = settings.get("hooks")
    if not hooks:
        return settings
    kept_hooks = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            kept_hooks[event] = groups
            continue
        kept = []
        for group in groups:
            handlers = group.get("hooks") if isinstance(group, dict) else None
            if isinstance(handlers, list):
                remaining = [handler for handler in handlers if not _retired_hook(handler)]
                if len(remaining) != len(handlers):
                    if remaining:
                        kept.append(dict(group, hooks=remaining))
                    continue
            kept.append(group)
        if kept or not groups:  # an event emptied by the removal goes; a preexisting empty list stays
            kept_hooks[event] = kept
    if kept_hooks == hooks:
        return settings
    result = {key: value for key, value in settings.items() if key != "hooks"}
    if kept_hooks:
        result["hooks"] = kept_hooks
    return result


def context(home: Path, core_source: Path | None = None) -> str:
    contract = contract_path(home)
    if not contract.is_file():
        raise ValueError(f"shared writing contract missing: {contract}; run scripts/install.sh to install the software copy")
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
            "Their source is the Agent Tools install root; Claude discovery links are views.\n\n"
            + f"For all reader-facing output, follow the [shared writing contract](<{contract.as_posix()}>). "
            "Read it when not already in context; this does not activate formal reporting or teaching.\n\n"
            "After pushing a GitHub PR, start `ci-watch <PR> --repo OWNER/NAME` with `run_in_background` and act on "
            "its exit: 1 prints the failure to fix, 2 means no check ran (not a pass).\n")


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


def link(path: Path, target: Path, home: Path) -> bool:
    """Create or repoint a symlink only when it is absent or already ours; return whether it changed."""
    safe_target(path, home)
    if path.is_symlink() and Path(os.path.abspath(path.parent / os.readlink(path))) == target:
        return False
    if path.exists() or path.is_symlink():
        raise ValueError(f"unmanaged Claude file/directory preserved: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)
    return True


def check(home: Path, core: Path | None = None) -> dict:
    install = layout.install_root(home)
    drift = skills.check_links(home, home / ".claude/skills", install)
    if drift:
        raise ValueError("Claude skill links missing or changed: " + ", ".join(drift))
    rule = home / RULE
    generated = context_path(home)
    if not rule.is_symlink() or Path(os.path.abspath(rule.parent / os.readlink(rule))) != generated:
        raise ValueError(f"Claude rule link missing or changed: {rule}")
    if core is not None:
        core_source = (core / "adapters/claude/CLAUDE.md").resolve()
        if generated.is_symlink() or generated.read_text() != context(home, core_source):
            raise ValueError("managed Claude context missing or changed; rerun installation")
    elif generated.is_symlink() or not generated.is_file():
        raise ValueError("managed Claude context missing")
    settings = read_settings(home)
    if strip_retired_hooks(settings) != settings:
        raise ValueError("retired agent-tools hook entries remain in settings.json; rerun installation")
    if settings.get("autoMemoryEnabled") is not False:
        raise ValueError("autoMemoryEnabled is not false")
    return {"status": "checked", "skills": len(skills.KEPT), "settings": str(home / ".claude/settings.json")}


def install(home: Path, core: Path) -> dict:
    install_root = layout.install_root(home)
    core_source = (core / "adapters/claude/CLAUDE.md").resolve()
    if not core_source.is_file():
        raise ValueError(f"Agent Core Claude context missing: {core_source}")
    for name in skills.KEPT:
        skills.source_dir(install_root, name)
    layout.require_separate(install_root)
    context(home, core_source)  # fails before any write when the contract is absent
    settings_path = home / ".claude/settings.json"
    settings = read_settings(home)
    merged = dict(strip_retired_hooks(settings))
    merged["autoMemoryEnabled"] = False
    changes = []
    if merged != settings:
        if settings_path.exists() and merged.get("hooks") != settings.get("hooks"):
            # Hook removal edits user settings, which may hold credentials: private backup, never printed.
            atomic_write(settings_path.with_name("settings.json.agent-tools-backup"),
                         settings_path.read_bytes(), 0o600)
        atomic_write(settings_path, (json.dumps(merged, indent=2) + "\n").encode())
        changes.append("settings")
    result = skills.link_skills(home, home / ".claude/skills", install_root)
    core_view = home / ".claude/CLAUDE.md"
    if not core_view.exists() and not core_view.is_symlink() and link(core_view, core_source, home):
        changes.append("core")
    rendered = context(home, core_source)  # after the global link: it decides whether Core is imported
    generated = context_path(home)
    safe_target(generated, home)
    if generated.is_symlink():
        raise ValueError(f"unmanaged context preserved: {generated}")
    if not generated.is_file() or generated.read_text() != rendered:
        atomic_write(generated, rendered.encode())
        changes.append("context")
    rule = home / RULE
    if rule.is_symlink():
        previous = Path(os.path.abspath(rule.parent / os.readlink(rule)))
        if previous != generated and previous.name == "context.md" and previous.parent.name == "claude":
            rule.unlink()  # view moved by an earlier layout; repoint it
    if link(rule, generated, home):
        changes.append("rule")
    # Views and manifest written by releases that registered hooks.
    for stale in (layout.install_root(home) / "claude/native_hook.py", home / LEGACY_VIEWS / "native_hook.py"):
        if stale.is_file() and not stale.is_symlink():
            stale.unlink()
            changes.append("native_hook")
    # Nothing writes this view manifest any more; it would keep listing native_hook.py.
    (layout.install_root(home) / "claude" / layout.MANIFEST).unlink(missing_ok=True)
    (home / OLD_STATE).unlink(missing_ok=True)
    return {**check(home, core), "status": "updated" if changes or result["linked"] or result["removed"] else "checked",
            "changes": changes, "preserved": result["preserved"]}


def remove(home: Path) -> dict:
    """Remove the links and context this adapter creates; settings and ~/.claude/CLAUDE.md are left as they are."""
    removed = skills.remove_links(home / ".claude/skills", layout.install_root(home))
    rule = home / RULE
    generated = context_path(home)
    if rule.is_symlink() and Path(os.path.abspath(rule.parent / os.readlink(rule))) == generated:
        rule.unlink()
    generated.unlink(missing_ok=True)
    return {"status": "removed", "skills": removed, "shared_packages": "preserved"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--remove", action="store_true")
    parser.add_argument("--install-cli", action="store_true", help="install/update official native latest CLI")
    parser.add_argument("--agent-core-home", type=Path, default=Path(os.environ.get("AGENT_CORE_HOME", Path.home() / "agent-core")))
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        parser.error("this adapter supports Linux/WSL Unix profiles only")
    if (args.check or args.remove) and args.install_cli:
        parser.error("check/remove cannot install the CLI")
    home = Path.home().resolve()
    try:
        skills.run_target_guard(home)
        if args.check:
            result = check(home, args.agent_core_home.resolve())
        elif args.remove:
            result = remove(home)
        else:
            if args.install_cli:
                install_cli()
            result = install(home, args.agent_core_home.resolve())
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 1
