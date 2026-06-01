# Codex, Claude Code, and cc-switch Server Bootstrap

This runbook installs the current latest Codex CLI, Claude Code, GitHub CLI,
`cc-switch-cli`, and `ripgrep` on a fresh Linux server, then configures Codex
API providers through user-level Codex config plus the local `cc-switch`
provider database.

Use this for repeat deployments on new servers. The only per-server inputs
should be:

- GitHub PAT for cloning `AlexJJ009/agent-tools`
- One or more provider IDs
- Provider Base URLs
- Provider API keys
- Default model, usually `gpt-5.5`

Do not commit real keys or paste them into reusable docs. Store them only on the
target server with `0600` permissions.

## Latest-Version Rule

Every deployment must fetch installers live instead of copying old binaries:

- Codex CLI: `curl -fsSL https://chatgpt.com/codex/install.sh | sh`
- Claude Code: `curl -fsSL https://claude.ai/install.sh | bash -s latest`
- cc-switch: download the latest GitHub release installer
- GitHub CLI: install from the official GitHub apt repository, then run
  `apt-get update && apt-get install -y gh`
- ripgrep: install from the OS package manager as `ripgrep`; Codex relies on
  the `rg` command for fast code and file searches.

After install, always record versions with:

```bash
gh --version | head -n 1
codex --version
claude --version
cc-switch --version
rg --version
```

## Server Bootstrap

Run as the Unix user that will use Codex. On a single-purpose root server, this
is usually `root`; for a shared lab machine, use the normal user account
instead.

```bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  ca-certificates curl git unzip tar gzip jq python3 python3-venv \
  gnupg lsb-release sqlite3 bubblewrap ripgrep

if ! command -v gh >/dev/null 2>&1; then
  mkdir -p -m 755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
  chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update
  apt-get install -y gh
fi

curl -fsSL https://chatgpt.com/codex/install.sh | sh
curl -fsSL https://claude.ai/install.sh | bash -s latest
curl -fsSL https://github.com/saladday/cc-switch-cli/releases/latest/download/install.sh | bash

export PATH="$HOME/.local/bin:$PATH"
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" \
  || printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
```

Authenticate `gh` without putting the token into shell history:

```bash
read -rsp "GitHub PAT: " GH_PAT
printf '\n'
printf '%s\n' "$GH_PAT" | gh auth login --hostname github.com --with-token
unset GH_PAT
gh auth setup-git
gh auth status --hostname github.com
```

Clone or update `agent-tools`:

```bash
if [ -d "$HOME/agent-tools/.git" ]; then
  git -C "$HOME/agent-tools" pull --ff-only
else
  gh repo clone AlexJJ009/agent-tools "$HOME/agent-tools"
fi

cd "$HOME/agent-tools"
```

Run the machine defaults, but let the provider script below own Codex API
provider config. Use `--codex-proxy-wrapper never` on ordinary Linux servers.
Only use the WSL2 proxy wrapper modes from `CODEX_REMOTE_CONTROL.md` when the
host actually needs that topology.

```bash
./install.sh \
  --root "$HOME" \
  --max-depth 3 \
  --codex-proxy-wrapper never \
  --no-codex-config \
  --no-codex-remote-control \
  --no-registry \
  --no-cron \
  --no-agent-core
```

## Provider Inputs

Fill these values on the target server. The example uses two providers, but the
JSON array can contain one or many entries.

Important Base URL rule:

- If a service root serves a web UI or HTML, use the API prefix, usually
  `/v1`.
- If a Docker service is published to the host, use the host-reachable address
  such as `http://127.0.0.1:8080/v1`, not the container DNS name, unless the
  client process runs inside the same Docker network.

