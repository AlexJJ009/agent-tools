# ChatGPT Codex Win11 Patch Prompt Template

Use this versioned template as the source prompt for future patch runs. Update this file when official behavior changes. Do not weaken the safety preamble.

## Safety Preamble

Patch a copied executable while preserving the existing Codex user profile. Do not create or pass a new `--user-data-dir`. Do not delete, reset, migrate, replace, or empty `%USERPROFILE%\.codex`, `%APPDATA%\Codex`, `%USERPROFILE%\.ssh`, or `%USERPROFILE%\.cc-switch`.

Before closing or launching Codex:

1. Create a restorable snapshot and manifest with `codex_state_guard.py snapshot`. Pass every active project root whose agent memory and planning must be preserved.
2. Record AppX package version and source `app.asar` SHA256.
3. Verify the patch script's write set is limited to the copied app, versioned backup directory, and selected shortcut files.
4. Reject launchers containing `--user-data-dir` or `--profile-directory`.
5. After patching and after first launch, run all four semantic gates. Abort if: user auth changes; any config key outside the explicit release allowlist changes; SSH config/Host/key fingerprints change or `ssh.exe -G` cannot resolve a Host; sessions disappear, truncate, or rewrite their existing prefix; memory/goal/log rows, global state, or supplied project planning files disappear/change; or CC Switch settings/provider templates drift. The allowlist is normally limited to `model_catalog_json`, `model_reasoning_effort`, and `service_tier`; a plugin release may additionally normalize only the named `openai-curated-remote-local` marketplace source from a stale WSL path to the exact native Windows path. Reports must be redacted.
6. Run `config-health` before snapshot and again before activation. Every configured external dependency must exist and validate. Do not treat an unchanged `config.toml` as safe when `model_catalog_json` or another referenced artifact disappeared. A required config artifact must declare its exact `configKey`, `targetPath`, and SHA256 and use a narrow restore companion; dependency-only repair must not invoke the full app patcher.

The background monitor may detect an update and prepare a report, but it must not automatically activate a new build.

## Versioned Release Selection

Before patching, select a release recipe by exact `packageVersion + sourceAsarSha256`. A verified exact match may be used for staging, but still requires a fresh snapshot and fresh verdict. A candidate or unknown match must go through probe and human-reviewed promotion. Never apply the nearest version, never overwrite a verified recipe, and never let an agent promote its own candidate without matching PASS/postflight evidence.

## Patch Objective

Create a complete independently runnable ChatGPT Codex patched copy under:

```text
%USERPROFILE%\Downloads\Report\CodexPatched
```

Automatically locate the current `OpenAI.Codex` AppX package. Never modify `C:\Program Files\WindowsApps`. Copy the complete `app` directory and patch only the copy. Find bundles by code signatures rather than fixed hashed filenames. Back up `app.asar` before editing. Make every patch idempotent. Preserve official implementations when the current build already supports a feature.

Create `Codex Patched.lnk` and the compatibility shortcut `Codex Fast Connections.lnk`, both targeting the copied `ChatGPT.exe` or `Codex.exe` without profile-isolation arguments. Leave a repeatable `Patch-CodexApp.ps1`.

## ASAR And WebView

Use a pinned `@electron/asar` version. Extract `resources\app.asar` and search `webview/assets` by behavior signatures. Hashed module names and chunk boundaries are not stable; current builds may consolidate these features into `app-initial-*.js`. Historical prefixes include:

- `use-is-fast-mode-enabled-*.js`
- `use-service-tier-settings-*.js`
- `read-service-tier-for-request-*.js`
- `general-settings-*.js`
- `model-queries-*.js`
- `model-list-filter-*.js`
- `model-and-reasoning-dropdown-*.js`
- `use-model-settings-*.js`

Required patch signatures must hard-fail when absent. Warnings are not success.

## API Key Fast Mode

Allow Fast/service-tier behavior for exactly `chatgpt` and `apikey`. Do not enable Copilot, Bedrock, or other auth modes. When the user's guarded custom bearer provider reports `authMethod = "chatgpt"`, bypass only the remote Fast entitlement check; do not bypass per-model capability checks. Preserve per-model `serviceTiers` and `additionalSpeedTiers` checks. `Fast` must produce `service_tier = "priority"`. Support `profiles.<active-profile>.service_tier`.

Ensure request-time service-tier reading does not reject `apikey`. Preserve the official implementation when the build already permits it.

