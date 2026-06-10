#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a fresh AutoDL Ubuntu machine for agent-driven training work.
#
# Required inputs are passed as environment variables:
#   GITHUB_PAT                  GitHub PAT for gh auth and repo clone/update.
#   GENERAL_SING_BOX_CONFIG     sing-box JSON for the fast ordinary proxy.
#   CLAUDE_MIHOMO_YAML          mihomo YAML containing Claude chained proxy nodes.
#
# Provider inputs:
#   Prefer CODEX_PROVIDER_TRANSFER_TGZ, a tarball containing .codex/ and
#   .cc-switch/ copied from a trusted configured machine.
#   Otherwise provide CODEX_PROVIDERS_JSON and CODEX_DEFAULT_PROVIDER.
#
# Optional inputs:
#   SING_BOX_TARBALL            Pre-staged sing-box linux-amd64 tar.gz.
#   SING_BOX_VERSION            Default: 1.13.12.
#   AGENT_TOOLS_REPO            Default: AlexJJ009/agent-tools.
#   AGENT_TOOLS_DIR             Default: $HOME/agent-tools.
#   GENERAL_PROXY_PORT          Default: 7890.
#   CLAUDE_PROXY_PORT           Default: 7891. Reserved for container Claude chain.
#   CLAUDE_BASE_PROXY_NAME      Default: 海外打底.
#   CLAUDE_CHAIN_PROXY_NAME     Default: ISP-HTTPS.
#   CLAUDE_INSTALL_TIMEOUT_SECONDS
#                              Default: 2400.
#   CODEX_RESUME_TRANSFER_TGZ  Optional tarball containing Codex resume data
#                              exported from another machine.

log() {
  printf '[autodl-bootstrap] %s\n' "$*" >&2
}

die() {
  printf '[autodl-bootstrap] ERROR: %s\n' "$*" >&2
  exit 1
}

require_file() {
  local path="$1"
  local label="$2"
  [[ -n "$path" && -f "$path" ]] || die "$label not found: $path"
}

export DEBIAN_FRONTEND=noninteractive
export PATH="$HOME/.local/bin:$PATH"

AGENT_TOOLS_REPO="${AGENT_TOOLS_REPO:-AlexJJ009/agent-tools}"
AGENT_TOOLS_DIR="${AGENT_TOOLS_DIR:-$HOME/agent-tools}"
SING_BOX_VERSION="${SING_BOX_VERSION:-1.13.12}"
GENERAL_PROXY_PORT="${GENERAL_PROXY_PORT:-7890}"
CLAUDE_PROXY_PORT="${CLAUDE_PROXY_PORT:-7891}"
CLAUDE_BASE_PROXY_NAME="${CLAUDE_BASE_PROXY_NAME:-海外打底}"
CLAUDE_CHAIN_PROXY_NAME="${CLAUDE_CHAIN_PROXY_NAME:-ISP-HTTPS}"
CLAUDE_INSTALL_TIMEOUT_SECONDS="${CLAUDE_INSTALL_TIMEOUT_SECONDS:-2400}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_MODEL_PROVIDER_ID="${CODEX_MODEL_PROVIDER_ID:-custom}"

: "${GITHUB_PAT:?GITHUB_PAT is required}"
: "${GENERAL_SING_BOX_CONFIG:?GENERAL_SING_BOX_CONFIG is required}"
: "${CLAUDE_MIHOMO_YAML:?CLAUDE_MIHOMO_YAML is required}"

require_file "$GENERAL_SING_BOX_CONFIG" "GENERAL_SING_BOX_CONFIG"
require_file "$CLAUDE_MIHOMO_YAML" "CLAUDE_MIHOMO_YAML"

install_base_packages() {
  log "Installing base packages"
  apt-get update
  apt-get install -y \
    ca-certificates curl git unzip tar gzip jq python3 python3-venv \
    python3-yaml gnupg lsb-release sqlite3 bubblewrap ripgrep tmux \
    net-tools lsof rsync
}

