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
- `autofit_workspace_developer`
- `autolens_workspace_developer`
- `autolens_assistant`
- `PyAutoBrain`
- `PyAutoBuild`

For each, verify:
```bash
git -C <repo> branch --show-current
git -C <repo> status --short
```

Every repository that pre-build mutates must be on clean `main`. `PyAutoBrain`
is a read-only dependency for `bin/ensure_workspace_labels.sh`; verify that
script exists, but do not require the support repo to be clean. If a mutated
repo is on a feature branch or has uncommitted changes, **stop and warn the
user**.

Then ask the user for the minor version number (default: 1).

### 2. Run `autobuild pre_build`

Invoke the bash entry point directly:

```bash
bash $HOME/Code/PyAutoLabs/PyAutoBuild/bin/autobuild pre_build <minor_version>
```

The script handles every mechanical step of the pre-build flow:

1. Ensures the canonical `pending-release` label exists on each release-window repo.
2. For every workspace, runs black on the staged dirs (`scripts/`, `slam_pipeline/`), runs `generate.py` for projects with a notebook target, and stages only what the run itself produced (`notebooks/`, `scripts/`, plus `slam_pipeline/` for `autolens_workspace`). It does not stage `dataset/` or `config/` — nothing in the run modifies them, and sweeping pre-existing human work into release commits was the #126 leak mechanism. Root-level artifacts and README Colab URLs are committed by `release.yml` on the runner, not here.
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

The release workflow is now running. Use the `review-release` skill
(`/review_release` in Claude) tomorrow to assess the results.
```

## Notes

- The same operation is callable from the shell as `autobuild pre_build <minor>` (or `autobuild-help pre_build` for documentation). Use this skill when you want the agent validation and summary wrapper; use the bash CLI when you just want to fire off the build.
- There is no README version-bump step: the audit (`docs/pre_build_failure_audit.md`, #156) found the old local sed's output was never staged and the runner-side step was removed under #120 — README pin ownership is a Phase 4 decision of the build-chain campaign (#155).