## Account-Visible Plugins

Keep plugin synchronization credentials separate from the App's API Key login. Prefer an independent ChatGPT/Codex OAuth `auth.json`. Reject `sk-*` keys. Never print tokens.

Create and maintain:

- `plugin-account.json`
- `sync-remote-plugins.mjs`
- `sync-remote-plugins.ps1`
- `plugin-marketplace`
- `README-remote-plugins.md`

Expose only account-authorized plugins for which an actual local or downloaded bundle exists. When no OAuth account catalog is available, label any public/local catalog fallback explicitly and do not claim it proves account entitlement. Generate a standard marketplace named `openai-curated-remote-local` and deduplicate plugin names. Register it with the copied native Windows `codex.exe` using a native `C:\...` path, never a WSL `/mnt/c/...` path. Verify with `codex plugin list --marketplace openai-curated-remote-local --available --json`; plain `plugin list --json` omits uninstalled plugins in current builds. Plugin visibility does not authorize GitHub, Figma, or other external services.

## Current Official Models

Use `codex debug models --bundled` from the copied current CLI as the runtime source of truth, and compare with `codex-rs/models-manager/models.json` from current `openai/codex` main when needed. Preserve the complete official catalog and adapt only schema fields required by the bundled CLI. Never invent models or overwrite a working bundled catalog.

Current GPT-5.6 expectations:

- `gpt-5.6-sol`: low, medium, high, xhigh, max, ultra
- `gpt-5.6-terra`: low, medium, high, xhigh, max, ultra
- `gpt-5.6-luna`: low, medium, high, xhigh, max

`max` and `ultra` are reasoning efforts, not model suffixes. Do not invent `gpt-5.6-pro`. Preserve the runtime's official defaults, context, tool mode, Responses Lite, multi-agent version, Fast tier, and all existing models. Do not hard-code a historical context value; build 5848 reports `272000` for the GPT-5.6 models.

Persist `model_catalog_json`, `model_reasoning_effort = "xhigh"`, and `service_tier = "priority"` through cc-switch `common_config_codex` when cc-switch owns the config. Preserve provider, base URL, API key, profiles, and official auth.

When official models make a custom catalog unnecessary, migrate away from `model_catalog_json` only as an explicit, reviewed config change. Until that migration is approved, preserve the referenced file at the exact path; never remove it merely because the new App bundles equivalent models.

## WebView Compatibility

Prefer native official 5.6 data. Build `26.721.4979.0` already provides all three models and must receive no model compatibility patch. A future release may add a model fallback only after exact bundled/native evidence proves the model absent; that requires a new candidate recipe. Always filter efforts by each model's official supported list so Luna never displays Ultra.

Preserve official model-switch behavior when it already selects the model default effort and passes a manually selected effort into next-turn thread settings. Support profile-aware config writes. Do not replace a working official implementation.

## Real Verification

Do not validate only the UI. Start a mock `/v1/responses` server bound only to `127.0.0.1` and use the copied `codex.exe` to capture real request JSON.

Terra + xhigh must include:

```json
{"model":"gpt-5.6-terra","reasoning":{"effort":"xhigh"},"service_tier":"priority"}
```

Sol + ultra must be normalized on the wire to:

```json
{"model":"gpt-5.6-sol","reasoning":{"effort":"max","context":"all_turns"},"service_tier":"priority"}
```

Do not force upstream `ultra`. Run `codex debug models` and verify the full reasoning, context, service-tier, tool-mode, Responses Lite, and multi-agent metadata.

## Packaging And Activation

Run `node --check` for every modified JavaScript file. Repack `app.asar`, copy it into the duplicate app, compare SHA256 with the packed artifact, and prove no backup/temp file entered the ASAR.

Before activation, close all Store and copied Codex processes. Issue a PASS/RED/ERROR verdict bound to the exact AppX identity, source/patched ASAR, executable, snapshot manifest, and all deterministic reports. Only PASS may unlock launch, and the activation command must rehash the bound files immediately before starting the copied executable. Launch using the existing default profile, never a separate profile. Immediately run the four-category protected-state postflight comparison.

Report changed files, preserved official behavior, patch signatures, SHA256 values, real wire fields, model metadata, plugin counts/unavailable bundles, separate PASS/FAIL results for user configuration, SSH Connections, project memory/planning, and CC Switch, cc-switch bucket findings, and the exact shortcut target/arguments.
