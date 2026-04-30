#!/usr/bin/env bash
# verify_workspace_versions.sh — fail fast if any workspace's version.txt is
# AHEAD of the currently-installed library version.
#
# Usage: bash PyAutoBuild/verify_workspace_versions.sh
#
# Background: the bootstrap commit for a new workspace-style repo (HowToLens,
# 2026-04-21) set version.txt to today's date as an aspirational tag. Until
# the next release dispatch wrote a real version.txt, every welcome.py run
# crashed with WorkspaceVersionMismatchError. This check blocks pre_build.sh
# from dispatching a release that would be invalidated by such a mismatch.
#
# Compares each of the 7 workspaces with a version.txt (3 main + 3 HowTo +
# euclid_pipeline) against its installed library version, parsed as a
# YYYY.M.D.B 4-tuple of ints. Exits 1 if any workspace.version > library.version.
#
# Workspace → library mapping mirrors the release_workspaces matrix in
# .github/workflows/release.yml.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYAUTOBASE="$(cd "$SCRIPT_DIR/.." && pwd)"

# workspace_dir|python_package
WORKSPACES=(
    "autofit_workspace|autofit"
    "autogalaxy_workspace|autogalaxy"
    "autolens_workspace|autolens"
    "HowToFit|autofit"
    "HowToGalaxy|autogalaxy"
    "HowToLens|autolens"
    "euclid_strong_lens_modeling_pipeline|autolens"
)

# Compare two YYYY.M.D.B versions. Echoes AHEAD / BEHIND / MATCH / BAD.
compare_versions() {
    local v1="$1" v2="$2"
    local IFS=.
    # shellcheck disable=SC2206
    local a=($v1) b=($v2)
    if [ "${#a[@]}" -ne 4 ] || [ "${#b[@]}" -ne 4 ]; then
        echo "BAD"
        return
    fi
    local i
    for i in 0 1 2 3; do
        if ! [[ "${a[$i]}" =~ ^[0-9]+$ && "${b[$i]}" =~ ^[0-9]+$ ]]; then
            echo "BAD"
            return
        fi
        if [ "${a[$i]}" -gt "${b[$i]}" ]; then echo "AHEAD";  return; fi
        if [ "${a[$i]}" -lt "${b[$i]}" ]; then echo "BEHIND"; return; fi
    done
    echo "MATCH"
}

failed=0

for entry in "${WORKSPACES[@]}"; do
    ws="${entry%%|*}"
    pkg="${entry#*|}"
    version_file="$PYAUTOBASE/$ws/version.txt"

    if [ ! -f "$version_file" ]; then
        printf "  %-45s SKIP (no version.txt)\n" "$ws"
        continue
    fi

    ws_version=$(tr -d '[:space:]' < "$version_file")
    if [ -z "$ws_version" ]; then
        printf "  %-45s FAIL (version.txt is empty)\n" "$ws" >&2
        failed=1
        continue
    fi

    if ! lib_version=$(python3 -c "import $pkg; print($pkg.__version__)" 2>/dev/null); then
        printf "  %-45s SKIP (cannot import %s)\n" "$ws" "$pkg"
        continue
    fi

    case "$(compare_versions "$ws_version" "$lib_version")" in
        MATCH)
            printf "  %-45s ok       (%s)\n" "$ws" "$ws_version"
            ;;
        BEHIND)
            printf "  %-45s ok       (workspace %s < installed %s — release will overwrite)\n" \
                "$ws" "$ws_version" "$lib_version"
            ;;
        AHEAD)
            printf "  %-45s FAIL     (workspace %s > installed %s — aspirational version!)\n" \
                "$ws" "$ws_version" "$lib_version" >&2
            failed=1
            ;;
        *)
            printf "  %-45s FAIL     (could not parse versions: ws=%s lib=%s)\n" \
                "$ws" "$ws_version" "$lib_version" >&2
            failed=1
            ;;
    esac
done

if [ "$failed" -ne 0 ]; then
    echo >&2
    echo "verify_workspace_versions: at least one workspace is AHEAD of its installed library." >&2
    echo "                           Release dispatch blocked. Patch the offending version.txt(s)" >&2
    echo "                           to match the installed library, then re-run." >&2
    exit 1
fi
