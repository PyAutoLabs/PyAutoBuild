"""Tests for stripping in-file env declarations from generated artefacts.

The ``__Env__`` docstring section (and the legacy ``# ENV:`` comment) are
developer-only test-harness configuration (docs/env_profile_redesign.md §10) and
must never appear in a generated notebook or markdown page. The strip lives in
``add_notebook_quotes.strip_env_declarations``, the single shared layer that
both notebook generation (``generate.py``) and markdown generation
(``generate_markdown.py``) route through via ``build_util.py_to_notebook``, and
that ``navigator`` reuses to segment docstrings.
"""

import subprocess
import sys
from pathlib import Path

AUTOHANDS_DIR = Path(__file__).parent.parent / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))

from add_notebook_quotes import (  # noqa: E402
    add_notebook_quotes,
    strip_env_declarations,
)


def _lines(text: str):
    return text.splitlines(keepends=True)


BOTTOM_SECTION_SCRIPT = (
    '"""\n'
    'Imaging Example\n'
    '===============\n'
    '"""\n'
    'import autolens as al\n'
    '\n'
    'al.do_something()\n'
    '\n'
    '"""\n'
    '__Env__ (Developer Only)\n'
    '\n'
    'Not user documentation: this section configures the test harness.\n'
    '\n'
    'ENV: full_datasets\n'
    '"""\n'
)

TOP_SECTION_SCRIPT = (
    '"""\n'
    'Test Script\n'
    '===========\n'
    '"""\n'
    '"""\n'
    '__Env__\n'
    '\n'
    'Test-harness configuration.\n'
    '\n'
    'ENV: jax\n'
    '"""\n'
    'import autolens as al\n'
    '\n'
    'al.do_something()\n'
)

COMMENT_SCRIPT = (
    '"""\n'
    'Imaging Example\n'
    '===============\n'
    '"""\n'
    '# ENV: full_datasets\n'
    '# rationale line that must also be dropped is NOT part of ENV strip\n'
    'import autolens as al\n'
)


MERGED_BOTTOM_SCRIPT = (
    '"""\n'
    'Imaging Example\n'
    '===============\n'
    '"""\n'
    'import autolens as al\n'
    '\n'
    'al.do_something()\n'
    '\n'
    '"""\n'
    'Wrap Up\n'
    '-------\n'
    '\n'
    'Closing prose about what to try next.\n'
    '\n'
    '__Env__ (Developer Only)\n'
    '\n'
    'Not user documentation: this section configures the test harness.\n'
    '\n'
    'ENV: full_datasets\n'
    '"""\n'
)

MERGED_MODULE_SCRIPT = (
    '"""\n'
    'Test Script\n'
    '===========\n'
    '\n'
    'Overview of what this integration test does.\n'
    '\n'
    '__Env__\n'
    '\n'
    'Test-harness configuration.\n'
    '\n'
    'ENV: jax\n'
    '"""\n'
    'import autolens as al\n'
    '\n'
    'al.do_something()\n'
)

EMPTIED_BLOCK_SCRIPT = (
    'import autolens as al\n'
    '\n'
    '"""\n'
    '\n'
    '__Env__\n'
    '\n'
    'ENV: jax\n'
    '"""\n'
    'al.do_something()\n'
)


def _assert_no_env_leak(joined: str):
    assert "__Env__" not in joined
    assert "ENV:" not in joined
    assert "Developer Only" not in joined
    assert "test harness" not in joined


def test_strip_removes_bottom_env_section():
    out = "".join(strip_env_declarations(_lines(BOTTOM_SECTION_SCRIPT)))
    _assert_no_env_leak(out)
    # The real content survives untouched.
    assert "Imaging Example" in out
    assert "al.do_something()" in out
    # The dangling separator blank line is trimmed; file ends on real content.
    assert out.endswith("al.do_something()\n")


def test_strip_removes_top_env_section_keeps_module_docstring():
    out = "".join(strip_env_declarations(_lines(TOP_SECTION_SCRIPT)))
    _assert_no_env_leak(out)
    assert "Test Script" in out  # module docstring preserved
    assert "al.do_something()" in out


