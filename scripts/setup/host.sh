#!/usr/bin/env bash
# Host hardening and shell conveniences: fail2ban sshd jail, tmux mouse mode,
# Claude Desktop SSH shim. Run on its own; install.sh does not call it.
set -euo pipefail

SETUP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SETUP_DIR/lib.sh"

INSTALL_FAIL2BAN_HARDENING="${INSTALL_FAIL2BAN_HARDENING:-auto}"
FAIL2BAN_SSHD_MAXRETRY="${FAIL2BAN_SSHD_MAXRETRY:-3}"
FAIL2BAN_SSHD_FINDTIME="${FAIL2BAN_SSHD_FINDTIME:-1h}"
FAIL2BAN_SSHD_BANTIME="${FAIL2BAN_SSHD_BANTIME:--1}"
FAIL2BAN_SSHD_IGNOREIP="${FAIL2BAN_SSHD_IGNOREIP:-127.0.0.1/8 ::1}"
FAIL2BAN_SSHD_FILTER="${FAIL2BAN_SSHD_FILTER:-sshd[mode=aggressive]}"
FAIL2BAN_SSHD_BANACTION="${FAIL2BAN_SSHD_BANACTION:-iptables-multiport[blocktype=DROP]}"
INSTALL_CLAUDE_DESKTOP_SSH="${INSTALL_CLAUDE_DESKTOP_SSH:-1}"
INSTALL_TMUX_MOUSE=1
FAIL2BAN_HARDENING_STATUS=""
CLAUDE_DESKTOP_SSH_STATUS=""

run_script_as_root_if_available() {
  local -a args=()
  local arg

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --)
        shift
        break
        ;;
      *)
        args+=("$1")
        shift
        ;;
    esac
  done

  if [[ "$(id -u)" -eq 0 ]]; then
    bash -s -- "${args[@]}" "$@"
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo bash -s -- "${args[@]}" "$@"
    return
  fi

  if grep -qi microsoft /proc/version 2>/dev/null && [[ -x /mnt/c/Windows/System32/wsl.exe ]]; then
    /mnt/c/Windows/System32/wsl.exe -u root -- bash -s -- "${args[@]}" "$@"
    return
  fi

  return 1
}

resolve_existing_path() {
  local path="$1"

  if command -v realpath >/dev/null 2>&1; then
    realpath -e -- "$path" 2>/dev/null && return
  fi
  if command -v readlink >/dev/null 2>&1; then
    readlink -f -- "$path" 2>/dev/null && return
  fi
  printf '%s\n' "$path"
}

configure_fail2ban_hardening() {
  local root_prefix="${AGENT_TOOLS_TEST_ROOT:-}"

  case "$INSTALL_FAIL2BAN_HARDENING" in
    1|true|yes|always)
      ;;
    0|false|no|never)
      FAIL2BAN_HARDENING_STATUS="skipped (--no-fail2ban)"
      echo "fail2ban hardening skipped (--no-fail2ban)."
      return
      ;;
    auto)
      if [[ -z "$root_prefix" ]] && grep -qi microsoft /proc/version 2>/dev/null; then
        FAIL2BAN_HARDENING_STATUS="skipped: WSL auto mode"
        echo "fail2ban hardening skipped: WSL auto mode."
        return
      fi
      if [[ -z "$root_prefix" ]] && ! command -v sshd >/dev/null 2>&1 && [[ ! -f /etc/ssh/sshd_config ]]; then
        FAIL2BAN_HARDENING_STATUS="skipped: no sshd detected"
        echo "fail2ban hardening skipped: no sshd detected."
        return
      fi
      ;;
    *)
      echo "invalid fail2ban hardening mode: $INSTALL_FAIL2BAN_HARDENING (expected auto|always|never)" >&2
      exit 2
      ;;
  esac

  if [[ "$INSTALL_FAIL2BAN_HARDENING" == "auto" ]]; then
    echo "fail2ban hardening auto mode: sshd detected, enforcing strict jail."
  fi

  if [[ -n "$root_prefix" ]]; then
    mkdir -p "$root_prefix/etc/fail2ban/jail.d"
    local test_conf="$root_prefix/etc/fail2ban/jail.d/zzz-agent-tools-sshd-hardening.local"
    # Same replace-not-union hazard as the privileged path below; keep the two
    # branches in step so a test root reproduces production merge behaviour.
    local test_ignoreip=""
    if [[ -f "$test_conf" ]]; then
      test_ignoreip="$(sed -n 's/^[[:space:]]*ignoreip[[:space:]]*=[[:space:]]*//p' "$test_conf")"
    fi
    test_ignoreip="$(
      printf '%s %s\n' "$FAIL2BAN_SSHD_IGNOREIP" "$test_ignoreip" \
        | tr ' \t' '\n\n' | grep -v '^$' | awk '!seen[$0]++' | paste -sd' ' -
    )"
    [[ -n "$test_ignoreip" ]] || test_ignoreip="$FAIL2BAN_SSHD_IGNOREIP"
    cat >"$test_conf" <<EOF
