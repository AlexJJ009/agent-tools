---
name: codex-win11-patch-safety
description: Safely detect, stage, patch, verify, release, repair, and explicitly activate Microsoft Store ChatGPT Codex updates on Win11 while preserving the existing Codex profile, auth, sessions, SSH Connections, project memory/planning, CC Switch state, and external config dependencies. Use for AppX update detection, CodexPatched rebuilds, Fast/model/plugin WebView compatibility patches, Windows setup failures after patching, missing model_catalog_json artifacts, version-specific patch release maintenance, patch candidate promotion, data-loss audits, or read-only update monitoring.
---

# Codex Win11 Patch Safety

Treat the patched executable as a replacement frontend for the same user state, never as a second profile. Do not pass `--user-data-dir` or `--profile-directory`, modify `WindowsApps`, kill Codex, or let monitoring activate a build.

Read [SAFETY_CONTRACT.md](references/SAFETY_CONTRACT.md) before any patch, backup, launcher, activation, migration, or automation change.

## Route The Task

- **Detect/audit:** run only read-only detection, CC Switch audit, and low-volatility checkpoint commands from [OPERATIONS.md](references/OPERATIONS.md). Do not patch or launch.
- **Patch a known build:** select an exact release by `packageVersion + sourceAsarSha256`. Follow the gated patch run in [OPERATIONS.md](references/OPERATIONS.md).
- **Handle a new build:** follow [RELEASE_LIFECYCLE.md](references/RELEASE_LIFECYCLE.md). Unknown builds become candidates; never reuse the nearest release.
- **Change patch behavior:** update [PATCH_PROMPT_TEMPLATE.md](references/PATCH_PROMPT_TEMPLATE.md), create a new candidate release, and preserve working official implementations.
- **Repair Windows setup/config fallback incidents:** read [INCIDENT_MODEL_CATALOG_DEPENDENCY.md](references/INCIDENT_MODEL_CATALOG_DEPENDENCY.md) before changing ACLs, reinstalling, resetting a profile, or repairing a configured dependency.
- **Migrate CC Switch history:** audit first. Use the repository migration only after explicit approval; it rewrites state.
- **Install monitoring:** install only the read-only scheduled detector. Activation remains explicit.

## Enforce The State Machine

The only valid path is:

`DETECTED -> SNAPSHOTTED -> STAGED -> VERIFIED -> PASS_ISSUED -> EXPLICIT_ACTIVATION -> POSTFLIGHT_OK`

Stop on missing signatures, warnings treated as success, unreadable protected state, RED/ERROR verdicts, stale artifacts, or any skipped semantic gate.

Before activation require:

1. Codex/ChatGPT is normally closed.
2. A fresh, restorable full snapshot exists.
3. Source AppX and source ASAR still match detection evidence.
4. Static audit, JS syntax, ASAR, model, wire, plugin, launcher, and state checks pass.
5. A hash-bound verdict is `PASS` for the exact source, candidate, snapshot, executable, and reports.
6. The activation command reverifies the PASS immediately before launch.

After first launch, rerun the four semantic gates. Never claim success when postflight is missing or failed.

## Protect Four State Categories

- **User configuration:** `auth.json` remains valid and unchanged. `config.toml` may change only release-approved keys, and every referenced external artifact must remain present and valid. The normal allowlist is `model_catalog_json`, `model_reasoning_effort`, and `service_tier`; a plugin-compatibility recipe may normalize only the named local marketplace from a stale WSL path to its exact native Windows path. Provider, base URL, profiles, credentials, other marketplaces, and plugin enablement stay unchanged.
- **SSH Connections:** `.ssh/config`, concrete Hosts, and private-key names/hashes stay unchanged. Resolve every Host with Windows `ssh.exe -G`; do not make network connections by default.
- **Project memory/planning:** protected files and database rows cannot disappear. Session JSONL may append but not truncate or rewrite its existing prefix. Include each active project's agent, status, plan, context, and memory files in the snapshot.
- **CC Switch:** official auth preservation stays enabled; current Codex templates remain `model_provider = "custom"`; settings/templates stay unchanged; only the three approved common-config keys may change.

Reports may contain hashes, counts, key names, and safe provider/base URL values. Never serialize tokens, API keys, auth blobs, provider secrets, or private-key contents.

## Use Human-Assisted Evolution

The stable safety framework and version-specific releases have separate lifecycles. Agents may detect, compare feature signatures, generate candidates, run tests, and collect evidence. Agents may not promote their own candidates.

A named human reviewer may promote a candidate only by supplying an approval artifact bound to the unchanged recipe, patcher, hash-bound PASS verdict, and four-gate postflight PASS. Agents may prepare an unapproved template but must not assert human approval. Promotion appends an audit event. Verified releases are immutable; changed AppX, source ASAR, patch method, or verification contract creates a new release.

Keep candidate evidence regenerable, release/evolution ledgers append-only, and safety principles slow-changing. See [RELEASE_LIFECYCLE.md](references/RELEASE_LIFECYCLE.md).

## Report The Outcome

Report the AppX/source ASAR identity, selected release and status, snapshot path, patch/official behavior, syntax and artifact hashes, model/wire/plugin verification, exact shortcut target/arguments, release verdict, and separate results for all four state categories.

State clearly whether activation reused the existing default profile. Treat non-`custom` CC Switch buckets as findings, not permission to rewrite them.