def test_strip_removes_merged_section_at_end_of_final_docstring():
    # Merged form: `__Env__` appended INSIDE the final docstring. The docstring's
    # earlier prose and its delimiters survive; only the section is dropped.
    out = "".join(strip_env_declarations(_lines(MERGED_BOTTOM_SCRIPT)))
    _assert_no_env_leak(out)
    assert "Imaging Example" in out
    assert "Wrap Up" in out
    assert "Closing prose about what to try next." in out
    # The docstring that carried the section keeps its closing delimiter.
    assert out.rstrip().endswith('"""')


def test_strip_removes_merged_section_at_end_of_module_docstring():
    out = "".join(strip_env_declarations(_lines(MERGED_MODULE_SCRIPT)))
    _assert_no_env_leak(out)
    assert "Test Script" in out
    assert "Overview of what this integration test does." in out
    assert "al.do_something()" in out


def test_strip_standalone_fallback_removes_whole_block():
    # A docstring holding ONLY the `__Env__` section (the standalone fallback)
    # is removed whole — the existing bottom/top fixtures are this shape.
    out = "".join(strip_env_declarations(_lines(BOTTOM_SECTION_SCRIPT)))
    _assert_no_env_leak(out)
    assert '"""' in out  # the module docstring block is untouched
    assert "Imaging Example" in out


def test_strip_emptied_docstring_block_is_removed_whole():
    # When the section is the block's only real content (prose before it is just
    # a separator), stripping must NOT leave an empty `"""` ... `"""` pair.
    out = "".join(strip_env_declarations(_lines(EMPTIED_BLOCK_SCRIPT)))
    _assert_no_env_leak(out)
    assert '"""' not in out  # no dangling empty docstring
    assert "import autolens as al" in out
    assert "al.do_something()" in out


def test_strip_removes_comment_form():
    out = "".join(strip_env_declarations(_lines(COMMENT_SCRIPT)))
    assert "# ENV:" not in out
    assert "import autolens as al" in out


def test_add_notebook_quotes_drops_env_section():
    # The full generation tokenizer (used by py_to_notebook and navigator) must
    # not carry any __Env__/ENV content into its output.
    out = "".join(add_notebook_quotes(_lines(BOTTOM_SECTION_SCRIPT)))
    _assert_no_env_leak(out)
    # The module docstring is still wrapped into a cell.
    assert "Imaging Example" in out


def test_py_to_notebook_generates_no_env_content(tmp_path, monkeypatch):
    # End-to-end through build_util.py_to_notebook -> the generated .ipynb must
    # contain no __Env__/ENV content.
    import json

    import build_util

    script = tmp_path / "example.py"
    script.write_text(BOTTOM_SECTION_SCRIPT)
    monkeypatch.chdir(tmp_path)

    notebook = build_util.py_to_notebook(script)
    text = Path(notebook).read_text()
    _assert_no_env_leak(text)
    # Sanity: it is a real notebook with the surviving content.
    data = json.loads(text)
    assert data["cells"]
    assert "Imaging Example" in text


def test_navigator_ignores_env_section(tmp_path):
    # An `__Env__` section (top or bottom) must not become a catalogue block,
    # and must not corrupt the header parse.
    import navigator

    script = tmp_path / "scripts" / "imaging" / "x.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        '"""\n'
        'Imaging Example\n'
        '===============\n'
        '\n'
        'A one-line summary of the example.\n'
        '"""\n'
        'import autolens as al\n'
        '\n'
        '"""\n'
        '__Env__ (Developer Only)\n'
        '\n'
        'harness config.\n'
        '\n'
        'ENV: full_datasets\n'
        '"""\n'
    )
    blocks = navigator._docstring_blocks(script)
    for block in blocks:
        joined = "\n".join(block)
        assert "__Env__" not in joined
        assert "ENV:" not in joined
    title, summary, _ = navigator._parse_header(blocks[0])
    assert title == "Imaging Example"
    assert "one-line summary" in summary
