# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

PyAutoBuild is a CI/CD build server for the PyAuto software family (PyAutoConf, PyAutoFit, PyAutoArray, PyAutoGalaxy, PyAutoLens). It automates:
1. Building and releasing packages to TestPyPI, then PyPI
2. Running workspace Python scripts (integration tests)
3. Converting Python scripts to Jupyter notebooks and executing them
4. Updating workspace `release` branches with generated notebooks

The pipeline is triggered via GitHub Actions (`release.yml`) and is manually dispatched with configurable options.

## Pre-Build Steps

Before triggering a build, run:

```bash
bash /mnt/c/Users/Jammy/Code/PyAutoJAX/PyAutoBuild/pre_build.sh [minor_version]
# minor_version defaults to 1
```

This script does the following for each repo:

| Repo | black | generate.py | commit & push |
|------|-------|-------------|---------------|
| `autofit_workspace` | yes | yes (`autofit`) | yes |
| `autogalaxy_workspace` | yes | yes (`autogalaxy`) | yes |
| `autolens_workspace` | yes | yes (`autolens`) | yes |
| `autofit_workspace_test` | yes | no | yes |
| `autolens_workspace_test` | yes | no | yes |

`generate.py` is run from the workspace root with `PYTHONPATH` pointing at `PyAutoBuild/autobuild/`. The `dataset/` folder in each repo is force-added before committing. After all workspaces are done, PyAutoBuild itself is committed and pushed, then `gh workflow run release.yml` dispatches the GitHub Actions release.

## Running Tests

```bash
# Run all tests
pytest

# Run a single test
pytest tests/test_files_to_run.py::test_script_order
```

## Key Scripts

All scripts in `autobuild/` are run from within a checked-out workspace directory (not from this repo root). They rely on `PYTHONPATH` including the PyAutoBuild directory.

- **`run_python.py <project> <directory>`** — Executes Python scripts in a workspace folder, skipping files listed in `config/no_run.yaml`
- **`run.py <project> <directory> [--visualise]`** — Executes Jupyter notebooks in a workspace folder, skipping files in `config/no_run.yaml`
- **`generate.py <project>`** — Converts Python scripts in `scripts/` to `.ipynb` notebooks in `notebooks/`, run from within the workspace root
- **`script_matrix.py <project1> [project2 ...]`** — Outputs a JSON matrix of `{name, directory}` pairs for GitHub Actions matrix strategy
- **`tag_and_merge.py --version <version>`** — Tags library repos for release

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

### Config Files (`autobuild/config/`)

- **`no_run.yaml`** — Per-project lists of script/notebook stems to skip during execution
- **`copy_files.yaml`** — Per-project lists of files to copy as-is to `notebooks/` instead of converting
- **`visualise_notebooks.yaml`** — Per-project lists of notebooks to run when `--visualise` flag is used
- **`notebooks_remove.yaml`** — Notebooks to remove

### Environment Variables

- `BUILD_PYTHON_INTERPRETER` — Python interpreter to use for script execution (defaults to `python3`)
- `PYAUTOFIT_TEST_MODE` — Set to `1` for workspace runs, `0` for `*_test` workspace runs
- `JAX_ENABLE_X64` — Set to `True` during CI runs

### GitHub Actions Workflow

The workflow (`release.yml`) is manually dispatched with inputs:
- `minor_version` — appended to date-based version (format: `YYYY.M.D.minor`)
- `skip_scripts` / `skip_notebooks` / `skip_release` — flags to skip pipeline stages
- `update_notebook_visualisations` — runs notebooks with `--visualise` and pushes to `release` branch

The `find_scripts` job uses `script_matrix.py` to dynamically generate the matrix for parallel `run_scripts` and `run_notebooks` jobs.
