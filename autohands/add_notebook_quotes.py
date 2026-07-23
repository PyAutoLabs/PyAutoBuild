#!/usr/bin/env python
"""
Usage
./add_notebook_quotes.py /path/to/input /path/to/output
"""

from typing import Iterable

from sys import argv


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
