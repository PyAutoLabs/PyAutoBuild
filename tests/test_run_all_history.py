"""Tests for the persistent timestamped-run layout in run_all.py.

The release-prep flow keeps every run on disk under
PyAutoHands/test_results/runs/<UTC-timestamp>/ and updates a `latest`
symlink on success. These tests use the helper functions directly so
we don't have to spawn subprocesses.
"""

import sys
from pathlib import Path

import pytest

AUTOHANDS_DIR = Path(__file__).parent.parent / "autohands"
sys.path.insert(0, str(AUTOHANDS_DIR))

import run_all  # noqa: E402


def test_workspaces_dict_has_ten_entries():
    """All 10 active workspaces (6 main + 3 HowTo + euclid pipeline) must be enumerable."""
    expected = {
        "autofit",
        "autogalaxy",
        "autolens",
        "autofit_test",
        "autogalaxy_test",
        "autolens_test",
        "howtofit",
        "howtogalaxy",
        "howtolens",
        "euclid",
    }
    assert set(run_all.WORKSPACES.keys()) == expected
    assert run_all.WORKSPACES["autogalaxy_test"][0] == "autogalaxy_workspace_test"
    assert run_all.WORKSPACES["autogalaxy_test"][1] == "autogalaxy_test"
    assert run_all.WORKSPACES["howtolens"][0] == "HowToLens"
    assert run_all.WORKSPACES["howtolens"][1] == "howtolens"
    assert run_all.WORKSPACES["euclid"][0] == "euclid_strong_lens_modeling_pipeline"
    assert run_all.WORKSPACES["euclid"][1] == "euclid"


def test_default_timeout_is_300():
    assert run_all.DEFAULT_TIMEOUT_SECS == 300


def test_utc_run_timestamp_format():
    ts = run_all.utc_run_timestamp()
    # Format: YYYY-MM-DDTHH-MM-SSZ — 20 chars
    assert len(ts) == 20
    assert ts.endswith("Z")
    assert ts[4] == "-" and ts[10] == "T"


def test_update_latest_symlink_creates_and_replaces(tmp_path, monkeypatch):
    """update_latest_symlink writes a fresh symlink and replaces an existing one."""
    base = tmp_path / "test_results"
    base.mkdir()
    monkeypatch.setattr(run_all, "RESULTS_BASE", base)

    first = base / "runs" / "2026-04-29T10-00-00Z"
    first.mkdir(parents=True)
    run_all.update_latest_symlink(first)

    latest = base / "latest"
    assert latest.is_symlink()
    assert latest.resolve() == first.resolve()

    second = base / "runs" / "2026-04-29T11-00-00Z"
    second.mkdir(parents=True)
    run_all.update_latest_symlink(second)

    assert latest.is_symlink()
    assert latest.resolve() == second.resolve()


def test_update_latest_symlink_cleans_tmp(tmp_path, monkeypatch):
    """A leftover .latest.tmp from a previous crash should be cleared."""
    base = tmp_path / "test_results"
    base.mkdir()
    monkeypatch.setattr(run_all, "RESULTS_BASE", base)

    leftover_tmp = base / ".latest.tmp"
    stale_target = base / "runs" / "stale"
    stale_target.mkdir(parents=True)
    leftover_tmp.symlink_to(stale_target)

    fresh = base / "runs" / "fresh"
    fresh.mkdir()
    run_all.update_latest_symlink(fresh)

    latest = base / "latest"
    assert latest.resolve() == fresh.resolve()
    assert not leftover_tmp.exists()
