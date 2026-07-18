# PyAutoHands — Agent Guidance

> **Formerly PyAutoBuild.** This repository is being renamed PyAutoBuild →
> PyAutoHands (see [MIGRATION.md](MIGRATION.md)). The `autobuild` CLI and Python
> package keep their names for now; only the repository/branding changes. The
> "Build" organ shorthand and the canonical `Brain → Heart (gate) → Build
> (execute)` call chain are updated at their source (`PyAutoBrain/ORGANISM.md`)
> in a later phase.

PyAutoHands is the **executor** (the Hands) of the PyAuto release ecosystem:
packaging, tagging, notebook generation, and PyPI publication via `release.yml`.
**PyAutoHands executes work on behalf of PyAutoBrain.** It runs no
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
executor primitives: the build/notebook pipeline (`pre_build`, `generate*`,
`run_all` / `run*`), the navigator catalogue (`navigator` /
`check_navigator` / `regenerate_navigator`), tagging + release
(`tag_and_merge`, `bump_colab_urls`, `release.yml`), the release-notes and
Slack tooling (`generate_release_notes`, `slack_release_notes`), assistant
seeding (`clone_seed`), and `repro_command`. See `docs/internals.md` for the
authoritative, current list.

See [`docs/internals.md`](docs/internals.md) for the build pipeline, workspace
folder structure, config files, and `release.yml` details. Read it when
changing the pipeline itself, not by default.

<!-- repos_sync:history:begin -->
## Never rewrite history

Never rewrite pushed history on any repo with a remote — no `git init` over a
tracked repo, no force-push to `main`, no fresh-start "Initial commit", no
`filter-repo` / `filter-branch` / `rebase -i` on pushed branches. To get a
clean tree: `git fetch origin && git reset --hard origin/main && git clean -fd`.
<!-- repos_sync:history:end -->
