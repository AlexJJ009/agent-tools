# Local learning workflow candidate installation

This installer handles one Linux/WSL user profile. It copies the Python
runtime, seven reusable skills, the ReadPapers adapter resource tree, and the
reader-facing writing contract into
`~/.local/share/agent-tools/learning-workflow`. Installed skill links point to
that copy and survive relocation of the source checkout. It does not run the
repository-wide `install.sh` or change Codex providers, authentication, or
development acceptance records.

Run `python3 scripts/install_learning_workflow.py --help` in the candidate
checkout. The installer always calls `scripts/codex_target_guard.py` before
writing profile state. To replace the five known teaching-suite symlinks, pass
the exact old checkout with `--legacy-root`; any different occupied target is
preserved and aborts installation. The reusable skills are installed under
`~/.agents/skills` and linked from `~/.claude/skills`. An explicit
`--read-papers-root /absolute/project/path` additionally installs the
`read-paper` adapter only in that project's `.agents/skills` and
`.claude/skills`. It does not install the project adapter globally.
It also creates a managed `~/.local/bin/learning-workflow` link to the copied
CLI. Ensure that directory is on `PATH` for commands shown in the skills.
If that project already contains a `read-paper` skill directory, pass its
exact path as `--legacy-read-paper-dir`; the installer moves that directory to
a profile-local backup and restores its bytes on rollback. Other occupied
project targets remain untouched.

Global user-level `read-paper` aliases would continue to expose the old broad
skill. If they exist, pass their exact old source directory as
`--legacy-global-read-paper-source`. Only matching symlinks under
`~/.agents/skills`, `~/.codex/skills`, and `~/.claude/skills` are deactivated.
Other links or directories abort installation. Rollback restores the original
link text only if the alias path remains absent; a newly occupied path is
preserved for manual resolution.

`--with-hooks` merges this workflow's five Codex event groups into
`~/.codex/hooks.json`. It preserves foreign groups and settings. The hook
command points to the installed runtime; installation only configures the
groups. Host trust and actual event delivery require separate native readback.
Unbound sessions receive only the runtime's thin hint, and the hooks cannot
intercept arbitrary shell commands or prove semantic routing.

`--check` verifies the bundle, links, installed CLI, and configured hook groups.
`--rollback` restores the prior recognized symlinks, removes newly created
links and exact installer-owned hook groups, and removes the copied bundle.
Rollback stops if an installed skill link, bundle, or installer-owned hook group
was changed after installation; it preserves those changes for manual review.
Foreign or newly added hook entries remain in place. The manifest is kept at
`~/.local/state/learning-workflow/install.json` until a successful rollback.

Use a disposable `HOME` and an explicit disposable ReadPapers root for the
installation trial. Do not treat a passing local `--check` as native host hook
acceptance, user acceptance, or permission to deploy to other profiles.
