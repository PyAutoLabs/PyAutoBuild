#!/usr/bin/env python3
"""
Regenerate the workspace catalogue (Phase 2 only — no notebook rebuild).

This is the lightweight entrypoint the reusable ``navigator_check`` staleness
job uses, and the one a maintainer runs locally to refresh a catalogue. It calls
``navigator.write_catalogue`` for the workspace checkout in the *current working
directory*, producing ``llms-full.txt`` and ``workspace_index.json`` *without*
running the full notebook generation and *without* needing the science stack
(only ``pyyaml``).

It lives beside ``navigator.py`` in PyAutoBuild, so it no longer needs the
``PYAUTOBUILD_DIR`` path plumbing the old per-workspace shim used — it imports
``navigator`` from its own directory. The generator project is taken from the
first CLI argument, falling back to the ``NAVIGATOR_PROJECT`` environment
variable, then ``autolens``.

Run from the workspace root (CWD is the workspace to catalogue, not this
package)::

    python /path/to/PyAutoBuild/autobuild/regenerate_navigator.py autogalaxy
    NAVIGATOR_PROJECT=autofit python /path/to/PyAutoBuild/autobuild/regenerate_navigator.py
"""

import os
import sys
from pathlib import Path


def main():
    project = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.environ.get("NAVIGATOR_PROJECT", "autolens")
    )

    # navigator.py is a sibling of this file; put its directory on the path so
    # ``import navigator`` resolves regardless of the current working directory
    # (CWD is the workspace target passed to write_catalogue, not this package).
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    # navigator imports generate.py lazily, whose module-level argparse expects a
    # project positional; supply it via argv so the import resolves cleanly.
    sys.argv = ["generate.py", project]

    import navigator

    navigator.write_catalogue(Path.cwd(), project)


if __name__ == "__main__":
    main()
