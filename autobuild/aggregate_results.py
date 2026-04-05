#!/usr/bin/env python
"""
Aggregate per-job JSON result files into a consolidated release readiness report.

Usage:
    python aggregate_results.py <results-dir> --output report.json --markdown report.md
"""

import json
import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path


def classify_failure(result: dict) -> str:
    """Classify a failure based on error message and traceback patterns."""
    error = result.get("error_message", "")
    tb = result.get("traceback", "")
    combined = f"{error}\n{tb}"

    if result.get("status") == "timeout":
        return "timeout"

    if "ModuleNotFoundError" in combined or "ImportError" in combined:
        return "environment"

    if "InversionException" in combined:
        return "known_numerical"

    if "FileNotFoundError" in combined and ".fits" in combined:
        return "workspace_data"

    if "PermissionError" in combined:
        return "environment"

    lib_patterns = ["PyAutoFit", "PyAutoArray", "PyAutoGalaxy", "PyAutoLens", "PyAutoConf",
                    "autofit/", "autoarray/", "autogalaxy/", "autolens/", "autoconf/"]
    if any(p in tb for p in lib_patterns):
        return "source_code_bug"

    if "scripts/" in tb or "notebooks/" in tb:
        return "workspace_issue"

    return "unknown"


def fetch_merged_prs() -> list:
    """Fetch recently merged PRs from library and workspace repos."""
    repos = [
        "rhayes777/PyAutoFit",
        "Jammy2211/PyAutoArray",
        "Jammy2211/PyAutoGalaxy",
        "Jammy2211/PyAutoLens",
        "Jammy2211/autofit_workspace",
        "Jammy2211/autogalaxy_workspace",
        "Jammy2211/autolens_workspace",
    ]
    prs = []
    for repo in repos:
        try:
            result = subprocess.run(
                ["gh", "pr", "list", "--repo", repo, "--state", "merged",
                 "--json", "title,url,body,mergedAt", "--limit", "10"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                repo_prs = json.loads(result.stdout)
                for pr in repo_prs:
                    pr["repo"] = repo
                prs.extend(repo_prs)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    return prs


def extract_pr_section(body: str, header: str) -> str:
    """Extract a markdown section from a PR body."""
    if not body:
        return ""
    pattern = rf"## {re.escape(header)}\s*\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, body, re.DOTALL)
    return match.group(1).strip() if match else ""


def correlate_failures_with_prs(failures: list, prs: list) -> dict:
    """Check if any failed scripts appear in recent PR Scripts Changed sections."""
    correlations = {}
    for pr in prs:
        scripts_changed = extract_pr_section(pr.get("body", ""), "Scripts Changed")
        if not scripts_changed:
            continue
        for failure in failures:
            file_path = failure.get("file", "")
            file_stem = Path(file_path).stem
            if file_stem in scripts_changed or Path(file_path).name in scripts_changed:
                correlations.setdefault(file_path, []).append({
                    "pr_url": pr.get("url", ""),
                    "pr_title": pr.get("title", ""),
                    "repo": pr.get("repo", ""),
                })
    return correlations


def aggregate(results_dir: Path) -> dict:
    """Read all JSON result files and produce a consolidated report."""
    json_files = sorted(results_dir.glob("**/*.json"))
    if not json_files:
        print(f"No JSON result files found in {results_dir}", file=sys.stderr)
        return {"runs": [], "summary": {}, "failures": [], "skipped": []}

    runs = []
    all_results = []
    for jf in json_files:
        with open(jf) as f:
            data = json.load(f)
        runs.append(data)
        for r in data.get("results", []):
            r["_project"] = data.get("project", "")
            r["_directory"] = data.get("directory", "")
            r["_run_type"] = data.get("run_type", "")
            all_results.append(r)

    summary = {}
    for r in all_results:
        status = r.get("status", "unknown")
        summary[status] = summary.get(status, 0) + 1

    per_project = {}
    for r in all_results:
        proj = r["_project"]
        status = r.get("status", "unknown")
        per_project.setdefault(proj, {})
        per_project[proj][status] = per_project[proj].get(status, 0) + 1

    failures = [r for r in all_results if r.get("status") in ("failed", "timeout")]
    for f in failures:
        f["classification"] = classify_failure(f)

    skipped = [r for r in all_results if r.get("status") == "skipped"]

    # Fetch merged PRs for correlation
    prs = fetch_merged_prs()
    pr_correlations = correlate_failures_with_prs(failures, prs)

    # Extract API/Scripts Changed sections from PRs
    pr_changes = []
    for pr in prs:
        api_changes = extract_pr_section(pr.get("body", ""), "API Changes")
        scripts_changed = extract_pr_section(pr.get("body", ""), "Scripts Changed")
        if api_changes or scripts_changed:
            pr_changes.append({
                "repo": pr.get("repo", ""),
                "title": pr.get("title", ""),
                "url": pr.get("url", ""),
                "api_changes": api_changes,
                "scripts_changed": scripts_changed,
            })

    has_failures = len(failures) > 0
    return {
        "ready": not has_failures,
        "summary": summary,
        "per_project": per_project,
        "failures": [_clean_result(f) for f in failures],
        "failure_pr_correlations": pr_correlations,
        "skipped": [_clean_result(s) for s in skipped],
        "pr_changes": pr_changes,
        "runs": [{k: v for k, v in run.items() if k != "results"} for run in runs],
    }


def _clean_result(r: dict) -> dict:
    """Remove internal keys from a result dict."""
    return {k: v for k, v in r.items() if not k.startswith("_")}


def generate_markdown(report: dict) -> str:
    """Generate a markdown release readiness report."""
    lines = []
    status = "READY" if report.get("ready") else "NOT READY"
    lines.append(f"# Release Readiness Report")
    lines.append("")
    lines.append(f"**Status: {status}**")
    lines.append("")

    # Summary
    s = report.get("summary", {})
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Passed | Failed | Skipped | Timeout |")
    lines.append(f"|--------|--------|---------|---------|")
    lines.append(f"| {s.get('passed', 0)} | {s.get('failed', 0)} | {s.get('skipped', 0)} | {s.get('timeout', 0)} |")
    lines.append("")

    # Per-project breakdown
    per_project = report.get("per_project", {})
    if per_project:
        lines.append("## Per-Project Breakdown")
        lines.append("")
        lines.append("| Project | Passed | Failed | Skipped | Timeout |")
        lines.append("|---------|--------|--------|---------|---------|")
        for proj, counts in sorted(per_project.items()):
            lines.append(f"| {proj} | {counts.get('passed', 0)} | {counts.get('failed', 0)} | {counts.get('skipped', 0)} | {counts.get('timeout', 0)} |")
        lines.append("")

    # Failures
    failures = report.get("failures", [])
    if failures:
        # Group by classification
        by_class = {}
        for f in failures:
            cls = f.get("classification", "unknown")
            by_class.setdefault(cls, []).append(f)

        lines.append("## Failures by Classification")
        lines.append("")
        class_labels = {
            "source_code_bug": "Source Code Bugs",
            "workspace_issue": "Workspace Issues",
            "environment": "Environment Issues",
            "timeout": "Timeouts",
            "known_numerical": "Known Numerical Issues",
            "workspace_data": "Missing Data Files",
            "unknown": "Unclassified",
        }
        for cls, label in class_labels.items():
            if cls in by_class:
                lines.append(f"### {label} ({len(by_class[cls])})")
                lines.append("")
                for f in by_class[cls]:
                    file_path = f.get("file", "unknown")
                    error = f.get("error_message", "")
                    lines.append(f"- `{file_path}`")
                    if error:
                        lines.append(f"  - {error[:200]}")

                    # PR correlation
                    correlations = report.get("failure_pr_correlations", {})
                    if file_path in correlations:
                        for corr in correlations[file_path]:
                            lines.append(f"  - **Recently modified** in [{corr['pr_title']}]({corr['pr_url']})")

                    tb = f.get("traceback", "")
                    if tb:
                        tb_lines = tb.strip().splitlines()
                        # Show last 10 lines
                        snippet = "\n".join(tb_lines[-10:])
                        lines.append(f"  <details><summary>Traceback (last 10 lines)</summary>")
                        lines.append(f"")
                        lines.append(f"  ```")
                        lines.append(f"  {snippet}")
                        lines.append(f"  ```")
                        lines.append(f"  </details>")
                lines.append("")

    # Skipped tests
    skipped = report.get("skipped", [])
    if skipped:
        lines.append("## Skipped Tests")
        lines.append("")
        lines.append("| Script | Reason |")
        lines.append("|--------|--------|")
        for s in skipped:
            file_path = s.get("file", "unknown")
            reason = s.get("skip_reason", "No reason")
            lines.append(f"| `{Path(file_path).name}` | {reason} |")
        lines.append("")

    # Changes since last release
    pr_changes = report.get("pr_changes", [])
    if pr_changes:
        lines.append("## Changes Since Last Release")
        lines.append("")
        for pc in pr_changes:
            lines.append(f"### [{pc['title']}]({pc['url']}) ({pc['repo']})")
            if pc.get("api_changes"):
                lines.append(f"**API Changes:** {pc['api_changes'][:300]}")
            if pc.get("scripts_changed"):
                lines.append(f"**Scripts Changed:** {pc['scripts_changed'][:300]}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = ArgumentParser(description="Aggregate release test results")
    parser.add_argument("results_dir", type=Path, help="Directory containing JSON result files")
    parser.add_argument("--output", type=Path, default=Path("release-report.json"),
                        help="Path for consolidated JSON report")
    parser.add_argument("--markdown", type=Path, default=Path("release-report.md"),
                        help="Path for Markdown report")

    args = parser.parse_args()

    report = aggregate(args.results_dir)

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"JSON report written to {args.output}")

    md = generate_markdown(report)
    with open(args.markdown, "w") as f:
        f.write(md)
    print(f"Markdown report written to {args.markdown}")


if __name__ == "__main__":
    main()
