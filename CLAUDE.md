# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

PyAutoBuild is the **executor** of the PyAuto release ecosystem (PyAutoConf, PyAutoFit, PyAutoArray, PyAutoGalaxy, PyAutoLens) — it runs **no** release-readiness checks of its own (that is PyAutoHeart's job; see [`AGENTS.md`](AGENTS.md) for the canonical Build/Heart/Brain boundary and the `Brain → Heart → Build` call chain). It automates:
1. Building and releasing packages to TestPyPI, then PyPI
2. Running workspace Python scripts (integration tests)
3. Converting Python scripts to Jupyter notebooks and executing them
4. Committing generated notebooks to workspace `main` branches and tagging each workspace with a version matching the released library

The pipeline is triggered via GitHub Actions (`release.yml`) and is manually dispatched with configurable options. Release-readiness gating happens upstream: the PyAutoBrain release agent calls `pyauto-heart readiness` and only dispatches `release.yml` on a green verdict.

## Bash CLI

Every operation in this repo is invokable from the shell via the `autobuild` dispatcher at `bin/autobuild`. List subcommands with `autobuild help`; print the docstring for one with `autobuild help <subcommand>` (or `autobuild <subcommand> --help`).

Recommended alias for `~/.bashrc`:

```bash
alias autobuild-help='$HOME/Code/PyAutoLabs/PyAutoBuild/bin/autobuild help'
```

The dispatcher routes to the underlying bash script directly, or to the Python tool with `PYTHONPATH` already set so the internal `build_util` / `result_collector` / `env_config` imports resolve. The same operations remain callable as Claude skills (`/pre_build`, `/verify_install`, `/review_release`); use the skill when you want the validation + summary wrapper, the CLI when you just want to fire the underlying tool.

## Pre-Build Steps

Before triggering a build, run:

```bash
bash $HOME/Code/PyAutoLabs/PyAutoBuild/bin/autobuild pre_build [minor_version]
# minor_version defaults to 1
# (equivalent to: bash $HOME/Code/PyAutoLabs/PyAutoBuild/pre_build.sh [minor_version])
```

This script does the following for each repo:

| Repo | black | generate.py | commit & push |
|------|-------|-------------|---------------|
| `autofit_workspace` | yes | yes (`autofit`) | yes |
| `autogalaxy_workspace` | yes | yes (`autogalaxy`) | yes |
| `autolens_workspace` | yes | yes (`autolens`) | yes |
| `autofit_workspace_test` | yes | no | yes |
| `autogalaxy_workspace_test` | yes | no | yes |
| `autolens_workspace_test` | yes | no | yes |
| `euclid_strong_lens_modeling_pipeline` | yes | no | yes |
| `HowToGalaxy` | yes | yes (`howtogalaxy`) | yes |
| `HowToLens` | yes | yes (`howtolens`) | yes |
| `HowToFit` | yes | yes (`howtofit`) | yes |

Before the per-repo loop, `pre_build.sh` invokes `admin_jammy/software/ensure_workspace_labels.sh` to assert the canonical `pending-release` label across every release-window repo (idempotent — a no-op when nothing has drifted).

Release-readiness checking is **not** Build's job — PyAutoBuild is a pure executor. The version-skew check that used to live here (`verify_workspace_versions.sh`, a fail-fast guard against a workspace pinned ahead of its installed library, or a `config/general.yaml` ↔ `version.txt` disagreement) now lives in **PyAutoHeart** as the `version_skew` check feeding `pyauto-heart readiness`. The PyAutoBrain release agent gates on `pyauto-heart readiness` before invoking `pre_build`; a human running `pre_build` directly is trusted to have checked readiness first. See PyAutoHeart for the resolution precedence (`config/general.yaml:version.workspace_version`, then `version.txt`) — identical to `autoconf.workspace.check_version`, so workspace/library mismatches still surface on every script run via each library's `__init__.py`.

`generate.py` is run from the workspace root with `PYTHONPATH` pointing at `PyAutoBuild/autobuild/`. Only specific safe directories are committed — never `output/`, `output_model/`, or run-generated artefacts. After all workspaces are done, PyAutoBuild itself is committed and pushed, then `gh workflow run release.yml` dispatches the GitHub Actions release.

## Workspace Folder Structure

Each workspace repo (`autofit_workspace`, `autogalaxy_workspace`, `autolens_workspace`, their `_test` variants, and the lecture repos `HowToGalaxy`/`HowToLens`) has the following expected structure. **Only these paths should ever be committed.**

| Folder / file | autofit | autogalaxy | autolens | Notes |
|---|---|---|---|---|
| `config/` | yes | yes | yes | PyAutoConf config files |
| `dataset/` | yes | yes | yes | Input data; force-added with `git add -f` |
| `notebooks/` | yes | yes | yes | Generated from `scripts/` by `generate.py` |
| `scripts/` | yes | yes | yes | Source Python scripts |
| `slam_pipeline/` | no | no | yes | autolens only |
| `output/` | — | — | — | **Always empty** — kept under git with a `.gitignore` only |
| Root-level files | yes | yes | yes | `README.md`, `setup.py`, `pyproject.toml`, `requirements.txt`, `*.cfg`, `*.ini`, `*.yml`, `*.yaml`, `LICENSE*` |

### Paths that must NEVER be committed

- `output/` contents — run results; the folder itself exists only via `.gitignore`
- `output_model/` — model JSON/pickle artefacts written during script execution
- `path/to/model/` or any nested model JSON files written at runtime
- `.fits` files outside `dataset/` (e.g. `image.fits`, `dataset.fits` generated by simulators into `scripts/` or other subdirectories)

## Running Tests

```bash
# Run all tests
pytest

# Run a single test
pytest tests/test_files_to_run.py::test_script_order
```

## Codex / sandboxed runs

When running Python from Codex or any restricted environment, set writable cache directories so `numba` and `matplotlib` do not fail on unwritable home or source-tree paths:

```bash
NUMBA_CACHE_DIR=/tmp/numba_cache MPLCONFIGDIR=/tmp/matplotlib pytest
```

This workspace is often imported from `/mnt/c/...` and Codex may not be able to write to module `__pycache__` directories or `/home/jammy/.cache`, which can cause import-time `numba` caching failures without this override.

## Key Scripts

All scripts in `autobuild/` are run from within a checked-out workspace directory (not from this repo root). They rely on `PYTHONPATH` including the PyAutoBuild directory.

- **`run_python.py <project> <directory>`** — Executes Python scripts in a workspace folder, skipping files listed in `config/no_run.yaml`
- **`run.py <project> <directory> [--visualise]`** — Executes Jupyter notebooks in a workspace folder, skipping files in `config/no_run.yaml`
- **`generate.py <project>`** — Converts Python scripts in `scripts/` to `.ipynb` notebooks in `notebooks/`, run from within the workspace root
- **`script_matrix.py <project1> [project2 ...]`** — Outputs a JSON matrix of `{name, directory}` pairs for GitHub Actions matrix strategy
- **`tag_and_merge.sh --version <version>`** — Commits pending changes and tags library repos (PyAutoConf, PyAutoFit, PyAutoArray, PyAutoGalaxy, PyAutoLens) for release
- **`url_check`** — URL hygiene moved to PyAutoHeart (Heart owns all health checking). `autobuild url_check` is now a thin shim to `pyauto-heart url_check`; the ecosystem-wide sweep runs from PyAutoHeart's central `url-check.yml` workflow (replacing the old per-repo `url_check.yml` workflows). The runnable scripts live at `PyAutoHeart/heart/checks/url_check*.{sh,py}`.
- **`bump_colab_urls.sh <new-tag>`** — Rewrites every `colab.research.google.com/github/PyAutoLabs/<repo>/blob/<old-tag>/...` URL in cwd to use `<new-tag>`, where `<repo>` is one of `autofit_workspace`, `autogalaxy_workspace`, `autolens_workspace`, `HowToGalaxy`, `HowToLens`. Called by the `release_workspaces` and `bump_library_colab_urls` jobs in `release.yml` so README/docs Colab links always pin to the just-released tag. Idempotent; skips URLs not in canonical PyAutoLabs/date-tagged form.

## Architecture

### Script-to-Notebook Conversion Pipeline

`generate.py` → `generate_autofit.py` + `build_util.py`:
1. `add_notebook_quotes.py` transforms triple-quoted docstrings into `# %%` cell markers in a temp `.py` file
2. `ipynb-py-convert` converts the temp file to `.ipynb`
3. `build_util.uncomment_jupyter_magic()` restores commented-out Jupyter magic commands (e.g. `# %matplotlib` → `%matplotlib`)
4. Generated notebooks are `git add -f`ed directly

### Script Execution Order

`build_util.find_scripts_in_folder()` enforces a specific ordering:
1. Scripts with "simulator" in the path (data must be generated first)
2. Scripts named `start_here.py`
3. All other scripts

### Config Files

Each workspace owns its own build config under `<workspace>/config/build/`:

- **`no_run.yaml`** — flat list of script/notebook patterns to skip during execution
- **`env_vars.yaml`** — defaults + per-pattern overrides for environment variables
- **`copy_files.yaml`** — flat list of script paths to copy as-is to `notebooks/` instead of converting
- **`visualise_notebooks.yaml`** — flat list of notebook stems to run when `--visualise` flag is used

`autobuild/config/` retains keyed-dict copies of `no_run.yaml`, `copy_files.yaml`, and `visualise_notebooks.yaml` as fallbacks for legacy workspaces (HowTo*, BSc_Galaxies_Project) that have not been migrated yet. The 6 main workspaces (autofit/autogalaxy/autolens and their `_test` variants) own their own configs and do not consult these fallbacks.

### Environment Variables

- `BUILD_PYTHON_INTERPRETER` — Python interpreter to use for script execution (defaults to `python3`)
- `PYAUTO_TEST_MODE` — Set to `1` for workspace runs, `0` for `*_test` workspace runs
- `PYAUTO_SMALL_DATASETS` — Set to `1` for workspace runs (caps grids to 15x15), not set for `*_test` runs
- `PYAUTO_FAST_PLOTS` — Set to `1` for workspace runs (skips `tight_layout()` in subplots and critical curve/caustic overlays in plots), not set for `*_test` runs
- `JAX_ENABLE_X64` — Set to `True` during CI runs

### GitHub Actions Workflow

The workflow (`release.yml`) is manually dispatched with inputs:
- `minor_version` — appended to date-based version (format: `YYYY.M.D.minor`)
- `rehearsal` — the one mode switch (default `false` = full real release). When `true`, it is
  TestPyPI-only rehearsal mode: build every package from source, publish to TestPyPI, emit the
  resolved version as the `testpypi-rehearsal-version` artifact, then STOP (no PyPI upload, no git
  tag, no notebook/version commits, no Colab bumps). This is the mode the Heart/Brain
  release-validation gate dispatches so it can install and validate the built wheels.

(The legacy `skip_scripts` / `skip_notebooks` / `skip_release` force-through knobs and the
`update_notebook_visualisations` path were removed with the Heart/Build split — Build is a pure
executor with no ad-hoc skip levers or inline notebook-visualisation job. "Build without
releasing" is now exactly what `rehearsal` mode is for.)

`release.yml` is a **pure executor**: it builds, tests-the-install, publishes to PyPI, and commits generated notebooks + version pins to the workspaces. Workspace-integration validation (the old `find_scripts` / `generate_notebooks` / `run_scripts` / `run_notebooks` / `analyze_results` jobs) moved to **PyAutoHeart**'s `workspace-validation.yml`; release readiness is gated upstream by the PyAutoBrain release agent via `pyauto-heart readiness` before this workflow is dispatched. The `script_matrix.py` / `run_python.py` / `run.py` / `aggregate_results.py` primitives remain here and are checked out + reused by the Heart workflow.
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
and any other agent. The "Initial commit — fresh start for AI workflow" pattern
that appeared independently on origin and local for three workspace repos is
exactly what this rule prevents — it costs ~40 commits of redundant local work
every time it happens.
