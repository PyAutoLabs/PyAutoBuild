#!/usr/bin/env python
"""
Run workspace scripts across one or more workspaces and produce summary reports.

Usage:
    python run_all.py                          # all 6 workspaces
    python run_all.py autolens                 # just autolens_workspace
    python run_all.py autolens_test autofit    # specific workspaces

Reports default to <autobuild>/../test_results/runs/<UTC-timestamp>/ with a
sibling `latest` symlink pointing at the most recent successful run, so every
release-prep run is preserved. Pass --results-dir to override (CI uses this);
in that mode the symlink is not touched.

Per-script timeout defaults to 300s and can be overridden via --timeout-secs.
This is forwarded to subprocesses via BUILD_SCRIPT_TIMEOUT.

Each workspace also gets a test_report.md in its root for easy access.
"""

import datetime
import os
import shutil
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

AUTOBUILD_DIR = Path(__file__).parent
PYAUTOBASE = AUTOBUILD_DIR.parent.parent  # PyAutoLabs/
RESULTS_BASE = AUTOBUILD_DIR.parent / "test_results"

WORKSPACES = {
    "autofit": ("autofit_workspace", "autofit"),
    "autogalaxy": ("autogalaxy_workspace", "autogalaxy"),
    "autolens": ("autolens_workspace", "autolens"),
    "autofit_test": ("autofit_workspace_test", "autofit_test"),
    "autogalaxy_test": ("autogalaxy_workspace_test", "autogalaxy_test"),
    "autolens_test": ("autolens_workspace_test", "autolens_test"),
}

DEFAULT_TIMEOUT_SECS = 300


def utc_run_timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def update_latest_symlink(run_dir: Path) -> None:
    """Atomically point <RESULTS_BASE>/latest at run_dir."""
    latest = RESULTS_BASE / "latest"
    tmp = RESULTS_BASE / ".latest.tmp"
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(run_dir.resolve(), target_is_directory=True)
    os.replace(tmp, latest)

# Local venv path — used when it exists, otherwise fall back to system python
LOCAL_VENV_PYTHON = Path.home() / "venv" / "PyAuto" / "bin" / "python3"


def _resolve_python() -> str:
    """Pick the Python interpreter: local venv if available, else system."""
    if LOCAL_VENV_PYTHON.exists():
        return str(LOCAL_VENV_PYTHON)
    return sys.executable


def run_workspace(name, workspace_dir, project, results_dir, python, timeout_secs):
    """Run all script directories for a single workspace."""
    scripts_dir = workspace_dir / "scripts"
    if not scripts_dir.exists():
        print(f"  Skipping {name}: no scripts/ directory")
        return

    directories = sorted(
        p.name for p in scripts_dir.iterdir()
        if p.is_dir() and p.name != "__pycache__"
    )

    # Ensure child processes (run_python.py -> build_util.py) use the same
    # interpreter and timeout for running scripts.
    env = os.environ.copy()
    env["BUILD_PYTHON_INTERPRETER"] = python
    env["BUILD_SCRIPT_TIMEOUT"] = str(timeout_secs)
    env["PYTHONUNBUFFERED"] = "1"

    for directory in directories:
        rel_dir = f"scripts/{directory}"
        print(f"\n  Running {name} / {rel_dir} ...")
        cmd = [
            python,
            str(AUTOBUILD_DIR / "run_python.py"),
            project,
            rel_dir,
            "--report-dir", str(results_dir),
        ]
        subprocess.run(cmd, cwd=str(workspace_dir), env=env)


