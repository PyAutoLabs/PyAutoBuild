#!/usr/bin/env python
"""
Usage
./add_notebook_quotes.py /path/to/input /path/to/output
"""

from typing import Iterable, List

from sys import argv


def strip_env_declarations(lines: List[str]) -> List[str]:
    """Remove in-file env declarations before notebook / markdown conversion.

    In-file env declarations are developer-only test-harness configuration
    (docs/env_profile_redesign.md §10) and must never appear in a generated
    notebook or markdown page. Two forms are stripped:

    * the ``__Env__`` docstring section — the ENTIRE triple-quoted block whose
      first non-blank line is the ``__Env__`` header (the user-workspace form);
    * a ``# ENV: ...`` comment line anchored at column 0 (the ``_test``-repo
      form — those repos are not doc-generated, but this is defence in depth).

    This is the single shared strip layer: ``build_util.py_to_notebook`` routes
    both notebook generation (``generate.py``) and markdown generation
    (``generate_markdown.py``) through ``add_notebook_quotes``, and
    ``navigator.py`` reuses this same tokenizer to segment docstrings — so
    stripping here drops the block from every generated artefact and keeps it
    out of the catalogue.
    """
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Comment form: a `# ENV:` line anchored at column 0.
        if stripped.startswith("# ENV:") and line[:1] == "#":
            i += 1
            continue

        # Docstring form: a bare `"""`/`'''` opener whose first non-blank inner
        # line is the `__Env__` header — drop the whole block, delimiters too.
        if stripped in ('"""', "'''"):
            delim = stripped
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and lines[j].strip().startswith("__Env__"):
                k = j
                while k < n and lines[k].strip() != delim:
                    k += 1
                i = k + 1  # skip through the closing delimiter
                continue

        out.append(line)
        i += 1

    # A bottom-of-file `__Env__` block leaves dangling blank lines (its leading
    # separator); trim them so the generated artefact ends on real content.
    while out and out[-1].strip() == "":
        out.pop()
    if out and not out[-1].endswith("\n"):
        out[-1] = out[-1] + "\n"
    return out


def add_notebook_quotes(lines: Iterable[str]):
    """
    Add %% above and below docs quotes with triple quotes.

    Used for conversion to ipynb notebooks

    Parameters
    ----------
    lines
        An iterable of lines loaded from a notebook file

    Returns
    -------
    Lines with %% inserted before and after docs
    """
    lines = strip_env_declarations(list(lines))
    out = list()
    is_in_quotes = False

    for line in lines:
        if line.startswith('"""') or line.startswith("'''"):
            if is_in_quotes:
                out.extend(["'''", "\n\n", "# %%\n"])
            else:
                out.extend(["# %%", "\n", "'''\n"])

            is_in_quotes = not is_in_quotes
        else:
            out.append(line)

    return out


if __name__ == "__main__":
    _, in_filename, out_filename = argv

    with open(in_filename) as f:
        lines = f.readlines()

    with open(out_filename, "w+") as f:
        f.writelines(add_notebook_quotes(lines))