[sshd]
enabled = true
port = ssh
filter = $FAIL2BAN_SSHD_FILTER
backend = systemd
maxretry = $FAIL2BAN_SSHD_MAXRETRY
findtime = $FAIL2BAN_SSHD_FINDTIME
bantime = $FAIL2BAN_SSHD_BANTIME
banaction = $FAIL2BAN_SSHD_BANACTION
ignoreip = $test_ignoreip
EOF
    FAIL2BAN_HARDENING_STATUS="test-root: $root_prefix/etc/fail2ban/jail.d/zzz-agent-tools-sshd-hardening.local"
    echo "fail2ban hardening test-root configured: $root_prefix/etc/fail2ban/jail.d/zzz-agent-tools-sshd-hardening.local"
    return
  fi

  if ! run_script_as_root_if_available \
    "$FAIL2BAN_SSHD_MAXRETRY" \
    "$FAIL2BAN_SSHD_FINDTIME" \
    "$FAIL2BAN_SSHD_BANTIME" \
    "$FAIL2BAN_SSHD_IGNOREIP" \
    "$FAIL2BAN_SSHD_FILTER" \
    "$FAIL2BAN_SSHD_BANACTION" \
    -- <<'SH'
set -eu
maxretry="$1"
findtime="$2"
bantime="$3"
ignoreip="$4"
filter="$5"
banaction="$6"

install_fail2ban() {
  if command -v fail2ban-client >/dev/null 2>&1; then
    return 0
  fi

  export DEBIAN_FRONTEND=noninteractive
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y fail2ban
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y fail2ban
  elif command -v yum >/dev/null 2>&1; then
    yum install -y fail2ban
  elif command -v pacman >/dev/null 2>&1; then
    pacman -Sy --noconfirm fail2ban
  elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache fail2ban
  else
    echo "fail2ban is not installed and no supported package manager was found." >&2
    exit 1
  fi
}

detect_sshd_ports() {
  if command -v sshd >/dev/null 2>&1; then
    ports="$(sshd -T 2>/dev/null | awk '$1 == "port" {print $2}' | sort -nu | paste -sd, -)"
    if [ -n "${ports:-}" ]; then
      printf '%s\n' "$ports"
      return 0
    fi
  fi
  printf '%s\n' "ssh"
}

# fail2ban resolves ignoreip by replacement, not union: the last jail.d file
# wins outright. Rewriting this file with only the requested value therefore
# un-whitelists every address an earlier run or a lower-precedence jail.d file
# had authorised, and with bantime = -1 those peers get locked out for good.
# Merge instead, so the operator still owns the list and a reinstall can only
# ever grow it. Sources: requested value, this file's current value, and the
# live effective list (absent on a first install, hence the guards).
merge_ignoreip() {
  {
    printf '%s\n' "$1" | tr ' \t' '\n\n'
    if [ -f "$conf" ]; then
      sed -n 's/^[[:space:]]*ignoreip[[:space:]]*=[[:space:]]*//p' "$conf" | tr ' \t' '\n\n'
    fi
    fail2ban-client get sshd ignoreip 2>/dev/null | sed -n 's/^[|`]-[[:space:]]*//p' || true
  } | sed 's/^[[:space:]]*//; s/[[:space:]]*$//' \
    | grep -v '^$' \
    | awk '!seen[$0]++' \
    | paste -sd' ' -
}