def main():
    parser = ArgumentParser(description="Run all workspace scripts and aggregate results")
    parser.add_argument(
        "workspaces",
        nargs="*",
        default=None,
        choices=list(WORKSPACES.keys()),
        help="Workspaces to run (default: all)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help=(
            "Directory for result files (default: "
            "PyAutoBuild/test_results/runs/<UTC-timestamp>/, with a "
            "test_results/latest symlink updated on success)."
        ),
    )
    parser.add_argument(
        "--timeout-secs",
        type=int,
        default=DEFAULT_TIMEOUT_SECS,
        help=(
            f"Per-script timeout in seconds (default: {DEFAULT_TIMEOUT_SECS}). "
            "Forwarded to subprocesses via BUILD_SCRIPT_TIMEOUT env var."
        ),
    )
    args = parser.parse_args()

    workspaces = args.workspaces or list(WORKSPACES.keys())
    python = _resolve_python()
    timeout_secs = args.timeout_secs

    user_supplied_results_dir = args.results_dir is not None
    if user_supplied_results_dir:
        results_dir = args.results_dir.resolve()
        if results_dir.exists():
            shutil.rmtree(results_dir)
        results_dir.mkdir(parents=True)
    else:
        results_dir = (RESULTS_BASE / "runs" / utc_run_timestamp()).resolve()
        results_dir.mkdir(parents=True)

    print(f"Python: {python}")
    print(f"Results directory: {results_dir}")
    print(f"Per-script timeout: {timeout_secs}s")
    print(f"Workspaces: {', '.join(workspaces)}")

    from slow_skip_check import (
        find_slow_skips,
        find_needs_fix_skips,
        format_warning_banner,
        format_report_section,
    )
    ws_dirs_for_scan = [
        PYAUTOBASE / WORKSPACES[k][0]
        for k in workspaces
        if (PYAUTOBASE / WORKSPACES[k][0]).exists()
    ]
    slow_skips = find_slow_skips(ws_dirs_for_scan)
    needs_fix_skips = find_needs_fix_skips(ws_dirs_for_scan)
    if slow_skips:
        print(format_warning_banner(slow_skips, category="slow"))
    if needs_fix_skips:
        print(format_warning_banner(needs_fix_skips, category="needs_fix"))

    for ws_key in workspaces:
        ws_name, project = WORKSPACES[ws_key]
        ws_dir = PYAUTOBASE / ws_name
        if not ws_dir.exists():
            print(f"\nSkipping {ws_key}: {ws_dir} not found")
            continue

        print(f"\n{'=' * 60}")
        print(f"  {ws_name}")
        print(f"{'=' * 60}")
        run_workspace(ws_key, ws_dir, project, results_dir, python, timeout_secs)

        # Copy per-workspace markdown summaries into the workspace root
        for md_file in results_dir.glob(f"{project}__*.md"):
            dest = ws_dir / "test_report.md"
            shutil.copy2(md_file, dest)
            print(f"  Summary written to {dest}")

    # Aggregate all results
    print(f"\n{'=' * 60}")
    print("  Aggregating results")
    print(f"{'=' * 60}")

    from aggregate_results import aggregate, generate_markdown

    report = aggregate(results_dir)
    report["slow_skips"] = [s.to_dict() for s in slow_skips]
    report["needs_fix_skips"] = [s.to_dict() for s in needs_fix_skips]

    import json
    with open(results_dir / "report.json", "w") as f:
        json.dump(report, f, indent=2)

    md = generate_markdown(report)
    md_path = results_dir / "report.md"
    with open(md_path, "w") as f:
        f.write(md)

    # Print summary to stdout
    s = report.get("summary", {})
    total = sum(s.values())
    print(f"\n{total} scripts total: "
          + ", ".join(f"{v} {k}" for k, v in sorted(s.items())))

    per_project = report.get("per_project", {})
    if per_project:
        print(f"\n{'Project':<30} {'Passed':>7} {'Failed':>7} {'Skipped':>8} {'Timeout':>8}")
        print("-" * 62)
        for proj, counts in sorted(per_project.items()):
            print(f"{proj:<30} {counts.get('passed', 0):>7} {counts.get('failed', 0):>7} "
                  f"{counts.get('skipped', 0):>8} {counts.get('timeout', 0):>8}")

    failures = report.get("failures", [])
    if failures:
        print(f"\n{len(failures)} failure(s) — see {md_path}")
    else:
        print(f"\nAll tests passed! Full report: {md_path}")

    if slow_skips:
        print(format_warning_banner(slow_skips, category="slow"))
    if needs_fix_skips:
        print(format_warning_banner(needs_fix_skips, category="needs_fix"))

    if not user_supplied_results_dir:
        try:
            update_latest_symlink(results_dir)
            print(f"\nlatest symlink → {results_dir}")
        except OSError as exc:
            print(f"\nCould not update latest symlink: {exc}", file=sys.stderr)

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
