#!/usr/bin/env bash
# verify_workspace_versions.sh — fail fast if any workspace's pinned version is
# AHEAD of the currently-installed library version.
#
# Usage: bash PyAutoBuild/verify_workspace_versions.sh
#
# Background: the bootstrap commit for a new workspace-style repo (HowToLens,
# 2026-04-21) set version.txt to today's date as an aspirational tag. Until
# the next release dispatch wrote a real version, every welcome.py run
# crashed with WorkspaceVersionMismatchError. This check blocks pre_build.sh
# from dispatching a release that would be invalidated by such a mismatch.
#
# Source-of-truth precedence (mirrors autoconf.workspace.check_version):
#   1. config/general.yaml's `version.workspace_version` key
#   2. version.txt at the workspace root (legacy fallback)
# If both exist and disagree, the script fails — they must be kept in sync
# by the release pipeline.
#
# Compares each of the 7 workspaces (3 main + 3 HowTo + euclid_pipeline)
# against its installed library version, parsed as a YYYY.M.D.B 4-tuple of
# ints. Exits 1 if any workspace.version > library.version.
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

# Resolve the workspace's pinned version using the same precedence as
# autoconf.workspace.check_version. Echoes the version string on stdout, or
# prints "MISSING" if neither source is present, "MISMATCH:<yaml>:<txt>" if
# both exist and disagree.
resolve_workspace_version() {
    local ws_root="$1"
    python3 - "$ws_root" <<'PY'
import pathlib, sys
root = pathlib.Path(sys.argv[1])
yaml_v = None
try:
    import yaml
    cfg = root / "config" / "general.yaml"
    if cfg.exists():
        with cfg.open() as f:
            data = yaml.safe_load(f) or {}
        v = (data.get("version") or {}).get("workspace_version")
        if v is not None:
            yaml_v = str(v).strip()
except Exception:
    pass
txt_v = None
txt_path = root / "version.txt"
if txt_path.exists():
    txt_v = txt_path.read_text().strip() or None
if yaml_v and txt_v and yaml_v != txt_v:
    print(f"MISMATCH:{yaml_v}:{txt_v}")
elif yaml_v:
    print(yaml_v)
elif txt_v:
    print(txt_v)
else:
    print("MISSING")
PY
}

failed=0

for entry in "${WORKSPACES[@]}"; do
    ws="${entry%%|*}"
    pkg="${entry#*|}"
    ws_root="$PYAUTOBASE/$ws"

    if [ ! -d "$ws_root" ]; then
        printf "  %-45s SKIP (workspace dir missing)\n" "$ws"
        continue
    fi

    ws_version=$(resolve_workspace_version "$ws_root")

    case "$ws_version" in
        MISSING)
            printf "  %-45s SKIP (no general.yaml workspace_version and no version.txt)\n" "$ws"
            continue
            ;;
        MISMATCH:*)
            yaml_v="${ws_version#MISMATCH:}"; yaml_v="${yaml_v%%:*}"
            txt_v="${ws_version##*:}"
            printf "  %-45s FAIL (general.yaml workspace_version=%s disagrees with version.txt=%s)\n" \
                "$ws" "$yaml_v" "$txt_v" >&2
            failed=1
            continue
            ;;
        "")
            printf "  %-45s FAIL (could not resolve workspace version)\n" "$ws" >&2
            failed=1
            continue
            ;;
    esac

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
    echo "verify_workspace_versions: at least one workspace is AHEAD of its installed library" >&2
    echo "                           or has a config/general.yaml ↔ version.txt disagreement." >&2
    echo "                           Release dispatch blocked. Patch the offending workspace(s)" >&2
    echo "                           to match the installed library, then re-run." >&2
    exit 1
fi
