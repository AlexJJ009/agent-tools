# Codex SQLite Log Guard

This is a short-term SSD protection patch for Codex builds that write large
amounts of diagnostic TRACE/DEBUG data into `logs_2.sqlite`.

The patch installs a SQLite trigger on the diagnostic `logs` table:

```sql
CREATE TRIGGER IF NOT EXISTS agent_tools_block_codex_log_inserts
BEFORE INSERT ON logs
BEGIN
  SELECT RAISE(IGNORE);
END;
```

It only affects `logs_2.sqlite`. It does not modify `config.toml`, `auth.json`,
`state_5.sqlite`, `memories_1.sqlite`, `goals_1.sqlite`, `sessions/`, plugins,
or cc-switch provider configuration.

## Why This Exists

Several Codex releases have been reported to write high-volume diagnostic rows
to `logs_2.sqlite`, especially during streaming and app-server automation. This
can grow the main DB and WAL quickly, increase SSD writes, and slow Codex
Desktop startup when the log DB becomes large.

This guard trades away local diagnostic log history to protect disk write
endurance and startup responsiveness. Keep it until OpenAI ships a durable fix
such as a working log-level control, bounded retention, or disabled-by-default
TRACE SQLite logging.

## Installer Behavior

`install.sh` enables the guard by default:

```bash
./install.sh --root ~/projects
```

On Linux servers, it patches:

```text
${CODEX_HOME:-$HOME/.codex}/logs_2.sqlite
```

On WSL, it patches the WSL Codex home and, by default, all detected Windows
Codex App homes under:

```text
/mnt/c/Users/*/.codex/logs_2.sqlite
```

Control the Windows side from WSL:

```bash
./install.sh --codex-sqlite-log-guard-wsl-windows auto
./install.sh --codex-sqlite-log-guard-wsl-windows always
./install.sh --codex-sqlite-log-guard-wsl-windows never
```

Skip the guard:

```bash
./install.sh --no-codex-sqlite-log-guard
```

Remove it after OpenAI fixes the underlying issue:

```bash
./install.sh --disable-codex-sqlite-log-guard
```

Use `--codex-sqlite-log-guard-vacuum` only after stopping Codex processes:

```bash
pkill -f 'codex|Codex|node_repl' || true
./install.sh --disable-codex-sqlite-log-guard --codex-sqlite-log-guard-vacuum
```

The vacuum option checkpoints WAL and compacts the DB. It is intentionally not
enabled by default because it needs an idle database and can take time on large
files.

## Standalone Commands

Enable for the current user:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode enable
```

Enable for WSL plus detected Windows Codex App homes:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode enable --include-wsl-windows
```

Check status:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode status --include-wsl-windows
```

Disable:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode disable --include-wsl-windows
```

Patch a specific Codex home:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py \
  --mode enable \
  --codex-home /root/.codex
```

On native Windows, run from PowerShell with Python available:

```powershell
python scripts\configure_codex_sqlite_log_guard.py --mode enable --codex-home "$env:USERPROFILE\.codex"
```

## What You Lose

The guard disables new rows in Codex's local diagnostic log DB. It does not
delete existing rows unless you separately vacuum or recreate the DB.

When debugging future Codex issues, temporarily disable the guard and reproduce:

```bash
python3 scripts/configure_codex_sqlite_log_guard.py --mode disable
# reproduce the bug
python3 scripts/configure_codex_sqlite_log_guard.py --mode enable
```

Fast Mode, Connections, plugins, browser tools, and cc-switch provider billing
do not depend on `logs_2.sqlite` inserts. The guard can make those issues harder
to diagnose after the fact, but it should not change their runtime behavior.
