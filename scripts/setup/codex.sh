#!/usr/bin/env bash
# Codex machine setup: config.toml defaults and features, provider auth, project
# hook features, proxy wrapper, codex-here and remote control. When cc-switch is
# in use, run setup/cc-switch.sh first so its provider sync lands before the
# defaults are applied.
set -euo pipefail

SETUP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SETUP_DIR/lib.sh"

MAX_DEPTH="3"
INSTALL_CODEX_CONFIG=1
INSTALL_CODEX_PROJECT_HOOKS=1
INSTALL_CODEX_HERE=1
INSTALL_CODEX_PROXY_WRAPPER="${INSTALL_CODEX_PROXY_WRAPPER:-auto}"
INSTALL_CODEX_REMOTE_CONTROL="${INSTALL_CODEX_REMOTE_CONTROL:-1}"
CODEX_STREAM_IDLE_TIMEOUT_MS="${CODEX_STREAM_IDLE_TIMEOUT_MS:-1800000}"
CODEX_STREAM_MAX_RETRIES="${CODEX_STREAM_MAX_RETRIES:-20}"
CODEX_APPROVAL_POLICY="${CODEX_APPROVAL_POLICY:-on-request}"
CODEX_SANDBOX_MODE="${CODEX_SANDBOX_MODE:-workspace-write}"
CODEX_APPROVALS_REVIEWER="${CODEX_APPROVALS_REVIEWER:-guardian_subagent}"
CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_MODEL_REASONING_EFFORT="${CODEX_MODEL_REASONING_EFFORT:-high}"
CODEX_FEATURE_FAST_MODE="${CODEX_FEATURE_FAST_MODE:-true}"
CODEX_FEATURE_HOOKS="${CODEX_FEATURE_HOOKS:-true}"
CODEX_FEATURE_MEMORIES="${CODEX_FEATURE_MEMORIES:-false}"
CODEX_FEATURE_GOALS="${CODEX_FEATURE_GOALS:-true}"
CODEX_FEATURE_TERMINAL_RESIZE_REFLOW="${CODEX_FEATURE_TERMINAL_RESIZE_REFLOW:-true}"
CODEX_FEATURE_REMOTE_CONTROL="${CODEX_FEATURE_REMOTE_CONTROL:-true}"
CODEX_PROXY_TEST_URL="${CODEX_PROXY_TEST_URL:-https://chatgpt.com/backend-api/codex/responses}"
SCAN_ROOTS=()

check_codex_fast_mode() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_SERVICE_TIER" "$CODEX_FEATURE_FAST_MODE" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1]).expanduser()
expected_tier = sys.argv[2]
expected_fast_mode = sys.argv[3]

if not path.exists():
    print(f"WARNING: Codex Fast mode check skipped: missing {path}")
    raise SystemExit(0)

text = path.read_text(encoding="utf-8")
service_tier = None
fast_mode = None
in_features = False

for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        in_features = stripped == "[features]"
        continue
    if stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not in_features and key == "service_tier":
        match = re.match(r"(['\"])(.*?)\1", value)
        service_tier = match.group(2) if match else value
    if in_features and key == "fast_mode":
        fast_mode = value.split("#", 1)[0].strip().lower()

warnings = []
if service_tier != expected_tier:
    warnings.append(f'top-level service_tier is {service_tier!r}; expected "{expected_tier}"')
if fast_mode != expected_fast_mode:
    warnings.append(f'[features].fast_mode is {fast_mode!r}; expected {expected_fast_mode}')

if warnings:
    print("WARNING: Codex Fast mode is not fully enabled:")
    for warning in warnings:
        print(f"  - {warning}")
else:
    print(f"Codex Fast mode: service_tier={expected_tier}, fast_mode={expected_fast_mode}")
PY

  if ! command -v cc-switch >/dev/null 2>&1; then
    echo "WARNING: cc-switch not found on PATH; provider switching and custom bucket sync are not available."
  fi
}

