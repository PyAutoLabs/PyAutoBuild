#!/bin/bash
# Pre-build script: run black + generate notebooks + git commit & push
# for all workspace repos, then commit & push PyAutoHands, then trigger
# the GitHub Actions release workflow.
#
# Usage: bash pre_build.sh [minor_version]
#   minor_version  Minor version suffix (default: 1)
#
# pre_build always dispatches a full real release. To build + publish to
# TestPyPI without releasing (e.g. the Heart/Brain validation gate), dispatch
# release.yml directly with rehearsal=true instead.

set -e

MINOR_VERSION="${1:-1}"

# Resolve PYAUTOBASE from this script's location (same idiom as bin/autobuild)
# so pre_build.sh works from any checkout — Linux, WSL, anywhere.
SELF="$(readlink -f "$0")"
PYAUTOBASE="$(cd "$(dirname "$SELF")/.." && pwd)"
AUTOBUILD="$PYAUTOBASE/PyAutoHands/autobuild"
PYTHONPATH_EXTRA="$AUTOBUILD"

# YYYY.M.D.<minor> — used to bump README version pins. %-m / %-d strip
# leading zeroes so the tag matches the canonical pattern (e.g. 2026.4.5.1).
VERSION="$(date +%Y.%-m.%-d).$MINOR_VERSION"

# Ensure the canonical `pending-release` label exists with the right config
# across every release-window repo. Idempotent — no-ops when nothing drifted.
if command -v gh >/dev/null 2>&1; then
    echo ""
    echo "=== Ensuring pending-release labels ==="
    bash "$PYAUTOBASE/PyAutoBrain/bin/ensure_workspace_labels.sh"
fi

run_workspace() {
    local repo="$1"
    local project="$2"
    local generate="${3:-true}"
    local slam="${4:-false}"
    local dir="$PYAUTOBASE/$repo"

    echo ""
    echo "=== $repo ==="

    cd "$dir"

    echo "  Running black..."
    # Format only the dirs this script stages — black'ing "." reformatted files
    # no staging rule covered (13 files across HowTo*/assistant), leaving them
    # perpetually dirty-local on every release (#156).
    for d in scripts slam_pipeline; do
        if [ -d "$d" ]; then black "$d/"; fi
    done

    if [ "$generate" = "true" ]; then
        echo "  Running generate.py ($project)..."
        PYTHONPATH="$PYTHONPATH_EXTRA" python "$AUTOBUILD/generate.py" "$project"
    fi

    echo "  Checking dataset allowlist (PyAutoBuild#126 leg 4)..."
    python3 "$AUTOBUILD/check_dataset_allowlist.py" || {
        echo "  ABORT: tracked dataset/ contains non-allowlisted simulated data." >&2
        exit 1
    }

    echo "  Staging what this run produced..."
    # Stage only what the run itself modifies: black'd scripts and the
    # generated notebooks. The former dataset/ and config/ adds staged nothing
    # the run produced — they swept pre-existing human-uncommitted work into
    # release commits, which is the mechanism that leaked simulated datasets
    # (#126). Releases require clean mains (Heart gates on it); human work is
    # committed by humans. See docs/pre_build_failure_audit.md §3/§6 (#156).
    for d in notebooks scripts; do
        if [ -d "$d" ]; then git add "$d/"; fi
    done
    if [ "$slam" = "true" ] && [ -d "slam_pipeline" ]; then
        git add slam_pipeline/
    fi
    # Root-level artifacts (llms-full.txt, workspace_index.json, README Colab
    # URLs) are produced and committed by release.yml's release_workspaces job
    # on the runner — pre_build deliberately does not stage root files. The
    # former glob line here was a measured no-op in all 13 repos (#156).

    echo "  Committing and pushing..."
    if git diff --cached --quiet; then
        echo "  No changes to commit."
    else
        git commit -m "pre build"
        git push
    fi
}

# Positional args: repo project [generate=true] [slam=false]
# The repo names are checked against PyAutoMind/repos.yaml (the body map) by
# `repos_sync.py --check`; the flags are Build policy and live only here.
# (The former readme_pkg arg / README version bump was deleted per the audit in
# docs/pre_build_failure_audit.md: its sed edit was never staged, the runner
# side was removed under #120, and the pins it targeted are owned by Phase 4 of
# the build-chain campaign — PyAutoBuild#155/#156.)
run_workspace "autofit_workspace"                    "autofit"      true   false
run_workspace "autogalaxy_workspace"                 "autogalaxy"   true   false
run_workspace "autolens_workspace"                   "autolens"     true   true
run_workspace "autofit_workspace_test"               "autofit"      false  false
run_workspace "autogalaxy_workspace_test"            "autogalaxy"   false  false
run_workspace "autolens_workspace_test"              "autolens"     false  false
run_workspace "euclid_strong_lens_modeling_pipeline" ""             false  false
run_workspace "HowToGalaxy"                          "howtogalaxy"  true   false
run_workspace "HowToLens"                            "howtolens"    true   false
run_workspace "HowToFit"                             "howtofit"     true   false
run_workspace "autofit_workspace_developer"          ""             false  false
run_workspace "autolens_workspace_developer"         ""             false  false
# The AI assistant repo. No notebook generation; release.yml's
# release_workspaces job stamps its workspace version and regenerates
# wiki/core/api_audit_baseline.json against the released wheels.
run_workspace "autolens_assistant"                   "autolens"     false  false

# Commit and push PyAutoHands itself
echo ""
echo "=== PyAutoHands ==="
cd "$PYAUTOBASE/PyAutoHands"
git add -A
if git diff --cached --quiet; then
    echo "  No changes to commit."
else
    git commit -m "pre build"
    git push
fi

# Release readiness (version skew, including the version.txt-ahead crash that
# used to be checked here) is now Heart's job, not Build's: PyAutoHands is a
# pure executor. The release agent gates on `pyauto-heart readiness` before
# invoking this script; a human running pre_build directly is trusted to have
# checked `pyauto-heart readiness` themselves.

# Trigger the GitHub Actions release workflow
echo ""
echo "=== Triggering release workflow (minor_version=$MINOR_VERSION) ==="
gh workflow run release.yml \
    --repo PyAutoLabs/PyAutoHands \
    --field minor_version="$MINOR_VERSION"

echo ""
echo "Pre-build complete. Workflow dispatched."
echo "Track it at: https://github.com/PyAutoLabs/PyAutoHands/actions"
