#!/usr/bin/env bash
# tag_and_merge.sh — commit pending changes and tag library repos for release.
#
# Usage: tag_and_merge.sh --version <VERSION>
#
# For each library repo (PyAutoConf, PyAutoFit, PyAutoArray, PyAutoGalaxy,
# PyAutoLens), commits pending changes with message "Update version to
# <VERSION>" and tags HEAD as v<VERSION>. Stops on the first failing repo.

set -euo pipefail

VERSION=""
while [ $# -gt 0 ]; do
    case "$1" in
        --version)
            if [ $# -lt 2 ]; then
                echo "tag_and_merge.sh: --version requires a value" >&2
                exit 2
            fi
            VERSION="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,7p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "tag_and_merge.sh: unknown argument '$1'" >&2
            exit 2
            ;;
    esac
done

if [ -z "$VERSION" ]; then
    echo "tag_and_merge.sh: --version is required" >&2
    exit 2
fi

PYAUTOBASE="$(cd "$(dirname "$0")/../.." && pwd)"
LIB_PROJECTS=(PyAutoConf PyAutoFit PyAutoArray PyAutoLens PyAutoGalaxy)

for project in "${LIB_PROJECTS[@]}"; do
    repo="$PYAUTOBASE/$project"
    echo "Tagging $project"
    if [ ! -d "$repo/.git" ]; then
        echo "tag_and_merge.sh: $repo is not a git repo" >&2
        exit 1
    fi
    git -C "$repo" commit -a -m "Update version to $VERSION"
    git -C "$repo" tag "v$VERSION"
done
