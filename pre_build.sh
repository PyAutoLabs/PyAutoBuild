#!/bin/bash
# Pre-build script: run black + generate notebooks + git commit & push
# for all workspace repos, then commit & push PyAutoBuild, then trigger
# the GitHub Actions release workflow.
#
# Usage: bash pre_build.sh [minor_version] [skip_release]
#   minor_version  Minor version suffix (default: 1)
#   skip_release   Whether to skip the release stage, true or false (default: false)
#
# Optional env vars (forwarded as workflow_dispatch inputs when set):
#   SKIP_SCRIPTS    true|false — skip run_scripts matrix in release.yml
#   SKIP_NOTEBOOKS  true|false — skip run_notebooks matrix in release.yml

set -e

MINOR_VERSION="${1:-1}"
SKIP_RELEASE="${2:-false}"
SKIP_SCRIPTS="${SKIP_SCRIPTS:-}"
SKIP_NOTEBOOKS="${SKIP_NOTEBOOKS:-}"

# Resolve PYAUTOBASE from this script's location (same idiom as bin/autobuild)
# so pre_build.sh works from any checkout — Linux, WSL, anywhere.
SELF="$(readlink -f "$0")"
PYAUTOBASE="$(cd "$(dirname "$SELF")/.." && pwd)"
AUTOBUILD="$PYAUTOBASE/PyAutoBuild/autobuild"
PYTHONPATH_EXTRA="$AUTOBUILD"

# YYYY.M.D.<minor> — used to bump README version pins. %-m / %-d strip
# leading zeroes so the tag matches the canonical pattern (e.g. 2026.4.5.1).
VERSION="$(date +%Y.%-m.%-d).$MINOR_VERSION"

# Ensure the canonical `pending-release` label exists with the right config
# across every release-window repo. Idempotent — no-ops when nothing drifted.
if command -v gh >/dev/null 2>&1; then
    echo ""
    echo "=== Ensuring pending-release labels ==="
    bash "$PYAUTOBASE/admin_jammy/software/ensure_workspace_labels.sh"
fi

run_workspace() {
    local repo="$1"
    local project="$2"
    local generate="${3:-true}"
    local slam="${4:-false}"
    local readme_pkg="${5:-}"
    local dir="$PYAUTOBASE/$repo"

    echo ""
    echo "=== $repo ==="

    cd "$dir"

    echo "  Running black..."
    black .

    if [ -n "$readme_pkg" ]; then
        echo "  Bumping README version → $readme_pkg v$VERSION..."
        sed -i "s/$readme_pkg v[0-9]\{4\}\.[0-9]*\.[0-9]*\.[0-9]*/$readme_pkg v$VERSION/g" \
            README.rst README.md 2>/dev/null || true
    fi

    if [ "$generate" = "true" ]; then
        echo "  Running generate.py ($project)..."
        PYTHONPATH="$PYTHONPATH_EXTRA" python "$AUTOBUILD/generate.py" "$project"
    fi

    echo "  Staging safe directories..."
    [ -d dataset ] && git add -f dataset/
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

# Positional args: repo project [generate=true] [slam=false] [readme_pkg=""]
# readme_pkg: when non-empty, the README's "<pkg> vYYYY.M.D.B" pin is bumped to
# the new VERSION. Empty for workspaces with no README version pin.
run_workspace "autofit_workspace"                    "autofit"      true   false  PyAutoFit
run_workspace "autogalaxy_workspace"                 "autogalaxy"   true   false  PyAutoGalaxy
run_workspace "autolens_workspace"                   "autolens"     true   true   PyAutoLens
run_workspace "autofit_workspace_test"               "autofit"      false  false  PyAutoFit
run_workspace "autogalaxy_workspace_test"            "autogalaxy"   false  false  PyAutoGalaxy
run_workspace "autolens_workspace_test"              "autolens"     false  false  PyAutoLens
run_workspace "euclid_strong_lens_modeling_pipeline" ""             false  false  ""
run_workspace "HowToGalaxy"                          "howtogalaxy"  true   false  PyAutoGalaxy
run_workspace "HowToLens"                            "howtolens"    true   false  PyAutoLens
run_workspace "HowToFit"                             "howtofit"     true   false  PyAutoFit

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

# Block release if any workspace's version.txt is ahead of its installed
# library — every welcome.py / start_here.py run would otherwise crash with
# WorkspaceVersionMismatchError until the release dispatch landed.
echo ""
echo "=== Verifying workspace versions ==="
bash "$PYAUTOBASE/PyAutoBuild/verify_workspace_versions.sh"

# Trigger the GitHub Actions release workflow
echo ""
echo "=== Triggering release workflow (minor_version=$MINOR_VERSION) ==="
EXTRA_FIELDS=()
if [ -n "$SKIP_SCRIPTS" ]; then
    EXTRA_FIELDS+=(--field "skip_scripts=$SKIP_SCRIPTS")
fi
if [ -n "$SKIP_NOTEBOOKS" ]; then
    EXTRA_FIELDS+=(--field "skip_notebooks=$SKIP_NOTEBOOKS")
fi
gh workflow run release.yml \
    --repo PyAutoLabs/PyAutoBuild \
    --field minor_version="$MINOR_VERSION" \
    --field skip_release="$SKIP_RELEASE" \
    "${EXTRA_FIELDS[@]}"

echo ""
echo "Pre-build complete. Workflow dispatched."
echo "Track it at: https://github.com/PyAutoLabs/PyAutoBuild/actions"
