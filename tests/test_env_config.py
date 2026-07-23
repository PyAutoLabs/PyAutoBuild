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
