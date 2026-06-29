# Pre-Build: Format, Generate, Push, Dispatch

Prepare all workspace repositories for a release build, then dispatch the GitHub Actions release workflow. This skill is a thin wrapper around `PyAutoBuild/bin/autobuild pre_build`, mirroring the pattern used by `/verify_install`.

A **PyAutoBuild (Hands)** skill — Build is the release/packaging executor, and
this is a **release-execution** entry point (format → generate → push →
dispatch). It is the one skill class PyAutoBuild's `skills/` root hosts; Build
owns **no** dev-workflow skills (`ship_*` live in PyAutoBrain and only *call*
this release step). Readiness is gated upstream by Heart before a release is
dispatched.

## Steps

### 1. Validate environment

Check that all required repositories exist under the workspace root:
- `autofit_workspace`
- `autogalaxy_workspace`
- `autolens_workspace`
- `autofit_workspace_test`
- `autogalaxy_workspace_test`
- `autolens_workspace_test`
- `euclid_strong_lens_modeling_pipeline`
- `HowToGalaxy`
- `HowToLens`
- `HowToFit`
- `PyAutoBuild`

For each, verify:
```bash
git -C <repo> branch --show-current
git -C <repo> status --short
```

All workspaces must be on `main`. If any are on a feature branch or have uncommitted changes, **stop and warn the user** — the pre-build expects clean `main` branches.

Then ask the user for the minor version number (default: 1).

### 2. Run `autobuild pre_build`

Invoke the bash entry point directly:

```bash
bash $HOME/Code/PyAutoLabs/PyAutoBuild/bin/autobuild pre_build <minor_version>
```

The script handles every mechanical step of the pre-build flow:

1. Ensures the canonical `pending-release` label exists on each release-window repo.
2. For every workspace, runs `black .`, bumps the README version pin (`<Package> vYYYY.M.D.<minor>`) where applicable, runs `generate.py` for projects with a notebook target, and stages only the safe directories (`config/`, `notebooks/`, `scripts/`, `dataset/`, plus `slam_pipeline/` for `autolens_workspace`).
3. Commits and pushes each workspace (skipping if no changes are staged).
4. Commits and pushes PyAutoBuild itself.
5. Dispatches `gh workflow run release.yml --repo PyAutoLabs/PyAutoBuild --field minor_version=<N>`.

Release-readiness — including the version-skew check that used to run here
(`verify_workspace_versions.sh`) — is gated **upstream by PyAutoHeart**
(`pyauto-heart readiness`) before `pre_build` is invoked, not by this step. Build
is a pure executor.

If the script exits non-zero, surface the failure to the user verbatim and stop. Do not attempt to retry or repair — the script's preconditions (`set -e`) ensure that any non-zero exit reflects a real problem (lint failure, push rejected, workflow dispatch error).

### 3. Summary

When the script completes successfully, fetch and display the dispatched run URL:

```bash
gh run list --workflow=release.yml --repo PyAutoLabs/PyAutoBuild --limit 1 --json url --jq '.[0].url'
```

Then display:
```
Pre-Build Complete
==================
Minor version: <N>
Workflow dispatched: <URL>

The release workflow is now running. Use /review_release tomorrow
to assess the results.
```

## Notes

- The same operation is callable from the shell as `autobuild pre_build <minor>` (or `autobuild-help pre_build` for documentation). Use this skill when you want the Claude validation + summary wrapper; use the bash CLI when you just want to fire off the build.
- README version-bump is now handled inside `pre_build.sh` (it used to live only in this skill).
