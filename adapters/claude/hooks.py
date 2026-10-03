"""Claude settings registration for the shared agent-tools hook runtimes.

Only definitions are adapted here; the installed shared runtimes remain the
source of truth. Claude has no Interrupt event. SessionEnd is deliberately not
mapped to it: ending or switching a session does not cancel report obligations.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import shlex
import sys

from scripts import install_agent_workflow_hooks as workflow
from scripts import install_learning_workflow as learning
from scripts import install_work_report_hooks as report

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")
TOOL_EVENTS = ("PreToolUse", "PostToolUse")


def view_root(home: Path) -> Path:
    """The one location of the generated Claude views: inside the software install root."""
    return learning.layout.install_root(home) / "claude"


def hook_groups(home: Path) -> dict[str, list[dict]]:
    """Build native groups using the current shared installer commands."""
    home = Path(home).resolve()
    bundle = learning.bundle_root(home)
    groups = {}
    for event in EVENTS:
        native = [learning.managed_group(event, bundle, home), workflow.managed_group(event, home)]
        if event in TOOL_EVENTS:
            # Both runtimes act only on shell commands, which Claude names Bash.
            for group in native:
                group["matcher"] = "Bash"
        if event in report.EVENTS:
            native.append(report.managed_group(event, home))
        for group in native:
            for handler in group["hooks"]:
                handler.pop("additionalContextLimit", None)
                handler["command"] = shlex.join([
                    sys.executable, str(view_root(home) / "native_hook.py"),
                    "--", *shlex.split(handler["command"]),
                ])
        groups[event] = native
    return groups


def _validate(settings: dict) -> None:
    if not isinstance(settings, dict) or not isinstance(settings.get("hooks", {}), dict):
        raise ValueError("invalid Claude settings: expected settings object and hooks object")
    for event, groups in settings.get("hooks", {}).items():
        if not isinstance(groups, list):
            raise ValueError(f"invalid Claude settings: hooks.{event} must be a list")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                raise ValueError(f"invalid Claude settings: hooks.{event} group requires a hooks list")
            if not all(isinstance(handler, dict) for handler in group["hooks"]):
                raise ValueError(f"invalid Claude settings: hooks.{event} handlers must be objects")


def _commands(home: Path, expected: dict | None = None) -> set[tuple[str, ...]]:
    return {
        tuple(shlex.split(handler["command"]))
        for groups in (expected if expected is not None else hook_groups(home)).values()
        for group in groups
        for handler in group["hooks"]
    }


def _owned(handler: dict, commands: set[tuple[str, ...]]) -> bool:
    # A marker or a filename mentioned in shell data never proves ownership.
    if handler.get("type") != "command" or not isinstance(handler.get("command"), str):
        return False
    try:
        return tuple(shlex.split(handler["command"])) in commands
    except ValueError:
        return False


def remove_owned(settings: dict, home: Path, expected: dict | None = None) -> dict:
    """Return a copy with only exact managed commands removed, even in mixed groups."""
    _validate(settings)
    result = deepcopy(settings)
    commands = _commands(home, expected)
    hooks = result.get("hooks", {})
    for event, groups in list(hooks.items()):
        kept = []
        for group in groups:
            remaining = [handler for handler in group["hooks"] if not _owned(handler, commands)]
            if remaining == group["hooks"]:
                kept.append(group)
            elif remaining:
                kept.append(dict(group, hooks=remaining))
        if kept:
            hooks[event] = kept
        else:
            # Preserve preexisting empty foreign event lists.
            if groups:
                del hooks[event]
    return result


def merge_install(settings: dict, home: Path) -> dict:
    """Return native definitions merged without changing foreign settings."""
    result = remove_owned(settings, home)
    hooks = result.setdefault("hooks", {})
    for event, groups in hook_groups(home).items():
        hooks.setdefault(event, []).extend(groups)
    return result


def check(settings: dict, home: Path, expected: dict | None = None) -> dict:
    """Check definitions, not runtime availability or native execution/trust."""
    _validate(settings)
    expected = hook_groups(home) if expected is None else expected
    commands = _commands(home, expected)
    actual = {}
    for event, groups in settings.get("hooks", {}).items():
        owned = []
        for group in groups:
            handlers = [handler for handler in group["hooks"] if _owned(handler, commands)]
            if handlers:
                owned.append(dict(group, hooks=handlers))
        if owned:
            actual[event] = owned
    if actual != expected:
        raise ValueError("Claude managed hook definitions are missing, duplicated, changed, or use unsupported events")
    return {"status": "pass", "events": list(EVENTS), "handlers": sum(len(g) for g in expected.values())}