configure_codex_defaults() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" "$CODEX_STREAM_IDLE_TIMEOUT_MS" "$CODEX_STREAM_MAX_RETRIES" "$CODEX_MODEL_CONTEXT_WINDOW" "$CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT" "$CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE" "$CODEX_MODEL_PROVIDER_ID" "$CODEX_APPROVAL_POLICY" "$CODEX_SANDBOX_MODE" "$CODEX_APPROVALS_REVIEWER" "$CODEX_MODEL" "$CODEX_MODEL_REASONING_EFFORT" "$CODEX_SERVICE_TIER" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
timeout = sys.argv[2]
retries = sys.argv[3]
context_window = sys.argv[4]
auto_compact_limit = sys.argv[5]
auto_compact_scope = sys.argv[6]
provider_id = sys.argv[7]
approval_policy = sys.argv[8]
sandbox_mode = sys.argv[9]
approvals_reviewer = sys.argv[10]
model = sys.argv[11]
model_reasoning_effort = sys.argv[12]
service_tier = sys.argv[13]
if not timeout.isdigit() or int(timeout) <= 0:
    raise SystemExit(f"invalid CODEX_STREAM_IDLE_TIMEOUT_MS: {timeout}")
if not retries.isdigit() or int(retries) <= 0:
    raise SystemExit(f"invalid CODEX_STREAM_MAX_RETRIES: {retries}")
if not context_window.isdigit() or int(context_window) <= 0:
    raise SystemExit(f"invalid CODEX_MODEL_CONTEXT_WINDOW: {context_window}")
if not auto_compact_limit.isdigit() or int(auto_compact_limit) <= 0:
    raise SystemExit(f"invalid CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT: {auto_compact_limit}")
if int(auto_compact_limit) >= int(context_window):
    raise SystemExit(
        "CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT must be lower than CODEX_MODEL_CONTEXT_WINDOW"
    )
if auto_compact_scope not in {"total", "body_after_prefix"}:
    raise SystemExit(f"invalid CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE: {auto_compact_scope}")
if not provider_id or not all(c.isalnum() or c in "-_." for c in provider_id):
    raise SystemExit(f"invalid CODEX_MODEL_PROVIDER_ID: {provider_id}")
ALLOWED_APPROVAL_POLICIES = {"on-request", "on-failure", "untrusted", "never"}
ALLOWED_SANDBOX_MODES = {"read-only", "workspace-write", "danger-full-access"}
ALLOWED_APPROVALS_REVIEWERS = {"user", "auto_review", "guardian_subagent"}
ALLOWED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "ultra"}
ALLOWED_SERVICE_TIERS = {"auto", "default", "fast", "priority"}
if approval_policy not in ALLOWED_APPROVAL_POLICIES:
    raise SystemExit(f"invalid CODEX_APPROVAL_POLICY: {approval_policy}")
if sandbox_mode not in ALLOWED_SANDBOX_MODES:
    raise SystemExit(f"invalid CODEX_SANDBOX_MODE: {sandbox_mode}")
if approvals_reviewer not in ALLOWED_APPROVALS_REVIEWERS:
    raise SystemExit(f"invalid CODEX_APPROVALS_REVIEWER: {approvals_reviewer}")
if not model or not all(c.isalnum() or c in "-_." for c in model):
    raise SystemExit(f"invalid CODEX_MODEL: {model}")
if model_reasoning_effort not in ALLOWED_REASONING_EFFORTS:
    raise SystemExit(f"invalid CODEX_MODEL_REASONING_EFFORT: {model_reasoning_effort}")
if service_tier not in ALLOWED_SERVICE_TIERS:
    raise SystemExit(f"invalid CODEX_SERVICE_TIER: {service_tier}")

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
preamble = lines[:first_table]
rest = lines[first_table:]

managed_top_level = {
    "disable_response_storage",
    "stream_idle_timeout_ms",
    "stream_max_retries",
    "model_context_window",
    "model_auto_compact_token_limit",
    "model_auto_compact_token_limit_scope",
    "model_provider",
    "approval_policy",
    "sandbox_mode",
    "approvals_reviewer",
    "model",
    "model_reasoning_effort",
    "service_tier",
}

kept = []
for line in preamble:
    stripped = line.strip()
    key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
    if key in managed_top_level:
        continue
    kept.append(line)

if kept and kept[-1].strip():
    kept.append("")
