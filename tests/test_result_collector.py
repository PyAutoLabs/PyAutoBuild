import json
import sys
import os
from pathlib import Path

# Add autobuild to path so we can import result_collector
sys.path.insert(0, str(Path(__file__).parent.parent / "autobuild"))

from result_collector import Status, ScriptResult, RunReport, parse_no_run_reasons


def test_test_result_to_dict_minimal():
    result = ScriptResult(file="test.py", status=Status.PASSED, duration_seconds=1.5)
    d = result.to_dict()
    assert d["file"] == "test.py"
    assert d["status"] == "passed"
    assert d["duration_seconds"] == 1.5
    assert "error_message" not in d
    assert "traceback" not in d
    assert "skip_reason" not in d


def test_test_result_to_dict_with_error():
    result = ScriptResult(
        file="fail.py",
        status=Status.FAILED,
        duration_seconds=2.3,
        error_message="Something broke",
        traceback="line 1\nline 2\nline 3",
    )
    d = result.to_dict()
    assert d["status"] == "failed"
    assert d["error_message"] == "Something broke"
    assert d["traceback"] == "line 1\nline 2\nline 3"


def test_test_result_traceback_truncation():
    long_tb = "\n".join(f"line {i}" for i in range(200))
    result = ScriptResult(
        file="fail.py",
        status=Status.FAILED,
        traceback=long_tb,
    )
    d = result.to_dict()
    tb_lines = d["traceback"].splitlines()
    assert len(tb_lines) == 100
    assert tb_lines[-1] == "line 199"


def test_test_result_skipped():
    result = ScriptResult(
        file="skip.py",
        status=Status.SKIPPED,
        skip_reason="GUI script",
    )
    d = result.to_dict()
    assert d["status"] == "skipped"
    assert d["skip_reason"] == "GUI script"


def test_run_report_summary():
    report = RunReport(project="autofit", directory="scripts/overview", run_type="script")
    report.results.append(ScriptResult(file="a.py", status=Status.PASSED))
    report.results.append(ScriptResult(file="b.py", status=Status.PASSED))
    report.results.append(ScriptResult(file="c.py", status=Status.FAILED))
    report.results.append(ScriptResult(file="d.py", status=Status.SKIPPED))

    assert report.summary == {"passed": 2, "failed": 1, "skipped": 1}
    assert report.has_failures is True


def test_run_report_no_failures():
    report = RunReport(project="autofit", directory="scripts/overview", run_type="script")
    report.results.append(ScriptResult(file="a.py", status=Status.PASSED))
    report.results.append(ScriptResult(file="b.py", status=Status.SKIPPED))

    assert report.has_failures is False


def test_run_report_write(tmp_path):
    report = RunReport(project="autofit", directory="scripts/overview", run_type="script")
    report.results.append(ScriptResult(file="a.py", status=Status.PASSED, duration_seconds=1.0))
    report.results.append(ScriptResult(file="b.py", status=Status.FAILED, error_message="oops"))

    path = report.write(tmp_path)
    assert path.exists()
    assert path.name == "autofit__scripts__overview__script.json"

    with open(path) as f:
        data = json.load(f)

    assert data["project"] == "autofit"
    assert data["directory"] == "scripts/overview"
    assert data["run_type"] == "script"
    assert data["completed_at"] is not None
    assert len(data["results"]) == 2
    assert data["summary"] == {"passed": 1, "failed": 1}


def test_parse_no_run_reasons():
    config_path = Path(__file__).parent.parent / "autobuild" / "config" / "no_run.yaml"
    if not config_path.exists():
        return  # Skip if config not available

    reasons = parse_no_run_reasons(config_path, "autofit")
    assert "get_dist" in reasons
    assert "install" in reasons["get_dist"].lower()

    reasons_lens = parse_no_run_reasons(config_path, "autolens")
    assert "gui/mask" in reasons_lens
    assert "GUI" in reasons_lens["gui/mask"]


def test_parse_no_run_reasons_empty_project():
    config_path = Path(__file__).parent.parent / "autobuild" / "config" / "no_run.yaml"
    if not config_path.exists():
        return

    reasons = parse_no_run_reasons(config_path, "autolens_test")
    assert reasons == {}
