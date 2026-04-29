"""Tests for the slowest-scripts section in aggregate_results.py."""

import json
import sys
from pathlib import Path

import pytest

AUTOBUILD_DIR = Path(__file__).parent.parent / "autobuild"
sys.path.insert(0, str(AUTOBUILD_DIR))

import aggregate_results  # noqa: E402


def _write_run_json(results_dir: Path, project: str, results: list) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": project,
        "directory": "scripts/imaging",
        "run_type": "script",
        "started_at": "2026-04-29T10:00:00",
        "completed_at": "2026-04-29T10:05:00",
        "summary": {},
        "results": results,
    }
    out = results_dir / f"{project}__scripts__imaging__script.json"
    out.write_text(json.dumps(payload))


def test_slowest_ordering_and_count(tmp_path, monkeypatch):
    """Slowest list is ordered descending by duration and capped at SLOWEST_TOP_N."""
    monkeypatch.setattr(aggregate_results, "fetch_merged_prs", lambda: [])
    monkeypatch.setattr(aggregate_results, "SLOWEST_TOP_N", 5)

    results = [
        {"file": f"scripts/imaging/{i}.py", "status": "passed", "duration_seconds": float(i)}
        for i in range(1, 11)
    ]
    _write_run_json(tmp_path, "autolens", results)

    report = aggregate_results.aggregate(tmp_path)
    slowest = report["slowest"]

    assert len(slowest) == 5
    durations = [s["duration_seconds"] for s in slowest]
    assert durations == sorted(durations, reverse=True)
    assert durations[0] == 10.0
    assert durations[-1] == 6.0
    # Project label preserved on each slowest entry
    assert all(s.get("project") == "autolens" for s in slowest)


def test_slowest_includes_failed_and_timeout(tmp_path, monkeypatch):
    """Slowest spans every status — useful for spotting regressions before they timeout."""
    monkeypatch.setattr(aggregate_results, "fetch_merged_prs", lambda: [])

    results = [
        {"file": "scripts/imaging/fast.py", "status": "passed", "duration_seconds": 2.0},
        {"file": "scripts/imaging/long_fail.py", "status": "failed", "duration_seconds": 295.0,
         "error_message": "boom", "traceback": "tb"},
        {"file": "scripts/imaging/timed_out.py", "status": "timeout", "duration_seconds": 300.0,
         "error_message": "Timed out after 300s"},
    ]
    _write_run_json(tmp_path, "autolens", results)

    report = aggregate_results.aggregate(tmp_path)
    statuses_in_slowest = {s["status"] for s in report["slowest"]}
    assert {"failed", "timeout", "passed"}.issubset(statuses_in_slowest)


def test_run_metadata_in_report_and_markdown(tmp_path, monkeypatch):
    """The aggregated report carries run_label, run_path, total_duration, and the markdown shows them."""
    monkeypatch.setattr(aggregate_results, "fetch_merged_prs", lambda: [])

    run_dir = tmp_path / "runs" / "2026-04-29T12-00-00Z"
    _write_run_json(
        run_dir,
        "autolens",
        [
            {"file": "scripts/imaging/a.py", "status": "passed", "duration_seconds": 1.5},
            {"file": "scripts/imaging/b.py", "status": "passed", "duration_seconds": 2.5},
        ],
    )

    report = aggregate_results.aggregate(run_dir)
    assert report["run_label"] == "2026-04-29T12-00-00Z"
    assert report["run_path"] == str(run_dir)
    assert report["total_duration_seconds"] == 4.0

    md = aggregate_results.generate_markdown(report)
    assert "**Run:** `2026-04-29T12-00-00Z`" in md
    assert "**Total duration:** 4.0s" in md
    assert "## Slowest scripts" in md
    assert "| Project |" in md  # per-project table header still rendered
    assert "Duration |" in md   # new duration column in per-project breakdown


def test_per_project_duration_aggregated(tmp_path, monkeypatch):
    monkeypatch.setattr(aggregate_results, "fetch_merged_prs", lambda: [])
    _write_run_json(
        tmp_path,
        "autofit",
        [
            {"file": "scripts/a.py", "status": "passed", "duration_seconds": 1.0},
            {"file": "scripts/b.py", "status": "passed", "duration_seconds": 2.5},
        ],
    )

    report = aggregate_results.aggregate(tmp_path)
    assert report["per_project_duration_seconds"] == {"autofit": 3.5}
