# AutoDL AI Tools Bootstrap

This runbook configures a fresh AutoDL Ubuntu machine for model-training work
with Codex CLI, Claude Code, GitHub CLI, `cc-switch`, `ripgrep`, `tmux`, and a
two-port `sing-box` proxy layout.

Use this when opening repeat AutoDL training machines. The target machine is
usually `root` inside an AutoDL container.

## Target State

The bootstrap creates two local proxy ports:

```text
127.0.0.1:7890  general proxy for GitHub, downloads, gh, git, and installers
127.0.0.1:7891  Claude-only chained proxy for Claude Code runtime
```

The shell does not globally export proxy variables. Use:

```bash
with-proxy git pull
with-proxy gh repo clone AlexJJ009/agent-tools ~/agent-tools
with-proxy curl -I https://github.com
```

The `claude` command is wrapped so Claude Code automatically uses
`127.0.0.1:7891`. The real binary is available as:

```bash
claude.real
```

Codex stays on one stable provider bucket:

```toml
model_provider = "custom"

[model_providers.custom]
supports_websockets = false
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
```

## Required Inputs

Prepare these before running the bootstrap.

| Input | Meaning |
| --- | --- |
| AutoDL SSH target | Example: `autodl` in `~/.ssh/config`. Public-key SSH should already work. |
| GitHub PAT | For `gh auth login` and cloning `AlexJJ009/agent-tools`. |
| General sing-box JSON | The fast ordinary proxy config, usually copied from the Japanese server `/etc/sing-box/config.json`. |
| Claude chained-proxy YAML | The mihomo YAML containing the Claude chain nodes, such as `海外打底` and `ISP-HTTPS`. |
| Codex provider config | Prefer a transfer tarball copied from a trusted configured machine, or provide `CODEX_PROVIDERS_JSON`. |

Optional:

| Input | Meaning |
| --- | --- |
| sing-box release tarball | Pre-stage this if the target cannot download GitHub releases before proxy setup. |
| Codex resume transfer tarball | Optional history/session data exported from another machine, used to make `codex resume` work on the new AutoDL host. |
| `GENERAL_OUTBOUND_TAG` | Override the ordinary proxy outbound tag. Defaults to the general config route `final`, usually `proxy`. |
| `CLAUDE_BASE_PROXY_NAME` | Defaults to `海外打底`. |
| `CLAUDE_CHAIN_PROXY_NAME` | Defaults to `ISP-HTTPS`. |

## Agent Workflow

From a controller machine that can SSH into both the reference Japanese server
and the AutoDL target:

1. Copy the reference general proxy config from the Japanese server:

   ```bash
   ssh yuyun-jp-newapi 'cat /etc/sing-box/config.json' > /tmp/yuyun-sing-box.json
   ```

2. Put the Claude chained-proxy YAML on the controller machine. Do not commit it
   to the repo because it contains proxy credentials.

3. Optionally create a Codex provider transfer tarball from a trusted machine:

   ```bash
   ssh yuyun-jp-newapi 'set -e
   tmp=$(mktemp -d)
   umask 077
   mkdir -p "$tmp/.codex" "$tmp/.cc-switch"
   cp -p ~/.codex/config.toml ~/.codex/auth.json "$tmp/.codex/"
   cp -p ~/.cc-switch/cc-switch.db "$tmp/.cc-switch/"
   tar -C "$tmp" -czf /tmp/codex-provider-transfer.tgz .codex .cc-switch
   rm -rf "$tmp"'

   scp yuyun-jp-newapi:/tmp/codex-provider-transfer.tgz /tmp/codex-provider-transfer.tgz
   ssh yuyun-jp-newapi 'rm -f /tmp/codex-provider-transfer.tgz'
   ```

