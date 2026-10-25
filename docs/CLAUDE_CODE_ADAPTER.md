# Claude Code adapter (Linux/WSL)

The Claude adapter exposes the plain Agent Tools skills through Claude's native
context and skill locations. Skill prose and Core prose remain shared sources; the
adapter only creates views. Native Windows installation is not covered by this Unix
adapter.

## Install

Run as the intended Unix user, without sudo. Agent Core should be available at
`~/agent-core`, or select it with `--agent-core-home`. The adapter links the
software copy in the install root, so run the machine installer first:

```sh
./scripts/install.sh --root ~/projects --claude-code existing   # or: latest
python3 ~/.local/lib/agent-tools/scripts/install_claude.py --check
```

`never` is the default for `--claude-code`; `--no-claude-code` skips this adapter
without removing existing state. `latest` also installs/updates the official native
CLI. The adapter can also run on its own once the install root is populated:

```sh
python3 scripts/install_claude.py             # link skills, write context, strip retired hooks
python3 scripts/install_claude.py --install-cli
python3 scripts/install_claude.py --check
python3 scripts/install_claude.py --remove
```

No credential, permission mode, Codex model/provider or CC Switch configuration is
changed. The target guard runs before installation.

## What it writes

| Claude entry | Source |
|---|---|
| `~/.claude/CLAUDE.md` | Existing Core entry and its native `@` imports; linked to Core only if missing |
| `~/.claude/rules/agent-tools.md` | Link to the generated view `~/.local/lib/agent-tools/claude/context.md` |
| `~/.claude/skills/<name>` | Link to `~/.local/lib/agent-tools/skills/<name>` for the seven [learning and writing skills](LEARNING_WORKFLOW.md) |
| `~/.claude/settings.json` | `autoMemoryEnabled = false`; retired hook entries removed; nothing else changed |

The context view imports Core through native `@` syntax when the global entry does
not directly point at Core, and links the shared writing contract at
`~/.local/lib/agent-tools/shared/writing/reader-facing-contract.md`. Existing
user-level `CLAUDE.md` contents stay untouched. The adapter preserves unrelated
Claude skills, agents, plugins and project configuration; unmanaged files or
directories in the way of a skill link are left alone and make `--check` fail.
Automatic agent memory is disabled; project rules belong in project
instructions/docs.

## No hooks

Agent Tools registers no Claude hooks ([ADR 0012](decisions/0012-retire-workflow-runtime.md)).
Earlier releases wrote `SessionStart`, `UserPromptSubmit`, `PreToolUse`,
`PostToolUse` and `Stop` commands that ran `.../claude/native_hook.py`. Installation
removes exactly those handlers from `settings.json` (matched by the
`<python> <...>/claude/native_hook.py` command shape), keeps every other handler,
including those sharing a group, and keeps a private copy of the previous file as
`settings.json.agent-tools-backup` (mode 0600; may contain credentials, do not
publish) whenever it removes hooks. It also deletes the old `native_hook.py` views,
the old `~/.local/state/agent-tools/claude/install.json` manifest, links to retired
skills and repoints skill links that still target the old learning bundle.

`--remove` unlinks the skills and the rule and deletes the generated context. It
leaves `settings.json` and `~/.claude/CLAUDE.md` as they are.

## Verification

```sh
python3 -m unittest tests.test_install_claude tests.test_install_skills
claude doctor
```

For native acceptance, inspect an actual session's initialization skill list and use
`InstructionsLoaded` observations to confirm Core and adapter context loading. The
temporary-profile tests do not establish native delivery or model behavior.

Official references: [memory and imports](https://code.claude.com/docs/en/memory),
[skills](https://code.claude.com/docs/en/skills), and
[CLI installation](https://code.claude.com/docs/en/setup).
