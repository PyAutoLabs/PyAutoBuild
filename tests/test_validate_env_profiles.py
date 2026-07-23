"""tests/test_validate_env_profiles.py — the PR-time profile validator.

Migration step 1 of docs/env_profile_redesign.md (#161).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "autohands"))
from validate_env_profiles import (  # noqa: E402
    is_jax_marked,
    resolve_clean,
    validate_workspace,
)


def _workspace(tmp_path, smoke: str, release: str, scripts: list[str]) -> Path:
    (tmp_path / "config" / "build").mkdir(parents=True)
    (tmp_path / "config" / "build" / "env_vars.yaml").write_text(smoke)
    (tmp_path / "config" / "build" / "env_vars_release.yaml").write_text(release)
    for rel in scripts:
        p = tmp_path / "scripts" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# script\n")
    return tmp_path


GOOD_SMOKE = 'defaults:\n  PYAUTO_TEST_MODE: "2"\noverrides: []\n'
GOOD_RELEASE = 'defaults:\n  PYAUTO_TEST_MODE: "0"\noverrides: []\n'


def test_clean_workspace_passes(tmp_path):
    ws = _workspace(tmp_path, GOOD_SMOKE, GOOD_RELEASE, ["imaging/run.py"])
    errors, warnings = validate_workspace(ws)
    assert errors == [] and warnings == []


def test_unknown_top_key_is_an_error(tmp_path):
    ws = _workspace(tmp_path, GOOD_SMOKE + "typo_key: 1\n", GOOD_RELEASE, ["a.py"])
    errors, _ = validate_workspace(ws)
    assert any("unknown top-level key 'typo_key'" in e for e in errors)


def test_dead_pattern_is_an_error(tmp_path):
    smoke = (
        'defaults: {PYAUTO_TEST_MODE: "2"}\n'
        "overrides:\n  - pattern: 'searches/DoesNotExist'\n    unset: [PYAUTO_TEST_MODE]\n"
    )
    ws = _workspace(tmp_path, smoke, GOOD_RELEASE, ["imaging/run.py"])
    errors, _ = validate_workspace(ws)
    assert any("matches no script" in e for e in errors)


def test_malformed_override_is_an_error(tmp_path):
    smoke = "defaults: {}\noverrides:\n  - unset: [X]\n"
    ws = _workspace(tmp_path, smoke, GOOD_RELEASE, ["a.py"])
    errors, _ = validate_workspace(ws)
    assert any("missing 'pattern'" in e for e in errors)


def test_release_disable_jax_override_warns_then_errors(tmp_path):
    release = (
        'defaults: {PYAUTO_DISABLE_JAX: "1"}\n'
        "overrides:\n  - pattern: 'jax_grad/'\n    set: {PYAUTO_DISABLE_JAX: '0'}\n"
    )
    ws = _workspace(tmp_path, GOOD_SMOKE, release, ["jax_grad/run.py"])
    errors, warnings = validate_workspace(ws)
    assert any("derivation" in w for w in warnings) and not any(
        "derivation" in e for e in errors
    )
    errors, _ = validate_workspace(ws, strict_derivation=True)
    assert any("derivation" in e for e in errors)


def test_marker_mismatch_warns_then_errors(tmp_path):
    # A jax-marked script the release profile leaves on NumPy: the vacuous pass.
    release = 'defaults: {PYAUTO_DISABLE_JAX: "1"}\noverrides: []\n'
    ws = _workspace(tmp_path, GOOD_SMOKE, release, ["searches/adam_jax.py"])
    errors, warnings = validate_workspace(ws)
    assert any("JAX-marked script resolves PYAUTO_DISABLE_JAX=1" in w for w in warnings)
    errors, _ = validate_workspace(ws, strict_markers=True)
    assert any("JAX-marked script resolves PYAUTO_DISABLE_JAX=1" in e for e in errors)


def test_jax_on_default_profile_is_not_flagged(tmp_path):
    # autofit's shape: DISABLE_JAX "0" by default — unmarked scripts on JAX is
    # the stated policy there, not a bypass.
    release = 'defaults: {PYAUTO_DISABLE_JAX: "0"}\noverrides: []\n'
    ws = _workspace(tmp_path, GOOD_SMOKE, release, ["imaging/run.py"])
    errors, warnings = validate_workspace(ws)
    assert errors == [] and warnings == []


def test_is_jax_marked_rule():
    assert is_jax_marked(Path("scripts/jax_grad/run.py"))
    assert is_jax_marked(Path("scripts/imaging/visualization_jax.py"))
    assert is_jax_marked(Path("scripts/imaging/modeling_visualization_jit.py"))
    assert not is_jax_marked(Path("scripts/imaging/visualization.py"))
    assert not is_jax_marked(Path("scripts/database/scrape/run.py"))


def test_resolve_clean_ignores_ambient_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PYAUTO_DISABLE_JAX", "1")
    env = resolve_clean(Path("scripts/a.py"), {"defaults": {}})
    assert "PYAUTO_DISABLE_JAX" not in env