4. Optionally create a Codex resume transfer tarball from the Japanese server.
   This copies only resumable state and avoids runtime caches, worktrees,
   packages, app-server sockets, provider config, and auth files:

   ```bash
   ssh yuyun-jp-newapi 'set -euo pipefail
   ts=$(date +%Y%m%d%H%M%S)
   export_dir="/tmp/codex-resume-export-$ts"
   tarball="/tmp/codex-resume-export-$ts.tgz"
   mkdir -p "$export_dir/.codex"

   for db in state_5.sqlite memories_1.sqlite goals_1.sqlite; do
     if [ -f "$HOME/.codex/$db" ]; then
       sqlite3 "$HOME/.codex/$db" ".backup '\''$export_dir/.codex/$db'\''"
     fi
   done

   cd "$HOME"
   for path in \
     .codex/sessions \
     .codex/archived_sessions \
     .codex/attachments \
     .codex/shell_snapshots \
     .codex/memories \
     .codex/session_index.jsonl \
     .codex/history.jsonl; do
     if [ -e "$path" ]; then
       rsync -a --relative "$path" "$export_dir/"
     fi
   done

   tar -C "$export_dir" -czf "$tarball" .codex
   sha256sum "$tarball"
   du -sh "$tarball"
   printf "TARBALL=%s\n" "$tarball"'
   ```

   Then transfer it through the controller machine:

   ```bash
   scp yuyun-jp-newapi:/tmp/codex-resume-export-YYYYMMDDHHMMSS.tgz /tmp/codex-resume-transfer.tgz
   ```

5. Copy inputs and the bootstrap script to AutoDL:

   ```bash
   scp scripts/bootstrap_autodl_ai_tools.sh autodl:/tmp/bootstrap_autodl_ai_tools.sh
   scp /tmp/yuyun-sing-box.json autodl:/tmp/yuyun-sing-box.json
   scp /path/to/claude-chain.yaml autodl:/tmp/claude-chain.yaml
   scp /tmp/codex-provider-transfer.tgz autodl:/tmp/codex-provider-transfer.tgz
   scp /tmp/codex-resume-transfer.tgz autodl:/tmp/codex-resume-transfer.tgz
   ```

6. Run the script on AutoDL. Put the PAT in an environment variable, not shell
   history:

   ```bash
   ssh autodl
   chmod +x /tmp/bootstrap_autodl_ai_tools.sh
   read -rsp "GitHub PAT: " GITHUB_PAT
   printf '\n'

   GITHUB_PAT="$GITHUB_PAT" \
   GENERAL_SING_BOX_CONFIG=/tmp/yuyun-sing-box.json \
   CLAUDE_MIHOMO_YAML=/tmp/claude-chain.yaml \
   CODEX_PROVIDER_TRANSFER_TGZ=/tmp/codex-provider-transfer.tgz \
   CODEX_RESUME_TRANSFER_TGZ=/tmp/codex-resume-transfer.tgz \
   /tmp/bootstrap_autodl_ai_tools.sh

   unset GITHUB_PAT
   rm -f /tmp/codex-provider-transfer.tgz /tmp/codex-resume-transfer.tgz
   ```

## Provider JSON Alternative

If no provider transfer tarball is available, pass provider JSON:

```bash
read -rsp "GitHub PAT: " GITHUB_PAT
printf '\n'
read -rsp "Codex provider API key: " CODEX_KEY
printf '\n'

export CODEX_DEFAULT_PROVIDER="dragtokens"
export CODEX_PROVIDERS_JSON="$(
  jq -n --arg key "$CODEX_KEY" '[
    {
      "id": "dragtokens",
      "name": "dragtokens",
      "base_url": "https://dragtokens.com/v1",
      "model": "gpt-5.5",
      "api_key": $key
    }
  ]'
)"

GITHUB_PAT="$GITHUB_PAT" \
GENERAL_SING_BOX_CONFIG=/tmp/yuyun-sing-box.json \
CLAUDE_MIHOMO_YAML=/tmp/claude-chain.yaml \
CODEX_DEFAULT_PROVIDER="$CODEX_DEFAULT_PROVIDER" \
CODEX_PROVIDERS_JSON="$CODEX_PROVIDERS_JSON" \
/tmp/bootstrap_autodl_ai_tools.sh

unset GITHUB_PAT CODEX_KEY CODEX_PROVIDERS_JSON
```

## Script Behavior

`scripts/bootstrap_autodl_ai_tools.sh` performs these steps:

