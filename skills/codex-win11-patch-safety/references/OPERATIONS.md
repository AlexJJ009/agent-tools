# Patch Operations

## Paths

```bash
WIN_HOME=/mnt/c/Users/<user>
PATCHED_ROOT="$WIN_HOME/Downloads/Report/CodexPatched"
SKILL=skills/codex-win11-patch-safety
GUARD="$SKILL/scripts/codex_state_guard.py"
REGISTRY="$SKILL/scripts/release_registry.py"
RELEASE_GATE="$SKILL/scripts/patch_release_gate.py"
```

## Detect And Select

```bash
python3 "$GUARD" detect --patched-root "$PATCHED_ROOT" > "$PATCHED_ROOT/update-detection.json"
python3 "$GUARD" config-health --user-home "$WIN_HOME" \
  --output "$PATCHED_ROOT/config-health.json"
python3 "$REGISTRY" --index "$SKILL/releases/index.json" \
  select --detect "$PATCHED_ROOT/update-detection.json"
python3 "$GUARD" audit-cc-switch --user-home "$WIN_HOME" --target custom
```

Only an exact verified release may proceed as known. Candidate and unknown results follow `RELEASE_LIFECYCLE.md`. A missing or invalid external config dependency is a hard failure even when `config.toml` itself is unchanged.

When the exact release declares `patcher.artifacts`, validate those files through the registry before repair. A repair may restore only the declared target from the matching hash-bound artifact; nearby output files are not provenance.

Preserve the selector exit status before parsing its JSON: `0` means an exact verified release, `3` means unknown, and `4` means candidate/non-activatable. Any other nonzero status is an error. Do not pipe or append another command in a way that replaces this status.

## Snapshot

Ask the operator to close all Codex/ChatGPT windows normally. Do not kill them.

```bash
python3 "$GUARD" snapshot \
  --user-home "$WIN_HOME" \
  --backup-root "$WIN_HOME/.codex/_codexpatched_backups" \
  --project-root '<each active project>'
```

Use the returned `manifest.json` for every later comparison. Snapshot failure blocks all writes and activation.

## Stage And Verify

Patch only the copied application. Find assets by feature signatures, preserve official behavior, hard-fail missing required signatures, and require idempotence.

```bash
python3 "$SKILL/scripts/audit_patch_script.py" \
  "$PATCHED_ROOT/Patch-CodexApp.ps1" \
  scripts/setup_codex_desktop_connection_fast_mode.py
python3 "$GUARD" lint-launcher --arguments ''
python3 "$GUARD" verify \
  --user-home "$WIN_HOME" \
  --baseline '<snapshot>/manifest.json' \
  --output "$PATCHED_ROOT/prelaunch-state-verification.json"
```

For a recipe that explicitly repairs the guarded local plugin marketplace path, add exactly:

```bash
--allow-marketplace-root 'openai-curated-remote-local=C:\Users\<user>\Downloads\Report\CodexPatched\plugin-marketplace'
```

Without this explicit name/path binding, any marketplace change remains a hard failure.

Also run `node --check` for modified JS, packed/runtime ASAR hash comparison, `codex debug models`, localhost mock Responses wire cases, and plugin verification required by `PATCH_PROMPT_TEMPLATE.md`.

## Issue The Release Verdict

Every `--check` report must be JSON with `ok: true`.

```bash
python3 "$RELEASE_GATE" issue \
  --recipe '<selected-release>/recipe.json' \
  --detect "$PATCHED_ROOT/update-detection.json" \
  --snapshot-manifest '<snapshot>/manifest.json' \
  --source-asar '<WindowsApps package>/app/resources/app.asar' \
  --candidate-asar "$PATCHED_ROOT/app/resources/app.asar" \
  --candidate-executable "$PATCHED_ROOT/app/ChatGPT.exe" \
  --check "$PATCHED_ROOT/prelaunch-state-verification.json" \
  --check "$PATCHED_ROOT/config-health.json" \
  --check "$PATCHED_ROOT/verification-report.json" \
  --output "$PATCHED_ROOT/release-verdict.json" \
  --ledger "$WIN_HOME/.codex/_codexpatched_backups/release-verdicts.jsonl"
```

`PASS` may proceed. `RED` is a real candidate failure. `ERROR` is incomplete verification infrastructure. Both block activation.

Immediately before explicit activation:

```bash
python3 "$RELEASE_GATE" verify --verdict "$PATCHED_ROOT/release-verdict.json"
```

Launch the copied executable with empty profile arguments, then rerun `codex_state_guard.py verify` as postflight. A postflight failure means the build is not accepted.

## Monitoring

`Install-CodexPatchMonitor.ps1` may schedule detection, read-only CC Switch audit, and low-volatility checkpoints. It must never patch, launch, kill processes, migrate profiles, or prune backups.