install_fail2ban
mkdir -p /etc/fail2ban/jail.d
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
conf="/etc/fail2ban/jail.d/zzz-agent-tools-sshd-hardening.local"
ports="$(detect_sshd_ports)"

effective_ignoreip="$(merge_ignoreip "$ignoreip")"
[ -n "$effective_ignoreip" ] || effective_ignoreip="$ignoreip"

if [ -f "$conf" ]; then
  cp -a "$conf" "$conf.backup-$timestamp"
fi

cat >"$conf" <<EOF
[sshd]
enabled = true
port = $ports
filter = $filter
backend = systemd
maxretry = $maxretry
findtime = $findtime
bantime = $bantime
banaction = $banaction
ignoreip = $effective_ignoreip
EOF
chmod 0644 "$conf"

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
  systemctl restart fail2ban
elif command -v service >/dev/null 2>&1; then
  service fail2ban restart
else
  fail2ban-client reload sshd >/dev/null 2>&1 || fail2ban-client reload >/dev/null 2>&1 || true
fi

ready=0
i=0
while [ "$i" -lt 10 ]; do
  if fail2ban-client status sshd >/dev/null 2>&1; then
    ready=1
    break
  fi
  i=$((i + 1))
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "fail2ban sshd jail is not active after hardening." >&2
  exit 1
fi

printf 'fail2ban sshd hardening: '
printf 'ports=%s ' "$ports"
printf 'maxretry=%s ' "$(fail2ban-client get sshd maxretry)"
printf 'findtime=%s ' "$(fail2ban-client get sshd findtime)"
printf 'bantime=%s ' "$(fail2ban-client get sshd bantime)"
printf 'blocktype=%s\n' "$(fail2ban-client get sshd action iptables-multiport blocktype 2>/dev/null || printf unknown)"
fail2ban-client get sshd ignoreip
SH
  then
    FAIL2BAN_HARDENING_STATUS="failed: root/sudo required or fail2ban setup failed"
    echo "fail2ban hardening failed: root/passwordless sudo is required or setup failed." >&2
    return 1
  fi

  FAIL2BAN_HARDENING_STATUS="enabled: sshd maxretry=${FAIL2BAN_SSHD_MAXRETRY}, findtime=${FAIL2BAN_SSHD_FINDTIME}, bantime=${FAIL2BAN_SSHD_BANTIME}, banaction=${FAIL2BAN_SSHD_BANACTION}, ignoreip=${FAIL2BAN_SSHD_IGNOREIP}"
}