install_sing_box() {
  if command -v sing-box >/dev/null 2>&1; then
    log "sing-box already installed: $(sing-box version | head -n 1)"
    return
  fi

  local tmp
  tmp="$(mktemp -d)"
  if [[ -n "${SING_BOX_TARBALL:-}" ]]; then
    require_file "$SING_BOX_TARBALL" "SING_BOX_TARBALL"
    log "Installing sing-box from pre-staged tarball"
    tar -C "$tmp" -xzf "$SING_BOX_TARBALL"
  else
    log "Downloading sing-box $SING_BOX_VERSION directly"
    curl -fL --connect-timeout 20 --max-time 300 \
      -o "$tmp/sing-box.tar.gz" \
      "https://github.com/SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}/sing-box-${SING_BOX_VERSION}-linux-amd64.tar.gz"
    tar -C "$tmp" -xzf "$tmp/sing-box.tar.gz"
  fi

  local bin
  bin="$(find "$tmp" -type f -name sing-box -perm -111 | head -n 1)"
  [[ -n "$bin" ]] || die "sing-box binary not found in archive"
  install -m 0755 "$bin" /usr/local/bin/sing-box
  rm -rf "$tmp"
  sing-box version | head -n 5
}

write_dual_proxy_config() {
  log "Writing dual sing-box proxy config"
  mkdir -p /etc/sing-box /var/log/sing-box

  GENERAL_SING_BOX_CONFIG="$GENERAL_SING_BOX_CONFIG" \
  CLAUDE_MIHOMO_YAML="$CLAUDE_MIHOMO_YAML" \
  GENERAL_PROXY_PORT="$GENERAL_PROXY_PORT" \
  CLAUDE_PROXY_PORT="$CLAUDE_PROXY_PORT" \
  CLAUDE_BASE_PROXY_NAME="$CLAUDE_BASE_PROXY_NAME" \
  CLAUDE_CHAIN_PROXY_NAME="$CLAUDE_CHAIN_PROXY_NAME" \
  python3 - <<'PY'
import json
import os
from pathlib import Path

import yaml

general_path = Path(os.environ["GENERAL_SING_BOX_CONFIG"])
claude_yaml_path = Path(os.environ["CLAUDE_MIHOMO_YAML"])
general_port = int(os.environ["GENERAL_PROXY_PORT"])
claude_port = int(os.environ["CLAUDE_PROXY_PORT"])
base_name = os.environ["CLAUDE_BASE_PROXY_NAME"]
chain_name = os.environ["CLAUDE_CHAIN_PROXY_NAME"]

general = json.loads(general_path.read_text())
clash = yaml.safe_load(claude_yaml_path.read_text(encoding="utf-8"))
clash_proxies = {p["name"]: p for p in clash.get("proxies", [])}

if base_name not in clash_proxies:
    raise SystemExit(f"missing Claude base proxy in YAML: {base_name}")
if chain_name not in clash_proxies:
    raise SystemExit(f"missing Claude chain proxy in YAML: {chain_name}")

general_outbounds = general.get("outbounds", [])
if not general_outbounds:
    raise SystemExit("GENERAL_SING_BOX_CONFIG has no outbounds")

general_outbound_tag = os.environ.get("GENERAL_OUTBOUND_TAG")
if not general_outbound_tag:
    route = general.get("route", {})
    general_outbound_tag = route.get("final") or "proxy"

known_tags = {o.get("tag") for o in general_outbounds}
if general_outbound_tag not in known_tags:
    raise SystemExit(
        f"GENERAL_OUTBOUND_TAG {general_outbound_tag!r} not found in general config outbounds"
    )

base = clash_proxies[base_name]
chain = clash_proxies[chain_name]

if base.get("type") != "http" or chain.get("type") != "http":
    raise SystemExit("this bootstrap currently expects Claude base and chain nodes to be HTTP proxies")

outbounds = list(general_outbounds)
outbounds.extend(
    [
        {
            "type": "http",
            "tag": "claude-base",
            "server": base["server"],
            "server_port": int(base["port"]),
            "username": base.get("username", ""),
            "password": base.get("password", ""),
            "tls": {
                "enabled": bool(base.get("tls")),
                "insecure": bool(base.get("skip-cert-verify")),
            },
        },
        {
            "type": "http",
            "tag": "claude-chain",
            "server": chain["server"],
            "server_port": int(chain["port"]),
            "username": chain.get("username", ""),
            "password": chain.get("password", ""),
            "detour": "claude-base",
        },
    ]
)

config = {
    "log": {"level": "info", "timestamp": True},
    "dns": general.get(
        "dns",
        {
            "servers": [{"type": "udp", "tag": "local-dns", "server": "223.5.5.5"}],
            "strategy": "prefer_ipv4",
        },
    ),
    "inbounds": [
        {
            "type": "mixed",
            "tag": "general-mixed-in",
            "listen": "127.0.0.1",
            "listen_port": general_port,
        },
        {
            "type": "mixed",
            "tag": "claude-mixed-in",
            "listen": "127.0.0.1",
            "listen_port": claude_port,
        },
    ],
    "outbounds": outbounds,
    "route": {
        "default_domain_resolver": {"server": "local-dns"},
        "rules": [
            {"ip_is_private": True, "outbound": "direct"},
            {
                "ip_cidr": [
                    "100.64.0.0/10",
                    "100.100.0.0/10",
                    "127.0.0.0/8",
                    "10.0.0.0/8",
                    "172.16.0.0/12",
                    "192.168.0.0/16",
                ],
                "outbound": "direct",
            },
            {"inbound": ["general-mixed-in"], "outbound": general_outbound_tag},
            {"inbound": ["claude-mixed-in"], "outbound": "claude-chain"},
        ],
        "final": "direct",
    },
}

out = Path("/etc/sing-box/dual-proxy.json")
out.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
out.chmod(0o600)
PY

  sing-box check -c /etc/sing-box/dual-proxy.json
}