```bash
read -rsp "Provider 1 API key: " PROVIDER_1_KEY
printf '\n'
read -rsp "Provider 2 API key: " PROVIDER_2_KEY
printf '\n'

export CODEX_DEFAULT_PROVIDER="dragtokens"
export CODEX_MODEL="gpt-5.5"
export CODEX_PROVIDERS_JSON="$(
  jq -n \
    --arg p1_key "$PROVIDER_1_KEY" \
    --arg p2_key "$PROVIDER_2_KEY" \
    '[
      {
        "id": "dragtokens",
        "name": "DragTokens",
        "base_url": "https://dragtokens.com/v1",
        "model": "gpt-5.5",
        "api_key": $p1_key
      },
      {
        "id": "sub2api",
        "name": "sub2api",
        "base_url": "http://127.0.0.1:8080/v1",
        "model": "gpt-5.5",
        "api_key": $p2_key
      }
    ]'
)"

unset PROVIDER_1_KEY PROVIDER_2_KEY
```

## Configure Codex and cc-switch

This script writes:

- API keys to `${CODEX_HOME:-$HOME/.codex}/keys/<provider>.key`
- Codex user config to `${CODEX_HOME:-$HOME/.codex}/config.toml`
- `cc-switch` Codex providers into `$HOME/.cc-switch/cc-switch.db`

It intentionally stores API keys through Codex provider `auth.command` instead
of embedding bearer tokens directly in `config.toml`. It also intentionally
uses one stable Codex bucket, `model_provider = "custom"`, for every provider.
`cc-switch` provider switches should replace `[model_providers.custom]` rather
than changing the bucket name; otherwise Codex resume history gets split by
provider id.

