# Codex Desktop Connections Fast Mode Patch

This note covers a Codex Desktop bundle issue where local Fast Mode works, but
Codex App Connections to WSL or SSH hosts start remote `codex app-server`
threads without passing `serviceTier`.

## Root Cause

Codex Desktop has a user setting named `default-service-tier`, and the
app-server protocol supports `serviceTier` on:

- `thread/start`
- `thread/resume`
- `turn/start`

The Windows Store build inspected on this machine has these bundle files inside
`app/resources/app.asar`:

- `webview/assets/read-service-tier-for-request-*.js`
- `webview/assets/use-service-tier-settings-*.js`
- `webview/assets/app-server-manager-signals-*.js`

The request builder already has a `serviceTier` field, but the UI/request helper
can drop Fast when the target host is authenticated as API key / relay instead
of ChatGPT OAuth, or when relay model metadata omits `serviceTiers`.

That is why static config such as:

```toml
service_tier = "priority"

[features]
fast_mode = true
```

can look correct while real new-api/sub2api logs still show
`service_tier = NULL` for Codex Desktop Connection traffic.

Older hosts may still contain `service_tier = "fast"`. Current standalone Codex
accepts both `fast` and `priority`, but the Responses/new-api billing row uses
`priority`. New installs should write `priority`; the Desktop patch normalizes
the old `fast` alias before sending Connection requests.

## What The Patch Does

Run:

```bash
python3 scripts/patch_codex_desktop_connection_fast_mode.py --dry-run
```

For the inspected Windows Store build, this reports these patch points:

- Allow explicit per-thread service tier selections.
- Allow explicit config `service_tier` values.
- Show the service-tier selector outside ChatGPT auth when the feature is not
  disabled.
- Add a Fast selector option when relay model metadata omits service tiers.
- Normalize the legacy `fast` tier alias to the provider/API tier id
  `priority`.
- For ordinary follow-up messages, read the host's default service tier when
  the composer did not pass an explicit `serviceTier`.

The patch is consent-preserving:

- It does not set Fast for standard/null requests.
- It does not modify new-api `param_override`.
- It only stops Codex Desktop from filtering out a tier that the user selected
  or configured. The follow-up fallback reads the selected host's Codex config;
  if that config has no Fast tier, the request remains standard/null.

## Why Not Force It In new-api

Do not use a channel-wide `param_override` such as:

```json
{"operations":[{"mode":"set","path":"service_tier","value":"priority"}]}
```

That makes every request on the channel bill as Fast, including users who did
not enable Fast Mode. The correct behavior is:

1. User enables Fast Mode in Codex Desktop or config.
2. Desktop sends `serviceTier` to the selected local/WSL/SSH app-server.
3. The remote app-server sends `service_tier` to the API provider.
4. new-api passes the field through.
5. sub2api logs and bills the request as Fast/priority.

## Windows Store Caveat

Microsoft Store Codex is installed under a read-only WindowsApps package, for
example:

```text
C:\Program Files\WindowsApps\OpenAI.Codex_26.608.1337.0_x64__2p2nqsd0c76g0\app\resources\app.asar
```

The helper can generate a patched asar:

```bash
python3 scripts/patch_codex_desktop_connection_fast_mode.py \
  --out /tmp/codex-app.connection-fast-patched.asar
```

Replacing the Store package in place may require Windows package ownership or a
non-Store Codex Desktop install. Treat the generated asar as a candidate patch
artifact, not an automatic Store-package mutation.

## Runtime Verification

Static config is not enough. Verify with bwg new-api/sub2api logs:

1. Restart Codex Desktop and the target Connection.
2. In a new WSL/SSH Connection thread, enable Fast Mode or confirm the model
   selector shows Fast.
3. Send a small prompt.
4. Query sub2api `usage_logs` for the request and confirm
   `service_tier = priority`.
5. Disable Fast/choose Standard and send another prompt.
6. Confirm the new request logs `service_tier = NULL` or standard.

Only the log/billing result is authoritative.
