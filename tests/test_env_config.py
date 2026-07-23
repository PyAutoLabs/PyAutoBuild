"""Unit tests for autohands/env_config.py — args_for_script() in particular.

build_env_for_script() is exercised indirectly by
test_workspace_config_precedence.py; here we focus on the args_default
plumbing added for workspaces whose scripts require CLI args (euclid).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
AUTOHANDS_DIR = PROJECT_ROOT / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))

from env_config import args_for_script  # noqa: E402


FAKE_FILE = Path("scripts/fake.py")


def test_args_for_script_none_env_config_returns_empty():
    assert args_for_script(FAKE_FILE, None) == []


def test_args_for_script_missing_key_returns_empty():
    assert args_for_script(FAKE_FILE, {"defaults": {"FOO": "bar"}}) == []


def test_args_for_script_empty_string_returns_empty():
    assert args_for_script(FAKE_FILE, {"args_default": ""}) == []


def test_args_for_script_whitespace_only_returns_empty():
    assert args_for_script(FAKE_FILE, {"args_default": "   \t  "}) == []


def test_args_for_script_simple_args():
    assert args_for_script(
        FAKE_FILE,
        {"args_default": "--dataset=foo --sample=bar"},
    ) == ["--dataset=foo", "--sample=bar"]


def test_args_for_script_quoted_arg_with_space():
    # shlex.split honours quoting so values containing spaces stay together.
    assert args_for_script(
        FAKE_FILE,
        {"args_default": '--name="a b" --flag'},
    ) == ["--name=a b", "--flag"]


# --- scrubbed baseline (docs/env_profile_redesign.md §5, #161 step 3) ---------
import os  # noqa: E402
from env_config import build_env_for_script  # noqa: E402


def test_ambient_pyauto_var_the_profile_is_silent_on_is_scrubbed(monkeypatch):
    # The audit's real leak: an ambient PYAUTO_ var the profile never mentions
    # must NOT reach the script (e.g. a developer's shell rc).
    monkeypatch.setenv("PYAUTO_SKIP_API_GATE", "1")
    env = build_env_for_script(Path("scripts/x.py"), {"defaults": {"PYAUTO_TEST_MODE": "2"}})
    assert "PYAUTO_SKIP_API_GATE" not in env
    assert env["PYAUTO_TEST_MODE"] == "2"


def test_profile_value_wins_over_ambient_for_a_managed_pyauto_key(monkeypatch):
    monkeypatch.setenv("PYAUTO_DISABLE_JAX", "1")
    env = build_env_for_script(Path("scripts/x.py"), {"defaults": {"PYAUTO_DISABLE_JAX": "0"}})
    assert env["PYAUTO_DISABLE_JAX"] == "0"


def test_non_pyauto_infra_vars_pass_through(monkeypatch):
    # Only PYAUTO_* is scrubbed — infra/reproducibility vars are untouched.
    monkeypatch.setenv("NUMBA_CACHE_DIR", "/tmp/numba")
    monkeypatch.setenv("PYTHONPATH", "/libs")
    monkeypatch.setenv("JAX_ENABLE_X64", "True")
    env = build_env_for_script(Path("scripts/x.py"), {"defaults": {"PYAUTO_TEST_MODE": "2"}})
    assert env["NUMBA_CACHE_DIR"] == "/tmp/numba"
    assert env["PYTHONPATH"] == "/libs"
    assert env["JAX_ENABLE_X64"] == "True"


def test_none_config_inherits_unchanged(monkeypatch):
    monkeypatch.setenv("PYAUTO_SKIP_API_GATE", "1")
    assert build_env_for_script(Path("scripts/x.py"), None) is None


# --- JAX-marker derivation (docs/env_profile_redesign.md §3, #161 step 4) -----
from env_config import is_jax_marked  # noqa: E402

DERIVING_RELEASE = {
    "defaults": {"PYAUTO_DISABLE_JAX": "1"},
    "derive_jax_markers": True,
}


def test_derivation_enables_jax_for_marked_script():
    env = build_env_for_script(Path("scripts/jax_assertions/nnls.py"), DERIVING_RELEASE)
    assert env["PYAUTO_DISABLE_JAX"] == "0"


def test_derivation_leaves_unmarked_script_on_default():
    env = build_env_for_script(Path("scripts/imaging/run.py"), DERIVING_RELEASE)
    assert env["PYAUTO_DISABLE_JAX"] == "1"


def test_no_derivation_key_means_no_derivation():
    cfg = {"defaults": {"PYAUTO_DISABLE_JAX": "1"}}
    env = build_env_for_script(Path("scripts/jax_assertions/nnls.py"), cfg)
    assert env["PYAUTO_DISABLE_JAX"] == "1"


def test_derivation_applies_after_overrides():
    # The marker set is derived, never enumerated — an override cannot carve
    # a marked script back out of it.
    cfg = {
        "defaults": {"PYAUTO_DISABLE_JAX": "1"},
        "overrides": [
            {"pattern": "jax_assertions/", "set": {"PYAUTO_DISABLE_JAX": "1"}}
        ],
        "derive_jax_markers": True,
    }
    env = build_env_for_script(Path("scripts/jax_assertions/nnls.py"), cfg)
    assert env["PYAUTO_DISABLE_JAX"] == "0"


def test_is_jax_marked_prefix_suffix_forms():
    assert is_jax_marked(Path("scripts/jax_grad/run.py"))
    assert is_jax_marked(Path("scripts/hessian_jax.py"))
    assert is_jax_marked(Path("scripts/imaging/modeling_visualization_jit.py"))
    assert not is_jax_marked(Path("scripts/imaging/visualization.py"))


def test_is_jax_marked_mid_stem_marker_does_not_match():
    # The decided shape (human, 2026-07-23): mid-stem markers are NOT matched;
    # such files are renamed to carry the suffix (e.g.
    # modeling_visualization_jit_delaunay.py -> ..._delaunay_jit.py).
    assert not is_jax_marked(
        Path("scripts/imaging/modeling_visualization_jit_delaunay.py")
    )
    assert is_jax_marked(
        Path("scripts/imaging/modeling_visualization_delaunay_jit.py")
    )


# --- In-file env declarations (docs/env_profile_redesign.md §10) --------------
import pytest  # noqa: E402
from env_config import (  # noqa: E402
    ENV_DECLARATION_TOKENS,
    apply_profile,
    read_env_declaration,
)


def _write_script(tmp_path, rel, body):
    p = tmp_path / "scripts" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def test_read_declaration_none_when_absent(tmp_path):
    p = _write_script(tmp_path, "imaging/x.py", "import autolens as al\n")
    assert read_env_declaration(p) is None


def test_read_declaration_tokens(tmp_path):
    p = _write_script(tmp_path, "imaging/x.py", "# ENV: jax full_datasets\nimport al\n")
    assert read_env_declaration(p) == ["jax", "full_datasets"]


def test_read_declaration_empty_line_is_no_tokens(tmp_path):
    p = _write_script(tmp_path, "imaging/x.py", "# ENV:\nimport al\n")
    assert read_env_declaration(p) == []


def test_read_declaration_unknown_token_raises(tmp_path):
    p = _write_script(tmp_path, "imaging/x.py", "# ENV: jax nonsense\n")
    with pytest.raises(ValueError, match="unknown env declaration token 'nonsense'"):
        read_env_declaration(p)


def test_read_declaration_duplicate_line_raises(tmp_path):
    p = _write_script(tmp_path, "imaging/x.py", "# ENV: jax\ncode\n# ENV: real_plots\n")
    with pytest.raises(ValueError, match="more than one '# ENV:'"):
        read_env_declaration(p)


def test_read_declaration_anchored_not_mid_line(tmp_path):
    # A '# ENV:' that is not at column 0 (indented / trailing comment) is prose.
    p = _write_script(tmp_path, "imaging/x.py", "code  # ENV: jax\n    # ENV: jax\n")
    assert read_env_declaration(p) is None


def test_real_output_expands_to_all_four(tmp_path):
    assert set(ENV_DECLARATION_TOKENS["real_output"]) == {
        "PYAUTO_DISABLE_JAX",
        "PYAUTO_SMALL_DATASETS",
        "PYAUTO_FAST_PLOTS",
        "PYAUTO_TEST_MODE",
    }
    _write_script(tmp_path, "imaging/x.py", "# ENV: real_output\n")
    cfg = {
        "defaults": {
            "PYAUTO_DISABLE_JAX": "1",
            "PYAUTO_SMALL_DATASETS": "1",
            "PYAUTO_FAST_PLOTS": "1",
            "PYAUTO_TEST_MODE": "2",
            "PYAUTO_SKIP_CHECKS": "1",  # not declarable — survives
        }
    }
    env = apply_profile({}, tmp_path / "scripts" / "imaging" / "x.py", cfg)
    for var in ENV_DECLARATION_TOKENS["real_output"]:
        assert var not in env
    assert env["PYAUTO_SKIP_CHECKS"] == "1"


def test_declaration_unsets_after_default(tmp_path):
    # A profile that pins SMALL_DATASETS=1 + a script declaring full_datasets:
    # the resolved env must LACK the var (falls back to the library default).
    _write_script(tmp_path, "imaging/x.py", "# ENV: full_datasets\ncode\n")
    cfg = {"defaults": {"PYAUTO_SMALL_DATASETS": "1"}}
    env = apply_profile({}, tmp_path / "scripts" / "imaging" / "x.py", cfg)
    assert "PYAUTO_SMALL_DATASETS" not in env


def test_declaration_unsets_after_override(tmp_path):
    # Declarations apply LAST — after an override that sets the var.
    _write_script(tmp_path, "imaging/x.py", "# ENV: jax\ncode\n")
    cfg = {
        "defaults": {},
        "overrides": [{"pattern": "imaging/", "set": {"PYAUTO_DISABLE_JAX": "1"}}],
    }
    env = apply_profile({}, tmp_path / "scripts" / "imaging" / "x.py", cfg)
    assert "PYAUTO_DISABLE_JAX" not in env


def test_declaration_resolves_via_scripts_relative_path(tmp_path, monkeypatch):
    # The per-PR gate passes a path relative to scripts/, with cwd = repo root.
    _write_script(tmp_path, "imaging/x.py", "# ENV: real_search\ncode\n")
    monkeypatch.chdir(tmp_path)
    cfg = {"defaults": {"PYAUTO_TEST_MODE": "2"}}
    env = apply_profile({}, Path("imaging/x.py"), cfg)
    assert "PYAUTO_TEST_MODE" not in env


def test_notebook_entry_maps_to_source_script(tmp_path, monkeypatch):
    # A .ipynb entry resolves the declaration from its .py source under scripts/.
    _write_script(tmp_path, "imaging/x.py", "# ENV: real_plots\ncode\n")
    monkeypatch.chdir(tmp_path)
    cfg = {"defaults": {"PYAUTO_FAST_PLOTS": "1"}}
    env = apply_profile({}, Path("imaging/x.ipynb"), cfg)
    assert "PYAUTO_FAST_PLOTS" not in env


def test_notebook_absolute_path_maps_notebooks_to_scripts(tmp_path):
    # The mega-run notebook runner passes an absolute path under notebooks/.
    _write_script(tmp_path, "imaging/x.py", "# ENV: real_plots\ncode\n")
    nb = tmp_path / "notebooks" / "imaging" / "x.ipynb"
    nb.parent.mkdir(parents=True, exist_ok=True)
    nb.write_text("{}")
    cfg = {"defaults": {"PYAUTO_FAST_PLOTS": "1"}}
    env = apply_profile({}, nb, cfg)
    assert "PYAUTO_FAST_PLOTS" not in env


def test_declaration_absolute_script_path(tmp_path):
    # The mega-run script runner passes an absolute path under scripts/.
    p = _write_script(tmp_path, "imaging/x.py", "# ENV: jax\ncode\n")
    cfg = {"defaults": {"PYAUTO_DISABLE_JAX": "1"}}
    env = apply_profile({}, p, cfg)
    assert "PYAUTO_DISABLE_JAX" not in env


def test_no_declaration_leaves_env_untouched(tmp_path, monkeypatch):
    _write_script(tmp_path, "imaging/x.py", "code only\n")
    monkeypatch.chdir(tmp_path)
    cfg = {"defaults": {"PYAUTO_TEST_MODE": "2"}}
    env = apply_profile({}, Path("imaging/x.py"), cfg)
    assert env["PYAUTO_TEST_MODE"] == "2"


def test_unknown_token_raises_in_resolver(tmp_path):
    p = _write_script(tmp_path, "imaging/x.py", "# ENV: bogus\n")
    with pytest.raises(ValueError, match="unknown env declaration token"):
        apply_profile({}, p, {"defaults": {}})
