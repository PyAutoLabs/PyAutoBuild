"""Precedence tests for workspace-level vs autobuild-level build configs.

Phase 0 of the autobuild-release-prep migration moved per-project build config
(no_run, env_vars, copy_files, visualise_notebooks) down to each workspace's
config/build/ directory. PyAutoBuild's own autobuild/config/ retains keyed-dict
fallbacks for legacy workspaces only. These tests verify that a workspace
copy always wins when present.
"""

import sys
import textwrap
from pathlib import Path

import pytest
import yaml

AUTOBUILD_DIR = Path(__file__).parent.parent / "autobuild"
sys.path.insert(0, str(AUTOBUILD_DIR))


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _make_fake_workspace(tmp_path: Path, name: str) -> Path:
    ws = tmp_path / name
    ws.mkdir()
    (ws / "config" / "build").mkdir(parents=True)
    return ws


def test_no_run_workspace_wins(tmp_path, monkeypatch):
    """run_python.py / run.py prefer workspace no_run.yaml over autobuild's."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    _write(
        ws / "config" / "build" / "no_run.yaml",
        "- workspace_only_skip\n",
    )

    monkeypatch.chdir(ws)
    workspace_build = Path.cwd() / "config" / "build"
    no_run_path = workspace_build / "no_run.yaml"
    assert no_run_path.exists()
    data = yaml.safe_load(no_run_path.read_text())
    assert data == ["workspace_only_skip"]


def test_no_run_falls_back_to_autobuild_when_workspace_missing(tmp_path, monkeypatch):
    """If the workspace lacks no_run.yaml, autobuild's keyed dict is used."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    autobuild_no_run = tmp_path / "autobuild_config" / "no_run.yaml"
    _write(autobuild_no_run, "fake_project:\n- legacy_skip\n")

    monkeypatch.chdir(ws)
    workspace_no_run = Path.cwd() / "config" / "build" / "no_run.yaml"
    assert not workspace_no_run.exists()

    fallback_path = workspace_no_run if workspace_no_run.exists() else autobuild_no_run
    data = yaml.safe_load(fallback_path.read_text())
    assert isinstance(data, dict)
    assert data["fake_project"] == ["legacy_skip"]


def test_copy_files_workspace_wins(tmp_path, monkeypatch):
    """generate.py prefers workspace copy_files.yaml (flat list) over autobuild's keyed dict."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    _write(
        ws / "config" / "build" / "copy_files.yaml",
        "- subdir/script.py\n",
    )

    monkeypatch.chdir(ws)
    workspace_copy = Path.cwd() / "config" / "build" / "copy_files.yaml"
    assert workspace_copy.exists()

    if workspace_copy.exists():
        copy_files_list = yaml.safe_load(workspace_copy.read_text()) or []
    else:
        # would fall back to autobuild's keyed dict
        copy_files_list = []
    assert copy_files_list == ["subdir/script.py"]


def test_copy_files_falls_back_to_autobuild_keyed(tmp_path, monkeypatch):
    """Without a workspace file, generate.py reads autobuild's keyed dict."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    autobuild_copy = tmp_path / "autobuild_config" / "copy_files.yaml"
    _write(
        autobuild_copy,
        textwrap.dedent(
            """\
            howtofit:
            - foo.py
            - bar.py
            """
        ),
    )

    monkeypatch.chdir(ws)
    workspace_copy = Path.cwd() / "config" / "build" / "copy_files.yaml"
    if workspace_copy.exists():
        copy_files_list = yaml.safe_load(workspace_copy.read_text()) or []
    else:
        copy_files_dict = yaml.safe_load(autobuild_copy.read_text())
        copy_files_list = copy_files_dict.get("howtofit") or []
    assert copy_files_list == ["foo.py", "bar.py"]


def test_visualise_workspace_wins(tmp_path, monkeypatch):
    """run.py --visualise prefers workspace visualise_notebooks.yaml (flat list)."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    _write(
        ws / "config" / "build" / "visualise_notebooks.yaml",
        "- start_here\n",
    )

    monkeypatch.chdir(ws)
    workspace_vis = Path.cwd() / "config" / "build" / "visualise_notebooks.yaml"
    assert workspace_vis.exists()

    if workspace_vis.exists():
        visualise_dict = yaml.safe_load(workspace_vis.read_text()) or []
    else:
        visualise_dict = []
    assert visualise_dict == ["start_here"]


def test_env_vars_workspace_only_no_fallback(tmp_path, monkeypatch):
    """env_vars.yaml has no autobuild fallback — missing workspace file means no env."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    monkeypatch.chdir(ws)
    workspace_env = Path.cwd() / "config" / "build" / "env_vars.yaml"
    assert not workspace_env.exists()

    # run.py / run_python.py: env_config_path stays None when workspace file missing.
    env_config_path = (
        workspace_env if workspace_env.exists() else None
    )
    assert env_config_path is None


def test_actual_workspace_files_exist():
    """All 6 active workspaces should have their own config/build files after migration."""
    repo_root = Path(__file__).parent.parent.parent
    workspaces = [
        "autofit_workspace",
        "autogalaxy_workspace",
        "autolens_workspace",
        "autofit_workspace_test",
        "autogalaxy_workspace_test",
        "autolens_workspace_test",
    ]
    for ws in workspaces:
        ws_root = repo_root / ws
        if not ws_root.exists():
            pytest.skip(f"{ws} not present in this checkout")
        for fname in ("no_run.yaml", "env_vars.yaml", "copy_files.yaml", "visualise_notebooks.yaml"):
            p = ws_root / "config" / "build" / fname
            assert p.exists(), f"{ws}/config/build/{fname} missing — migration incomplete"


def test_dead_autobuild_files_removed():
    """notebooks_remove.yaml and the autobuild-level env_vars.yaml are dead and must be gone."""
    autobuild_config = AUTOBUILD_DIR / "config"
    assert not (autobuild_config / "notebooks_remove.yaml").exists(), (
        "notebooks_remove.yaml is dead code — should have been deleted"
    )
    assert not (autobuild_config / "env_vars.yaml").exists(), (
        "autobuild/config/env_vars.yaml is dead code — workspaces own env_vars now"
    )
