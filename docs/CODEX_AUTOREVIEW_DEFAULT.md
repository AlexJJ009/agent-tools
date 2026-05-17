# Codex Default Configuration

This runbook configures Codex so new conversations use the local default
permission posture and tolerate long compression or streaming pauses.

**As of the current `install.sh`, every section below is applied
automatically.** Re-run `./install.sh` (with or without `--root` flags) and the
target state lands in `~/.codex/config.toml` exactly as written here. The rest
of this document is the rationale, override knobs, and manual fallback when
running `install.sh` is not an option.

Tested with `codex-cli 0.130.0`.

## Target State

Set these top-level keys in the Codex user config:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "auto_review"
stream_idle_timeout_ms = 900000
stream_max_retries = 20
model_provider = "openai-no-ws"
```

Define the HTTPS-only Codex provider:

```toml
[model_providers.openai-no-ws]
name = "OpenAI HTTPS no WebSocket"
base_url = "https://chatgpt.com/backend-api/codex"
requires_openai_auth = true
supports_websockets = false
stream_idle_timeout_ms = 900000
stream_max_retries = 20
```

Set the current hooks feature key under `[features]`:

```toml
[features]
hooks = true
```

Meaning:

- `approval_policy = "on-request"` keeps approval flow enabled.
- `sandbox_mode = "workspace-write"` keeps the default session out of Full
  Access.
- `approvals_reviewer = "auto_review"` routes eligible approval requests to the
  AutoReview reviewer instead of directly to the user.
- `stream_idle_timeout_ms = 900000` gives Codex 15 minutes of idle stream time
  before treating compression or app/CLI streaming as timed out.
- `stream_max_retries = 20` gives transient SSE streaming disconnects more
  retry attempts before Codex gives up on the active response.
- `model_provider = "openai-no-ws"` uses OpenAI/ChatGPT auth but disables the
  Responses WebSocket transport. This avoids `tls handshake eof` failures seen
  on this WSL2-to-Windows-proxy path while keeping HTTPS `/responses` working.
- `[features].hooks = true` enables Codex lifecycle hooks with the current
  feature flag name. If an older config contains `[features].codex_hooks`,
  remove that key; Codex now warns that it is deprecated.

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
    "stream_max_retries",
    "model_provider",
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
    'stream_max_retries = 20',
    'model_provider = "openai-no-ws"',
])

provider_header = "[model_providers.openai-no-ws]"
filtered_rest = []
i = 0
while i < len(rest):
    if rest[i].strip() == provider_header:
        i += 1
        while i < len(rest) and not rest[i].lstrip().startswith("["):
            i += 1
        continue
    filtered_rest.append(rest[i])
    i += 1
rest = filtered_rest

if rest:
    kept.append("")
    kept.extend(rest)

if kept and kept[-1].strip():
    kept.append("")
kept.extend([
    provider_header,
    'name = "OpenAI HTTPS no WebSocket"',
    'base_url = "https://chatgpt.com/backend-api/codex"',
    "requires_openai_auth = true",
    "supports_websockets = false",
    "stream_idle_timeout_ms = 900000",
    "stream_max_retries = 20",
])

lines = kept
out = []
in_features = False
found_features = False
inserted_hooks = False

for line in lines:
    stripped = line.strip()
    starts_table = stripped.startswith("[") and stripped.endswith("]")

    if starts_table and in_features:
        if out and out[-1].strip():
            out.append("")
        out.append("hooks = true")
        inserted_hooks = True
        in_features = False

    if stripped == "[features]":
        found_features = True
        in_features = True
        out.append(line)
        continue

    if in_features and "=" in stripped and not stripped.startswith("#"):
        key = stripped.split("=", 1)[0].strip()
        if key in {"codex_hooks", "hooks"}:
            continue

    out.append(line)

if in_features and not inserted_hooks:
    if out and out[-1].strip():
        out.append("")
    out.append("hooks = true")

if not found_features:
    if out and out[-1].strip():
        out.append("")
    out.extend(["[features]", "hooks = true"])

config_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
print(config_path)
PY
```

This preserves existing top-level settings such as `model`, existing project
trust entries, and other TOML tables. It only replaces the three permission
defaults, the stream timeout/retry defaults, and the managed HTTPS-only Codex
provider above. If `[features]` exists, also ensure it uses `hooks = true`
rather than the deprecated `codex_hooks` key.

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
stream_max_retries = 20
model_provider = "openai-no-ws"
```

Ensure this provider table exists:

```toml
[model_providers.openai-no-ws]
name = "OpenAI HTTPS no WebSocket"
base_url = "https://chatgpt.com/backend-api/codex"
requires_openai_auth = true
supports_websockets = false
stream_idle_timeout_ms = 900000
stream_max_retries = 20
```

Ensure the `[features]` table contains the current hooks flag:

```toml
[features]
hooks = true
```

If older lines exist with different values for the same keys, replace them
instead of adding duplicates. If `[features].codex_hooks` exists, replace it
with `[features].hooks`.

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
2. Run `./install.sh` (with appropriate `--root` flags). It writes all six
   managed keys plus the `openai-no-ws` provider and `[features].hooks = true`.
3. If `install.sh` cannot run, use the One-Shot Setup or Manual Setup block
   above to patch `${CODEX_HOME:-$HOME/.codex}/config.toml` directly.
4. Preserve existing `model`, `[projects.*]`, and other TOML tables. The
   installer already does this.
5. Validate with `codex features list`.
6. Tell the user that only new Codex sessions pick up the new default.

To deviate from the defaults (e.g. keep an existing `approvals_reviewer = "user"`
or use a non-default stream timeout), set the matching env var before running
`install.sh`: `CODEX_APPROVAL_POLICY`, `CODEX_SANDBOX_MODE`,
`CODEX_APPROVALS_REVIEWER`, `CODEX_STREAM_IDLE_TIMEOUT_MS`,
`CODEX_STREAM_MAX_RETRIES`, `CODEX_MODEL_PROVIDER_ID`. Use `--no-codex-config`
to skip the codex patch entirely.

## Rollback

To return approval requests directly to the user while staying out of Full
Access:

```toml
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "user"
```
