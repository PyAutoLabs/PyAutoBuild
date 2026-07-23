"""Regression tests for the path-pattern matchers in autohands.

Both ``env_config._pattern_matches`` and ``build_util.should_skip`` substring-
match against the file's full path including extension. Patterns can therefore
end in ``.py`` to anchor against the script form and avoid clobbering sibling
``_jax`` / ``_jit`` variants. These tests lock in that convention — without
them, the previous bug (substring match against the path with ``.py`` stripped)
silently disabled overrides ending in ``.py``.
"""

from pathlib import Path

from autohands.build_util import should_skip
from autohands.env_config import _pattern_matches


def test_dot_py_pattern_matches_only_the_py_script():
    """Pattern ending in `.py` must NOT also match sibling files whose stem
    starts with the same prefix (e.g. `_jax`, `_jit`)."""
    py_file = Path("scripts/imaging/visualization.py")
    jax_file = Path("scripts/imaging/visualization_jax.py")
    jit_file = Path("scripts/imaging/visualization_jit.py")

    assert _pattern_matches(py_file, "imaging/visualization.py") is True
    assert _pattern_matches(jax_file, "imaging/visualization.py") is False
    assert _pattern_matches(jit_file, "imaging/visualization.py") is False


def test_prefix_pattern_substring_matches_siblings():
    """A pattern without `.py` still substring-matches both the `.py` script
    and `_jax` / `_jit` siblings, because the prefix is shared. Authors who
    want to target only one must anchor with `.py`."""
    py_file = Path("scripts/imaging/visualization.py")
    jax_file = Path("scripts/imaging/visualization_jax.py")

    assert _pattern_matches(py_file, "imaging/visualization") is True
    assert _pattern_matches(jax_file, "imaging/visualization") is True
    # _jax-specific pattern only matches the _jax file.
    assert _pattern_matches(py_file, "imaging/visualization_jax") is False
    assert _pattern_matches(jax_file, "imaging/visualization_jax") is True


def test_stem_pattern_matches_exactly():
    """Patterns without `/` must match the file stem exactly — not as a
    substring."""
    assert _pattern_matches(Path("scripts/a/foo.py"), "foo") is True
    assert _pattern_matches(Path("scripts/a/foobar.py"), "foo") is False
    assert _pattern_matches(Path("scripts/a/foo.py"), "foo.py") is False


def test_directory_pattern_matches_anything_in_directory():
    """A pattern ending in `/` matches every script under that directory."""
    assert _pattern_matches(Path("scripts/aggregator/test_x.py"), "aggregator/") is True
    assert _pattern_matches(Path("scripts/foo/bar.py"), "aggregator/") is False


def test_should_skip_uses_same_convention():
    """`should_skip` shares the convention with `_pattern_matches`; the same
    `.py` anchoring works there."""
    no_run = ["imaging/visualization.py"]
    assert should_skip(Path("scripts/imaging/visualization.py"), no_run) is True
    assert should_skip(Path("scripts/imaging/visualization_jax.py"), no_run) is False


def test_should_skip_stem_pattern():
    no_run = ["foo"]
    assert should_skip(Path("scripts/a/foo.py"), no_run) is True
    assert should_skip(Path("scripts/a/foobar.py"), no_run) is False


def test_should_skip_directory_pattern():
    no_run = ["aggregator/"]
    assert should_skip(Path("scripts/aggregator/test_x.py"), no_run) is True
    assert should_skip(Path("scripts/foo/bar.py"), no_run) is False


def test_should_skip_empty_list():
    assert should_skip(Path("scripts/a/foo.py"), []) is False
