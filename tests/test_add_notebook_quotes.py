"""Regression tests for narrative-docstring notebook cell boundaries."""

import json
import sys
from pathlib import Path


AUTOHANDS_DIR = Path(__file__).parent.parent / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))

from add_notebook_quotes import add_notebook_quotes  # noqa: E402


ADJACENT_SCRIPT = (
    '"""\n'
    "__First__\n"
    '"""\n'
    "\n"
    '"""\n'
    "__Second__\n"
    '"""\n'
    "\n"
    "value = 1\n"
    "\n"
    '"""\n'
    "__Third__\n"
    '"""\n'
)


def _lines(text: str):
    return text.splitlines(keepends=True)


def test_adjacent_docstrings_do_not_emit_an_empty_code_cell_boundary():
    converted = "".join(add_notebook_quotes(_lines(ADJACENT_SCRIPT)))

    assert "# %%\n\n# %%" not in converted
    assert converted.count("# %%") == 4


def test_adjacent_docstrings_generate_separate_markdown_cells(tmp_path, monkeypatch):
    import build_util

    script = tmp_path / "adjacent.py"
    script.write_text(ADJACENT_SCRIPT)
    monkeypatch.chdir(tmp_path)

    notebook_path = build_util.py_to_notebook(script)
    notebook = json.loads(notebook_path.read_text())

    assert [cell["cell_type"] for cell in notebook["cells"]] == [
        "markdown",
        "markdown",
        "code",
        "markdown",
    ]
    assert "__First__" in "".join(notebook["cells"][0]["source"])
    assert "__Second__" in "".join(notebook["cells"][1]["source"])
    assert "value = 1" in "".join(notebook["cells"][2]["source"])

    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            source = "".join(cell["source"])
            assert "# %%" not in source
            assert "'''" not in source
