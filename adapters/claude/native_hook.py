#!/usr/bin/env python3
"""Translate native host context without changing shared hook decisions or state."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

NOTIFICATION = re.compile(r"<task-notification>.*?</task-notification>", re.DOTALL)


def prepare(event: dict) -> dict | None:
    """Return the event to forward, or None when the prompt is not user input."""
    if event.get("hook_event_name") != "UserPromptSubmit":
        return event
    prompt = event.get("prompt")
    # Claude delivers background task completions as UserPromptSubmit whose whole
    # prompt is <task-notification> envelopes; user text outside them is kept.
    if isinstance(prompt, str) and NOTIFICATION.search(prompt) and not NOTIFICATION.sub("", prompt).strip():
        return None
    # Claude sends a per-submission prompt_id but no turn_id; without it two
    # identical prompts ("continue") in one session share one input id.
    if not event.get("turn_id") and isinstance(event.get("prompt_id"), str) and event["prompt_id"]:
        return dict(event, turn_id=event["prompt_id"])
    return event


def adapt(event: dict, output: dict, command: list[str]) -> dict:
    specific = output.get("hookSpecificOutput")
    if isinstance(specific, dict) and "systemMessage" in specific:
        output["systemMessage"] = specific.pop("systemMessage")
        if set(specific) == {"hookEventName"}:
            output.pop("hookSpecificOutput")
    # The shared learning hook exposes identity when unbound, but bound startup
    # context only describes the record. Expose host identity once per start.
    if (event.get("hook_event_name") == "SessionStart"
            and any(Path(arg).name == "learning-workflow-hook" for arg in command)):
        session, cwd = event.get("session_id"), event.get("cwd")
        if isinstance(session, str) and isinstance(cwd, str):
            specific = output.setdefault("hookSpecificOutput", {"hookEventName": event["hook_event_name"]})
            existing = specific.get("additionalContext", "")
            if f"Native session_id={session};" not in existing:
                state = command[command.index("--state-root") + 1] if "--state-root" in command else ""
                identity = f"Native session_id={session}; workspace={cwd}; hook state_root={state}. Use this exact session identity when binding or resuming a route."
                specific["additionalContext"] = identity + ("\n" + existing if existing else "")
    return output


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] != "--":
        print("expected -- followed by shared hook argv", file=sys.stderr)
        return 1
    command = sys.argv[2:]
    raw = sys.stdin.read()
    event = json.loads(raw)
    forwarded = prepare(event)
    if forwarded is None:
        print("{}")
        return 0
    if forwarded is not event:
        raw = json.dumps(forwarded, ensure_ascii=False)
    result = subprocess.run(command, input=raw, text=True, capture_output=True)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode:
        sys.stdout.write(result.stdout)
        return result.returncode
    try:
        output = json.loads(result.stdout) if result.stdout.strip() else {}
    except ValueError:
        output = None
    if not isinstance(output, dict):
        print(json.dumps({"systemMessage": "agent-tools hook output was not a JSON object; ignored: "
                          + result.stdout.strip()[:200]}, ensure_ascii=False))
        return 0
    print(json.dumps(adapt(event, output, command), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
