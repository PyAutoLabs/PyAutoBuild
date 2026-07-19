# PyAutoHands — internals

Operational detail for working **inside** this repo: the `autobuild` CLI, the
pre-build steps, workspace folder structure, config files, and `release.yml`.
What PyAutoHands *is* and the Brain/Heart/Build boundary live in
[`AGENTS.md`](../AGENTS.md) — read that first; read this only when changing the
build pipeline itself.

## What the pipeline automates

PyAutoHands runs **no** release-readiness checks of its own (that is
PyAutoHeart's job). It automates:
1. Building and releasing packages to TestPyPI, then PyPI
2. Running workspace Python scripts (integration tests)
3. Converting Python scripts to Jupyter notebooks and executing them
4. Committing generated notebooks to workspace `main` branches and tagging each workspace with a version matching the released library

The pipeline is triggered via GitHub Actions (`release.yml`) and is manually dispatched with configurable options. Release-readiness gating happens upstream: the PyAutoBrain release agent calls `pyauto-heart readiness` and only dispatches `release.yml` on a green verdict.

## Bash CLI

Every operation in this repo is invokable from the shell via the `autobuild` dispatcher at `bin/autobuild`. List subcommands with `autobuild help`; print the docstring for one with `autobuild help <subcommand>` (or `autobuild <subcommand> --help`).

Recommended alias for `~/.bashrc`:

```bash
alias autobuild-help='$HOME/Code/PyAutoLabs/PyAutoHands/bin/autobuild help'
```

The dispatcher routes to the underlying bash script directly, or to the Python tool with `PYTHONPATH` already set so the internal `build_util` / `result_collector` / `env_config` imports resolve. The same operations remain callable as Claude skills (`/pre_build`, `/verify_install`, `/review_release`); use the skill when you want the validation + summary wrapper, the CLI when you just want to fire the underlying tool.

## Pre-Build Steps

Before triggering a build, run:

```bash
bash $HOME/Code/PyAutoLabs/PyAutoHands/bin/autobuild pre_build [minor_version]
# minor_version defaults to 1
# (equivalent to: bash $HOME/Code/PyAutoLabs/PyAutoHands/pre_build.sh [minor_version])
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

Before the per-repo loop, `pre_build.sh` invokes `PyAutoBrain/bin/ensure_workspace_labels.sh` to assert the canonical `pending-release` label across every release-window repo (idempotent — a no-op when nothing has drifted).

Release-readiness checking is **not** Build's job — PyAutoHands is a pure executor. The version-skew check that used to live here (`verify_workspace_versions.sh`, a fail-fast guard against a workspace pinned ahead of its installed library, or a `config/general.yaml` ↔ `version.txt` disagreement) now lives in **PyAutoHeart** as the `version_skew` check feeding `pyauto-heart readiness`. The PyAutoBrain release agent gates on `pyauto-heart readiness` before invoking `pre_build`; a human running `pre_build` directly is trusted to have checked readiness first. See PyAutoHeart for the resolution precedence (`config/general.yaml:version.workspace_version`, then `version.txt`) — mirroring `autoconf.workspace.check_version`. Since PyAutoBuild#120, releases no longer write workspace version pins or commit `__init__.py` stamps back to library mains (wheels are stamped at build time; tags are the release anchor): the runtime check enforces a compatibility **floor** (`version.minimum_library_version`, bumped deliberately — PyAutoNerves#118), and Heart's `version_skew` check needs a follow-up rework to compare floors against release tags rather than stamp-vs-pin.

`generate.py` is run from the workspace root with `PYTHONPATH` pointing at `PyAutoHands/autobuild/`. Only specific safe directories are committed — never `output/`, `output_model/`, or run-generated artefacts. After all workspaces are done, PyAutoHands itself is committed and pushed, then `gh workflow run release.yml` dispatches the GitHub Actions release.

## Workspace Folder Structure

Each workspace repo (`autofit_workspace`, `autogalaxy_workspace`, `autolens_workspace`, their `_test` variants, and the lecture repos `HowToGalaxy`/`HowToLens`) has the following expected structure. **Only these paths should ever be committed.**

| Folder / file | autofit | autogalaxy | autolens | Notes |
|---|---|---|---|---|
| `config/` | yes | yes | yes | PyAutoNerves config files |
| `dataset/` | yes | yes | yes | Allowlisted real observational data only; simulated datasets are never committed (#126/#150) |
| `notebooks/` | yes | yes | yes | Generated from `scripts/` by `generate.py` |
| `scripts/` | yes | yes | yes | Source Python scripts |
| `slam_pipeline/` | no | no | yes | autolens only |
| `output/` | — | — | — | **Always empty** — kept under git with a `.gitignore` only |
| Root-level files | yes | yes | yes | `README.md`, `llms-full.txt`, `workspace_index.json`, `requirements.txt`, `LICENSE*` — committed by `release.yml` on the runner, not by `pre_build.sh` (#156) |

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

All scripts in `autobuild/` are run from within a checked-out workspace directory (not from this repo root). They rely on `PYTHONPATH` including the PyAutoHands directory.

- **`run_python.py <project> <directory>`** — Executes Python scripts in a workspace folder, skipping files listed in `config/no_run.yaml`
- **`run.py <project> <directory> [--visualise]`** — Executes Jupyter notebooks in a workspace folder, skipping files in `config/no_run.yaml`
- **`generate.py <project>`** — Converts Python scripts in `scripts/` to `.ipynb` notebooks in `notebooks/`, run from within the workspace root
- **`generate_markdown.py <project> [--only <substring>]`** — Renders the curated scripts listed in the workspace's `config/build/markdown_examples.yaml` to **executed** markdown pages with output images under `markdown/`, plus an index, committed so examples are readable on GitHub. Manual / at-release only, never per-commit; refuses `PYAUTO_TEST_MODE` (truncated searches make wrong images — model-fit reruns instead resume from the completed `output/` cache); never renders `features/` scripts; restores tracked files a script modifies (e.g. simulators rewriting `dataset/`). Rules and rationale in the module docstring.
- **`script_matrix.py <project1> [project2 ...]`** — Outputs a JSON matrix of `{name, directory}` pairs for GitHub Actions matrix strategy
- **`tag_and_merge.sh --version <version>`** — Commits pending changes and tags library repos (PyAutoNerves, PyAutoFit, PyAutoArray, PyAutoGalaxy, PyAutoLens) for release
- **`url_check`** — URL hygiene moved to PyAutoHeart (Heart owns all health checking). `autobuild url_check` is now a thin shim to `pyauto-heart url_check`; the ecosystem-wide sweep runs from PyAutoHeart's central `url-check.yml` workflow (replacing the old per-repo `url_check.yml` workflows). The runnable scripts live at `PyAutoHeart/heart/checks/url_check*.{sh,py}`.
- **`bump_colab_urls.sh <new-tag>`** — Rewrites every `colab.research.google.com/github/PyAutoLabs/<repo>/blob/<old-tag>/...` URL in cwd to use `<new-tag>`, where `<repo>` is one of `autofit_workspace`, `autogalaxy_workspace`, `autolens_workspace`, `HowToFit`, `HowToGalaxy`, `HowToLens`. Called by the `release_workspaces` and `bump_library_colab_urls` jobs in `release.yml` so README/docs Colab links always pin to the just-released tag. Idempotent; skips URLs not in canonical PyAutoLabs/date-tagged form.

## Architecture

### Script-to-Notebook Conversion Pipeline

`generate.py` → `generate_autofit.py` + `build_util.py`:
1. `add_notebook_quotes.py` transforms triple-quoted docstrings into `# %%` cell markers in a temp `.py` file
2. `ipynb-py-convert` converts the temp file to `.ipynb`
3. `build_util.uncomment_jupyter_magic()` restores commented-out Jupyter magic commands (e.g. `# %matplotlib` → `%matplotlib`)
4. `build_util.inject_colab_setup()` prepends the standard Google Colab setup cell pair (see "Google Colab architecture" below)
5. Generated notebooks are `git add -f`ed directly

### Google Colab architecture

Every published notebook must be runnable on Google Colab with zero local
installation. Four pieces, spread over three organs plus PyAutoNerves:

1. **Runtime bootstrap** — `PyAutoNerves/autoconf/setup_colab.py`. A `_PROJECTS`
   registry (`autofit`, `autogalaxy`, `autolens`, `howtofit`, `howtogalaxy`,
   `howtolens`) maps each notebook repo to its package stack, workspace repo
   and Colab directory. `setup_colab.setup("<project>")` is a no-op outside
   Colab; on Colab it pip-installs the stack (`--no-deps` — Colab ships the
   scientific base), shallow-clones the workspace at the tag matching the
   installed release (default branch as fallback) and points autoconf's
   config/output paths at it.
2. **Generation-time injection** — `build_util.inject_colab_setup(notebook,
   project)`, called by `generate.py` / `generate_autofit.py` after every
   py→ipynb conversion. It prepends a markdown explainer + code cell calling
   `setup_colab.setup("<project>")`, immediately after the notebook's title
   cell. Notebooks whose script already hand-writes a `setup_colab` call are
   left untouched. `build_util.COLAB_PROJECTS` must stay in sync with the
   PyAutoNerves registry; an unknown project fails generation loudly. Coverage
   is therefore guaranteed by construction — every generated notebook is
   Colab-ready, with no per-script maintenance.
3. **Release maintenance** — `bump_colab_urls.sh` (above) re-pins every
   canonical Colab URL in READMEs/docs/notebooks to the just-released tag,
   from the `release_workspaces` and `bump_library_colab_urls` jobs. Only
   date-tagged `PyAutoLabs/<repo>` URLs are bumped — unpinned or wrong-owner
   URLs are invisible to it, which is why Heart forbids them (next item).
4. **Monitoring** — PyAutoHeart's central `url-check.yml` (weekly): the
   offline guard (`heart/checks/url_check.sh`) forbids Colab URL forms that
   rot (Binder, `Jammy2211` owner, `/blob/release/`, unpinned `/blob/main/`,
   chapter paths pointing at workspace repos instead of the HowTo repos); the
   live audit (`url_check_live.py`) converts Colab URLs to raw-GitHub form and
   404-checks that each linked notebook actually exists at its pinned tag.

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

`release.yml` is a **pure executor**: it builds, tests-the-install, publishes to PyPI, tags every library and workspace, and commits generated notebooks + Colab URL bumps to the workspaces (version stamps are build-tree-only since #120 — no `__init__.py` commit-backs to library mains, no workspace version pins). Workspace-integration validation (the old `find_scripts` / `generate_notebooks` / `run_scripts` / `run_notebooks` / `analyze_results` jobs) moved to **PyAutoHeart**'s `workspace-validation.yml`; release readiness is gated upstream by the PyAutoBrain release agent via `pyauto-heart readiness` before this workflow is dispatched. The `script_matrix.py` / `run_python.py` / `run.py` / `aggregate_results.py` primitives remain here and are checked out + reused by the Heart workflow.
The never-rewrite-history rules live in [`AGENTS.md`](../AGENTS.md) and apply
here as everywhere.
