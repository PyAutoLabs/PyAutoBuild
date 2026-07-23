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
    """Build a workspace with the canonical profile_*.yaml names (the only
    layout accepted since #161 step-6 stage 3)."""
    (tmp_path / "config" / "build").mkdir(parents=True)
    (tmp_path / "config" / "build" / "profile_smoke.yaml").write_text(smoke)
    (tmp_path / "config" / "build" / "profile_release.yaml").write_text(release)
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


def test_legacy_name_is_an_error(tmp_path):
    # A workspace that kept the dead env_vars.yaml name errors — the old names
    # died at step-6 stage 3 and must not creep back.
    ws = _workspace(tmp_path, GOOD_SMOKE, GOOD_RELEASE, ["imaging/run.py"])
    (ws / "config" / "build" / "env_vars.yaml").write_text(GOOD_SMOKE)
    errors, _ = validate_workspace(ws)
    assert any(
        "legacy env_vars.yaml found — renamed to profile_smoke.yaml" in e
        for e in errors
    )


def test_missing_smoke_profile_is_an_error(tmp_path):
    # The smoke profile is the universal contract — its absence errors.
    (tmp_path / "config" / "build").mkdir(parents=True)
    (tmp_path / "config" / "build" / "profile_release.yaml").write_text(GOOD_RELEASE)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("# script\n")
    errors, _ = validate_workspace(tmp_path)
    assert any("profile_smoke.yaml: missing" in e for e in errors)


def test_smoke_only_workspace_passes(tmp_path):
    # The release profile is optional: smoke-only workspaces (HowTo*) are a
    # legitimate shape and must validate clean on their smoke profile alone.
    (tmp_path / "config" / "build").mkdir(parents=True)
    (tmp_path / "config" / "build" / "profile_smoke.yaml").write_text(GOOD_SMOKE)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run.py").write_text("# script\n")
    errors, warnings = validate_workspace(tmp_path)
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


# --- derive_jax_markers (docs/env_profile_redesign.md §3, #161 step 4) --------

DERIVING_RELEASE = (
    'defaults: {PYAUTO_DISABLE_JAX: "1"}\nderive_jax_markers: true\n'
)


def test_deriving_profile_is_accepted_and_marked_scripts_resolve_jax(tmp_path):
    ws = _workspace(
        tmp_path, GOOD_SMOKE, DERIVING_RELEASE, ["jax_assertions/nnls.py", "imaging/run.py"]
    )
    errors, warnings = validate_workspace(ws, strict_derivation=True, strict_markers=True)
    assert errors == [] and warnings == []
    cfg = {"defaults": {"PYAUTO_DISABLE_JAX": "1"}, "derive_jax_markers": True}
    assert resolve_clean(Path("scripts/jax_assertions/nnls.py"), cfg) == {
        "PYAUTO_DISABLE_JAX": "0"
    }
    assert resolve_clean(Path("scripts/imaging/run.py"), cfg) == {
        "PYAUTO_DISABLE_JAX": "1"
    }


def test_non_bool_derive_jax_markers_is_an_error(tmp_path):
    # A quoted "true" is a truthy str, and a quoted "false" would be too —
    # the resolver would silently derive either way, so the type is enforced.
    release = 'defaults: {PYAUTO_DISABLE_JAX: "1"}\nderive_jax_markers: "false"\n'
    ws = _workspace(tmp_path, GOOD_SMOKE, release, ["imaging/run.py"])
    errors, _ = validate_workspace(ws)
    assert any("derive_jax_markers must be a YAML bool" in e for e in errors)


def test_init_py_is_not_a_script(tmp_path):
    # Package inits are plumbing the runner never executes — a marked
    # jax_assertions/__init__.py must not trip the marker check.
    release = 'defaults: {PYAUTO_DISABLE_JAX: "1"}\noverrides: []\n'
    ws = _workspace(tmp_path, GOOD_SMOKE, release, ["jax_assertions/__init__.py"])
    errors, warnings = validate_workspace(ws, strict_markers=True)
    assert errors == [] and warnings == []


# --- In-file declarations (docs/env_profile_redesign.md §10) ------------------


def _write(ws: Path, rel: str, body: str) -> None:
    p = ws / "scripts" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_unknown_declaration_token_is_an_error(tmp_path):
    ws = _workspace(tmp_path, GOOD_SMOKE, GOOD_RELEASE, ["imaging/run.py"])
    _write(ws, "imaging/run.py", "# ENV: jax bogus\ncode\n")
    errors, _ = validate_workspace(ws)
    assert any("unknown env declaration token 'bogus'" in e for e in errors)