```bash
python3 - <<'PY'
import json
import os
import re
import sqlite3
import time
from pathlib import Path

home = Path.home()
codex_home = Path(os.environ.get("CODEX_HOME", home / ".codex")).expanduser()
providers = json.loads(os.environ["CODEX_PROVIDERS_JSON"])
default_provider = os.environ["CODEX_DEFAULT_PROVIDER"]
default_model = os.environ.get("CODEX_MODEL", "gpt-5.5")
codex_provider_bucket = os.environ.get("CODEX_MODEL_PROVIDER_ID", "custom")
safe_id = re.compile(r"^[A-Za-z0-9_.-]+$")

if not providers:
    raise SystemExit("CODEX_PROVIDERS_JSON must contain at least one provider")
if default_provider not in {p["id"] for p in providers}:
    raise SystemExit(f"default provider not found: {default_provider}")
if not safe_id.match(codex_provider_bucket):
    raise SystemExit(f"invalid CODEX_MODEL_PROVIDER_ID: {codex_provider_bucket}")

keys_dir = codex_home / "keys"
keys_dir.mkdir(parents=True, exist_ok=True)
keys_dir.chmod(0o700)
codex_home.mkdir(parents=True, exist_ok=True)

for provider in providers:
    pid = provider["id"]
    if not safe_id.match(pid):
        raise SystemExit(f"invalid provider id: {pid}")
    api_key = provider["api_key"]

    key_path = keys_dir / f"{pid}.key"
    key_path.write_text(api_key.rstrip() + "\n", encoding="utf-8")
    key_path.chmod(0o600)

default_provider_config = next(p for p in providers if p["id"] == default_provider)
default_provider_name = default_provider_config.get("name", default_provider)
default_base_url = default_provider_config["base_url"].rstrip("/")
default_key_path = keys_dir / f"{default_provider}.key"

provider_block = f"""
[model_providers.{codex_provider_bucket}]
name = "{default_provider_name}"
base_url = "{default_base_url}"
wire_api = "responses"
supports_websockets = false
stream_idle_timeout_ms = 1800000
stream_max_retries = 20

[model_providers.{codex_provider_bucket}.auth]
command = "cat"
args = ["{default_key_path}"]
timeout_ms = 5000
refresh_interval_ms = 0
""".strip()

config_text = f"""
approval_policy = "on-request"
sandbox_mode = "workspace-write"
approvals_reviewer = "auto_review"
model = "{default_model}"
model_reasoning_effort = "high"
model_provider = "{codex_provider_bucket}"

[features]
hooks = true
memories = true
goals = true
terminal_resize_reflow = true
remote_control = true

{provider_block}
""".strip() + "\n"

(codex_home / "config.toml").write_text(config_text, encoding="utf-8")

# Initialize cc-switch DB if this is the first run.
os.system("cc-switch provider list -a codex >/dev/null 2>&1 || true")

db_path = home / ".cc-switch" / "cc-switch.db"
conn = sqlite3.connect(db_path)
now = int(time.time() * 1000)
conn.execute("UPDATE providers SET is_current=0 WHERE app_type='codex'")

for index, provider in enumerate(providers, start=1):
    pid = provider["id"]
    name = provider.get("name", pid)
    base_url = provider["base_url"].rstrip("/")
    model = provider.get("model", default_model)
    key_path = str(keys_dir / f"{pid}.key")
    is_current = 1 if pid == default_provider else 0
    sort_index = index * 10

    snippet = f"""
model = "{model}"
model_provider = "{codex_provider_bucket}"
model_reasoning_effort = "high"

[model_providers.{codex_provider_bucket}]
name = "{name}"
base_url = "{base_url}"
wire_api = "responses"
supports_websockets = false
stream_idle_timeout_ms = 1800000
stream_max_retries = 20

[model_providers.{codex_provider_bucket}.auth]
command = "cat"
args = ["{key_path}"]
timeout_ms = 5000
refresh_interval_ms = 0
""".strip() + "\n"

    settings = {"auth": {"type": "command", "keyFile": key_path}, "config": snippet}
    meta = {"model": model, "wire_api": "responses", "managed_by": "agent-tools-bootstrap"}

    conn.execute(
        """
        INSERT INTO providers (
          id, app_type, name, settings_config, website_url, category,
          created_at, sort_index, notes, icon, icon_color, meta, is_current,
          in_failover_queue, provider_type
        )
        VALUES (?, 'codex', ?, ?, ?, 'custom', ?, ?, ?, 'openai', '#00A67E', ?, ?, 0, 'openai-compatible')
        ON CONFLICT(id, app_type) DO UPDATE SET
          name=excluded.name,
          settings_config=excluded.settings_config,
          website_url=excluded.website_url,
          category=excluded.category,
          sort_index=excluded.sort_index,
          notes=excluded.notes,
          meta=excluded.meta,
          is_current=excluded.is_current,
          provider_type=excluded.provider_type
        """,
        (
            pid,
            name,
            json.dumps(settings),
            base_url,
            now,
            sort_index,
            f"Configured for Codex {model} Responses API",
            json.dumps(meta),
            is_current,
        ),
    )
    conn.execute("DELETE FROM provider_endpoints WHERE provider_id=? AND app_type='codex'", (pid,))
    conn.execute(
        "INSERT INTO provider_endpoints (provider_id, app_type, url, added_at) VALUES (?, 'codex', ?, ?)",
        (pid, base_url, now),
    )

conn.commit()
conn.close()
PY

unset CODEX_PROVIDERS_JSON
```

## Validate

First validate local installs and config parsing:

```bash
gh --version | head -n 1
codex --version
claude --version
cc-switch --version
bwrap --version
rg --version

gh auth status --hostname github.com
codex features list >/dev/null && echo "codex_config_parse=ok"
cc-switch config validate -a codex
cc-switch provider list -a codex
cc-switch provider current -a codex
```

Check the default provider with the real Codex client:

```bash
codex exec --strict-config \
  -s read-only --skip-git-repo-check --ephemeral \
  'Reply exactly OK'
```

Expected success is a final `OK`.

The bootstrap script intentionally keeps Codex on a single history bucket:
`model_provider = "custom"` and `[model_providers.custom]`. Test other
providers through `cc-switch provider switch`; each stored provider snippet
rewrites the same `custom` bucket with that provider's endpoint and auth.

