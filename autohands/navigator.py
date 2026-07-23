"""
Generate an LLM-facing catalogue of an autolens-style workspace from script
docstrings.

This module is the companion to ``generate.py``: where ``generate.py`` converts
each ``scripts/**/*.py`` into a Jupyter notebook, this module walks the *same*
set of scripts (via the shared :func:`generate.iter_script_paths` selector) and
emits a machine- and LLM-readable catalogue describing each one.

It deliberately **reuses** the existing docstring segmentation
(:func:`add_notebook_quotes.add_notebook_quotes`) rather than introducing a
second parser — the same triple-quote tokenizer that turns docstrings into
notebook markdown cells is used here to isolate the title, summary,
``__Contents__`` list and the per-section ``__Section__`` docstring blocks.

Two artefacts are written into the workspace root:

- ``llms-full.txt``      — an expanded, human-readable ``llms.txt`` form.
- ``workspace_index.json`` — the same records as a machine-readable array.

The curated ``llms.txt`` is never read or written here; that file is hand
maintained routing and is intentionally left alone.

Output is **deterministic**: scripts are sorted lexicographically by their
repo-relative path, groups follow a fixed order, JSON is serialised with sorted
keys and a fixed indent, and no timestamps / absolute paths / hostnames are
embedded. Running the generator twice on an unchanged tree produces
byte-identical files.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from add_notebook_quotes import add_notebook_quotes

logger = logging.getLogger(__name__)

# Fixed display order for the top-level ``scripts/`` folders in llms-full.txt.
# This is a *preference* for projects whose folder set is known; any folder not
# listed here is appended afterwards in sorted order, so a project organised by a
# completely different folder set (e.g. autofit's inference-feature folders such
# as ``model``, ``searches``, ``features``) still groups correctly — every folder
# is derived from the actual ``scripts/`` tree, none are assumed to exist.
GROUP_ORDER = [
    "imaging",
    "group",
    "interferometer",
    "point_source",
    "cluster",
    "multi",
    "weak",
    "guides",
]

# Display name for the workspace header in llms-full.txt, keyed by the project
# name passed to generate.py. Falls back to a generic, project-derived title so a
# new project still produces a sensible header without a code change — and so no
# project's framing (e.g. lensing) leaks into another's catalogue.
WORKSPACE_TITLES = {
    "autofit": "PyAutoFit Workspace",
    "autonerves": "PyAutoNerves Workspace",
    "autocti": "PyAutoCTI Workspace",
    "autogalaxy": "PyAutoGalaxy Workspace",
    "autolens": "PyAutoLens Workspace",
    "howtolens": "HowToLens Lectures",
    "howtogalaxy": "HowToGalaxy Lectures",
    "howtofit": "HowToFit Lectures",
}


def _workspace_title(project: Optional[str]) -> str:
    """Human-readable workspace title for the llms-full.txt header."""
    if project and project in WORKSPACE_TITLES:
        return WORKSPACE_TITLES[project]
    if project:
        return f"{project} workspace"
    return "Workspace"

# Best-effort cross-reference detection: any token ending in .py or .ipynb that
# appears inside the header docstrings. Matches bare names and paths alike.
_CROSS_REF_RE = re.compile(r"[\w./-]+\.(?:py|ipynb)")


def _docstring_blocks(script_path: Path) -> List[List[str]]:
    """
    Return the docstring blocks of a script, in order, as lists of inner lines.

    The script's lines are passed through
    :func:`add_notebook_quotes.add_notebook_quotes` — the same segmentation used
    to build notebooks — which wraps every docstring block in ``'''`` delimiter
    lines. We then read the content between successive delimiters back out, so
    no independent triple-quote parser is introduced here.
    """
    with open(script_path, encoding="utf-8") as f:
        lines = f.readlines()

    quoted = add_notebook_quotes(lines)

    blocks: List[List[str]] = []
    current: Optional[List[str]] = None
    for line in quoted:
        stripped = line.strip()
        if stripped == "'''":
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
            continue
        if current is not None:
            current.append(line.rstrip("\n"))
    # An unterminated block (malformed script) is still returned best-effort.
    if current is not None:
        blocks.append(current)
    return blocks


def _parse_header(block: List[str]):
    """
    Parse the header docstring block into (title, summary, contents).

    The expected shape is::

        Title Line
        ==========

        First prose paragraph (the summary).

        More prose...

        __Contents__

        - **Name:** description.

    Any of these may be missing; callers handle the ``None`` results.
    """
    title = None
    summary = None
    contents: List[str] = []

    # Strip leading blank lines.
    idx = 0
    while idx < len(block) and block[idx].strip() == "":
        idx += 1

    # Title is the first non-blank line, provided the following line is an
    # ``===`` underline (the workspace convention for an H1).
    if idx < len(block):
        candidate = block[idx].strip()
        underline = block[idx + 1].strip() if idx + 1 < len(block) else ""
        if candidate and set(underline) == {"="} and underline:
            title = candidate
            idx += 2
        else:
            # No underline — fall back to treating the first line as the title
            # so a mildly non-conforming script still yields something useful.
            title = candidate or None
            idx += 1

    # Summary: the first non-empty prose paragraph after the title, stopping at
    # ``__Contents__`` or any other ``__Section__`` marker.
    paragraph: List[str] = []
    while idx < len(block):
        line = block[idx].strip()
        if line.startswith("__") and line.endswith("__"):
            break
        if line == "":
            if paragraph:
                break
        else:
            paragraph.append(line)
        idx += 1
    if paragraph:
        summary = " ".join(paragraph)

    # Contents: parse the bullet list under the ``__Contents__`` marker.
    in_contents = False
    for line in block:
        stripped = line.strip()
        if stripped == "__Contents__":
            in_contents = True
            continue
        if in_contents:
            if stripped.startswith("__") and stripped.endswith("__"):
                break
            if stripped.startswith("-"):
                item = stripped.lstrip("-").strip()
                # Entries look like ``**Name:** description.`` — keep the name.
                match = re.match(r"\*\*(.+?):?\*\*", item)
                if match:
                    contents.append(match.group(1).strip())
                elif item:
                    contents.append(item)

    return title, summary, contents


