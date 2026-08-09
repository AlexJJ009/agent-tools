# Contribution contract

A delivery is identified by `(linear_batch_or_issue, repository_full_name,
base_branch, working_branch, candidate_sha)`. Repository names use canonical
`owner/repository`; GitHub work items use `owner/repository#number`; SHAs are
lowercase 40-hex values.

Standard and High Batch branches use
`linear/<batch-id-lowercase>-<slug>`. A Fast single-Issue branch uses the Issue
ID. One Batch normally produces one primary PR per repository. PR titles begin
with the Batch ID and bodies record Batch, Issues, repository, base SHA,
candidate SHA, GitHub Issues, and risk profile.

Commit subjects use `<type>(<scope>): <imperative summary>` where type is one
of `feat`, `fix`, `refactor`, `test`, `docs`, `perf`, `build`, `ci`, `chore`, or
`revert`. Review candidates reject `WIP`, `fixup!`, and `squash!` subjects.
Ordinary checkouts retain the human Git identity and add the relevant Agent as
a co-author.

Each Issue gets only targeted checks. After every included Issue is complete,
fix the candidate and run required CI once. A new commit creates a new candidate
and invalidates prior CI, review, and integration verdicts.

Review verdict history is append-only. Every round uses a new artifact path
under the policy-owned verdict root. Evidence preserves the exact base verdict
prefix and records each verdict-commit path with its Git diff status. A valid
verdict-only commit contains only `added` paths for the newly appended rounds;
reusing, modifying, or deleting an existing artifact path fails admission.
PR commit evidence is an ordered complete chain whose final SHA equals the
fetched PR head. The reviewed candidate appears exactly once; every later
commit must match a newly appended verdict's artifact commit and may add only
that verdict's new artifact path. Any intervening code commit invalidates the
candidate CI and review. The evidence chain must exactly equal the ordered
commit SHA list returned by the fetched GitHub PR metadata and bind the same
base SHA, so omitting an intermediate commit also fails admission.
