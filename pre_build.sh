#!/bin/bash
# Pre-build script: run black + generate notebooks + git commit & push
# for all workspace repos, then commit & push PyAutoBuild, then trigger
# the GitHub Actions release workflow.
#
# Usage: bash pre_build.sh [minor_version] [skip_release]
#   minor_version  Minor version suffix (default: 1)
#   skip_release   Whether to skip the release stage, true or false (default: false)

set -e

MINOR_VERSION="${1:-1}"
SKIP_RELEASE="${2:-false}"
PYAUTOBASE="/mnt/c/Users/Jammy/Code/PyAutoLabs"
AUTOBUILD="$PYAUTOBASE/PyAutoBuild/autobuild"
PYTHONPATH_EXTRA="$AUTOBUILD"

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
    black .

    if [ "$generate" = "true" ]; then
        echo "  Running generate.py ($project)..."
        PYTHONPATH="$PYTHONPATH_EXTRA" python "$AUTOBUILD/generate.py" "$project"
    fi

    echo "  Staging safe directories..."
    git add -f dataset/
    for d in config notebooks scripts; do
        [ -d "$d" ] && git add "$d/"
    done
    if [ "$slam" = "true" ] && [ -d "slam_pipeline" ]; then
        git add slam_pipeline/
    fi
    # Stage root-level recognised files only (no output/, output_model/, or stray .fits)
    git add -- *.py *.md *.txt *.cfg *.ini *.toml *.yml *.yaml LICENSE* requirements* setup* 2>/dev/null || true

    echo "  Committing and pushing..."
    if git diff --cached --quiet; then
        echo "  No changes to commit."
    else
        git commit -m "pre build"
        git push
    fi
}

run_workspace "autofit_workspace"                    "autofit"
run_workspace "autogalaxy_workspace"                 "autogalaxy"
run_workspace "autolens_workspace"                   "autolens"     true  true
run_workspace "autofit_workspace_test"               "autofit"      false
run_workspace "autolens_workspace_test"              "autolens"     false
run_workspace "euclid_strong_lens_modeling_pipeline" ""             false

# Commit and push PyAutoBuild itself
echo ""
echo "=== PyAutoBuild ==="
cd "$PYAUTOBASE/PyAutoBuild"
git add -A
if git diff --cached --quiet; then
    echo "  No changes to commit."
else
    git commit -m "pre build"
    git push
fi

# Trigger the GitHub Actions release workflow
echo ""
echo "=== Triggering release workflow (minor_version=$MINOR_VERSION) ==="
gh workflow run release.yml \
    --repo PyAutoLabs/PyAutoBuild \
    --field minor_version="$MINOR_VERSION" \
    --field skip_release="$SKIP_RELEASE"

echo ""
echo "Pre-build complete. Workflow dispatched."
echo "Track it at: https://github.com/PyAutoLabs/PyAutoBuild/actions"
