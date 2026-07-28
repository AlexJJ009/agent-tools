# Win11 Codex Patch Safety Contract

## Identity

Treat the patched app as a replacement executable for the same Codex user state. Do not create a second profile.

The launcher must not contain `--user-data-dir` or `--profile-directory`. Close the Store app completely, then launch the copied executable against the existing default profile.

## Protected State

Treat these paths as read-only during app copying, ASAR extraction, JavaScript patching, repacking, and launcher creation:

- `%USERPROFILE%\.codex\auth.json`
- `%USERPROFILE%\.codex\config.toml`, except an explicitly approved top-level key update
- `%USERPROFILE%\.codex\.codex-global-state.json`
- `%USERPROFILE%\.codex\state_5.sqlite`
- `%USERPROFILE%\.codex\memories_1.sqlite`
- `%USERPROFILE%\.codex\goals_1.sqlite`
- `%USERPROFILE%\.codex\logs_2.sqlite`
- `%USERPROFILE%\.codex\sqlite\codex-dev.db`
- `%USERPROFILE%\.codex\session_index.jsonl`
- `%USERPROFILE%\.codex\sessions`
- `%USERPROFILE%\.codex\archived_sessions`
- `%USERPROFILE%\.ssh`
- `%USERPROFILE%\.cc-switch\cc-switch.db`
- `%USERPROFILE%\.cc-switch\settings.json`
- `%APPDATA%\Codex`

Never run `Remove-Item`, `rm -rf`, `rmtree`, `robocopy /MIR`, or equivalent against these paths or any ancestor.

Also include every active project's agent-facing memory and planning files in the baseline: `AGENTS.md`, `AGENTS.override.md`, `CLAUDE.md`, `status.md`, plan/planning/context/memory files, and the project's `.codex`, `memory`, `memories`, `plans`, or `planning` directories.

## Four Mandatory Semantic Gates

1. User configuration: `auth.json` remains semantically identical and valid. `config.toml` may change only release-approved keys. The default allowlist is `model_catalog_json`, `model_reasoning_effort`, and `service_tier`. A plugin-compatibility release may additionally replace only `marketplaces.openai-curated-remote-local` with the same marketplace name and exact native Windows root after proving the prior WSL path is unusable. Provider, provider tables, base URLs, profiles, credential presence, all other marketplaces, and installed-plugin enablement are immutable.

Treat every path referenced by protected configuration as part of that configuration's runtime contract. In particular, `model_catalog_json` must resolve to a present, non-empty, valid catalog before snapshot, staging, activation, and postflight. An unchanged TOML file with a missing dependency is RED, not preserved state. Never repair an arbitrary missing path from a nearby release; only a hash-bound release artifact may restore its exact declared target.
2. SSH Connections: `.ssh/config`, concrete Host entries, and every private-key name/hash are immutable. Validate every concrete Host with Windows OpenSSH `ssh.exe -G`; this parses configuration but does not connect.
3. Project memory and planning: session JSONL files may append but their existing prefix may not be rewritten or truncated; protected files may not disappear; tracked SQLite table row counts may not decrease; supplied project memory/planning files may neither disappear nor change. App roaming-cache drift is reported as a warning unless the profile directory disappears or is emptied.
4. CC Switch: `preserveCodexOfficialAuthOnSwitch` remains true; current Codex provider templates remain `model_provider = "custom"`; settings/provider templates are immutable; only the three approved common-config keys may change.

The manifest and report may contain hashes, key names, safe provider/base-URL values, and counts. They must never contain token values, API keys, auth blobs, provider secrets, or private-key contents.

## Allowed Writes

Limit patch writes to:

- `%USERPROFILE%\Downloads\Report\CodexPatched`
- a versioned backup directory under `%USERPROFILE%\.codex\_codexpatched_backups`
- the exact shortcut files selected by the operator
- explicit cc-switch configuration changes performed by its own validated migration tool
- the single guarded `marketplaces.openai-curated-remote-local` path normalization explicitly declared by a versioned plugin-compatibility recipe

Do not modify `C:\Program Files\WindowsApps`.

## State Machine

1. `DETECTED`: discover AppX package and immutable source ASAR hash.
2. `SNAPSHOTTED`: stop Codex, create a protected-state manifest and restorable backup.
3. `STAGED`: copy and patch only the app duplicate.
4. `VERIFIED`: run JS syntax, ASAR hash, model catalog, mock wire, plugin, launcher, and protected-state checks.
5. `PASS_ISSUED`: issue a machine verdict bound to the source AppX identity, source/patched ASAR hashes, executable hash, snapshot manifest, and every check report.
6. `ACTIVATED`: reverify the bound PASS and launch the patched executable with the existing default profile.
7. `POSTFLIGHT_OK`: verify no protected path, session, SSH key, auth file, or state DB row disappeared.

Do not transition to `ACTIVATED` unless all earlier stages succeeded. Never auto-activate merely because an update was detected.

## Hard Failures

Fail without launching when any condition is true:

- snapshot or manifest creation failed;
- a protected config dependency is missing, invalid, or replaced without release-bound evidence;
- launcher contains a profile-isolation argument;
- source AppX changed during staging;
- required patch feature signatures are missing;
- a protected file became missing or empty;
- SSH private-key count decreased;
- session JSONL count decreased;
- `state_5.sqlite` thread count decreased;
- runtime ASAR hash differs from the packed artifact;
- cc-switch would clear official auth;
- the active history/provider contract is not understood.
- any of the four mandatory semantic gates fails or is skipped.
- release verdict is RED/ERROR, missing, stale, or bound to different artifacts.

## Verdict And Audit Record

Use three verdicts: `PASS` means all deterministic checks passed, `RED` means the candidate failed a real gate, and `ERROR` means the verification infrastructure/report was incomplete. Only PASS unlocks activation. Record every issued verdict as one append-only JSONL row containing timestamp, AppX identity, source and candidate hashes, snapshot hash, status, and verdict path. Never use a prose success claim as an activation credential.

## Release Registry

A release recipe matches one exact `packageVersion + sourceAsarSha256`. Never use semantic version proximity, filename similarity, or “latest known recipe” fallback. Verified releases are immutable: a new official build or changed source ASAR creates a new candidate directory and registry row.

Agents may record candidates but may not self-promote them. Promotion requires a human-supplied approval artifact binding the release, recipe, PASS verdict, and four-gate postflight hashes, plus a named reviewer and concrete reason. The artifact is auditable but not cryptographic identity proof unless offline signature verification is added. Record candidate creation and promotion in an append-only JSONL ledger. A legacy successful build that used an isolated profile remains candidate until reverified under the existing-default-profile contract.

## Automation Boundary

Allow a scheduled task to detect versions, create reports, and take content-change checkpoints of critical low-volatility state. Exclude the large, continuously written `logs_2.sqlite`, App roaming caches, and dev catalog from frequent checkpoints; they remain part of the closed-App full snapshot. Do not let monitoring kill Codex, rewrite user state, activate a new build, or delete old backups. Activation requires an explicit patch run with a fresh full snapshot and postflight verification.
