# Project Memory (Retired From Active Use)

Automatic Codex and Claude Code memory was disabled and the audited memory
stores on reachable profiles were cleared by the user's decision on 2026-10-04.
OVH `15.204.46.107` could not be accessed and remains unverified. Project rules and
architecture belong in the owning project's maintained instructions and docs;
unfinished work belongs in current task state. Do not create or synchronize a
separate agent memory library during installation or ordinary project work.

The historical `scripts/codex_project_memory.py` helper remains available for
explicitly requested compatibility inspection. Do not run its `init` or `sync`
commands as an installation or migration prerequisite. Native Codex memory,
Claude auto memory, explicit `.codex/project-memory`, imported mirrors and
handwritten loading instructions are separate mechanisms: disabling a native
feature alone does not retire the others.

Codex's `[features].memories` is off in installer defaults. Existing profiles
also disable `memories.generate_memories` and `memories.use_memories`; Claude
profiles use `autoMemoryEnabled = false`. Provider switches and reinstallations
must preserve this decision without changing auth, model or approval settings.

Memory cleanup does not authorize deleting conversations, credentials,
maintained project docs, business data or current task state. Retained pricing
and EmailEngine deployment information was moved into its owning projects,
with historical observations distinguished from current facts.
