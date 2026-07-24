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
    notebook or markdown page. The stripped forms:

    * the ``__Env__`` docstring section — a column-0 ``__Env__`` header appended
      anywhere inside a docstring block (the canonical merged form) plus its one
      ``ENV:`` line, through the line before the block's closing delimiter. The
      docstring's earlier prose and its delimiters are PRESERVED; the blank /
      separator line(s) immediately before the header are trimmed. When the
      header is the block's only content (the standalone fallback), or when the
      strip would leave an empty docstring, the whole block is removed;
    * a ``# ENV: ...`` comment line anchored at column 0 — the comment form was
      removed at runtime (it now raises in ``read_env_declaration``), but a stray
      one is still stripped here defensively so it never reaches an artefact.

    This is the single shared strip layer: ``build_util.py_to_notebook`` routes
    both notebook generation (``generate.py``) and markdown generation
    (``generate_markdown.py``) through ``add_notebook_quotes``, and
    ``navigator.py`` reuses this same tokenizer to segment docstrings — so
    stripping here drops the section from every generated artefact and keeps it
    out of the catalogue.
    """
    out: List[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Comment form (removed at runtime): strip a column-0 `# ENV:` defensively.
        if stripped.startswith("# ENV:") and line[:1] == "#":
            i += 1
            continue

        # Docstring block: a bare `"""`/`'''` opener. Scan to its closing
        # delimiter for a column-0 `__Env__` header appended anywhere inside.
        if stripped in ('"""', "'''"):
            delim = stripped
            k = i + 1
            header = None
            while k < n and lines[k].strip() != delim:
                if header is None and lines[k].startswith("__Env__"):
                    header = k
                k += 1
            close = k  # closing-delimiter index (== n if unterminated)

            if header is not None:
                # Prose kept before the `__Env__` section, with the blank /
                # separator line(s) immediately preceding the header trimmed off.
                kept = list(lines[i + 1 : header])
                while kept and kept[-1].strip() == "":
                    kept.pop()
                if any(seg.strip() for seg in kept):
                    # Merged form: keep the opener, the earlier prose and the
                    # closing delimiter; drop the header through the closer's
                    # preceding line.
                    out.append(line)
                    out.extend(kept)
                    if close < n:
                        out.append(lines[close])
                # else: the block holds only the `__Env__` section (standalone
                # fallback) or is emptied by the strip — drop it whole.
                i = close + 1 if close < n else n
                continue

            # A non-`__Env__` docstring block: emit it unchanged, delimiters too.
            out.extend(lines[i : close + 1] if close < n else lines[i:])
            i = close + 1 if close < n else n
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

    A closing docstring does not emit its following code-cell marker until a
    non-blank code line is seen. This prevents adjacent docstrings from
    producing an empty code segment whose duplicate ``# %%`` markers are
    interpreted as literal code by ``ipynb-py-convert``.

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
    pending_code_boundary = False
    pending_lines: List[str] = []

    for line in lines:
        if line.startswith('"""') or line.startswith("'''"):
            if is_in_quotes:
                out.extend(["'''", "\n\n"])
                pending_code_boundary = True
            else:
                if pending_code_boundary:
                    out.extend(pending_lines)
                    pending_lines = []
                    pending_code_boundary = False
                out.extend(["# %%", "\n", "'''\n"])

            is_in_quotes = not is_in_quotes
        elif pending_code_boundary:
            if line.strip():
                out.append("# %%\n")
                out.extend(pending_lines)
                pending_lines = []
                pending_code_boundary = False
                out.append(line)
            else:
                pending_lines.append(line)
        else:
            out.append(line)

    out.extend(pending_lines)
    return out


if __name__ == "__main__":
    _, in_filename, out_filename = argv

    with open(in_filename) as f:
        lines = f.readlines()

    with open(out_filename, "w+") as f:
        f.writelines(add_notebook_quotes(lines))
