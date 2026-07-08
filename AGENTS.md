# PyAutoBuild — Agent Guidance

PyAutoBuild is the **executor** of the PyAuto release ecosystem: packaging,
tagging, notebook generation, and PyPI publication via `release.yml`. It runs no
release-readiness checks of its own — that is PyAutoHeart's job.

## The boundary

The organs, boundaries and the `Brain → Heart (gate) → Build (execute)` call
chain are defined once in `PyAutoBrain/ORGANISM.md`. Build's side of it:
**pure executor** — it runs no readiness checks of its own and never
re-derives a gate decision; readiness is gated upstream by the Brain via
`pyauto-heart readiness`.

## What moved out of Build

Release-readiness checking is no longer Build's job. The version-skew gate, the
deep `verify_install` suite, and URL hygiene all live in PyAutoHeart now;
`autobuild verify_install` / `autobuild url_check` / `autobuild watch|status|
tick|fix` are thin shims that delegate to `pyauto-heart`. Build keeps only the
executor primitives (`pre_build`, `generate`, `run*`, `tag_and_merge`,
`bump_colab_urls`, `release.yml`).

See [`docs/internals.md`](docs/internals.md) for the build pipeline, workspace
folder structure, config files, and `release.yml` details. Read it when
changing the pipeline itself, not by default.

## Never rewrite history

NEVER perform these operations on any repo with a remote:

- `git init` in a directory already tracked by git
- `rm -rf .git && git init`
- Commit with subject "Initial commit", "Fresh start", "Start fresh", "Reset
  for AI workflow", or any equivalent message on a branch with a remote
- `git push --force` to `main` (or any branch tracked as `origin/HEAD`)
- `git filter-repo` / `git filter-branch` on shared branches
- `git rebase -i` rewriting commits already pushed to a shared branch

If the working tree needs a clean state, the **only** correct sequence is:

    git fetch origin
    git reset --hard origin/main
    git clean -fd

This applies equally to humans, local Claude Code, cloud Claude agents, Codex,
and any other agent.