configure_claude_desktop_ssh() {
  local claude_cmd claude_target node_cmd node_target root_prefix part
  local env_file usr_local_bin claude_link node_link
  local status_parts=()

  if [[ "$INSTALL_CLAUDE_DESKTOP_SSH" -eq 0 ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped (--no-desktop-ssh)"
    return
  fi

  claude_cmd="$(type -P claude 2>/dev/null || true)"
  if [[ -z "$claude_cmd" ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: claude not installed on PATH"
    echo "Claude Desktop SSH compatibility skipped: claude is not on PATH."
    return
  fi

  if [[ ! -x "$claude_cmd" ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: claude is not executable ($claude_cmd)"
    echo "Claude Desktop SSH compatibility skipped: claude is not executable at $claude_cmd." >&2
    return
  fi

  claude_target="$claude_cmd"
  case "$claude_cmd" in
    /run/user/*|/tmp/*|/var/tmp/*)
      claude_target="$(resolve_existing_path "$claude_cmd")"
      ;;
  esac

  if [[ -z "$claude_target" || ! -x "$claude_target" ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: could not resolve stable claude target from $claude_cmd"
    echo "Claude Desktop SSH compatibility skipped: could not resolve a stable claude target from $claude_cmd." >&2
    return
  fi

  if [[ "$claude_target" == /run/user/* || "$claude_target" == /tmp/* || "$claude_target" == /var/tmp/* ]]; then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: resolved claude target is temporary ($claude_target)"
    echo "Claude Desktop SSH compatibility skipped: resolved claude target is temporary: $claude_target." >&2
    return
  fi

  root_prefix="${AGENT_TOOLS_TEST_ROOT:-}"
  env_file="$root_prefix/etc/environment"
  usr_local_bin="$root_prefix/usr/local/bin"
  claude_link="$usr_local_bin/claude"
  node_link="$usr_local_bin/node"

  # PATH may already find claude through the managed link; never point the link at itself.
  if [[ "$claude_target" == "$claude_link" ]]; then
    claude_target="$(resolve_existing_path "$claude_link")"
    if [[ -z "$claude_target" || "$claude_target" == "$claude_link" || ! -x "$claude_target" ]]; then
      CLAUDE_DESKTOP_SSH_STATUS="skipped: claude on PATH is the managed link and does not resolve ($claude_link)"
      echo "Claude Desktop SSH compatibility skipped: $claude_link does not resolve to an executable." >&2
      return
    fi
  fi

  if ! run_script_as_root_if_available "$env_file" -- <<'SH'
set -eu
env_file="$1"
if [ -f "$env_file" ] && grep -q "^IS_SANDBOX=1$" "$env_file"; then
  exit 0
fi
timestamp=$(date +%Y%m%d-%H%M%S)
if [ -f "$env_file" ]; then
  cp -a "$env_file" "${env_file}.agent-tools-backup-${timestamp}"
fi
if [ -f "$env_file" ] && grep -q "^IS_SANDBOX=" "$env_file"; then
  sed -i "s/^IS_SANDBOX=.*/IS_SANDBOX=1/" "$env_file"
else
  mkdir -p "$(dirname "$env_file")"
  if [ -s "$env_file" ] && [ "$(tail -c 1 "$env_file" 2>/dev/null || true)" != "" ]; then
    printf "\n" >>"$env_file"
  fi
  printf "IS_SANDBOX=1\n" >>"$env_file"
fi
chmod 0644 "$env_file"
SH
  then
    CLAUDE_DESKTOP_SSH_STATUS="skipped: root/sudo required to write $env_file"
    echo "Claude Desktop SSH compatibility skipped: root or passwordless sudo is required to write $env_file." >&2
    return
  fi
  status_parts+=("IS_SANDBOX=1 in $env_file")

  if ! run_script_as_root_if_available "$claude_target" "$claude_link" -- <<'SH'
set -eu
target="$1"
link_path="$2"
mkdir -p "$(dirname "$link_path")"
if [ -e "$link_path" ] || [ -L "$link_path" ]; then
  current=$(readlink -f "$link_path" 2>/dev/null || true)
  wanted=$(readlink -f "$target" 2>/dev/null || true)
  if [ -n "$current" ] && [ -n "$wanted" ] && [ "$current" != "$wanted" ]; then
    timestamp=$(date +%Y%m%d-%H%M%S)
    mv "$link_path" "${link_path}.agent-tools-backup-${timestamp}"
  fi
fi
ln -sfn "$target" "$link_path"
chmod 0755 "$(dirname "$link_path")"
SH
  then
    CLAUDE_DESKTOP_SSH_STATUS="partial: IS_SANDBOX configured, but root/sudo required for $claude_link"
    echo "Claude Desktop SSH compatibility partially configured: root or passwordless sudo is required to write $claude_link." >&2
    return
  fi
  status_parts+=("$claude_link -> $claude_target")

  if ! env -i PATH="$usr_local_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" IS_SANDBOX=1 "$claude_link" --version >/dev/null 2>&1 && [[ ! -x "$node_link" ]]; then
    node_cmd="$(type -P node 2>/dev/null || true)"
    if [[ -n "$node_cmd" ]]; then
      node_target="$node_cmd"
      case "$node_cmd" in
        /run/user/*|/tmp/*|/var/tmp/*)
          node_target="$(resolve_existing_path "$node_cmd")"
          ;;
      esac
      if [[ -n "$node_target" && -x "$node_target" && "$node_target" != /run/user/* && "$node_target" != /tmp/* && "$node_target" != /var/tmp/* ]]; then
        if run_script_as_root_if_available "$node_target" "$node_link" -- <<'SH'
set -eu
target="$1"
link_path="$2"
mkdir -p "$(dirname "$link_path")"
if [ ! -e "$link_path" ] && [ ! -L "$link_path" ]; then
  ln -s "$target" "$link_path"
fi
SH
        then
          status_parts+=("$node_link -> $node_target")
        else
          status_parts+=("node symlink skipped: root/sudo required")
        fi
      else
        status_parts+=("node symlink skipped: stable node target not found")
      fi
    else
      status_parts+=("node symlink skipped: node not on PATH")
    fi
  fi

  if ! env -i PATH="$usr_local_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" IS_SANDBOX=1 "$claude_link" --version >/dev/null 2>&1; then
    status_parts+=("warning: $claude_link still failed with a minimal SSH-like PATH")
  fi

  if [[ -z "$root_prefix" && -f /etc/pam.d/sshd ]] && ! grep -q 'pam_env\.so' /etc/pam.d/sshd 2>/dev/null; then
    status_parts+=("warning: /etc/pam.d/sshd does not mention pam_env.so")
  fi

  CLAUDE_DESKTOP_SSH_STATUS=""
  for part in "${status_parts[@]}"; do
    if [[ -n "$CLAUDE_DESKTOP_SSH_STATUS" ]]; then
      CLAUDE_DESKTOP_SSH_STATUS+="; "
    fi
    CLAUDE_DESKTOP_SSH_STATUS+="$part"
  done
  echo "Claude Desktop SSH compatibility: $CLAUDE_DESKTOP_SSH_STATUS"
}

configure_tmux_mouse_mode() {
  local tmux_conf="${TMUX_CONF:-$HOME/.tmux.conf}"

  select_python_bin
  "$PYTHON_BIN" - "$tmux_conf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1]).expanduser()
begin = "# BEGIN agent-tools tmux mouse"
end = "# END agent-tools tmux mouse"
block = "\n".join([
    begin,
    "# Required on Linux/WSL2 servers so mouse-wheel scrolling works inside tmux.",
    "set -g mouse on",
    end,
])

path.parent.mkdir(parents=True, exist_ok=True)
text = path.read_text(encoding="utf-8") if path.exists() else ""

while True:
    start = text.find(begin)
    if start == -1:
        break
    stop = text.find(end, start)
    if stop == -1:
        break
    stop += len(end)
    text = text[:start].rstrip() + "\n\n" + text[stop:].lstrip()

new_text = text.rstrip()
if new_text:
    new_text += "\n\n"
new_text += block + "\n"

if new_text != (path.read_text(encoding="utf-8") if path.exists() else ""):
    path.write_text(new_text, encoding="utf-8")
PY

  if command -v tmux >/dev/null 2>&1; then
    tmux source-file "$tmux_conf" >/dev/null 2>&1 || true
    tmux set-option -g mouse on >/dev/null 2>&1 || true
  fi
}

usage() {
  cat <<'EOF'
Usage: setup/host.sh [options]

Runs every step below unless skipped.

Options:
  --no-fail2ban       Skip sshd hardening: fail2ban installed if missing,
                      aggressive matching, 3 failures in 1 hour, permanent
                      ban, DROP, loopback-only ignoreip. Auto mode skips WSL
                      and hosts without sshd; INSTALL_FAIL2BAN_HARDENING=
                      auto|always|never overrides.
  --no-tmux           Skip "set -g mouse on" in ~/.tmux.conf.
  --no-desktop-ssh    Skip the Claude Desktop SSH root/bypass shim for an
                      existing Claude Code.
  -h, --help          Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-fail2ban) INSTALL_FAIL2BAN_HARDENING=0; shift ;;
    --no-tmux) INSTALL_TMUX_MOUSE=0; shift ;;
    --no-desktop-ssh) INSTALL_CLAUDE_DESKTOP_SSH=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ "$INSTALL_TMUX_MOUSE" -eq 1 ]]; then
  configure_tmux_mouse_mode
  echo "tmux mouse mode: ${TMUX_CONF:-$HOME/.tmux.conf}"
else
  echo "tmux mouse mode not changed (--no-tmux)."
fi
configure_fail2ban_hardening
configure_claude_desktop_ssh
echo "fail2ban hardening: $FAIL2BAN_HARDENING_STATUS"
echo "Claude Desktop SSH compatibility: $CLAUDE_DESKTOP_SSH_STATUS"
