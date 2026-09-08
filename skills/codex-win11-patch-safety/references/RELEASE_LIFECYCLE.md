# Versioned Release Lifecycle

## Release Identity

A recipe matches exactly one `packageVersion + sourceAsarSha256`. Store it under `releases/<version>/` with:

- `recipe.json`: application identity, status, patcher contract, verification requirements, and provenance;
- the actual feature-signature patcher source;
- optional non-secret fixtures needed to reproduce deterministic checks.

`releases/index.json` is the machine-readable selector. Never select by nearest version, filename similarity, or latest release fallback.

## Statuses

- `candidate`: an agent or human captured a new patch method and evidence, but activation is not approved.
- `verified`: a named human reviewed the unchanged candidate and the exact build passed a hash-bound verdict plus four-gate postflight.
- `retired`: reserve for a future explicit retirement event; never delete historical recipes.

The captured `26.707.8168.0` release is candidate because its legacy verification used an isolated profile. Reverify it on the existing default profile before promotion.

## Create A Candidate

For an unknown build, unpack without activation and compare it with the latest verified release by code feature signatures. Prefer official implementations and remove compatibility patches that official code made unnecessary.

Generate a new patcher and record it without overwriting an existing release:

```bash
python3 scripts/release_registry.py --index releases/index.json \
  record-candidate \
  --detect '<detection-report.json>' \
  --patcher '<new-patcher.mjs>' \
  --author '<agent-or-human>' \
  --reason '<what changed and why a new recipe is needed>' \
  --ledger '<release-evolution.jsonl>'
```

Run syntax, idempotence, mutation, model, wire, plugin, state, and release-verdict tests. Candidate evidence can be regenerated; the candidate registry event remains append-only.

## Human Review And Promotion

Review the patch diff, source signatures, official behavior preserved, write set, tests, real wire output, state protection, and unresolved findings. The reviewer must be distinct from an autonomous agent's self-assertion.

After reviewing, the human supplies an approval JSON that binds the evidence:

```json
{
  "releaseId": "<release-id>",
  "recipeSha256": "<sha256>",
  "verdictSha256": "<sha256>",
  "postflightSha256": "<sha256>",
  "reviewer": "<human identity>",
  "reason": "<concrete review conclusion>",
  "humanApproval": true
}
```

An Agent may calculate hashes and generate a template with `humanApproval: false`; it must not assert the human approval itself. This artifact provides explicit binding and auditability, not cryptographic identity. Add offline signature verification before treating it as tamper-proof authorization across untrusted operators.

```bash
python3 scripts/release_registry.py --index releases/index.json \
  promote \
  --release-id '<release-id>' \
  --verdict '<hash-bound-PASS.json>' \
  --postflight '<four-gate-postflight.json>' \
  --approval '<human-supplied-approval.json>' \
  --ledger '<release-evolution.jsonl>'
```

Promotion checks package/source identity, the recorded patcher hash, PASS status, and all four postflight categories. It records evidence hashes, never credentials.

## Evolution Rules

- Never edit a verified release. Create a new candidate for changed AppX/source ASAR, patcher behavior, or verification contract.
- Keep release recipes reproducible and small. Put large generated reports outside the skill and bind them by hash.
- Store runtime artifacts required to keep protected config valid inside the exact candidate release and bind each required config artifact to `configKey`, exact `targetPath`, and SHA256 in `patcher.artifacts`; do not depend on leftovers in an output directory. Provide a narrow restore companion that cannot stage apps, rewrite shortcuts/config, register plugins, activate, or promote.
- Keep three lifecycles separate: candidate evidence is regenerable, evolution/verdict ledgers are append-only machine records, and safety principles change only after a lesson generalizes.
- Agents may propose and test; humans approve promotion and activation.

## Captured Candidates

- `26.707.8168.0`: retained as candidate because its historical verification used an isolated profile.
- `26.721.4979.0`: retains official GPT-5.6 behavior and patches Fast/service-tier and local plugin compatibility. Its runtime contract includes the hash-bound model catalog while the existing default profile still references `model_catalog_json`.
