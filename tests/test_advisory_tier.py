"""tests/test_advisory_tier.py — the mode=release advisory tier.

A timeout on a workspace-declared advisory-tier (known-slow real-search) script
is `timeout_advisory` — reported but NOT release-blocking — while a timeout on an
undeclared script stays a plain `timeout` (release-blocking). Covers the runner
classification (build_util), the result model (result_collector), and the
aggregate `ready` axis + report surfacing (aggregate_results).
"""

import json
import sys
from pathlib import Path

# Add autobuild to path so we can import the run primitives.
sys.path.insert(0, str(Path(__file__).parent.parent / "autobuild"))

import build_util
import aggregate_results as agg
from result_collector import RunReport, Status


# --- runner classification (build_util) ------------------------------------

def test_advisory_timeout_matches_path_pattern():
    """A timeout on a script listed in the advisory list → TIMEOUT_ADVISORY."""
    result = build_util._advisory_timeout_result(
        "scripts/imaging/slow_fit.py",
        1800.0,
        advisory_list=["imaging/slow_fit.py"],
        advisory_reasons={"imaging/slow_fit.py": "real-search fit, known slow"},
    )
    assert result.status is Status.TIMEOUT_ADVISORY
    assert result.skip_reason == "real-search fit, known slow"


def test_undeclared_timeout_stays_plain_timeout():
    """A timeout on a script NOT in the advisory list stays release-blocking."""
    result = build_util._advisory_timeout_result(
        "scripts/imaging/fast_fit.py",
        1800.0,
        advisory_list=["imaging/slow_fit.py"],
        advisory_reasons={},
    )
    assert result.status is Status.TIMEOUT


def test_empty_advisory_list_is_todays_behaviour():
    """No advisory list → every timeout is a plain TIMEOUT (no tiering)."""
    result = build_util._advisory_timeout_result(
        "scripts/imaging/slow_fit.py", 1800.0, advisory_list=[], advisory_reasons=None
    )
    assert result.status is Status.TIMEOUT


# --- result model (result_collector) ---------------------------------------

def test_advisory_timeout_is_not_a_failure():
    """RunReport.has_failures ignores advisory timeouts but not plain ones."""
    advisory_only = RunReport(project="p", directory="d", run_type="script")
    advisory_only.results.append(
        build_util._advisory_timeout_result("a/slow.py", 1800.0, ["a/slow.py"], {})
    )
    assert advisory_only.has_failures is False
    assert advisory_only.summary.get("timeout_advisory") == 1

    with_plain = RunReport(project="p", directory="d", run_type="script")
    with_plain.results.append(
        build_util._advisory_timeout_result("a/bad.py", 1800.0, advisory_list=[], advisory_reasons={})
    )
    assert with_plain.has_failures is True


# --- aggregate ready axis + report (aggregate_results) ----------------------

def _aggregate(tmp_path, results):
    (tmp_path / "run.json").write_text(
        json.dumps({"project": "p", "directory": "d", "run_type": "script", "results": results})
    )
    return agg.aggregate(tmp_path)


def test_aggregate_ready_true_when_only_advisory_timeouts(tmp_path):
    report = _aggregate(
        tmp_path,
        [
            {"file": "a/slow.py", "status": "timeout_advisory", "duration_seconds": 1800,
             "skip_reason": "known slow"},
            {"file": "a/ok.py", "status": "passed", "duration_seconds": 5},
        ],
    )
    assert report["ready"] is True
    assert [a["file"] for a in report["advisory_timeouts"]] == ["a/slow.py"]
    assert report["summary"].get("timeout_advisory") == 1
    md = agg.generate_markdown(report)
    assert "Advisory-Tier Timeouts" in md
    assert "a/slow.py" in md


def test_aggregate_ready_false_on_undeclared_timeout(tmp_path):
    report = _aggregate(
        tmp_path,
        [
            {"file": "a/slow.py", "status": "timeout_advisory", "duration_seconds": 1800},
            {"file": "a/bad.py", "status": "timeout", "duration_seconds": 1800},
        ],
    )
    # The advisory timeout is de-gated, but the plain (undeclared) timeout still
    # blocks the release.
    assert report["ready"] is False