1. Installs base Ubuntu packages.
2. Installs `sing-box`.
3. Builds `/etc/sing-box/dual-proxy.json`.
4. Starts `sing-box` and writes `start-singbox-proxy`.
5. Installs `with-proxy`.
6. Installs `gh`, `cc-switch`, Codex CLI, and Claude Code.
7. Authenticates `gh` and clones or updates `~/agent-tools`.
8. Runs `~/agent-tools/install.sh` with server-safe flags.
9. Configures Codex provider config from either transfer tarball or JSON.
10. Optionally imports Codex resume history from `CODEX_RESUME_TRANSFER_TGZ`.
11. Validates tools, proxy ports, Codex config, and cc-switch provider state.

The script avoids the current Codex installer checksum issue by downloading the
latest GitHub release asset directly, verifying `codex-package_SHA256SUMS`, and
installing the standalone binary manually.

If the Claude native installer downloads the official binary but hangs during
its install phase, the script installs the downloaded binary manually and then
wraps `claude` to use the Claude chained proxy.

## Validation Commands

Run these on the AutoDL target:

```bash
gh --version | head -n 1
codex --version
claude --version
cc-switch --version
sing-box version | head -n 1
rg --version | head -n 1

netstat -lntp | grep -E '7890|7891'
env | grep -i '_proxy' || true

with-proxy curl -I --max-time 60 https://github.com
curl --proxy http://127.0.0.1:7891 -I -L --max-time 60 https://claude.ai/install.sh

cc-switch config validate -a codex
cc-switch provider current -a codex

codex exec --strict-config \
  -s read-only --skip-git-repo-check --ephemeral \
  'Reply exactly OK'

sqlite3 ~/.codex/state_5.sqlite \
  'select count(*) from threads; select model_provider, count(*) from threads group by 1;'

python3 - <<'PY'
import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path.home() / ".codex/state_5.sqlite")
missing = [(tid, path) for tid, path in conn.execute("select id, rollout_path from threads") if not Path(path).exists()]
print(f"missing_rollout_paths={len(missing)}")
PY
```

Expected:

- `7890` and `7891` listen only on `127.0.0.1`.
- Default shell has no global proxy variables.
- `with-proxy` can access GitHub.
- Claude chain returns a redirect to `downloads.claude.ai`, not the regional
  unavailable page.
- Codex strict-config request returns `OK`.
- If resume history was imported, all rows should remain under
  `model_provider = custom`, and `missing_rollout_paths` should be `0`.

## Current Known Good Layout

Observed working setup on AutoDL:

```text
general proxy:
  AutoDL 127.0.0.1:7890
  -> Japanese server sing-box main selector `proxy`
  -> default `vless-reality`

Claude proxy:
  AutoDL 127.0.0.1:7891
  -> YAML `海外打底`
  -> YAML `ISP-HTTPS`
```

Tested alternatives:

- `Japanese main proxy -> data center SOCKS5` connected but Claude returned a
  Cloudflare challenge `403`.
- `Japanese main proxy -> ISP-HTTPS` returned `400 Bad Request` from the second
  hop.

Therefore, keep the Claude chain on the original YAML chain unless a new live
test proves another path works.

## Security Rules

- Do not commit GitHub PATs, Codex provider keys, or proxy credentials.
- Keep `/root/.codex/auth.json` and `/root/.cc-switch/cc-switch.db` at `0600`.
- Remove `/tmp/codex-provider-transfer.tgz` after bootstrap.
- Keep the source YAML and copied sing-box JSON outside git unless they are
  sanitized.

## Handoff To An Agent

Prompt for a future agent:

```text
Configure this AutoDL host using docs/AUTODL_AI_TOOLS_BOOTSTRAP.md.
Use scripts/bootstrap_autodl_ai_tools.sh.
I will provide:
- SSH alias for the AutoDL host
- GitHub PAT
- reference general sing-box config JSON
- Claude chained-proxy mihomo YAML
- Codex provider transfer tarball or provider JSON

After running, validate all commands in the Validation Commands section and
report exact versions, proxy ports, current cc-switch provider, and Codex
strict-config result.
```
