#!/usr/bin/env python3
"""Translate native host context without changing shared hook decisions or state."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def adapt(event: dict, output: dict, command: list[str]) -> dict:
    specific = output.get("hookSpecificOutput")
    if isinstance(specific, dict) and "systemMessage" in specific:
        output["systemMessage"] = specific.pop("systemMessage")
        if set(specific) == {"hookEventName"}:
            output.pop("hookSpecificOutput")
    # The shared learning hook exposes identity when unbound, but bound startup
    # and prompt context only describe the record. Always expose host identity.
    if (event.get("hook_event_name") in {"SessionStart", "UserPromptSubmit"}
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
    result = subprocess.run(command, input=raw, text=True, capture_output=True)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode:
        sys.stdout.write(result.stdout)
        return result.returncode
    output = json.loads(result.stdout) if result.stdout.strip() else {}
    print(json.dumps(adapt(event, output, command), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