kept.append(f'approval_policy = "{approval_policy}"')
kept.append(f'sandbox_mode = "{sandbox_mode}"')
kept.append(f'approvals_reviewer = "{approvals_reviewer}"')
kept.append(f'model = "{model}"')
kept.append(f'model_reasoning_effort = "{model_reasoning_effort}"')
kept.append(f'service_tier = "{service_tier}"')
kept.append(f"model_context_window = {context_window}")
kept.append(f"model_auto_compact_token_limit = {auto_compact_limit}")
kept.append(f'model_auto_compact_token_limit_scope = "{auto_compact_scope}"')
kept.append(f'model_provider = "{provider_id}"')

provider_header = f"[model_providers.{provider_id}]"
provider_sections_to_remove = {
    "model_providers.openai-no-ws",
    "model_providers.ccswitch",
}
reserved_provider_ids = {
    "amazon-bedrock",
    "lmstudio",
    "ollama",
    "ollama-chat",
    "openai",
    "oss",
}

def _toml_section_path(line):
    stripped = line.strip()
    if stripped.startswith("[[") or not stripped.startswith("[") or not stripped.endswith("]"):
        return None
    return stripped[1:-1].strip()

def _is_toml_section(line):
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")

def _remove_model_provider_section(line):
    path = _toml_section_path(line)
    if not path:
        return False
    return any(path == section or path.startswith(section + ".") for section in provider_sections_to_remove)

def _has_third_party_model_provider(lines):
    for line in lines:
        path = _toml_section_path(line)
        if not path:
            continue
        parts = path.split(".")
        if len(parts) >= 2 and parts[0] == "model_providers":
            model_provider = parts[1]
            if model_provider != provider_id and model_provider not in reserved_provider_ids:
                return True
    return False

def _has_model_provider(lines, candidate):
    for line in lines:
        path = _toml_section_path(line)
        if not path:
            continue
        parts = path.split(".")
        if len(parts) >= 2 and parts[0] == "model_providers" and parts[1] == candidate:
            return True
    return False

has_third_party_model_provider = _has_third_party_model_provider(rest)
has_target_model_provider = _has_model_provider(rest, provider_id)
filtered_rest = []
i = 0
while i < len(rest):
    if _remove_model_provider_section(rest[i]):
        i += 1
        while i < len(rest) and not _is_toml_section(rest[i]):
            i += 1
        continue
    filtered_rest.append(rest[i])
    i += 1
rest = filtered_rest

def _force_target_provider_defaults(lines):
    updated = []
    in_target_provider = False
    target_found = False
    seen = set()
    transport_defaults = [
        ("supports_websockets", "true"),
        ("wire_api", '"responses"'),
        ("stream_idle_timeout_ms", timeout),
        ("stream_max_retries", retries),
    ]
    managed_provider_keys = {key for key, _ in transport_defaults}

    def append_missing_defaults():
        if not in_target_provider:
            return
        while updated and not updated[-1].strip():
            updated.pop()
        for key, value in transport_defaults:
            if key not in seen:
                updated.append(f"{key} = {value}")

    for line in lines:
        path = _toml_section_path(line)
        if path:
            append_missing_defaults()
            parts = path.split(".")
            in_target_provider = (
                len(parts) == 2
                and parts[0] == "model_providers"
                and parts[1] == provider_id
            )
            if in_target_provider:
                target_found = True
                seen = set()

        if in_target_provider:
            stripped = line.strip()
            key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
            if key in managed_provider_keys:
                if key not in seen:
                    value = dict(transport_defaults)[key]
                    updated.append(f"{key} = {value}")
                    seen.add(key)
                continue

        updated.append(line)

    append_missing_defaults()

    return updated, target_found

rest, has_target_model_provider = _force_target_provider_defaults(rest)

if rest:
    kept.append("")
    kept.extend(rest)

if kept and kept[-1].strip():
    kept.append("")
if not has_target_model_provider and not has_third_party_model_provider:
    kept.extend([
        provider_header,
        'name = "OpenAI WebSocket"',
        'base_url = "https://chatgpt.com/backend-api/codex"',
        "requires_openai_auth = true",
        "supports_websockets = true",
        'wire_api = "responses"',
        f"stream_idle_timeout_ms = {timeout}",
        f"stream_max_retries = {retries}",
    ])

# Collapse runs of 2+ blank lines into 1 and strip leading blanks. Idempotent
# across repeated runs so cosmetic gaps stop accumulating.
def _compact(lines):
    out = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and (prev_blank or not out):
            continue
        out.append(line)
        prev_blank = is_blank
    return out

kept = _compact(kept)

