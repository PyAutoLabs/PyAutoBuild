#!/usr/bin/env bash
# url_check.sh - fail if forbidden Binder/Colab URL patterns appear in docs.
#
# Usage: url_check.sh [directory]
# Exits 0 if clean, 1 if any forbidden patterns are found, 2 on usage error.
#
# Forbidden patterns:
#   1. Any mybinder.org URL — Binder is no longer supported, use Colab.
#   2. Colab URL with Jammy2211 owner — workspaces now live under PyAutoLabs.
#   3. Colab URL pinned to /blob/release/ — the release branch is gone, pin to a tag.

set -u

DIR="${1:-.}"

if [ ! -d "$DIR" ]; then
  echo "url_check.sh: not a directory: $DIR" >&2
  exit 2
fi

PATTERNS=(
  'mybinder\.org'
  'colab\.research\.google\.com/github/Jammy2211/'
  'colab\.research\.google\.com/github/[^/]+/[^/]+/blob/release/'
)

LABELS=(
  'mybinder.org URL (Binder is no longer supported — use Colab)'
  'Colab URL with Jammy2211 owner (use PyAutoLabs)'
  'Colab URL pinned to /blob/release/ (use a tagged version)'
)

found=0
for i in "${!PATTERNS[@]}"; do
  pattern="${PATTERNS[$i]}"
  label="${LABELS[$i]}"
  matches=$(grep -REn \
    --include='*.rst' --include='*.md' --include='*.ipynb' --include='*.py' \
    "$pattern" "$DIR" 2>/dev/null || true)
  if [ -n "$matches" ]; then
    found=1
    echo ""
    echo "FORBIDDEN: $label"
    echo "$matches"
  fi
done

if [ "$found" -eq 1 ]; then
  exit 1
fi
exit 0
