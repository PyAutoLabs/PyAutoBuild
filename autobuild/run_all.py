#!/usr/bin/env python
"""
Run workspace scripts across one or more workspaces and produce summary reports.

Usage:
    python run_all.py                          # all 5 workspaces
    python run_all.py autolens                 # just autolens_workspace
    python run_all.py autolens_test autofit    # specific workspaces

Reports are written to <autobuild>/test_results/ (per-workspace JSON + markdown)
and an aggregated report.md is produced at the end.

Each workspace also gets a test_report.md in its root for easy access.
"""

import shutil
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

AUTOBUILD_DIR = Path(__file__).parent
PYAUTOBASE = AUTOBUILD_DIR.parent.parent  # PyAutoLabs/

WORKSPACES = {
    "autofit": ("autofit_workspace", "autofit"),
    "autogalaxy": ("autogalaxy_workspace", "autogalaxy"),
    "autolens": ("autolens_workspace", "autolens"),
    "autofit_test": ("autofit_workspace_test", "autofit_test"),
    "autolens_test": ("autolens_workspace_test", "autolens_test"),
}

# Local venv path — used when it exists, otherwise fall back to system python
LOCAL_VENV_PYTHON = Path.home() / "venv" / "PyAuto" / "bin" / "python3"


def _resolve_python() -> str:
    """Pick the Python interpreter: local venv if available, else system."""
    if LOCAL_VENV_PYTHON.exists():
        return str(LOCAL_VENV_PYTHON)
    return sys.executable


def run_workspace(name, workspace_dir, project, results_dir, python):
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
    # interpreter for running scripts.
    import os
    env = os.environ.copy()
    env["BUILD_PYTHON_INTERPRETER"] = python

    for directory in directories:
        print(f"\n  Running {name} / scripts/{directory} ...")
        cmd = [
            python,
            str(AUTOBUILD_DIR / "run_python.py"),
            project,
            directory,
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
        default=AUTOBUILD_DIR.parent / "test_results",
        help="Directory for result files (default: PyAutoBuild/test_results/)",
    )
    args = parser.parse_args()

    workspaces = args.workspaces or list(WORKSPACES.keys())
    python = _resolve_python()
    results_dir = args.results_dir.resolve()
    if results_dir.exists():
        shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True)

    print(f"Python: {python}")
    print(f"Results directory: {results_dir}")
    print(f"Workspaces: {', '.join(workspaces)}")

    for ws_key in workspaces:
        ws_name, project = WORKSPACES[ws_key]
        ws_dir = PYAUTOBASE / ws_name
        if not ws_dir.exists():
            print(f"\nSkipping {ws_key}: {ws_dir} not found")
            continue

        print(f"\n{'=' * 60}")
        print(f"  {ws_name}")
        print(f"{'=' * 60}")
        run_workspace(ws_key, ws_dir, project, results_dir, python)

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

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
