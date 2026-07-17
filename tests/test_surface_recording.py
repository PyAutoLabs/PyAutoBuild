"""tests/test_surface_recording.py — report.json states its own denominator.

PyAutoHeart#83 §5.3: on 2026-07-15 a test_run leg's "3 failed" and a later
"30 failed" were read as 27 regressions when the two runs had measured
different surfaces (different projects; scripts vs scripts+notebooks). Nothing
in the report said so, because the report never stated its surface.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "autobuild"))
from aggregate_results import aggregate  # noqa: E402


def _shard(results_dir: Path, project: str, directory: str, run_type: str,
           env_profile: str, statuses: list[str]) -> None:
    payload = {
        "project": project,
        "directory": directory,
        "run_type": run_type,
        "env_profile": env_profile,
        "summary": {},
        "results": [
            {"file": f"scripts/{directory}/s{i}.py", "status": s, "duration_seconds": 1.0}
            for i, s in enumerate(statuses)
        ],
    }
    (results_dir / f"{project}__{directory}__{run_type}.json").write_text(
        json.dumps(payload)
    )


def test_surface_records_projects_shards_types_and_profile(tmp_path):
    _shard(tmp_path, "autolens", "imaging", "script", "env_vars.yaml", ["passed"])
    _shard(tmp_path, "howtolens", "chapter_1", "notebook", "env_vars.yaml", ["passed"])
    report = aggregate(tmp_path)
    s = report["surface"]
    assert s["projects"] == ["autolens", "howtolens"]
    assert s["shards"] == ["autolens/imaging", "howtolens/chapter_1"]
    assert s["run_types"] == ["notebook", "script"]
    assert s["env_profiles"] == ["env_vars.yaml"]
    assert s["script_count"] == 2


def test_two_runs_with_equal_counts_but_different_surfaces_are_distinguishable(tmp_path):
    # The 2026-07-15 shape: same pass count, different denominator. The counts
    # alone say "no change"; the surfaces say "not comparable".
    a = tmp_path / "a"
    a.mkdir()
    _shard(a, "autolens", "imaging", "script", "env_vars.yaml", ["passed"])
    b = tmp_path / "b"
    b.mkdir()
    _shard(b, "autolens", "imaging", "script", "env_vars.yaml", ["passed"])
    _shard(b, "autolens", "imaging", "notebook", "env_vars.yaml", [])
    ra, rb = aggregate(a), aggregate(b)
    assert ra["summary"] == rb["summary"]              # counts agree ...
    assert ra["surface"] != rb["surface"]              # ... surfaces do not
    assert ra["surface"]["run_types"] == ["script"]
    assert rb["surface"]["run_types"] == ["notebook", "script"]


def test_release_profile_surface_is_named(tmp_path):
    _shard(tmp_path, "autolens", "imaging", "script", "env_vars_release.yaml", ["passed"])
    assert aggregate(tmp_path)["surface"]["env_profiles"] == ["env_vars_release.yaml"]


def test_empty_results_dir_still_carries_a_surface_key(tmp_path):
    # Consumers must always be able to read .surface — never a KeyError.
    report = aggregate(tmp_path)
    assert report["surface"]["script_count"] == 0
    assert report["surface"]["projects"] == []