install_proxy_helpers() {
  log "Installing proxy helper scripts"
  mkdir -p "$HOME/.local/bin"

  cat > "$HOME/.local/bin/start-singbox-proxy" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /var/log/sing-box
if [ -s /var/run/sing-box-dual.pid ] && kill -0 "$(cat /var/run/sing-box-dual.pid)" 2>/dev/null; then
  exit 0
fi
nohup /usr/local/bin/sing-box run -c /etc/sing-box/dual-proxy.json >/var/log/sing-box/dual-proxy.log 2>&1 &
echo "$!" > /var/run/sing-box-dual.pid
SH
  chmod 0755 "$HOME/.local/bin/start-singbox-proxy"

  cat > "$HOME/.local/bin/with-proxy" <<SH
#!/usr/bin/env bash
export HTTP_PROXY="http://127.0.0.1:${GENERAL_PROXY_PORT}"
export HTTPS_PROXY="http://127.0.0.1:${GENERAL_PROXY_PORT}"
export http_proxy="http://127.0.0.1:${GENERAL_PROXY_PORT}"
export https_proxy="http://127.0.0.1:${GENERAL_PROXY_PORT}"
export ALL_PROXY="socks5://127.0.0.1:${GENERAL_PROXY_PORT}"
exec "\$@"
SH
  chmod 0755 "$HOME/.local/bin/with-proxy"

  local bashrc="$HOME/.bashrc"
  touch "$bashrc"
  python3 - <<'PY'
from pathlib import Path

p = Path.home() / ".bashrc"
text = p.read_text() if p.exists() else ""
start = "# >>> agent-tools AutoDL proxy >>>"
end = "# <<< agent-tools AutoDL proxy <<<"
block = f"""{start}
export PATH="$HOME/.local/bin:$PATH"
if [ -x "$HOME/.local/bin/start-singbox-proxy" ]; then
  "$HOME/.local/bin/start-singbox-proxy" >/dev/null 2>&1 || true
fi
{end}
"""
if start in text and end in text:
    pre = text.split(start)[0]
    post = text.split(end, 1)[1]
    text = pre + block + post.lstrip("\n")
else:
    text = text.rstrip() + "\n\n" + block
p.write_text(text)
PY

  "$HOME/.local/bin/start-singbox-proxy"
}