def test_duplicate_declaration_line_is_an_error(tmp_path):
    ws = _workspace(tmp_path, GOOD_SMOKE, GOOD_RELEASE, ["imaging/run.py"])
    _write(ws, "imaging/run.py", "# ENV: jax\ncode\n# ENV: real_plots\n")
    errors, _ = validate_workspace(ws)
    assert any("more than one '# ENV:'" in e for e in errors)


def test_valid_declaration_passes_and_round_trips(tmp_path):
    # A script declaring full_datasets against a profile that pins
    # SMALL_DATASETS=1: valid syntax, and the round-trip check confirms the
    # resolved env drops the var.
    smoke = 'defaults: {PYAUTO_TEST_MODE: "2", PYAUTO_SMALL_DATASETS: "1"}\noverrides: []\n'
    ws = _workspace(tmp_path, smoke, GOOD_RELEASE, ["imaging/run.py"])
    _write(ws, "imaging/run.py", "# ENV: full_datasets\ncode\n")
    errors, warnings = validate_workspace(ws)
    assert errors == [] and warnings == []
    assert "PYAUTO_SMALL_DATASETS" not in resolve_clean(
        ws / "scripts" / "imaging" / "run.py",
        {"defaults": {"PYAUTO_SMALL_DATASETS": "1"}},
    )


def test_strict_declarations_flags_pure_declarable_unset(tmp_path):
    # An override that only unsets declarable vars (no set:) is migratable.
    smoke = (
        'defaults: {PYAUTO_TEST_MODE: "2"}\n'
        "overrides:\n  - pattern: 'guides/'\n    unset: [PYAUTO_TEST_MODE]\n"
    )
    ws = _workspace(tmp_path, smoke, GOOD_RELEASE, ["guides/run.py"])
    errors, _ = validate_workspace(ws)  # default off
    assert not any("--strict-declarations" in e for e in errors)
    errors, _ = validate_workspace(ws, strict_declarations=True)
    assert any("--strict-declarations" in e for e in errors)


def test_strict_declarations_skips_jax_unset_on_unmarked_scripts(tmp_path):
    # An override unsetting PYAUTO_DISABLE_JAX that matches a NON-jax-marked
    # script is not migratable: a profile-agnostic `jax` declaration would flip
    # release "1" -> absent (numpy -> JAX) on that script — outside the
    # verified "0" -> absent equivalence class. Must NOT be flagged.
    smoke = (
        'defaults: {PYAUTO_DISABLE_JAX: "1"}\n'
        "overrides:\n"
        "  - pattern: 'database/scrape/'\n    unset: [PYAUTO_DISABLE_JAX]\n"
    )
    ws = _workspace(
        tmp_path,
        smoke,
        GOOD_RELEASE,
        ["database/scrape/general.py", "database/scrape/slam_general_jax.py"],
    )
    errors, _ = validate_workspace(ws, strict_declarations=True)
    assert not any("--strict-declarations" in e for e in errors)

    # Same override shape matching ONLY jax-marked scripts stays flagged.
    smoke_marked = (
        'defaults: {PYAUTO_DISABLE_JAX: "1"}\n'
        "overrides:\n"
        "  - pattern: 'jax_grad/'\n    unset: [PYAUTO_DISABLE_JAX]\n"
    )
    ws2 = _workspace(
        tmp_path / "marked", smoke_marked, GOOD_RELEASE, ["jax_grad/imaging.py"]
    )
    errors2, _ = validate_workspace(ws2, strict_declarations=True)
    assert any("--strict-declarations" in e for e in errors2)


def test_strict_declarations_ignores_mixed_and_set_overrides(tmp_path):
    # unset includes a NON-declarable var -> not fully migratable -> not flagged.
    # a set: clause -> not a pure unset -> not flagged.
    smoke = (
        'defaults: {PYAUTO_TEST_MODE: "2"}\n'
        "overrides:\n"
        "  - pattern: 'guides/'\n    unset: [PYAUTO_TEST_MODE, PYAUTO_SKIP_FIT_OUTPUT]\n"
        "  - pattern: 'imaging/'\n    set: {PYAUTO_TEST_MODE: '1'}\n"
    )
    ws = _workspace(tmp_path, smoke, GOOD_RELEASE, ["guides/run.py", "imaging/run.py"])
    errors, _ = validate_workspace(ws, strict_declarations=True)
    assert not any("--strict-declarations" in e for e in errors)
