# Project Adapters

## Core Rule

Share immutable or content-addressed cache data. Keep writable installed
environments and runtime state isolated unless a project-specific identity and
immutability contract proves they are safe to share.

| Detection | Built-in setup plan | Shared layer | Worktree-local layer |
|---|---|---|---|
| `pnpm-lock.yaml` | `pnpm install --frozen-lockfile` | pnpm store | `node_modules` graph |
| `package-lock.json` | `npm ci` | npm download cache | `node_modules` |
| `yarn.lock` | `yarn install --immutable` | Yarn cache | install state per project configuration |
| `bun.lock` / `bun.lockb` | `bun install --frozen-lockfile` | Bun cache | installed dependency graph |
| `uv.lock` | `uv sync --frozen` | uv cache | `.venv` |
| Python requirements only | report manual sync | pip cache | `.venv` |
| Conda environment file | report manual create/update | Conda package cache | named/prefix environment |
| `go.mod` | no install step | `GOMODCACHE`, build cache | source/build outputs |
| `Cargo.toml` | no install step | Cargo registry/git cache | `target` unless explicitly configured |

The CLI reports these commands as guidance only. v1 never executes dependency
installation, package lifecycle scripts, repository hooks, or arbitrary setup.

## Artifact Policy

Treat these as artifact candidates when they contain generated data:

```text
outputs  output  artifacts  wandb  checkpoints  checkpoint
validation  metrics  logs  runs  results  eval_outputs
```

Do not relocate them automatically: a directory named `results` can contain
source-controlled fixtures. Configure the application to write to the external
artifact root shown by `agent-wt create`, then use `doctor` to detect large
generated directories that remain in the checkout.

## Runtime Namespaces

- Docker Compose: derive a unique project name from repo and branch.
- Ports: allocate explicitly or derive from a stable branch hash; do not assume
  the same port can be shared.
- Databases: share the server only when each worktree has its own database,
  schema, or key prefix.
- Hugging Face: share `HF_HOME`/Hub blobs; do not copy snapshots into worktrees.
- W&B and training: send run directories, checkpoints, metrics, and validation
  output to the external artifact root.

The CLI reports namespace suggestions. Application-specific wiring remains a
project policy decision.