install_gh() {
  if command -v gh >/dev/null 2>&1; then
    log "gh already installed: $(gh --version | head -n 1)"
    return
  fi
  log "Installing GitHub CLI"
  local tmp asset url
  tmp="$(mktemp -d)"
  url="$(with-proxy curl -fsSL https://api.github.com/repos/cli/cli/releases/latest \
    | jq -r '.assets[] | select(.name | test("^gh_[0-9.]+_linux_amd64.deb$")) | .browser_download_url' \
    | head -n 1)"
  [[ -n "$url" ]] || die "could not resolve latest gh linux amd64 .deb"
  asset="$tmp/gh.deb"
  with-proxy curl -fL --connect-timeout 20 --max-time 600 -o "$asset" "$url"
  dpkg -i "$asset"
  rm -rf "$tmp"
}

install_cc_switch() {
  if command -v cc-switch >/dev/null 2>&1; then
    log "cc-switch already installed: $(cc-switch --version)"
    return
  fi
  log "Installing cc-switch"
  with-proxy curl -fsSL --connect-timeout 20 --max-time 600 \
    https://github.com/saladday/cc-switch-cli/releases/latest/download/install.sh \
    | CC_SWITCH_FORCE=1 bash
}

install_codex() {
  if command -v codex >/dev/null 2>&1; then
    log "codex already installed: $(codex --version)"
    return
  fi

  log "Installing Codex CLI from GitHub release package"
  local tmp latest tag asset checksum sums_url asset_url codex_bin
  tmp="$(mktemp -d)"
  latest="$tmp/latest.json"
  with-proxy curl -fsSL https://api.github.com/repos/openai/codex/releases/latest > "$latest"
  tag="$(jq -r '.tag_name' "$latest")"
  asset="codex-package-x86_64-unknown-linux-musl.tar.gz"
  asset_url="$(jq -r --arg name "$asset" '.assets[] | select(.name == $name) | .browser_download_url' "$latest")"
  sums_url="$(jq -r '.assets[] | select(.name == "codex-package_SHA256SUMS") | .browser_download_url' "$latest")"
  [[ -n "$tag" && -n "$asset_url" && -n "$sums_url" ]] || die "could not resolve Codex release assets"

  with-proxy curl -fL --connect-timeout 20 --max-time 1200 -o "$tmp/$asset" "$asset_url"
  with-proxy curl -fsSL "$sums_url" > "$tmp/codex-package_SHA256SUMS"
  checksum="$(awk -v asset="$asset" '$2 == asset {print $1}' "$tmp/codex-package_SHA256SUMS")"
  [[ -n "$checksum" ]] || die "checksum not found for $asset in $tag"
  (cd "$tmp" && printf '%s  %s\n' "$checksum" "$asset" | sha256sum -c -)
  tar -C "$tmp" -xzf "$tmp/$asset"
  codex_bin="$(find "$tmp" -type f -name codex -perm -111 | head -n 1)"
  [[ -n "$codex_bin" ]] || die "Codex binary not found in package"

  local version="${tag#rust-v}"
  mkdir -p "$HOME/.codex/packages/standalone/releases/${version}-x86_64-unknown-linux-musl/bin" "$HOME/.local/bin"
  install -m 0755 "$codex_bin" "$HOME/.codex/packages/standalone/releases/${version}-x86_64-unknown-linux-musl/bin/codex"
  ln -sfn "$HOME/.codex/packages/standalone/releases/${version}-x86_64-unknown-linux-musl" "$HOME/.codex/packages/standalone/current"
  ln -sfn "$HOME/.codex/packages/standalone/current/bin/codex" "$HOME/.local/bin/codex"
  rm -rf "$tmp"
  codex --version
}