new_text = "\n".join(kept).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
}

configure_codex_features() {
  local codex_config="${CODEX_HOME:-$HOME/.codex}/config.toml"

  select_python_bin
  "$PYTHON_BIN" - "$codex_config" \
      "$CODEX_FEATURE_FAST_MODE" \
      "$CODEX_FEATURE_HOOKS" \
      "$CODEX_FEATURE_MEMORIES" \
      "$CODEX_FEATURE_GOALS" \
      "$CODEX_FEATURE_TERMINAL_RESIZE_REFLOW" \
      "$CODEX_FEATURE_REMOTE_CONTROL" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()

FEATURE_KEYS = [
    ("fast_mode", sys.argv[2]),
    ("hooks", sys.argv[3]),
    ("memories", sys.argv[4]),
    ("goals", sys.argv[5]),
    ("terminal_resize_reflow", sys.argv[6]),
    ("remote_control", sys.argv[7]),
]

ALLOWED_VALUES = {"true", "false"}
for name, value in FEATURE_KEYS:
    if value not in ALLOWED_VALUES:
        raise SystemExit(f"invalid CODEX_FEATURE_{name.upper()}: {value} (expected true|false)")

managed = {name for name, _ in FEATURE_KEYS} | {"codex_hooks", "remote_connections", "service_tier"}

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()

first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
lines = [
    line
    for i, line in enumerate(lines)
    if not (
        i < first_table
        and "=" in line.strip()
        and line.strip().split("=", 1)[0].strip() in {"remote_control", "remote_connections"}
    )
]

out = []
in_features = False
found_features = False
inserted = False

def feature_block():
    return [f"{name} = {value}" for name, value in FEATURE_KEYS]

for line in lines:
    stripped = line.strip()
    starts_table = stripped.startswith("[") and stripped.endswith("]")

    if starts_table and in_features:
        if out and out[-1].strip():
            out.append("")
        out.extend(feature_block())
        inserted = True
        in_features = False

    if stripped == "[features]":
        found_features = True
        in_features = True
        out.append(line)
        continue

    if in_features and "=" in stripped and not stripped.startswith("#"):
        key = stripped.split("=", 1)[0].strip()
        if key in managed:
            continue

    out.append(line)

if in_features and not inserted:
    if out and out[-1].strip():
        out.append("")
    out.extend(feature_block())
    inserted = True

if not found_features:
    if out and out[-1].strip():
        out.append("")
    out.append("[features]")
    out.extend(feature_block())

# Collapse runs of 2+ blank lines into 1 and strip leading blanks, then re-
# tighten table headers so each `[table]` line abuts its keys (no blank line
# right after the header).
def _compact(lines):
    cleaned = []
    prev_blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and (prev_blank or not cleaned):
            continue
        cleaned.append(line)
        prev_blank = is_blank
    # Drop a single blank line that appears immediately after a table header.
    out = []
    for i, line in enumerate(cleaned):
        if i > 0 and not line.strip():
            prev = cleaned[i - 1].strip()
            if prev.startswith("[") and prev.endswith("]"):
                continue
        out.append(line)
    return out

out = _compact(out)

new_text = "\n".join(out).rstrip() + "\n"
if new_text != text:
    path.write_text(new_text, encoding="utf-8")
PY
}

