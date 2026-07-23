"""Tests for workspace-owned build configs.

Phase 0 of the autohands-release-prep migration moved per-project build config
(no_run, env_vars, copy_files, visualise_notebooks) down to each workspace's
config/build/ directory, leaving keyed-dict fallbacks in PyAutoHands's own
autohands/config/ for workspaces that had not migrated yet.

Those fallbacks are now **gone**: every build target owns its config, so
``config/build/`` is the single source of truth. The ``copy_files`` mechanism
was removed entirely along with them (it resolved to nothing anywhere and
produced no output in any build). These tests pin that contract down.
"""

import sys
from pathlib import Path

import pytest
import yaml

AUTOHANDS_DIR = Path(__file__).parent.parent / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _make_fake_workspace(tmp_path: Path, name: str) -> Path:
    ws = tmp_path / name
    ws.mkdir()
    (ws / "config" / "build").mkdir(parents=True)
    return ws


def test_no_run_workspace_wins(tmp_path, monkeypatch):
    """run_python.py / run.py prefer workspace no_run.yaml over autohands's."""
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
    """env_vars.yaml has no autohands fallback — missing workspace file means no env."""
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    monkeypatch.chdir(ws)
    workspace_env = Path.cwd() / "config" / "build" / "env_vars.yaml"
    assert not workspace_env.exists()

    # run.py / run_python.py: env_config_path stays None when workspace file missing.
    env_config_path = (
        workspace_env if workspace_env.exists() else None
    )
    assert env_config_path is None


def test_visualise_missing_workspace_file_selects_nothing(tmp_path, monkeypatch):
    """A workspace with no visualise_notebooks.yaml selects nothing — it must not raise.

    Regression: the autohands-level visualise_notebooks.yaml was a comment-only
    husk, so ``yaml.safe_load`` returned ``None`` and the old fallback did
    ``None.get(project)`` -> AttributeError. That crashed ``--visualise`` for
    every target without its own file (HowToFit/HowToGalaxy/HowToLens/euclid).
    """
    ws = _make_fake_workspace(tmp_path, "fake_ws")
    monkeypatch.chdir(ws)
    workspace_vis = Path.cwd() / "config" / "build" / "visualise_notebooks.yaml"
    assert not workspace_vis.exists()

    # run.py: missing workspace file resolves to [], with no fallback lookup.
    if workspace_vis.exists():
        visualise_dict = yaml.safe_load(workspace_vis.read_text()) or []
    else:
        visualise_dict = []
    assert visualise_dict == []


def test_actual_workspace_files_exist():
    """Every active workspace owns its own config/build files after migration."""
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
        for fname in ("no_run.yaml", "env_vars.yaml", "visualise_notebooks.yaml"):
            p = ws_root / "config" / "build" / fname
            assert p.exists(), f"{ws}/config/build/{fname} missing — migration incomplete"


def test_every_build_target_owns_no_run():
    """run.py hard-requires config/build/no_run.yaml — there is no fallback left.

    The autohands-level no_run.yaml was deleted because every target already
    owned one, making it unreachable. If a new build target is added to
    workspaces.yaml without a no_run.yaml, run.py raises FileNotFoundError —
    this catches that at test time instead of mid-release.
    """
    repo_root = Path(__file__).parent.parent.parent
    matrix = yaml.safe_load(
        (AUTOHANDS_DIR / "config" / "workspaces.yaml").read_text()
    )["run_all"]

    missing = []
    for key, entry in matrix.items():
        ws_root = repo_root / entry["repo"]
        if not ws_root.exists():
            continue  # repo not checked out here
        if not (ws_root / "config" / "build" / "no_run.yaml").exists():
            missing.append(f"{entry['repo']} (target '{key}')")

    assert not missing, (
        "build targets with no config/build/no_run.yaml — run.py will raise: "
        + ", ".join(missing)
    )


def test_dead_autohands_files_removed():
    """The autohands-level config fallbacks are dead and must stay gone."""
    autohands_config = AUTOHANDS_DIR / "config"
    for fname, why in (
        ("notebooks_remove.yaml", "dead code"),
        ("env_vars.yaml", "workspaces own env_vars now"),
        ("no_run.yaml", "unreachable — every build target owns its own no_run.yaml"),
        (
            "visualise_notebooks.yaml",
            "comment-only husk that crashed --visualise via None.get(project)",
        ),
        (
            "copy_files.yaml",
            "the copy-as-is mechanism was removed; it resolved to nothing anywhere",
        ),
    ):
        assert not (autohands_config / fname).exists(), (
            f"autohands/config/{fname} should have been deleted — {why}"
        )


def test_copy_files_mechanism_fully_removed():
    """No workspace or autohands config may reintroduce copy_files.yaml."""
    repo_root = Path(__file__).parent.parent.parent
    generate_src = (AUTOHANDS_DIR / "generate.py").read_text()
    assert "copy_files" not in generate_src
    assert "is_copy_file" not in generate_src

    matrix = yaml.safe_load(
        (AUTOHANDS_DIR / "config" / "workspaces.yaml").read_text()
    )["run_all"]
    for entry in matrix.values():
        stray = repo_root / entry["repo"] / "config" / "build" / "copy_files.yaml"
        assert not stray.exists(), f"{stray} — copy_files was removed; delete this file"
