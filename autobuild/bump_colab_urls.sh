#!/usr/bin/env bash
# bump_colab_urls.sh - bump the tag ref in Colab URLs across the cwd.
#
# Usage: bump_colab_urls.sh <new-tag>
#
# Replaces every URL of the form
#   colab.research.google.com/github/PyAutoLabs/<workspace>/blob/<old-tag>/...
# with <new-tag>, in-place across *.rst, *.md, *.ipynb, *.py.
#
# <workspace> is one of autofit_workspace, autogalaxy_workspace, autolens_workspace.
# <old-tag> must match the date-based scheme YYYY.M.D.B (anything else is left alone,
# so the bumper is a no-op until the URL sweep migrates URLs to canonical form).
# The script is idempotent: running it twice with the same tag is a no-op.

set -eu

NEW_TAG="${1:-}"
if [ -z "$NEW_TAG" ]; then
  echo "Usage: bump_colab_urls.sh <new-tag>" >&2
  exit 2
fi

if ! [[ "$NEW_TAG" =~ ^[0-9]{4}\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "bump_colab_urls.sh: tag must look like YYYY.M.D.B; got: $NEW_TAG" >&2
  exit 2
fi

PATTERN='(colab\.research\.google\.com/github/PyAutoLabs/(autofit|autogalaxy|autolens)_workspace/blob/)[0-9]{4}\.[0-9]+\.[0-9]+\.[0-9]+/'
REPLACE="\${1}${NEW_TAG}/"

find . -type f \( -name '*.rst' -o -name '*.md' -o -name '*.ipynb' -o -name '*.py' \) \
  -exec perl -i -pe "s#${PATTERN}#${REPLACE}#g" {} +