For HTTP-level diagnostics, test `/models` first:

```bash
curl -sS -H "Authorization: Bearer $(cat ~/.codex/keys/dragtokens.key)" \
  https://dragtokens.com/v1/models | jq '.data | length'
```

Some gateways return `403` for a raw `curl /v1/responses` request with a message
like "only allows Codex official clients". Treat `codex exec` as the decisive
provider test when `/models` works and raw `/responses` is client-gated.

## Switching Providers

Use `cc-switch` to switch the default Codex provider:

```bash
cc-switch provider switch -a codex sub2api
codex features list >/dev/null && echo "switched_sub2api_parse=ok"
codex exec --strict-config \
  -s read-only --skip-git-repo-check --ephemeral \
  'Reply exactly OK'

cc-switch provider switch -a codex dragtokens
codex features list >/dev/null && echo "switched_dragtokens_parse=ok"
codex exec --strict-config \
  -s read-only --skip-git-repo-check --ephemeral \
  'Reply exactly OK'
```

## Existing History Migration

If the machine already used Codex before the stable `custom` bucket convention,
run the local migration script once after closing Codex:

```bash
python3 ~/agent-tools/migrate_codex_provider_bucket.py --target custom
python3 ~/agent-tools/migrate_codex_provider_bucket.py --target custom --apply --yes --kill-running-codex
```

The dry-run shows every source bucket and every cc-switch template that would
change. The apply run backs up `config.toml`, `state_5.sqlite`, changed JSONL
session files, and the cc-switch DB under `~/.cc-switch/backups/`. It rewrites
Codex history to `custom`, updates live `~/.codex/config.toml`, and changes
cc-switch Codex provider templates so future switches keep
`model_provider = "custom"` / `[model_providers.custom]`. It should terminate
running Codex processes before writing; otherwise a process that already loaded
the old config/key can keep using the old in-memory provider until restarted.

## Troubleshooting

- `Could not resolve host: sub2api`: the shell is running on the host, not
  inside Docker. Use the published host URL, for example
  `http://127.0.0.1:8080/v1`.
- HTML from `/models` or `/responses`: the Base URL points at a web UI root.
  Add the API prefix, usually `/v1`.
- `unknown configuration field stream_idle_timeout_ms`: remove top-level
  `stream_idle_timeout_ms` and `stream_max_retries`; keep those keys inside
  `[model_providers.custom]`.
- Bubblewrap warning: install `bubblewrap` through the OS package manager.
- Existing Codex sessions do not hot-load config changes. Start a new Codex
  process after changing `config.toml` or switching providers.
- `Image generation is not enabled for this group`: Codex custom providers use
  `wire_api = "responses"`, so even a text-only prompt is sent to
  `/v1/responses`. Some gateways reject the request before generation if the
  selected group/channel does not allow the image-generation capability
  declaration. Put Codex keys in a trusted Codex-only group/channel that can
  accept Responses requests, or configure gateway routing so Codex requests go
  to such a channel. Do not enable image generation on public or untrusted test
  groups just to make Codex work; issue separate public text-only keys instead.
- `cc-switch provider list/current` shows the wrong API URL: check the actual
  `~/.codex/config.toml` top-level `model_provider = "custom"` and
  `[model_providers.custom].base_url`. This can happen if a provider entry was
  manually populated with a full multi-provider TOML blob. The bootstrap script
  stores one-provider snippets in `cc-switch` to avoid that ambiguity.

## References

- Codex config reference: https://developers.openai.com/codex/config-reference
- Codex standalone installer: https://chatgpt.com/codex/install.sh
- Claude Code installer: https://claude.ai/install.sh
- GitHub CLI Linux install: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
- cc-switch-cli releases: https://github.com/saladday/cc-switch-cli/releases/latest
