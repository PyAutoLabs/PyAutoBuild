# PyAutoBuild — Agent Guidance

PyAutoBuild is the **executor** of the PyAuto release ecosystem: packaging,
tagging, notebook generation, and PyPI publication via `release.yml`. It runs no
release-readiness checks of its own — that is PyAutoHeart's job.

## The boundary (one description, mirrored in all three repos)

- **PyAutoHeart — the health authority.** All health/readiness logic lives here:
  version drift, install-path, URL hygiene, CI/worktree/timing monitoring.
  `pyauto-heart readiness` is the **authoritative** green/yellow/red verdict —
  the single "is it safe to release?" gate. Heart is an observer: it reads and
  emits verdicts; it never writes into other repos and never triggers Build.
- **PyAutoBuild — the executor.** Packaging, tagging, notebook generation, and
  PyPI publication via `release.yml`. Build runs **no** readiness checks of its
  own and never re-derives a gate decision; it just executes.
- **PyAutoBrain — the brain.** Hosts the agents that connect the two. It owns no
  checks and no release steps; it gates on Heart and delegates execution to
  Build.

## The call chain (always this order)

```
Brain  →  Heart (gate)  →  Build (execute)
```

The agent asks `pyauto-heart readiness --json`; only on a **green** verdict does
it trigger Build's release. Heart never triggers Build; Build never re-derives a
gate decision the agent already made.

## What moved out of Build

Release-readiness checking is no longer Build's job. The version-skew gate, the
deep `verify_install` suite, and URL hygiene all live in PyAutoHeart now;
`autobuild verify_install` / `autobuild url_check` / `autobuild watch|status|
tick|fix` are thin shims that delegate to `pyauto-heart`. Build keeps only the
executor primitives (`pre_build`, `generate`, `run*`, `tag_and_merge`,
`bump_colab_urls`, `release.yml`).

See [`CLAUDE.md`](CLAUDE.md) for the build pipeline, workspace folder structure,
config files, and `release.yml` details.
