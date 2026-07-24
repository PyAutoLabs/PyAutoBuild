"""Tests for the persistent timestamped-run layout in run_all.py.

The release-prep flow keeps every run on disk under
PyAutoHands/run_logs/runs/<run-type>/<YYYY>/<MM>/<UTC-timestamp>/, updates a
`latest` symlink on success, and refreshes an index.md + AGENTS.md. These
tests use the helper functions directly so we don't have to spawn
subprocesses.
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
    base = tmp_path / "run_logs"
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
    base = tmp_path / "run_logs"
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


def test_default_run_type_is_smoke():
    assert run_all.DEFAULT_RUN_TYPE == "smoke"


def test_run_dir_for_nests_type_year_zero_padded_month(tmp_path):
    """run_dir_for → <base>/runs/<run-type>/<YYYY>/<MM>/<timestamp>/ with a
    zero-padded month so lexical order is chronological."""
    base = tmp_path / "run_logs"
    rd = run_all.run_dir_for("2026-04-29T14-48-47Z", "smoke", base)
    assert rd.relative_to(base.resolve()).parts == (
        "runs",
        "smoke",
        "2026",
        "04",
        "2026-04-29T14-48-47Z",
    )
    # A release-type run lands under a distinct run-type segment.
    rel = run_all.run_dir_for("2026-11-02T09-00-00Z", "release", base)
    assert rel.relative_to(base.resolve()).parts[1:3] == ("release", "2026")
    assert rel.parent.name == "11"  # month stays zero-padded (two digits)


def _make_run(base, ts, run_type, passed, failed, per_project=None):
    import json

    rd = run_all.run_dir_for(ts, run_type, base)
    rd.mkdir(parents=True)
    report = {
        "summary": {"passed": passed, "failed": failed, "skipped": 3, "timeout": 0},
        "per_project": per_project or {"autolens": {"passed": passed, "failed": failed}},
    }
    (rd / "report.json").write_text(json.dumps(report))
    (rd / "report.md").write_text("# report")
    return rd


def test_regenerate_index_lists_runs_newest_first(tmp_path):
    base = tmp_path / "run_logs"
    _make_run(base, "2026-04-29T10-00-00Z", "smoke", passed=10, failed=1)
    _make_run(base, "2026-07-21T19-05-22Z", "smoke", passed=646, failed=13)

    index_path = run_all.regenerate_index(base)
    text = index_path.read_text()

    # Header + both runs present.
    assert "# PyAutoHands run-log index" in text
    assert "| Date | Type | Passed | Failed | Skipped |" in text
    # Newest run appears before the older one.
    assert text.index("2026-07-21") < text.index("2026-04-29")
    # Counts and relative link into the nested tree are rendered.
    assert "| 646 | 13 |" in text
    assert "runs/smoke/2026/07/2026-07-21T19-05-22Z/report.md" in text


def test_regenerate_index_ignores_runs_without_report(tmp_path):
    """A run dir with no report.json is skipped, not crashed on."""
    base = tmp_path / "run_logs"
    good = _make_run(base, "2026-05-01T08-00-00Z", "smoke", passed=5, failed=0)
    bare = run_all.run_dir_for("2026-05-02T08-00-00Z", "smoke", base)
    bare.mkdir(parents=True)  # no report.json

    text = run_all.regenerate_index(base).read_text()
    assert "2026-05-01" in text
    assert "2026-05-02" not in text
    assert good.is_dir()


def test_write_agents_md_describes_layout(tmp_path):
    base = tmp_path / "run_logs"
    run_all.write_agents_md(base)
    agents = (base / "AGENTS.md").read_text()
    assert "run_logs" in agents
    assert "runs/<run-type>/<YYYY>/<MM>/" in agents
    assert "test_run.py" in agents  # documents who reads what