install_claude() {
  if command -v claude >/dev/null 2>&1; then
    log "claude already installed: $(claude --version)"
    return
  fi

  log "Installing Claude Code through chained Claude proxy"
  local status=0
  HTTP_PROXY="http://127.0.0.1:${CLAUDE_PROXY_PORT}" \
  HTTPS_PROXY="http://127.0.0.1:${CLAUDE_PROXY_PORT}" \
  http_proxy="http://127.0.0.1:${CLAUDE_PROXY_PORT}" \
  https_proxy="http://127.0.0.1:${CLAUDE_PROXY_PORT}" \
  ALL_PROXY="socks5://127.0.0.1:${CLAUDE_PROXY_PORT}" \
    timeout "$CLAUDE_INSTALL_TIMEOUT_SECONDS" \
    bash -c 'curl -fsSL --connect-timeout 20 --max-time 1800 https://claude.ai/install.sh | bash -s latest' || status=$?

  if ! command -v claude >/dev/null 2>&1; then
    log "Claude installer did not finish cleanly (status $status); trying downloaded native binary fallback"
    local bin version
    bin="$(find "$HOME/.claude/downloads" -maxdepth 1 -type f -name 'claude-*-linux-x64' -perm -111 2>/dev/null | sort -V | tail -n 1 || true)"
    [[ -n "$bin" ]] || die "Claude installer failed and no downloaded binary was found"
    version="$(basename "$bin" | sed -E 's/^claude-([0-9.]+)-linux-x64$/\1/')"
    mkdir -p "$HOME/.local/share/claude/versions" "$HOME/.local/bin"
    install -m 0755 "$bin" "$HOME/.local/share/claude/versions/$version"
    ln -sfn "$HOME/.local/share/claude/versions/$version" "$HOME/.local/bin/claude"
  fi

  wrap_claude
}

wrap_claude() {
  log "Installing host Claude proxy wrapper"
  local current real
  current="$(command -v claude)"
  real="$(readlink -f "$current")"
  mkdir -p "$HOME/.local/bin"
  if [[ "$real" == "$HOME/.local/bin/claude" ]]; then
    mv "$HOME/.local/bin/claude" "$HOME/.local/bin/claude.real"
  else
    ln -sfn "$real" "$HOME/.local/bin/claude.real"
  fi

  cat > "$HOME/.local/bin/claude" <<SH
#!/usr/bin/env bash
# Host Claude Code uses the normal host proxy. Container Claude Code should
# use per-container chain proxy configuration instead.
export HTTP_PROXY="\${HTTP_PROXY:-http://127.0.0.1:${GENERAL_PROXY_PORT}}"
export HTTPS_PROXY="\${HTTPS_PROXY:-http://127.0.0.1:${GENERAL_PROXY_PORT}}"
export http_proxy="\${http_proxy:-http://127.0.0.1:${GENERAL_PROXY_PORT}}"
export https_proxy="\${https_proxy:-http://127.0.0.1:${GENERAL_PROXY_PORT}}"
export ALL_PROXY="\${ALL_PROXY:-socks5://127.0.0.1:${GENERAL_PROXY_PORT}}"
exec "\$HOME/.local/bin/claude.real" "\$@"
SH
  chmod 0755 "$HOME/.local/bin/claude"
}

configure_github_and_clone() {
  log "Authenticating gh and cloning/updating $AGENT_TOOLS_REPO"
  printf '%s\n' "$GITHUB_PAT" | with-proxy gh auth login --hostname github.com --with-token >/dev/null
  with-proxy gh auth setup-git >/dev/null

  if [[ -d "$AGENT_TOOLS_DIR/.git" ]]; then
    with-proxy git -C "$AGENT_TOOLS_DIR" pull --ff-only
  else
    mkdir -p "$(dirname "$AGENT_TOOLS_DIR")"
    with-proxy gh repo clone "$AGENT_TOOLS_REPO" "$AGENT_TOOLS_DIR"
  fi
}

run_agent_tools_install() {
  log "Running agent-tools install.sh"
  (cd "$AGENT_TOOLS_DIR" && ./install.sh \
    --root "$HOME" \
    --max-depth 3 \
    --codex-proxy-wrapper never \
    --no-codex-config \
    --no-codex-remote-control \
    --no-registry \
    --no-cron \
    --no-agent-core \
    --no-cc-switch-update)
}

clean_codex_strict_config() {
  python3 - <<'PY'
from pathlib import Path

p = Path.home() / ".codex/config.toml"
if not p.exists():
    raise SystemExit(0)
remove = {"disable_response_storage", "network_access"}
out = []
for line in p.read_text().splitlines():
    key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("[") else None
    if key in remove:
        continue
    out.append(line)
p.write_text("\n".join(out) + "\n")
PY
}