configure_codex_project_hooks_features() {
  if [[ ${#SCAN_ROOTS[@]} -eq 0 ]]; then
    return
  fi

  select_python_bin
  "$PYTHON_BIN" - "$MAX_DEPTH" "${SCAN_ROOTS[@]}" <<'PY'
from pathlib import Path
import sys

max_depth = int(sys.argv[1])
roots = [Path(root).expanduser().resolve() for root in sys.argv[2:]]


def has_hooks_config(lines):
    return any(
        line.strip() == "[hooks]"
        or line.strip().startswith("[[hooks.")
        or line.strip().startswith("[hooks.")
        for line in lines
    )


def migrate_project_config(path):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not has_hooks_config(lines) and "codex_hooks" not in text and "remote_control" not in text and "remote_connections" not in text:
        return False

    first_table = next((i for i, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
    lines = [
        line
        for i, line in enumerate(lines)
        if not (
            i < first_table
            and "=" in line.strip()
            and line.strip().split("=", 1)[0].strip() in {"remote_control", "remote_connections"}
        )
    ]

    out = []
    in_features = False
    found_features = False
    inserted = False

    def feature_block():
        return ["hooks = true", "remote_control = true"]

    for line in lines:
        stripped = line.strip()
        starts_table = stripped.startswith("[") and stripped.endswith("]")

        if starts_table and in_features:
            if out and out[-1].strip():
                out.append("")
            out.extend(feature_block())
            inserted = True
            in_features = False

        if stripped == "[features]":
            found_features = True
            in_features = True
            out.append(line)
            continue

        if in_features and "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in {"codex_hooks", "hooks", "remote_control", "remote_connections"}:
                continue

        out.append(line)

    if in_features and not inserted:
        if out and out[-1].strip():
            out.append("")
        out.extend(feature_block())
        inserted = True

    if not found_features:
        insert_at = next((i for i, line in enumerate(out) if line.lstrip().startswith("[")), len(out))
        out = out[:insert_at] + ["[features]", "hooks = true", "remote_control = true", ""] + out[insert_at:]

    new_text = "\n".join(out).rstrip() + "\n"
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


changed = []
for root in roots:
    if not root.exists():
        continue
    for config_path in root.rglob(".codex/config.toml"):
        try:
            rel = config_path.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) - 2 > max_depth:
            continue
        if migrate_project_config(config_path):
            changed.append(str(config_path))

for path in changed:
    print(f"Codex project hooks feature migrated: {path}")
PY
}

probe_codex_proxy_url() {
  local proxy_url="$1"
  local status

  if ! command -v curl >/dev/null 2>&1; then
    return 2
  fi

  status="$(
    curl -sS -o /dev/null -w '%{http_code}' \
      --connect-timeout "$CODEX_PROXY_CONNECT_TIMEOUT" \
      --max-time "$CODEX_PROXY_MAX_TIME" \
      -x "$proxy_url" \
      "$CODEX_PROXY_TEST_URL" 2>/dev/null || true
  )"

  case "$status" in
    200|204|301|302|401|404|405)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

select_codex_proxy_url() {
  local port proxy_url

  if [[ -n "${CODEX_PROXY_URL:-}" ]]; then
    if [[ "${CODEX_PROXY_SKIP_CHECK:-0}" == "1" ]] || probe_codex_proxy_url "$CODEX_PROXY_URL"; then
      printf '%s\n' "$CODEX_PROXY_URL"
      return 0
    fi
    echo "Codex proxy check failed for CODEX_PROXY_URL=$CODEX_PROXY_URL" >&2
    return 1
  fi

  for port in $CODEX_PROXY_PORTS; do
    proxy_url="http://${CODEX_PROXY_HOST}:${port}"
    if probe_codex_proxy_url "$proxy_url"; then
      printf '%s\n' "$proxy_url"
      return 0
    fi
  done

  return 1
}

configure_codex_proxy_wrapper() {
  local mode="$INSTALL_CODEX_PROXY_WRAPPER"
  local proxy_url real_bin target timestamp backup

  case "$mode" in
    auto|always|never)
      ;;
    *)
      echo "invalid Codex proxy wrapper mode: $mode" >&2
      exit 2
      ;;
  esac

  if [[ "$mode" == "never" ]]; then
    echo "Codex proxy wrapper not installed (mode=never)."
    return
  fi

  if ! proxy_url="$(select_codex_proxy_url)"; then
    if [[ "$mode" == "always" ]]; then
      echo "Codex proxy wrapper requested, but no reachable proxy was found." >&2
      echo "Set CODEX_PROXY_URL or CODEX_PROXY_HOST/CODEX_PROXY_PORTS for this host." >&2
      exit 1
    fi
    echo "Codex proxy wrapper not installed: no reachable proxy found in CODEX_PROXY_PORTS=[$CODEX_PROXY_PORTS]."
    return
  fi

  real_bin="${CODEX_REAL_BIN:-${CODEX_HOME:-$HOME/.codex}/packages/standalone/current/codex}"
  if [[ ! -x "$real_bin" ]]; then
    if [[ "$mode" == "always" ]]; then
      echo "Codex proxy wrapper requested, but standalone Codex binary is not executable: $real_bin" >&2
      echo "Install standalone Codex first or set CODEX_REAL_BIN." >&2
      exit 1
    fi
    echo "Codex proxy wrapper not installed: standalone Codex binary not found at $real_bin."
    echo "Install with: curl -fsSL https://chatgpt.com/codex/install.sh | sh"
    return
  fi

  target="${CODEX_WRAPPER_PATH:-$HOME/.local/bin/codex}"
  mkdir -p "$(dirname "$target")"

  timestamp="$(date +%Y%m%d-%H%M%S)"
  if [[ -e "$target" || -L "$target" ]]; then
    if grep -q "BEGIN agent-tools codex proxy wrapper" "$target" 2>/dev/null; then
      :
    else
      if [[ -L "$target" ]]; then
        backup="${target}.standalone-symlink-${timestamp}"
      else
        backup="${target}.backup-${timestamp}"
      fi
      mv "$target" "$backup"
      echo "Backed up existing Codex launcher: $backup"
    fi
  fi

  cat >"$target" <<EOF
#!/usr/bin/env bash
set -euo pipefail

# BEGIN agent-tools codex proxy wrapper
REAL_CODEX="\${CODEX_REAL_BIN:-$real_bin}"
CODEX_PROXY_URL="\${CODEX_PROXY_URL:-$proxy_url}"

export HTTP_PROXY="\$CODEX_PROXY_URL"
export HTTPS_PROXY="\$CODEX_PROXY_URL"
export http_proxy="\$CODEX_PROXY_URL"
export https_proxy="\$CODEX_PROXY_URL"
export WS_PROXY="\$CODEX_PROXY_URL"
export WSS_PROXY="\$CODEX_PROXY_URL"
export ws_proxy="\$CODEX_PROXY_URL"
export wss_proxy="\$CODEX_PROXY_URL"
export ALL_PROXY="\$CODEX_PROXY_URL"
export all_proxy="\$CODEX_PROXY_URL"
export CODEX_NETWORK_PROXY_ACTIVE=1

export NO_PROXY="\${NO_PROXY:-127.0.0.1,localhost,100.64.0.0/10,.local,beihang.edu.cn}"
export no_proxy="\${no_proxy:-\$NO_PROXY}"

exec "\$REAL_CODEX" "\$@"
# END agent-tools codex proxy wrapper
EOF
  chmod 0755 "$target"
  echo "Codex proxy wrapper: $target -> $real_bin via $proxy_url"
}

install_codex_here() {
  local source target timestamp backup

  select_python_bin
  source="$("$PYTHON_BIN" "$SOURCE_DIR/scripts/install_layout.py" roots --source "$SOURCE_DIR")/bin/codex-here"
  if [[ ! -f "$source" ]]; then
    echo "codex-here not installed: missing source script at $source" >&2
    return 1
  fi

  target="${CODEX_HERE_PATH:-$HOME/.local/bin/codex-here}"
  mkdir -p "$(dirname "$target")"

  timestamp="$(date +%Y%m%d-%H%M%S)"
  if [[ -e "$target" || -L "$target" ]]; then
    if grep -q "BEGIN agent-tools codex-here" "$target" 2>/dev/null; then
      rm -f "$target"
    else
      if [[ -L "$target" ]]; then
        backup="${target}.symlink-${timestamp}"
      else
        backup="${target}.backup-${timestamp}"
      fi
      mv "$target" "$backup"
      echo "Backed up existing codex-here launcher: $backup"
    fi
  fi

  install -m 0755 "$source" "$target"
  echo "codex-here launcher: $target -> codex -C \"\$PWD\""
}

start_codex_remote_control() {
  if [[ "$INSTALL_CODEX_REMOTE_CONTROL" -eq 0 ]]; then
    echo "Codex remote control not started (--no-remote-control)."
    return
  fi

  if ! command -v codex >/dev/null 2>&1; then
    echo "Codex remote control not started: codex is not on PATH." >&2
    return
  fi

  if codex remote-control start; then
    return
  fi

  echo "Codex remote control start failed." >&2
  echo "If this is an npm-only install, install standalone Codex first:" >&2
  echo "  curl -fsSL https://chatgpt.com/codex/install.sh | sh" >&2
}

usage() {
  cat <<'EOF'
Usage: setup/codex.sh [options]

Runs every step below unless skipped.

Options:
  --no-config           Do not patch config.toml (approval policy, sandbox,
                        reviewer, model and reasoning effort, context window,
                        stream timeout/retry, provider, [features]).
  --no-project-hooks    Do not enable hook features in project .codex/config.toml
                        files found under --root.
  --root PATH           Project scan root for hook features. Repeatable.
                        Default: current directory.
  --max-depth N         Scan depth. Default: 3.
  --proxy-wrapper MODE  Install the Codex proxy wrapper: auto|always|never.
                        Default: auto.
  --proxy-url URL       Use this proxy, e.g. http://127.0.0.1:7897.
  --proxy-ports LIST    Space-separated proxy ports to probe.
                        Default: "7897 7890 7891 10809 10808 8080".
  --no-here             Do not install ~/.local/bin/codex-here.
  --no-remote-control   Do not run "codex remote-control start".
  -h, --help            Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-config) INSTALL_CODEX_CONFIG=0; shift ;;
    --no-project-hooks) INSTALL_CODEX_PROJECT_HOOKS=0; shift ;;
    --root) SCAN_ROOTS+=("${2:?--root needs a value}"); shift 2 ;;
    --max-depth) MAX_DEPTH="${2:?--max-depth needs a value}"; shift 2 ;;
    --proxy-wrapper) INSTALL_CODEX_PROXY_WRAPPER="${2:?--proxy-wrapper needs a value}"; shift 2 ;;
    --proxy-url) CODEX_PROXY_URL="${2:?--proxy-url needs a value}"; shift 2 ;;
    --proxy-ports) CODEX_PROXY_PORTS="${2:?--proxy-ports needs a value}"; shift 2 ;;
    --no-here) INSTALL_CODEX_HERE=0; shift ;;
    --no-remote-control) INSTALL_CODEX_REMOTE_CONTROL=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ${#SCAN_ROOTS[@]} -eq 0 ]]; then
  SCAN_ROOTS+=("$(pwd)")
fi

run_codex_target_guard before
if [[ "$INSTALL_CODEX_HERE" -eq 1 ]]; then
  install_codex_here
else
  echo "codex-here not installed (--no-here)."
fi
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  configure_codex_defaults
  normalize_codex_provider_auth
  configure_codex_features
fi
check_codex_fast_mode
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 && "$INSTALL_CODEX_PROJECT_HOOKS" -eq 1 ]]; then
  configure_codex_project_hooks_features
