# Migrating from PyAutoBuild to PyAutoHands

The **Hands** organ of the PyAuto organism is being renamed at the repository
level: **PyAutoBuild → PyAutoHands**. The name change makes the architecture read
as a living organism — *the Brain decides, the Hands do* — so this repo's brand
matches its role: **PyAutoHands executes work on behalf of PyAutoBrain**.

This guide is the single reference for what changes, what does **not**, and what
(if anything) you need to do.

## TL;DR

- The **repository** and its **branding/docs** become PyAutoHands.
- The **`autobuild` command** and the **`autobuild` Python package** keep their
  names. `bash bin/autobuild …`, `import autobuild`, and
  `PYTHONPATH=…/PyAutoBuild/autobuild` all continue to work unchanged.
- Nothing you depend on breaks the moment the repo is renamed: GitHub serves an
  automatic redirect from the old `PyAutoLabs/PyAutoBuild` URL to the new one.

## Why the `autobuild` command/package name stays

The PyAuto ecosystem already decouples **organ names** from **package names**:
PyAutoNerves is the *Nerves* organ but ships the `autoconf` package; PyAutoFit,
PyAutoGalaxy and PyAutoLens ship `autofit` / `autogalaxy` / `autolens`. Keeping
`autobuild` as the command and importable package is consistent with that
pattern and avoids a high-risk churn of every `PYTHONPATH`, `sys.path`, CI
checkout, and import site across the organism. Renaming the *package* is
deliberately **out of scope** for this migration.

## Rollout phases

The rename ships as a small sequence of PRs so nothing breaks mid-migration:

1. **In-repo rebrand (this PR).** README, `AGENTS.md`, `CONTRIBUTING.md`,
   `docs/internals.md` and the `pre_build` skill are rebranded to PyAutoHands,
   and this guide is added. No GitHub rename yet; every functional token
   (`autobuild` CLI/package, `PyAutoLabs/PyAutoBuild` URLs, on-disk
   `PyAutoBuild/…` paths, `PyAutoBuild#NNN` issue links) is left untouched, so
   the repo keeps working exactly as before.
2. **GitHub repository rename** (`PyAutoLabs/PyAutoBuild` →
   `PyAutoLabs/PyAutoHands`). GitHub auto-creates a redirect from the old slug,
   so existing clones, `git remote`s, `actions/checkout`, reusable-workflow
   `uses:` references, and issue/PR links keep resolving.
3. **Cross-repo reference sweep.** The organism's repo-identity source
   (`PyAutoMind/repos.yaml`) and boundary prose (`PyAutoBrain/ORGANISM.md`) are
   updated and the generated organ tables regenerated (`repos_sync.py --write`);
   CI checkouts, sibling-checkout paths, the `autobuild` binary resolver, and
   the workspace/HowTo notebook-generation instructions are re-pointed at the
   new name. The canonical `Brain → Heart (gate) → Build (execute)` call-chain
   wording is updated at its source here too.

## What you need to do

**Downstream users / notebooks:** nothing. Colab setup, pip installs, and
released packages are unaffected — PyAutoHands publishes the same libraries.

**Local developers with a sibling checkout:** after the GitHub rename you may
rename your local clone directory `PyAutoBuild/` → `PyAutoHands/` and update its
`git remote` when convenient — the redirect means there is no rush. Until the
cross-repo sweep lands, tooling still expects the sibling directory to be found;
either directory name works during the transition because the `autobuild`
package path inside it is unchanged.

**Shell aliases:** any `alias autobuild-help='…/PyAutoBuild/bin/autobuild help'`
keeps working through the redirect; update the path to `…/PyAutoHands/…` when you
rename your local checkout.

## Backwards compatibility summary

| Handle | Before | After | Compatibility |
|---|---|---|---|
| GitHub repo | `PyAutoLabs/PyAutoBuild` | `PyAutoLabs/PyAutoHands` | Old URL redirects |
| `autobuild` CLI | `bin/autobuild` | `bin/autobuild` | Unchanged |
| Python package | `import autobuild` | `import autobuild` | Unchanged |
| Release workflow | `release.yml` | `release.yml` | Unchanged |
| Brand / docs | PyAutoBuild | PyAutoHands | Rebranded |
