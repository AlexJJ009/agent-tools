# Incident: Missing Model Catalog Dependency

Load this reference when the Store or patched app reports Windows setup failure, config fallback, missing models, or an invalid configuration after a patch or reinstall.

## Symptom Pattern

The confirmed incident had all of these properties:

- Both the Store app and patched app failed, so the executable alone was not the shared cause.
- `config.toml` still parsed and still referenced `model_catalog_json`.
- The referenced catalog file had disappeared.
- App logs reported `Invalid configuration; using defaults` and Windows error `os error 2`.
- The UI presented a misleading Windows setup failure because app-server had discarded the effective user config.

An unchanged config file is not preserved state when one of its dependencies is gone. Missing or invalid `model_catalog_json` is RED.

## Recorded Evidence

This evidence identifies the historical case; it is not permission to reuse its artifact for another build:

- Package: `OpenAI.Codex_26.721.4979.0`
- Source ASAR SHA256: `44884f86d619a12c3c0af1b8c65945005bda4379775b03270674c666226ff4b7`
- Missing target: `C:\Users\Alex Mercer\Downloads\Report\CodexPatched\model-catalog.json`
- Restored catalog SHA256: `6d6c694360ad6adaf91b4d72b32014afce4c8c8322a304cd01ade377cc00d5f6`
- Catalog result: eight models, including Sol, Terra, and Luna
- Current-timestamp verification after restoration: sandbox readiness `ready`, setup started, setup completed successfully, readiness remained `ready`

The earlier access-denied event under `C:\AppsExternal\automation` had already been repaired and was stale by the time this failure occurred.

## Misleading Signals

- Reinstalling the Store app does not repair `%USERPROFILE%\.codex`; Store and patched executables share that state.
- A previous ACL error can be stale evidence. Do not continue changing ACLs after the current failure points to a missing file.
- A UAC illustration or setup screen does not prove that a helper process launched. Check current processes, app-server logs, and event timestamps.
- A successful UI launch does not prove that the intended provider, model catalog, Fast tier, SSH state, project memory, or CC Switch state survived.

## Forbidden Actions

- Do not delete, reset, rename, recreate, or isolate `%USERPROFILE%\.codex`.
- Do not delete or reset `%USERPROFILE%\.ssh`, sessions, memories, goals, plans, projects, or CC Switch state.
- Do not add `--user-data-dir` or `--profile-directory` to work around the failure.
- Do not kill ChatGPT/Codex as a normal repair step. Ask the operator to close it normally before any write.
- Do not restore a similarly named catalog from the newest or nearest release.
- Do not activate a candidate release. Candidate activation remains blocked until the normal human-reviewed promotion contract is satisfied.

## Read-Only Diagnosis

1. Capture the exact AppX package version and source ASAR SHA256 with `detect`.
2. Run `config-health` against the existing Windows user home before changing files.
3. Read `config.toml` structurally and resolve every configured external dependency. Never print credentials.
4. Confirm whether the same error occurs in Store and patched apps, then correlate current app-server logs by timestamp.
5. Inspect helper/app-server process state if setup claims a helper failed. Treat static UI art as no evidence.
6. Check current ACLs only when the current log identifies access denial. Do not repair an ACL merely because an older log did.
7. Audit the four protected categories and take a closed-App snapshot before any repair write.

The expected command entrypoint is:

```bash
python3 "$GUARD" config-health --user-home "$WIN_HOME" \
  --output "$PATCHED_ROOT/config-health.json"
```

## Hash-Bound Repair

Repair is permitted only when all of the following match:

1. The detected `packageVersion + sourceAsarSha256` selects the exact release.
2. Its immutable recipe declares the catalog in `patcher.artifacts` with source path, target path, and SHA256.
3. `release_registry.py` validates recipe containment and artifact hash.
4. The target path exactly equals the existing `model_catalog_json` value.
5. ChatGPT/Codex has been closed normally and a fresh snapshot succeeded.

Then run that release's narrow `Restore-CodexModelCatalog.ps1` companion. Do not use the full `Patch-CodexApp.ps1` for dependency-only repair: it has a larger staging, shortcut, and plugin write set.

```powershell
& '<exact-release>\Restore-CodexModelCatalog.ps1' `
  -RecipePath '<exact-release>\recipe.json' `
  -DetectionReport '<CodexPatched>\update-detection.json' `
  -SnapshotManifest '<closed-app-snapshot>\manifest.json' `
  -ConfigHealthReport '<CodexPatched>\config-health.json' `
  -OutputReport '<CodexPatched>\model-catalog-repair.json'
```

The companion may restore only the declared artifact to the declared target and must verify the resulting SHA256. It refuses an existing target, missing target directory, running App process, mismatched evidence, and all config writes. Its report always keeps `activationAllowed = false`; repair does not promote or activate the candidate.

If any identity, path, or hash differs, stop with RED. Generate a new candidate and evidence; never guess provenance from a filename.

## Verification After Repair

1. Rerun `config-health`; the dependency must be present, non-empty, valid JSON, and hash-correct.
2. Start the selected executable with empty profile arguments against the existing default profile.
3. Verify app-server RPC/readiness and Windows setup completion from current timestamps.
4. Run model and mock Responses checks required by the exact release.
5. Run postflight for user config/auth, SSH Connections, project memory/planning, and CC Switch.
6. Keep the release candidate and non-activatable unless the complete release lifecycle independently permits promotion.

## Future Removal Rule

Official model support does not authorize deleting `model_catalog_json`. Removal is a separate, explicit, reviewed migration that must update both the config reference and CC Switch-owned common config, preserve provider/history state, pass the four semantic gates, and prove native behavior before and after. Until that migration is approved, the referenced catalog remains part of the profile's runtime contract.
