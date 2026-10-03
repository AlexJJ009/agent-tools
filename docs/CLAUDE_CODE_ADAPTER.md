# Claude Code adapter (Linux/WSL)

The Claude adapter exposes the existing Agent Tools packages through Claude's
native context, skill and hook locations. Skill prose, Core prose, task records
and runtime semantics remain shared. Native Windows installation is not covered
by this Unix adapter.

## Install

Run as the intended Unix user, without sudo. Agent Core should be available at
`~/agent-core`, or select it with `--agent-core-home`.

```sh
# Existing CLI: prepare shared packages and install the Claude adapter.
python3 scripts/install_claude.py --install-packages
python3 scripts/install_claude.py --check

# Also install/update the official native CLI to latest.
python3 scripts/install_claude.py --install-packages --install-cli
```

The machine installer offers the same opt-in:

```sh
./install.sh --root ~/projects --claude-code existing
./install.sh --root ~/projects --claude-code latest
```

`never` is the default for `--claude-code`; `--no-claude-code` skips this adapter
without removing existing state. The machine installer retains its other setup
steps. Use the dedicated Python command when only Claude adaptation is needed.
No credential, permission mode, Codex model/provider or CC Switch configuration
is changed by the dedicated adapter. Its target guard runs before installation.
Shared package preparation uses their existing installers: workflow/report can
refresh managed packages; an existing learning bundle is updated with its
recorded choices through its own installer. Rerunning the adapter moves views
recorded under the old `~/.local/share/agent-tools/claude/` into the install
root and repoints the rule link, skill links and hook commands. Resolve learning package drift through its
[installer](LEARNING_WORKFLOW_INSTALL.md), rather than overwriting its state.

## Locations and single source of truth

| Claude entry | Authoritative source |
|---|---|
| `~/.claude/CLAUDE.md` | Existing Core entry and its native `@` imports; linked to Core if missing |
| `~/.claude/rules/agent-tools.md` | Generated profile view at `~/.local/lib/agent-tools/claude/context.md` (install root, beside `native_hook.py`) |
| `~/.claude/skills/<name>` | Existing shared workflow/report packages and learning bundle |
| `~/.claude/settings.json` hook commands | Existing installed workflow, learning and report hook runtimes |
| Task/route/report records | Existing runtime storage and explicit records; no Claude copy |

The adapter installs fourteen shared skills. It preserves unrelated Claude
skills, agents, plugins and project configuration. This repository's
`.agents/skills/build-eval` and `hillclimb` are Codex-only and have no
`.claude/skills` links; Claude uses its native `claude-api` and `skill-creator`.

The context view links to the shared writing contract. If the existing global
entry does not directly point at Core, the view imports Core through native
`@` syntax. Core's symlink is never written through. Existing user-level
`CLAUDE.md` contents remain untouched.
Unmanaged regular files/directories and conflicting links are rejected.

For explicitly selected old skill symlinks, provide their exact source directory:

```sh
python3 scripts/install_claude.py \
  --legacy-skill-root /absolute/old-checkout/skills \
  --legacy-skill-root ~/agent-core/skills
```

Only links whose resolved targets match `<specified-root>/<skill-name>` may
migrate. Source files are left intact. The private install manifest records the
previous links; removal restores them. A credentials-bearing settings backup,
when needed, is written with mode `0600` under
`~/.local/state/agent-tools/claude/`. Do not publish it.

## Native hooks and process state

Claude reads hook definitions from `settings.json`; `.claude/hooks.json` is not
this adapter's registration location. The adapter registers `SessionStart`,
`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `Stop` as applicable to each
shared runtime. It strips Codex-only context-limit fields. Foreign settings and
hook handlers survive installation and removal, including handlers in mixed
groups. Unchanged reinstallation creates no additional backups. Learning and
workflow `PreToolUse`/`PostToolUse` groups match only `Bash`, the only tool
they act on; work-report `PostToolUse` keeps `.*`. Codex registrations keep
`.*` because Codex shell tool names are not verified here.

The small managed `native_hook.py` adapter forwards events to the shared
runtimes. At `SessionStart` it ensures the learning context includes the actual
native `session_id`, workspace and state root even when a record is already
bound, and it moves report diagnostics to Claude's top-level `systemMessage`
field. A `UserPromptSubmit` whose prompt is only background
`<task-notification>` envelopes is system text, not user input, and is not
forwarded to any runtime; user text outside the envelopes is forwarded intact.
Claude's prompt payload has no `turn_id` but carries a per-submission
`prompt_id` (observed on Claude Code 2.1.288); the adapter forwards it as
`turn_id`, so identical repeated prompts become distinct inputs while a retried
submission stays idempotent. Non-JSON runtime output becomes a short
`systemMessage` instead of a traceback.
Shared block/deny decisions and process-state writes remain unchanged.
Bind and resume using those observed values and the existing runtime
commands. The adapter does not create a task merely because Claude starts, or
turn a Stop event into acceptance. Existing bound-record obligations apply.

Claude has no Codex `Interrupt` event. `SessionEnd` is not substituted: switching
or clearing a session must not silently cancel resumable report obligations.
Codex queue/exec scheduling and report timers are not converted into Claude
schedulers. Native context injection and ordinary Stop blocking use the shared
compatible output.

## Check and remove

```sh
python3 scripts/install_claude.py --check
python3 scripts/install_claude.py --remove
```

Check validates links, context, the managed hook adapter and hook definitions;
it is not proof of native
execution. Removal refuses changed managed entries, restores prior skill links,
and removes only this adapter's hook commands and context view. It preserves
shared packages, CLI, Core contents, user auth and subsequent unrelated settings
edits. Fresh Claude sessions load new definitions; an already running session
may retain its settings snapshot. After updating the source checkout, rerun
installation to refresh verified managed context/helper/definitions. It refuses
user-modified managed files, preserves unrelated settings, and rolls back failed
publication. The stored installation snapshot also permits removal after a
source update.

## Verification

```sh
python3 -m unittest tests.test_claude_hooks tests.test_install_claude tests.test_claude_native_hook
claude doctor
```

For native acceptance, inspect an actual session's initialization skill list
and use `InstructionsLoaded` observations to confirm Core and adapter context
loading. Exercise `Skill`, a read-only shell command and the resulting tool
hooks. With an isolated fixture binding, verify prompt capture in the same
record. Keep fixture sessions distinct from the user's live task session.
Simulated hook tests do not establish native delivery or model behavior.

Official references: [memory and imports](https://code.claude.com/docs/en/memory),
[skills](https://code.claude.com/docs/en/skills),
[native hook settings](https://code.claude.com/docs/en/hooks), and
[CLI installation](https://code.claude.com/docs/en/setup).
