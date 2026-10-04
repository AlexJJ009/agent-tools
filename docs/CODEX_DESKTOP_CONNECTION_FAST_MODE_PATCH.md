# Codex Connections Fast Mode Diagnostics

A local Fast setting does not prove that Codex App Connections pass the selected
tier through the remote app-server to the provider. This guide retains the
observed failure and the request-level verification method. Win11 App patching
uses the [versioned safety workflow](../skills/codex-win11-patch-safety/SKILL.md),
with exact package/source identity, the existing user profile, staged checks and
explicit activation. Historical version heuristics and isolated-profile launchers
are not the current Win11 update procedure.

## Diagnose the transport

The selected local, WSL or SSH host needs:

```toml
service_tier = "priority"

[features]
fast_mode = true
```

The Desktop protocol uses `serviceTier` in `thread/start`, `thread/resume` and
`turn/start`; the provider request uses `service_tier`. Fast-capable model
metadata and UI settings can be present while the Desktop request builder drops
the tier for API-key authentication or incomplete relay metadata. Inspect the
selected host's configuration and actual request separately.

The observed Win11 data point was Store package `26.616.6631.0`, Desktop UA
`Codex Desktop/0.142.0-alpha.6` with build `26.616.51431`. On that build the
legacy bundle patch did not reliably forward the tier. A scoped NewAPI override
for Codex `/v1/responses` traffic produced `service_tier = priority` in the
provider logs. That observation does not establish behavior for newer builds
or authorize changing a shared provider. It also cannot establish that a user
can switch back to Standard if an override forces every matching request to
priority; test that distinction on the actual configuration.

## Existing helpers and their limits

| Helper | Maintained purpose |
|---|---|
| `scripts/configure_codex_app_fast_mode.py` | Patch Fast defaults in the target user's config |
| `scripts/setup_codex_desktop_connection_fast_mode.py` | Legacy Desktop bundle/launcher setup used by the general installer |
| `scripts/patch_codex_desktop_connection_fast_mode.py` | Generate checked bundle patch artifacts for supported historical patterns |
| `scripts/verify_codex_fast_mode_runtime.py` | Read sub2api request usage rows and check the observed tier |

The legacy setup helper remains in source and uses version heuristics. It is
separate from the Win11 safety skill's exact-release state machine; its presence
is not evidence that an unknown App build is supported. Use the versioned
workflow for Win11 updates and activation. For macOS setup, see the
[macOS guide](CODEX_APP_FAST_MODE_MACOS_GUIDE.md). Installer options remain in
[installation](INSTALLATION.md).

## Verify a real request

Send a small request in a fresh Connection thread and obtain its actual request
ID. Query the correct provider host, not an unrelated machine's traffic:

```bash
python3 scripts/verify_codex_fast_mode_runtime.py \
  --ssh-host PROVIDER_HOST --since-minutes 15

python3 scripts/verify_codex_fast_mode_runtime.py \
  --ssh-host PROVIDER_HOST --request-id REQUEST_ID --expect fast
```

Select Standard, send another request, and check that request separately:

```bash
python3 scripts/verify_codex_fast_mode_runtime.py \
  --ssh-host PROVIDER_HOST --request-id STANDARD_REQUEST_ID --expect standard
```

Configure `--container`, `--db-user` and `--db-name` for the actual sub2api
Postgres deployment. The helper's existing defaults describe one installation,
not every provider. Use `--user-agent-like` and `--model-like` to bound a time
window when exact request IDs are unavailable.

For the documented newapi-to-sub2api path, Fast requests should show
`service_tier = priority`; ordinary requests should have no priority tier.
Compare billing rows for the same model and actual provider pricing. The
helper's `--expect fast` name is a check mode; the request value is `priority`.
A UI badge, static configuration or unrelated priority row does not prove the
request under examination used Fast. Report missing rows and failed Standard
checks separately rather than treating them as successful verification.