fi
configure_codex_proxy_wrapper
start_codex_remote_control
if [[ "$INSTALL_CODEX_CONFIG" -eq 1 ]]; then
  run_codex_target_guard after
  echo "Codex approval policy: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_APPROVAL_POLICY}"
  echo "Codex sandbox mode: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_SANDBOX_MODE}"
  echo "Codex approvals reviewer: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_APPROVALS_REVIEWER}"
  echo "Codex model: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL} (reasoning: ${CODEX_MODEL_REASONING_EFFORT})"
  echo "Codex service tier: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_SERVICE_TIER}"
  echo "Codex context window: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL_CONTEXT_WINDOW}"
  echo "Codex auto compact token limit: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT} (${CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE})"
  echo "Codex stream idle timeout: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_IDLE_TIMEOUT_MS} ms"
  echo "Codex stream max retries: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_STREAM_MAX_RETRIES}"
  echo "Codex model provider: ${CODEX_HOME:-$HOME/.codex}/config.toml -> ${CODEX_MODEL_PROVIDER_ID} (WebSocket enabled)"
  echo "Codex [features]: fast_mode=${CODEX_FEATURE_FAST_MODE} hooks=${CODEX_FEATURE_HOOKS} memories=${CODEX_FEATURE_MEMORIES} goals=${CODEX_FEATURE_GOALS} terminal_resize_reflow=${CODEX_FEATURE_TERMINAL_RESIZE_REFLOW} remote_control=${CODEX_FEATURE_REMOTE_CONTROL}"
  echo "Codex target guard: ${CODEX_TARGET_GUARD_STATUS}"
else
  echo "Codex config not changed (--no-config)."
fi
echo "Codex proxy wrapper mode: $INSTALL_CODEX_PROXY_WRAPPER"
echo "Codex proxy port candidates: $CODEX_PROXY_PORTS"
if [[ "$INSTALL_CODEX_HERE" -eq 1 ]]; then
  echo "codex-here: ${CODEX_HERE_PATH:-$HOME/.local/bin/codex-here}"
fi
