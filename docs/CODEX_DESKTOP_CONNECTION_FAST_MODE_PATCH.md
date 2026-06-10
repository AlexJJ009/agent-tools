# Codex Desktop Connections Fast Mode Patch

This note covers a Codex Desktop bundle issue where local Fast Mode works, but
Codex App Connections to WSL or SSH hosts start remote `codex app-server`
threads without passing `serviceTier`.

It is the runbook for Win11 and macOS Codex App. The principle is the same on
both platforms:

1. The selected local, WSL, or SSH host must have Codex config with
   `service_tier = "priority"` and `[features].fast_mode = true`.
2. Codex Desktop must pass that selected/default tier through the Connection
   protocol.
3. The remote app-server must send `service_tier` to the provider.
4. Provider logs and billing rows must show `service_tier = priority`.

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

## Install.sh Routing

`install.sh` now handles both layers:

- `scripts/configure_codex_app_fast_mode.py` writes Codex config for CLI, local
  App, WSL App home, and SSH hosts when run there.
- `scripts/setup_codex_desktop_connection_fast_mode.py` prepares or patches the
  Codex Desktop bundle so WSL/SSH Connections preserve `serviceTier`.

Default behavior:

- On WSL/Win11, `./install.sh` uses `auto` mode and prepares a writable patched
  Microsoft Store Codex copy.
- On macOS, `./install.sh` uses `auto` mode and attempts to patch the installed
  `Codex.app` bundle. If the app is not writable, `auto` reports a warning and
  continues; use `always` when patch failure should fail the install, or
  `never` when the app bundle must not be touched.

Common commands:

```bash
# Win11 from WSL: configure Codex config, prepare patched Desktop copy, and
# write launchers. This is the default on WSL, shown here explicitly.
./install.sh --codex-desktop-connection-fast-mode auto

# Win11 from WSL: also launch the prepared Desktop copy after setup.
./install.sh \
  --codex-desktop-connection-fast-mode auto \
  --launch-codex-desktop-fast-mode

# macOS: patch the installed Codex.app bundle. In auto mode a permission
# failure is a warning; always makes it fatal.
./install.sh --codex-desktop-connection-fast-mode always

# Disable Desktop bundle preparation while still keeping config Fast defaults.
./install.sh --no-codex-desktop-connection-fast-mode
```

## Win11 Launcher

Microsoft Store Codex is installed under protected `WindowsApps`, so the
installer does not modify the Store package in place. From WSL it copies:

```text
C:\Program Files\WindowsApps\OpenAI.Codex_...\app
```

to a writable app directory:

```text
C:\Users\<USER>\AppData\Local\OpenAI\CodexDesktopPatched\app
```

Then it patches the copied `resources\app.asar` and writes launchers:

```text
C:\Users\<USER>\AppData\Local\OpenAI\CodexDesktopPatched\Start-Codex-Fast-Connections.ps1
C:\Users\<USER>\AppData\Local\OpenAI\CodexDesktopPatched\Start-Codex-Fast-Connections.cmd
```

Use that launcher for Codex Desktop when testing WSL/SSH Connections. It starts
the patched `Codex.exe` with:

```text
--user-data-dir=C:\Users\Public\CodexPatchedProfile --no-first-run
```

The isolated profile avoids mixing the patched copy with the Store app's normal
profile. If Windows shows a data-directory error, confirm the launcher was used;
that error usually means `--user-data-dir` was typed manually without quoting a
path that contains spaces.

Direct script usage from WSL:

```bash
python3 scripts/setup_codex_desktop_connection_fast_mode.py \
  --platform win11 \
  --launch
```

Dry-run the copy/patch plan:

```bash
python3 scripts/setup_codex_desktop_connection_fast_mode.py \
  --platform win11 \
  --dry-run
```

## macOS Bundle Patch

macOS uses the same bundle patch, but the installed app is normally under:

```text
/Applications/Codex.app/Contents/Resources/app.asar
```

Patch only after static config is correct and provider logs still show
`service_tier = NULL` for Connection traffic.

Direct script usage:

```bash
python3 scripts/setup_codex_desktop_connection_fast_mode.py \
  --platform macos
```

Dry-run first:

```bash
python3 scripts/setup_codex_desktop_connection_fast_mode.py \
  --platform macos \
  --dry-run
```

If `/Applications/Codex.app` requires admin write permission, rerun with the
same Python and `sudo`, or copy Codex to a user-writable location and pass
`--asar /path/to/Codex.app/Contents/Resources/app.asar`.

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

## Lower-Level Patch Script

The lower-level patcher only modifies an `app.asar` path you give it. It is
useful for inspecting a specific Codex Desktop build:

```bash
python3 scripts/patch_codex_desktop_connection_fast_mode.py --dry-run
```

Generate a patched asar artifact without replacing the source:

```bash
python3 scripts/patch_codex_desktop_connection_fast_mode.py \
  --out /tmp/codex-app.connection-fast-patched.asar
```

Patch a non-Store or user-writable build in place:

```bash
python3 scripts/patch_codex_desktop_connection_fast_mode.py \
  --asar /path/to/app.asar \
  --in-place
```

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

Useful sub2api query shape:

```sql
select id, created_at, model, coalesce(service_tier,'<NULL>') tier,
       request_id,
       case when input_tokens > 0 then round(input_cost * 1000000 / input_tokens, 2) end as input_usd_per_m,
       case when output_tokens > 0 then round(output_cost * 1000000 / output_tokens, 2) end as output_usd_per_m,
       total_cost,
       left(user_agent,120) as ua
from usage_logs
where created_at >= now() - interval '15 minutes'
  and user_agent like 'Codex Desktop/%'
order by created_at desc
limit 20;
```

Expected behavior:

- Fast-enabled Connection requests show `service_tier = priority`.
- Standard requests stay `service_tier = NULL`.
- For the same model, priority rows show the Fast price and NULL rows show the
  normal price.

## Rollback

Win11:

1. Stop Codex Desktop.
2. Launch the Microsoft Store Codex normally instead of
   `Start-Codex-Fast-Connections.ps1`.
3. Delete the writable patched copy if needed:

```text
C:\Users\<USER>\AppData\Local\OpenAI\CodexDesktopPatched
```

macOS:

1. Stop Codex.
2. Restore the backup:

```bash
cp /Applications/Codex.app/Contents/Resources/app.asar.connection-fast-backup \
   /Applications/Codex.app/Contents/Resources/app.asar
```

Then restart Codex and verify provider logs again.