configure_codex_from_transfer() {
  local tgz="${CODEX_PROVIDER_TRANSFER_TGZ:-}"
  [[ -n "$tgz" ]] || return 1
  require_file "$tgz" "CODEX_PROVIDER_TRANSFER_TGZ"
  log "Configuring Codex providers from transfer tarball"
  tar -C "$HOME" -xzf "$tgz"
  chmod 700 "$HOME/.codex" "$HOME/.cc-switch" 2>/dev/null || true
  chmod 600 "$HOME/.codex/auth.json" "$HOME/.codex/config.toml" "$HOME/.cc-switch/cc-switch.db" 2>/dev/null || true
  clean_codex_strict_config
}

configure_codex_from_json() {
  [[ -n "${CODEX_PROVIDERS_JSON:-}" ]] || die "set CODEX_PROVIDER_TRANSFER_TGZ or CODEX_PROVIDERS_JSON"
  : "${CODEX_DEFAULT_PROVIDER:?CODEX_DEFAULT_PROVIDER is required when using CODEX_PROVIDERS_JSON}"
  log "Configuring Codex providers from CODEX_PROVIDERS_JSON"

  CODEX_MODEL="$CODEX_MODEL" \
  CODEX_MODEL_PROVIDER_ID="$CODEX_MODEL_PROVIDER_ID" \
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
bucket = os.environ.get("CODEX_MODEL_PROVIDER_ID", "custom")
safe_id = re.compile(r"^[A-Za-z0-9_.-]+$")

if not providers:
    raise SystemExit("CODEX_PROVIDERS_JSON is empty")
if default_provider not in {p["id"] for p in providers}:
    raise SystemExit(f"default provider not found: {default_provider}")
if not safe_id.match(bucket):
    raise SystemExit(f"invalid bucket id: {bucket}")

codex_home.mkdir(parents=True, exist_ok=True)
default = next(p for p in providers if p["id"] == default_provider)
default_key = default["api_key"].strip()
if not default_key:
    raise SystemExit("default provider api_key is empty")

config = f"""
approval_policy = "on-request"
sandbox_mode = "workspace-write"
model = "{default.get('model', default_model)}"
model_reasoning_effort = "high"
service_tier = "priority"
model_provider = "{bucket}"

[features]
fast_mode = true
hooks = true
memories = true
goals = true
terminal_resize_reflow = true
remote_control = true

[model_providers.{bucket}]
name = "{default.get('name', default['id'])}"
base_url = "{default['base_url'].rstrip('/')}"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = false
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
""".strip() + "\n"
(codex_home / "config.toml").write_text(config)
(codex_home / "auth.json").write_text(json.dumps({"OPENAI_API_KEY": default_key}, indent=2) + "\n")
(codex_home / "auth.json").chmod(0o600)

os.system("cc-switch provider list -a codex >/dev/null 2>&1 || true")
db_path = home / ".cc-switch" / "cc-switch.db"
conn = sqlite3.connect(db_path)
now = int(time.time() * 1000)
conn.execute("UPDATE providers SET is_current=0 WHERE app_type='codex'")

for index, provider in enumerate(providers, start=1):
    pid = provider["id"]
    if not safe_id.match(pid):
        raise SystemExit(f"invalid provider id: {pid}")
    name = provider.get("name", pid)
    base_url = provider["base_url"].rstrip("/")
    model = provider.get("model", default_model)
    api_key = provider["api_key"].strip()
    if not api_key:
        raise SystemExit(f"provider {pid} has empty api_key")
    snippet = f"""
model = "{model}"
model_provider = "{bucket}"
model_reasoning_effort = "high"

[model_providers.{bucket}]
name = "{name}"
base_url = "{base_url}"
wire_api = "responses"
requires_openai_auth = true
supports_websockets = false
stream_idle_timeout_ms = 1800000
stream_max_retries = 20
""".strip() + "\n"
    settings = {"auth": {"OPENAI_API_KEY": api_key}, "config": snippet}
    meta = {"model": model, "wire_api": "responses", "managed_by": "autodl-bootstrap"}
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
            index * 10,
            f"Configured for Codex {model} Responses API",
            json.dumps(meta),
            1 if pid == default_provider else 0,
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
}

