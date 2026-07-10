"""
Render a curated set of workspace example scripts to executed markdown pages.

For each script listed in the workspace's ``config/build/markdown_examples.yaml``
this tool converts the script to a notebook (the same ``py_to_notebook``
machinery as ``generate.py``), executes it **for real**, and renders the result
to ``markdown/<path>/<name>.md`` with the output figures extracted as PNGs
alongside (``<name>_files/``). A ``markdown/README.md`` index is generated from
the same list. The rendered pages are committed to the workspace repo so the
examples can be read on GitHub with their output images visible.

Run from the workspace root, exactly like ``generate.py``:

    python ../PyAutoBuild/autobuild/generate_markdown.py autolens [--only <substring>]

Rules this tool enforces:

- **Never TEST_MODE.** A truncated non-linear search produces wrong images; the
  build aborts if ``PYAUTO_TEST_MODE`` is set. Model-fit scripts instead rely on
  PyAutoFit's completed-run resume: the first build pays one full sampling run,
  and regeneration loads the completed result from ``output/`` near-instantly.
- **Nothing from a ``features/`` folder is rendered.**
- **Tracked files outside ``markdown/`` are protected.** Any tracked file that
  *becomes* modified during the build (e.g. a simulator rewriting ``dataset/``
  with a new noise realization) is restored after the script that touched it,
  reported loudly. Files already modified when the build starts are warned
  about, used as-is, and left alone. Corollary: leave the workspace tree alone
  while a build is running — a hand edit made mid-build is indistinguishable
  from script side-effects and will be reverted with them.
- Regeneration is manual / at-release, only when a curated script changes —
  never per-commit.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

import build_util

CONFIG_RELATIVE_PATH = Path("config") / "build" / "markdown_examples.yaml"
MARKDOWN_DIR = "markdown"
DEFAULT_MAX_MINUTES = 60

PROJECT_DISPLAY_NAMES = {
    "autofit": "PyAutoFit",
    "autogalaxy": "PyAutoGalaxy",
    "autolens": "PyAutoLens",
    "howtofit": "HowToFit",
    "howtogalaxy": "HowToGalaxy",
    "howtolens": "HowToLens",
}

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
STREAM_HEAD_LINES = 10
STREAM_TAIL_LINES = 20
STREAM_MAX_LINES = STREAM_HEAD_LINES + STREAM_TAIL_LINES + 10


def load_examples(workspace_path: Path):
    """
    Read the curated example list, validating every entry.

    Entries are ``{script: <path relative to workspace root>, max_minutes: N}``
    dicts (a bare string is shorthand for the dict with the default timeout).
    """
    config_path = workspace_path / CONFIG_RELATIVE_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"No curated example list at {config_path} — create it to use "
            f"generate_markdown.py (see PyAutoBuild docs/internals.md)."
        )
    with open(config_path) as f:
        raw = yaml.safe_load(f) or []

    examples = []
    for entry in raw:
        if isinstance(entry, str):
            entry = {"script": entry}
        script = entry.get("script")
        if not script:
            raise ValueError(f"markdown_examples.yaml entry missing 'script': {entry}")
        script_rel = Path(script)
        if "features" in script_rel.parts:
            raise ValueError(
                f"markdown_examples.yaml: '{script}' is inside a features/ "
                f"folder — feature scripts are never rendered to markdown."
            )
        if script_rel.suffix != ".py":
            raise ValueError(f"markdown_examples.yaml: '{script}' is not a .py script.")
        if not (workspace_path / script_rel).exists():
            raise FileNotFoundError(
                f"markdown_examples.yaml: '{script}' does not exist in {workspace_path}."
            )
        examples.append(
            {
                "script": script_rel,
                "max_minutes": int(entry.get("max_minutes", DEFAULT_MAX_MINUTES)),
            }
        )
    return examples


def markdown_destination(script_rel: Path):
    """
    Map a script path to its markdown output directory (relative to the
    workspace root): ``scripts/imaging/modeling.py -> markdown/imaging``,
    ``start_here.py -> markdown``.
    """
    parent = script_rel.parent
    parts = parent.parts
    if parts and parts[0] == "scripts":
        parts = parts[1:]
    return Path(MARKDOWN_DIR).joinpath(*parts)


def script_title(script_path: Path) -> str:
    """First non-empty line of the script's opening docstring, as the index title."""
    text = script_path.read_text(errors="replace")
    match = re.search(r'"""(.*?)"""', text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            line = line.strip().strip("_*").strip()
            if line and not set(line) <= {"=", "-"}:
                return line
    return script_path.stem


def _redactions_for(workspace_path: Path):
    """
    Substitutions scrubbing the local machine layout out of published output:
    the workspace path becomes its bare name, sibling checkouts (e.g. library
    paths in warnings) become `...`, and any other home path becomes `~`.
    """
    return [
        (str(workspace_path), workspace_path.name),
        (str(workspace_path.parent), "..."),
        (os.path.expanduser("~"), "~"),
    ]


def _clean_stream_text(text: str, redactions=()) -> str:
    """
    Make captured stream output readable in markdown: drop ANSI escapes,
    resolve carriage-return progress lines to their final state, redact
    absolute local paths (a machine layout must not be published), and
    truncate very long output (search progress logs) to head + tail.
    """
    text = ANSI_RE.sub("", text)
    for old, new in redactions:
        text = text.replace(old, new)
    lines = [raw.split("\r")[-1] for raw in text.split("\n")]
    if len(lines) > STREAM_MAX_LINES:
        truncated = len(lines) - STREAM_HEAD_LINES - STREAM_TAIL_LINES
        lines = (
            lines[:STREAM_HEAD_LINES]
            + [f"... [{truncated} lines of output truncated] ..."]
            + lines[-STREAM_TAIL_LINES:]
        )
    return "\n".join(lines)


def clean_notebook_outputs(notebook_path: Path, redactions=()):
    """Clean every stream output in an executed notebook, in place."""
    with open(notebook_path) as f:
        notebook = json.load(f)

    for cell in notebook.get("cells", []):
        for output in cell.get("outputs", []):
            if output.get("output_type") != "stream":
                continue
            source = output.get("text", "")
            if isinstance(source, list):
                source = "".join(source)
            output["text"] = _clean_stream_text(source, redactions=redactions)

    with open(notebook_path, "w") as f:
        json.dump(notebook, f, indent=1)


def _markdown_header(script_rel: Path, md_dir: Path) -> str:
    script_link = os.path.relpath(script_rel, md_dir)
    notebook_rel = Path("notebooks").joinpath(
        *script_rel.with_suffix(".ipynb").parts[1:]
    ) if script_rel.parts[0] == "scripts" else script_rel.with_suffix(".ipynb")
    notebook_link = os.path.relpath(notebook_rel, md_dir)
    return (
        f"> ✏️ **This page is auto-generated from [`{script_rel}`]({script_link}) — do not edit it directly.**\n"
        f"> It shows the example fully executed, with its real output images.\n"
        f"> Run it yourself via the [Python script]({script_link}) or the "
        f"[Jupyter notebook]({notebook_link}).\n\n"
    )


def _dirty_tracked_paths(workspace_path: Path):
    """Tracked files with modifications, excluding anything under markdown/."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace_path,
        capture_output=True,
        text=True,
        check=True,
    )
    dirty = []
    for line in result.stdout.splitlines():
        status, _, path = line[:2], line[2], line[3:].strip()
        if status == "??":
            continue
        if path.startswith(f"{MARKDOWN_DIR}/"):
            continue
        dirty.append(path)
    return dirty


def restore_tracked_files(workspace_path: Path, exclude=frozenset()):
    """
    Restore tracked files a rendered script modified (e.g. a simulator
    rewriting its tracked dataset with a fresh noise realization), except
    those in *exclude* (the files already dirty before the build started).
    Returns the restored paths, loudly.
    """
    dirty = [p for p in _dirty_tracked_paths(workspace_path) if p not in exclude]
    if dirty:
        subprocess.run(
            ["git", "checkout", "--"] + dirty,
            cwd=workspace_path,
            check=True,
        )
        print(f"  RESTORED tracked files modified by the script: {dirty}")
    return dirty


def render_script(
    workspace_path: Path, script_rel: Path, max_minutes: int, pre_dirty=frozenset()
):
    """
    Convert one script to an executed markdown page + extracted images.
    Raises on any failure — a wrong or missing page must never ship silently.
    """
    script_path = workspace_path / script_rel
    md_dir = markdown_destination(script_rel)
    (workspace_path / md_dir).mkdir(parents=True, exist_ok=True)

    notebook_path = build_util.py_to_notebook(script_path)
    timeout_secs = max_minutes * 60

    print(f"Executing <{script_rel}> (timeout {max_minutes}m) ...", flush=True)
    start = time.time()
    try:
        subprocess.run(
            [
                "jupyter",
                "nbconvert",
                "--to",
                "notebook",
                "--execute",
                f"--ExecutePreprocessor.timeout={timeout_secs}",
                "--output",
                str(notebook_path),
                str(notebook_path),
            ],
            check=True,
            timeout=timeout_secs + 60,
        )
        print(f"  executed in {time.time() - start:.0f}s")

        clean_notebook_outputs(notebook_path, redactions=_redactions_for(workspace_path))

        # nbconvert never removes stale support files, so a script that now
        # produces fewer figures would leave orphan PNGs behind.
        files_dir = workspace_path / md_dir / f"{script_rel.stem}_files"
        if files_dir.exists():
            shutil.rmtree(files_dir)

        subprocess.run(
            [
                "jupyter",
                "nbconvert",
                "--to",
                "markdown",
                str(notebook_path),
                "--output-dir",
                str(workspace_path / md_dir),
            ],
            check=True,
        )
    finally:
        if notebook_path.exists():
            os.remove(notebook_path)
        restore_tracked_files(workspace_path, exclude=pre_dirty)

    md_path = workspace_path / md_dir / script_rel.with_suffix(".md").name
    md_path.write_text(_markdown_header(script_rel, md_dir) + md_path.read_text())

    ignored = subprocess.run(
        ["git", "check-ignore", str(md_dir)],
        cwd=workspace_path,
        capture_output=True,
    )
    if ignored.returncode == 0:
        raise RuntimeError(
            f"{md_dir} is matched by .gitignore — the rendered pages and their "
            f"images must be tracked. Fix .gitignore before building."
        )

    subprocess.run(["git", "add", "-f", str(md_dir)], cwd=workspace_path, check=True)
    return md_path


def write_index(workspace_path: Path, project: str, examples):
    """Generate markdown/README.md linking every curated page."""
    display = PROJECT_DISPLAY_NAMES.get(project, project)
    lines = [
        f"# {display} examples, executed — browse with output images",
        "",
        "Every page below is the corresponding example script **fully executed**, "
        "rendered to markdown with its real output images, so you can read the "
        "examples on GitHub exactly as they run. Each page links back to the "
        "`.py` script and Jupyter notebook it was generated from.",
        "",
    ]
    for example in examples:
        script_rel = example["script"]
        md_dir = markdown_destination(script_rel)
        md_rel = os.path.relpath(
            md_dir / script_rel.with_suffix(".md").name, MARKDOWN_DIR
        )
        title = script_title(workspace_path / script_rel)
        lines.append(f"- [{title}]({md_rel}) — from `{script_rel}`")
    lines.append("")
    lines.append(
        "These pages are regenerated manually by PyAutoBuild's "
        "`generate_markdown.py` when a curated script changes."
    )
    index_path = workspace_path / MARKDOWN_DIR / "README.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines) + "\n")
    subprocess.run(
        ["git", "add", "-f", str(Path(MARKDOWN_DIR) / "README.md")],
        cwd=workspace_path,
        check=True,
    )
    return index_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=str, help="The project the workspace belongs to")
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Only render curated scripts whose path contains this substring",
    )
    args = parser.parse_args()

    if os.environ.get("PYAUTO_TEST_MODE"):
        sys.exit(
            "generate_markdown.py refuses to run with PYAUTO_TEST_MODE set: a "
            "truncated search produces wrong images. Unset it and rely on the "
            "completed-run resume cache in output/ instead."
        )

    workspace_path = Path.cwd()
    examples = load_examples(workspace_path)

    pre_dirty = frozenset(_dirty_tracked_paths(workspace_path))
    if pre_dirty:
        print(
            f"WARNING: tracked files already modified before the build — the "
            f"renders will use them as-is and they will NOT be restored: "
            f"{sorted(pre_dirty)}"
        )

    to_render = examples
    if args.only:
        to_render = [e for e in examples if args.only in str(e["script"])]
        if not to_render:
            sys.exit(f"--only '{args.only}' matches no curated script.")

    failures = []
    for example in to_render:
        try:
            md_path = render_script(
                workspace_path,
                example["script"],
                example["max_minutes"],
                pre_dirty=pre_dirty,
            )
            print(f"  PASS {example['script']} -> {md_path.relative_to(workspace_path)}")
        except Exception as e:
            print(f"  FAIL {example['script']}: {e}")
            failures.append((example["script"], e))

    write_index(workspace_path, args.project, examples)

    if failures:
        sys.exit(
            f"{len(failures)}/{len(to_render)} curated scripts failed to render: "
            f"{[str(s) for s, _ in failures]}"
        )
    print(f"Rendered {len(to_render)} scripts to {MARKDOWN_DIR}/ and updated the index.")


if __name__ == "__main__":
    main()
