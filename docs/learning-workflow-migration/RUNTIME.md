# Learning workflow runtime

The Main Agent reads the user's current request, exclusions, active agreement,
and source scope. It supplies the semantic decision. `learning-workflow` stores
and checks that decision; it does not classify keywords or certify meaning.
The runtime supports Linux/WSL Python 3.10+ (local file locks use `fcntl`).

## Minimal use

Run `learning-workflow decision-schema` for field types and an example packet.
Skill instructions and CLI help are English; request snapshots and generated
content may be in the user's chosen language. A brief answer or straightforward
repair may stay in conversation. Persistent learning/writing, changed stages,
and covered operations need current state.

```sh
learning-workflow init --query request.txt --decision decision.json \
  --workspace /path/to/project --session-id ACTUAL_NATIVE_SESSION_ID
learning-workflow show --record /path/returned/by/init
learning-workflow input --record /path/to/record --input-id turn-2 --query turn-2.txt
learning-workflow classify --record /path/to/record --input-id turn-2 \
  --decision next-decision.json --base-revision 2
```

`input` advances the revision. Read its result before classifying. Identical
input/decision retries are idempotent; changed content under the same ID is an
error. Stale updates fail. If a newer input has already been classified, an older
pending input can only be resolved with the current decision; it cannot restore
an earlier activity or remove newer exclusions. Classification/read operations
remain available while input is pending.

`routing.json` is canonical and contains the versioned decision under `decision`,
request snapshots, input states, and a compact history. `task.md` is a derived
view. A development task uses `development_record_ref: {path, revision}` and
stores the route in the existing record directory, with `routing.md` as its view.
The reference `path` is a directory containing `checklist.yaml` or a
project-equivalent `task.md`; it is not the Markdown file itself. Omit `--record`
or use that same directory. Read the revision from the actual project record.
It never overwrites the development `request.txt`, `task.md`, or checklist.
A reference is not a second authorization or acceptance record.

## Covered operations and limits

`check-action` checks a named action at the expected route revision. Ordinary
reads can continue with pending input. Dependent writes require resolved input,
available selected skills and declared output paths. Default skill lookup includes
user `.agents/skills` and `.codex/skills`, plus workspace `.agents/skills` and
`.claude/skills`; explicit `skill_roots` replaces this search list. A failed
capability check is recovered in the existing task record. For an inspected
location correction, snapshot the preserved request with a distinct recovery
input ID and classify at the returned revision; this creates no new authority.
Library/close-reading
checks additionally require the explicit configured ReadPapers scope and the
project adapter. Remote read scopes use canonical `host:/absolute/path`
locators, with no traversal segments. A code read never authorizes an experiment.
Experiments and external publication must use their existing authorization
mechanism; this runtime does not launch either.

These checks validate supplied facts, not the truth of a model's permission
claim. Main must ground scopes in the user request and actual project config.
They do not intercept arbitrary Python, shell, MCP, filesystem access or chat.
There is no central daemon, hidden classification request, or general sandbox.

`curate` is a real guarded write entry: it rechecks state even with Hooks off,
copies a finished note, and creates one `artifact-index.json` in the selected
knowledge directory. An explicit stable `project_id` plus source-relative path
identifies an entry. A directory basename is insufficient. Reimport updates the
same entry but refuses to overwrite a curated file edited since the last import.
Source project ID/revision/path and artifact digest retain provenance. An absent
Git revision remains null. Main must still review self-containedness and privacy.
Use `inspect-index --index PATH [--source-root DIR]` after relocation to read
actual artifact/source availability; missing source access is not synchronization.
Curation cannot place artifacts inside the route's internal state directory.

## Native Hook boundary

`learning-workflow bind --record DIR --session-id ID --workspace DIR
--state-root DIR [--on-stop]` binds one actual session/workspace pair. Unbound
SessionStart/UserPromptSubmit add only a thin routing reminder and the actual
host identity. They do not create a persistent record or start a classifier.
Bound input is saved before Main classifies it. Hosts lacking turn IDs only
provide content-level prompt retry identity; repeated identical requests cannot
be distinguished there without an explicit `input-id`.

The adapter declares five events. PreToolUse/PostToolUse recognize direct
`learning-workflow curate` and `python -m learning_workflow curate` invocations
for `Bash` and `exec_command`-shaped payloads. Compound shell commands and other
tools are outside automatic coverage. The real curation entry still validates
on invocation. PostToolUse records an observation, never acceptance. Stop can
issue one continuation for an explicitly registered obligation; ordinary
learning does not create a Work Report. Actual native host coverage and latency
must be reported separately from these supported adapter shapes.

## Migration compatibility

The old keyword router remains importable, but a prompt without an explicit
Main decision returns `semantic-decision-required`, never a teaching route.
The v1 teaching validator, fixtures and Zotero resolver retain their original
bytes/behavior. Existing ZotLit managed regions are not rewritten. New portable
learning records are opt-in; no bulk conversion is performed.

W1–W9 are maintained at `shared/writing/reader-facing-contract.md`. Generated
copies let the report and brief work independently. Their six-section reporting
and report Judge stay genre-specific. `academic-writing` supports direct draft,
revision and argument review without teaching state. ReadPapers' adapter stays
project-local; other repositories may consume supplied evidence.