import_codex_resume_history() {
  local tgz="${CODEX_RESUME_TRANSFER_TGZ:-}"
  [[ -n "$tgz" ]] || return 0
  require_file "$tgz" "CODEX_RESUME_TRANSFER_TGZ"
  log "Importing Codex resume history from transfer tarball"

  local ts import_root backup_dir backup_root
  ts="$(date +%Y%m%d%H%M%S)"
  import_root="$(mktemp -d)"
  backup_dir="$HOME/.codex-migration-backups"
  backup_root="$backup_dir/codex-before-resume-import-$ts"
  mkdir -p "$backup_root/.codex"

  for db in state_5.sqlite memories_1.sqlite goals_1.sqlite logs_2.sqlite; do
    if [[ -f "$HOME/.codex/$db" ]]; then
      sqlite3 "$HOME/.codex/$db" ".backup '$backup_root/.codex/$db'" || true
    fi
  done

  for path in \
    auth.json config.toml installation_id session_index.jsonl history.jsonl .personality_migration \
    sessions archived_sessions attachments shell_snapshots memories skills; do
    if [[ -e "$HOME/.codex/$path" ]]; then
      rsync -a --ignore-missing-args "$HOME/.codex/$path" "$backup_root/.codex/"
    fi
  done

  if [[ -d "$HOME/.cc-switch" ]]; then
    mkdir -p "$backup_root/.cc-switch"
    rsync -a --exclude tmp --exclude cache --ignore-missing-args "$HOME/.cc-switch/" "$backup_root/.cc-switch/"
  fi

  tar -C "$backup_root" -czf "$backup_root.tgz" .
  chmod 600 "$backup_root.tgz"
  rm -rf "$backup_root"

  tar -C "$import_root" -xzf "$tgz"

  for d in sessions archived_sessions attachments shell_snapshots memories; do
    if [[ -d "$import_root/.codex/$d" ]]; then
      mkdir -p "$HOME/.codex/$d"
      rsync -a --ignore-existing "$import_root/.codex/$d/" "$HOME/.codex/$d/"
    fi
  done

  python3 - "$import_root" <<'PY'
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

home = Path.home()
import_root = Path(sys.argv[1])
codex = home / ".codex"
src_codex = import_root / ".codex"


def merge_jsonl_by_id(src: Path, dst: Path, key: str) -> tuple[int, int]:
    if not src.exists():
        return (0, 0)
    dst.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = set()
    existing_lines = set()
    if dst.exists():
        for line in dst.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line:
                continue
            existing_lines.add(line)
            try:
                value = json.loads(line).get(key)
                if value:
                    existing_ids.add(str(value))
            except Exception:
                pass

    total = appended = 0
    with src.open("r", encoding="utf-8", errors="replace") as f, dst.open("a", encoding="utf-8") as out:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            total += 1
            use_line = line not in existing_lines
            value = None
            try:
                value = json.loads(line).get(key)
                if value:
                    use_line = str(value) not in existing_ids
            except Exception:
                pass
            if use_line:
                out.write(line + "\n")
                appended += 1
                existing_lines.add(line)
                if value:
                    existing_ids.add(str(value))
    return total, appended


def merge_jsonl_exact(src: Path, dst: Path) -> tuple[int, int]:
    if not src.exists():
        return (0, 0)
    dst.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if dst.exists():
        existing = set(x for x in dst.read_text(encoding="utf-8", errors="replace").splitlines() if x)

    total = appended = 0
    with src.open("r", encoding="utf-8", errors="replace") as f, dst.open("a", encoding="utf-8") as out:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                continue
            total += 1
            if line not in existing:
                out.write(line + "\n")
                existing.add(line)
                appended += 1
    return total, appended


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_set(conn: sqlite3.Connection, schema: str) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            f"SELECT name FROM {schema}.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    escaped = table.replace('"', '""')
    return [r[1] for r in conn.execute(f'PRAGMA {schema}.table_info("{escaped}")')]


def merge_sqlite(src: Path, dst: Path, wanted: list[str] | None = None, skip: set[str] | None = None) -> dict[str, int]:
    if not src.exists() or not dst.exists():
        return {}
    skip = skip or set()
    conn = sqlite3.connect(dst)
    conn.execute("PRAGMA foreign_keys=OFF")
    src_sql = str(src).replace("'", "''")
    conn.execute(f"ATTACH DATABASE '{src_sql}' AS src")
    changed: dict[str, int] = {}
    try:
        main_tables = table_set(conn, "main")
        src_tables = table_set(conn, "src")
        candidates = wanted if wanted is not None else sorted(src_tables)
        for table in candidates:
            if table in skip or table not in main_tables or table not in src_tables:
                continue
            dst_cols = columns(conn, "main", table)
            src_cols = columns(conn, "src", table)
            cols = [c for c in dst_cols if c in src_cols]
            if not cols:
                continue
            before = conn.total_changes
            col_sql = ", ".join(qident(c) for c in cols)
            conn.execute(
                f"INSERT OR IGNORE INTO main.{qident(table)} ({col_sql}) "
                f"SELECT {col_sql} FROM src.{qident(table)}"
            )
            changed[table] = conn.total_changes - before
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE src")
        conn.close()
    return changed


idx_total, idx_appended = merge_jsonl_by_id(src_codex / "session_index.jsonl", codex / "session_index.jsonl", "id")
hist_total, hist_appended = merge_jsonl_exact(src_codex / "history.jsonl", codex / "history.jsonl")
state_changed = merge_sqlite(
    src_codex / "state_5.sqlite",
    codex / "state_5.sqlite",
    wanted=["agent_jobs", "agent_job_items", "threads", "thread_dynamic_tools", "thread_spawn_edges"],
)
mem_changed = merge_sqlite(src_codex / "memories_1.sqlite", codex / "memories_1.sqlite", skip={"_sqlx_migrations"})
goal_changed = merge_sqlite(src_codex / "goals_1.sqlite", codex / "goals_1.sqlite", skip={"_sqlx_migrations"})

print(json.dumps({
    "session_index": {"source_lines": idx_total, "appended": idx_appended},
    "history": {"source_lines": hist_total, "appended": hist_appended},
    "state_5": state_changed,
    "memories_1": mem_changed,
    "goals_1": goal_changed,
}, ensure_ascii=False, sort_keys=True))
PY

  python3 "$AGENT_TOOLS_DIR/migrate_codex_provider_bucket.py" \
    --target "$CODEX_MODEL_PROVIDER_ID" \
    --all-non-target-providers \
    --skip-live-config \
    --skip-cc-switch \
    --allow-running-codex \
    --apply \
    --yes

  python3 - <<'PY'
import sqlite3
from pathlib import Path

conn = sqlite3.connect(Path.home() / ".codex/state_5.sqlite")
missing = [(tid, path) for tid, path in conn.execute("select id, rollout_path from threads") if not Path(path).exists()]
if missing:
    for tid, path in missing[:20]:
        print(f"missing rollout path: {tid} {path}")
    raise SystemExit(f"{len(missing)} rollout paths are missing")
PY

  rm -rf "$import_root"
  log "Codex resume import complete; backup saved at $backup_root.tgz"
}

validate_install() {
  log "Validating install"
  gh --version | head -n 1
  codex --version
  claude --version
  cc-switch --version
  sing-box version | head -n 1
  rg --version | head -n 1

  netstat -lntp 2>/dev/null | grep -E ":(${GENERAL_PROXY_PORT}|${CLAUDE_PROXY_PORT})\\b" || die "proxy ports are not listening"
  with-proxy curl -I --connect-timeout 20 --max-time 60 https://github.com >/dev/null
  curl --proxy "http://127.0.0.1:${GENERAL_PROXY_PORT}" -I -L --connect-timeout 20 --max-time 60 https://claude.ai/install.sh >/dev/null
  codex features list >/dev/null
  cc-switch config validate -a codex >/dev/null
  cc-switch provider current -a codex
}

main() {
  install_base_packages
  install_sing_box
  write_dual_proxy_config
  install_proxy_helpers
  install_gh
  install_cc_switch
  configure_github_and_clone
  install_codex
  install_claude
  run_agent_tools_install
  configure_codex_from_transfer || configure_codex_from_json
  import_codex_resume_history
  validate_install
  log "Bootstrap complete"
}

main "$@"
