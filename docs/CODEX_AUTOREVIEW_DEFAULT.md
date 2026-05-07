# Codex Default Configuration

This runbook configures Codex so new conversations use the local default
permission posture and tolerate long compression or streaming pauses.

Tested with `codex-cli 0.125.0`.

## Target State

Set these top-level keys in the Codex user config:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "auto_review"
stream_idle_timeout_ms = 900000
```

Meaning:

- `approval_policy = "on-request"` keeps approval flow enabled.
- `sandbox_mode = "workspace-write"` keeps the default session out of Full
  Access.
- `approvals_reviewer = "auto_review"` routes eligible approval requests to the
  AutoReview reviewer instead of directly to the user.
- `stream_idle_timeout_ms = 900000` gives Codex 15 minutes of idle stream time
  before treating compression or app/CLI streaming as timed out.

Do not set these as the default for AutoReview:

```toml
approval_policy = "never"
sandbox_mode = "danger-full-access"
```

That is Full Access by default, which should only be enabled manually when
needed.

## Config Location

Codex reads:

```bash
${CODEX_HOME:-$HOME/.codex}/config.toml
```

On Linux or WSL2, run the setup as the same Unix user that runs `codex`.
Examples:

- root user: `/root/.codex/config.toml`
- normal user: `/home/<user>/.codex/config.toml`
- custom home: `$CODEX_HOME/config.toml`

Each WSL2 distro has its own Linux home directory. Configure the distro where
Codex is actually launched.

## One-Shot Setup

Run this from any shell on the target machine:

```bash
python3 - <<'PY'
from pathlib import Path
import os

config_dir = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
config_path = config_dir / "config.toml"
config_dir.mkdir(parents=True, exist_ok=True)

text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
preamble = lines[:first_table]
rest = lines[first_table:]

managed = {
    "approval_policy",
    "sandbox_mode",
    "approvals_reviewer",
    "stream_idle_timeout_ms",
}

kept = []
for line in preamble:
    stripped = line.strip()
    key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
    if key in managed:
        continue
    kept.append(line)

if kept and kept[-1].strip():
    kept.append("")

kept.extend([
    'approval_policy = "on-request"',
    'sandbox_mode = "workspace-write"',
    'approvals_reviewer = "auto_review"',
    'stream_idle_timeout_ms = 900000',
])

if rest:
    kept.append("")
    kept.extend(rest)

config_path.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
print(config_path)
PY
```

This preserves existing top-level settings such as `model`, existing project
trust entries, and other TOML tables. It only replaces the three permission
defaults and the stream idle timeout above.

## Manual Setup

Edit the config directly:

```bash
${EDITOR:-nano} "${CODEX_HOME:-$HOME/.codex}/config.toml"
```

Ensure the top-level section contains:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "auto_review"
stream_idle_timeout_ms = 900000
```

If older lines exist with different values for the same keys, replace them
instead of adding duplicates.

## Validate

Check the saved config:

```bash
sed -n '1,40p' "${CODEX_HOME:-$HOME/.codex}/config.toml"
```

Check that Codex can parse the config:

```bash
codex features list >/dev/null && echo "Codex config parses"
```

Then open a new Codex conversation. The `/approvals` state should be AutoReview,
not Full Access, and long remote compression/streaming pauses should use the
larger idle timeout. Existing already-open conversations do not automatically
adopt the changed default.

## Daily Use

Default flow:

1. Start Codex normally with `codex`.
2. Keep the default AutoReview mode for routine work.
3. Use `/approvals` only when a session needs manual Full Access.
4. When switching to Full Access, do not choose a "remember this choice" option
   unless the goal is to change the global default.

## Agent Checklist

When asked to apply this on a new server or WSL2 machine:

1. Confirm which Unix user launches Codex.
2. Patch `${CODEX_HOME:-$HOME/.codex}/config.toml`.
3. Preserve existing `model`, `[projects.*]`, `[features]`, and other tables.
4. Validate with `codex features list`.
5. Tell the user that only new Codex sessions pick up the new default.

When the user only asks for the compression/streaming timeout fix, patch only
`stream_idle_timeout_ms = 900000` and preserve the current
`approvals_reviewer` value.

## Rollback

To return approval requests directly to the user while staying out of Full
Access:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "user"
```