def _cross_refs(blocks: List[List[str]], self_path: Path) -> List[str]:
    """
    Best-effort collection of other script/notebook names referenced in the
    header docstrings. Self-references and duplicates are removed; the result is
    sorted for determinism.
    """
    self_names = {self_path.name, self_path.with_suffix(".ipynb").name}
    refs = set()
    for block in blocks:
        for line in block:
            for match in _CROSS_REF_RE.findall(line):
                name = match.strip("`'\"(),")
                if name and name not in self_names:
                    refs.add(name)
    return sorted(refs)


def build_records(workspace_path: Path) -> List[dict]:
    """
    Build one catalogue record per script in the workspace.

    The set of scripts is exactly the set ``generate.py`` converts to notebooks
    (via the shared :func:`generate.iter_script_paths` selector), so the
    catalogue and the notebook set are equal by construction.
    """
    # Imported lazily to avoid a circular import at module load (generate.py
    # imports navigator).
    from generate import iter_script_paths, notebook_path_

    workspace_path = Path(workspace_path)
    scripts_path = workspace_path / "scripts"

    records: List[dict] = []
    for script_path in iter_script_paths(scripts_path):
        rel_path = script_path.relative_to(workspace_path).as_posix()

        # notebook_path_ maps /scripts/ -> /notebooks/ but keeps the suffix;
        # the generated notebook is the .ipynb form of that path.
        notebook_abs = notebook_path_(script_path).with_suffix(".ipynb")
        notebook_rel = (
            notebook_abs.relative_to(workspace_path).as_posix()
            if notebook_abs.exists()
            else None
        )

        title = None
        summary = None
        contents: List[str] = []
        cross_refs: List[str] = []

        try:
            blocks = _docstring_blocks(script_path)
            if blocks:
                title, summary, contents = _parse_header(blocks[0])
            cross_refs = _cross_refs(blocks, script_path)
        except Exception as exc:  # never crash the whole run on one bad file
            logger.warning("Failed to parse docstring of %s: %s", rel_path, exc)

        if not title:
            logger.warning(
                "No title found in %s; falling back to filename", rel_path
            )
            title = script_path.stem
        if not summary:
            logger.warning("No summary found in %s", rel_path)
            summary = "(no summary in script docstring)"

        records.append(
            {
                "path": rel_path,
                "notebook": notebook_rel,
                "title": title,
                "summary": summary,
                "contents": contents,
                "cross_refs": cross_refs,
            }
        )

    # Deterministic order: lexicographic by repo-relative path.
    records.sort(key=lambda r: r["path"])
    return records


def _group_for(record: dict) -> str:
    """Top-level ``scripts/`` folder a record belongs to (for grouping)."""
    parts = Path(record["path"]).parts
    # parts[0] == "scripts"; the group is parts[1] if present.
    return parts[1] if len(parts) > 2 else "(root)"


def _render_llms_full(records: List[dict], project: Optional[str] = None) -> str:
    """Render the human-readable ``llms-full.txt`` content (deterministic)."""
    lines: List[str] = []
    lines.append(
        "AUTO-GENERATED by PyAutoHands — do not edit by hand; "
        "regenerate with generate.py."
    )
    lines.append("")
    lines.append(f"# {_workspace_title(project)} — Full Catalogue")
    lines.append("")
    lines.append(
        "> Complete, generated listing of every script (and its matching "
        "notebook) in this"
    )
    lines.append(
        "> workspace, grouped by top-level `scripts/` folder. This is the "
        "expanded companion to"
    )
    lines.append(
        "> the curated `llms.txt` routing layer. Each entry links the script's "
        "title to its path"
    )
    lines.append(
        "> and gives the first line of its docstring; `Contents:` lists the "
        "sections within."
    )
    lines.append("")

    # Determine group order: fixed list first, then any extras sorted.
    present_groups = {_group_for(r) for r in records}
    ordered_groups = [g for g in GROUP_ORDER if g in present_groups]
    extras = sorted(present_groups - set(GROUP_ORDER))
    ordered_groups.extend(extras)

    for group in ordered_groups:
        group_records = [r for r in records if _group_for(r) == group]
        if not group_records:
            continue
        lines.append(f"## {group}")
        lines.append("")
        for record in group_records:
            lines.append(
                f"- [{record['title']}]({record['path']}): {record['summary']}"
            )
            if record["contents"]:
                joined = ", ".join(record["contents"])
                lines.append(f"  - Contents: {joined}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def write_catalogue(workspace_path: Path, project: Optional[str] = None) -> List[Path]:
    """
    Build the catalogue and write ``llms-full.txt`` and ``workspace_index.json``
    into the workspace root. Returns the paths written.

    ``project`` (the name passed to ``generate.py``) only selects the workspace
    title in the ``llms-full.txt`` header; the records and grouping are derived
    entirely from the workspace's actual ``scripts/`` tree.
    """
    workspace_path = Path(workspace_path)
    records = build_records(workspace_path)

    llms_full_path = workspace_path / "llms-full.txt"
    index_path = workspace_path / "workspace_index.json"

    llms_full_path.write_text(_render_llms_full(records, project), encoding="utf-8")
    index_path.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"Catalogue written: {llms_full_path.name}, {index_path.name} "
        f"({len(records)} scripts)"
    )
    return [llms_full_path, index_path]
