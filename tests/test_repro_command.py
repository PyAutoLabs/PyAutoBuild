"""Tests for autohands/repro_command.py.

These mirror the tmp_path + monkeypatch.chdir pattern used by
test_workspace_config_precedence.py — build a fake workspace tree,
run the helper, assert the emitted command string.
"""

import sys
from pathlib import Path

import pytest

AUTOHANDS_DIR = Path(__file__).parent.parent / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))

import repro_command  # noqa: E402


def _make_fake_workspace(tmp_path: Path, name: str, env_yaml: str) -> Path:
    ws = tmp_path / name
    (ws / "config" / "build").mkdir(parents=True)
    (ws / "config" / "build" / "env_vars.yaml").write_text(env_yaml)
    (ws / "scripts" / "imaging").mkdir(parents=True)
    return ws


def test_emits_env_prefix_from_defaults(tmp_path):
    ws = _make_fake_workspace(
        tmp_path,
        "fake_ws",
        """\
defaults:
  PYAUTO_TEST_MODE: "2"
  JAX_ENABLE_X64: "True"
""",
    )
    script = ws / "scripts" / "imaging" / "modeling.py"
    script.write_text("# placeholder\n")

    cmd = repro_command.repro_command(str(script))

    assert cmd.startswith("(cd fake_ws && env ")
    assert "PYAUTO_TEST_MODE=2" in cmd
    assert "JAX_ENABLE_X64=True" in cmd
    assert cmd.endswith("python3 scripts/imaging/modeling.py)")


def test_override_set_takes_precedence_over_default(tmp_path):
    ws = _make_fake_workspace(
        tmp_path,
        "fake_ws",
        """\
defaults:
  PYAUTO_TEST_MODE: "2"
overrides:
  - pattern: "imaging/"
    set:
      PYAUTO_TEST_MODE: "0"
""",
    )
    script = ws / "scripts" / "imaging" / "modeling.py"
    script.write_text("# placeholder\n")

    cmd = repro_command.repro_command(str(script))

    assert "PYAUTO_TEST_MODE=0" in cmd
    assert "PYAUTO_TEST_MODE=2" not in cmd


def test_override_unset_removes_default(tmp_path):
    ws = _make_fake_workspace(
        tmp_path,
        "fake_ws",
        """\
defaults:
  PYAUTO_TEST_MODE: "2"
  PYAUTO_SMALL_DATASETS: "1"
overrides:
  - pattern: "imaging/"
    unset: [PYAUTO_SMALL_DATASETS]
""",
    )
    script = ws / "scripts" / "imaging" / "modeling.py"
    script.write_text("# placeholder\n")

    cmd = repro_command.repro_command(str(script))

    assert "PYAUTO_TEST_MODE=2" in cmd
    assert "PYAUTO_SMALL_DATASETS" not in cmd


def test_no_overrides_match_just_defaults(tmp_path):
    ws = _make_fake_workspace(
        tmp_path,
        "fake_ws",
        """\
defaults:
  KEY_A: "1"
overrides:
  - pattern: "guides/"
    unset: [KEY_A]
""",
    )
    script = ws / "scripts" / "imaging" / "modeling.py"
    script.write_text("# placeholder\n")

    cmd = repro_command.repro_command(str(script))

    assert "KEY_A=1" in cmd


def test_script_not_found_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="script not found"):
        repro_command.repro_command(str(tmp_path / "nope.py"))


def test_no_workspace_root_raises(tmp_path):
    orphan = tmp_path / "orphan.py"
    orphan.write_text("# no workspace above me\n")
    with pytest.raises(FileNotFoundError, match="no workspace root"):
        repro_command.repro_command(str(orphan))


def test_empty_env_config_emits_no_env_prefix(tmp_path):
    ws = tmp_path / "fake_ws"
    (ws / "config" / "build").mkdir(parents=True)
    (ws / "config" / "build" / "env_vars.yaml").write_text("# empty\n")
    script_dir = ws / "scripts"
    script_dir.mkdir()
    script = script_dir / "foo.py"
    script.write_text("# placeholder\n")

    cmd = repro_command.repro_command(str(script))

    assert cmd == "(cd fake_ws && python3 scripts/foo.py)"
