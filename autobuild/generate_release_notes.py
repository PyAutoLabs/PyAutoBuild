#!/usr/bin/env python
"""
Generate release notes from merged PRs and create GitHub Releases.

For downstream repos (PyAutoGalaxy, PyAutoLens), includes upstream
changes from dependency repos.

Usage:
    python generate_release_notes.py --version <version> --repo <owner/repo> [--dry-run]
"""

import json
import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path


# Dependency chain: downstream repos include upstream changes
UPSTREAM_DEPS = {
    "PyAutoLabs/PyAutoFit": [],
    "PyAutoLabs/PyAutoArray": [],
    "PyAutoLabs/PyAutoGalaxy": [
        "PyAutoLabs/PyAutoFit",
        "PyAutoLabs/PyAutoArray",
    ],
    "PyAutoLabs/PyAutoLens": [
        "PyAutoLabs/PyAutoFit",
        "PyAutoLabs/PyAutoArray",
        "PyAutoLabs/PyAutoGalaxy",
    ],
}

# Human-readable short names
REPO_NAMES = {
    "PyAutoLabs/PyAutoConf": "PyAutoConf",
    "PyAutoLabs/PyAutoFit": "PyAutoFit",
    "PyAutoLabs/PyAutoArray": "PyAutoArray",
    "PyAutoLabs/PyAutoGalaxy": "PyAutoGalaxy",
    "PyAutoLabs/PyAutoLens": "PyAutoLens",
}

# Base branches per repo
BASE_BRANCHES = {
    "PyAutoLabs/PyAutoFit": "main",
    "PyAutoLabs/PyAutoArray": "main",
    "PyAutoLabs/PyAutoGalaxy": "main",
    "PyAutoLabs/PyAutoLens": "main",
}


def gh_json(args, timeout=30):
    """Run a gh command and return parsed JSON."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def get_previous_release_tag(repo):
    """Find the most recent release tag for a repo."""
    releases = gh_json([
        "release", "list", "--repo", repo,
        "--limit", "1", "--json", "tagName,publishedAt",
    ])
    if releases:
        return releases[0]

    # Fallback: look at tags directly
    tags = gh_json([
        "api", f"repos/{repo}/tags", "--jq", ".[0]",
    ])
    if tags and isinstance(tags, dict):
        return {"tagName": tags.get("name", ""), "publishedAt": ""}

    return None


def get_merged_prs(repo, since_tag=None):
    """Fetch PRs merged since the given tag."""
    base = BASE_BRANCHES.get(repo, "main")

    prs = gh_json([
        "pr", "list", "--repo", repo, "--state", "merged",
        "--base", base,
        "--json", "title,url,body,labels,number,mergedAt",
        "--limit", "50",
    ])
    if not prs:
        return []

    # Filter by date if we have a previous release
    if since_tag and since_tag.get("publishedAt"):
        cutoff = since_tag["publishedAt"][:10]
        prs = [pr for pr in prs if pr.get("mergedAt", "")[:10] >= cutoff]

    return prs


def extract_api_changes(body):
    """Extract the ## API Changes section from a PR body."""
    if not body:
        return ""
    pattern = r"## API Changes\s*\n(.*?)(?=\n## |\n<details>|\Z)"
    match = re.search(pattern, body, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_full_api_details(body):
    """Extract the full API details from a <details> block."""
    if not body:
        return ""
    pattern = r"<details>.*?<summary>Full API Changes.*?</summary>\s*(.*?)</details>"
    match = re.search(pattern, body, re.DOTALL)
    return match.group(1).strip() if match else ""


def classify_pr(pr):
    """Classify a PR into a category based on its API Changes and title."""
    api_changes = extract_api_changes(pr.get("body", ""))
    details = extract_full_api_details(pr.get("body", ""))
    title = pr.get("title", "").lower()
    labels = [l.get("name", "").lower() for l in pr.get("labels", [])]
    combined = f"{api_changes}\n{details}"

    if "none" in api_changes.lower() and "internal" in api_changes.lower():
        return "internal"

    has_breaking = any(
        heading in combined
        for heading in ["### Removed", "### Renamed", "### Changed Signature",
                        "### Changed Behaviour"]
    )
    if has_breaking:
        return "breaking"

    has_added = "### Added" in combined
    if has_added:
        return "feature"

    if "fix" in title or "bug" in labels or "fix" in labels:
        return "fix"

    if api_changes:
        return "feature"

    return "internal"


def format_pr_line(pr):
    """Format a single PR as a markdown bullet."""
    title = pr.get("title", "Untitled")
    url = pr.get("url", "")
    number = pr.get("number", "")
    return f"- {title} ([#{number}]({url}))"


def generate_notes(repo, version, prs, upstream_prs_by_repo):
    """Generate markdown release notes."""
    name = REPO_NAMES.get(repo, repo.split("/")[-1])
    lines = [f"# {name} v{version}", ""]

    # Classify own PRs
    categories = {"breaking": [], "feature": [], "fix": [], "internal": []}
    for pr in prs:
        cat = classify_pr(pr)
        categories[cat].append(pr)

    has_own_changes = any(categories.values())

    if has_own_changes:
        lines.append("## What's New")
        lines.append("")

        if categories["breaking"]:
            lines.append("### Breaking Changes")
            for pr in categories["breaking"]:
                lines.append(format_pr_line(pr))
                api = extract_api_changes(pr.get("body", ""))
                if api and "none" not in api.lower():
                    # Include a brief summary of what broke
                    for api_line in api.splitlines()[:3]:
                        api_line = api_line.strip()
                        if api_line and not api_line.startswith("See"):
                            lines.append(f"  - {api_line}")
            lines.append("")

        if categories["feature"]:
            lines.append("### New Features")
            for pr in categories["feature"]:
                lines.append(format_pr_line(pr))
            lines.append("")

        if categories["fix"]:
            lines.append("### Bug Fixes")
            for pr in categories["fix"]:
                lines.append(format_pr_line(pr))
            lines.append("")

        if categories["internal"]:
            lines.append("### Internal")
            for pr in categories["internal"]:
                lines.append(format_pr_line(pr))
            lines.append("")
    else:
        lines.append("No direct changes in this release.")
        lines.append("")

    # Upstream changes
    if upstream_prs_by_repo:
        has_upstream = any(upstream_prs_by_repo.values())
        if has_upstream:
            lines.append("## Upstream Changes")
            lines.append("")
            for upstream_repo, upstream_prs in upstream_prs_by_repo.items():
                if not upstream_prs:
                    continue
                upstream_name = REPO_NAMES.get(upstream_repo, upstream_repo)
                lines.append(f"### {upstream_name}")
                for pr in upstream_prs:
                    lines.append(format_pr_line(pr))
                lines.append("")

    # Full changelog link
    prev_tag = get_previous_release_tag(repo)
    if prev_tag:
        prev = prev_tag.get("tagName", "")
        if prev:
            lines.append("---")
            lines.append(
                f"Full changelog: https://github.com/{repo}/compare/{prev}...{version}"
            )
            lines.append("")

    return "\n".join(lines)


def main():
    parser = ArgumentParser(description="Generate release notes from merged PRs")
    parser.add_argument("--version", required=True, help="Release version (e.g. 2026.4.5.1)")
    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--dry-run", action="store_true", help="Print notes without creating release")

    args = parser.parse_args()

    repo = args.repo
    version = args.version
    name = REPO_NAMES.get(repo, repo.split("/")[-1])

    print(f"Generating release notes for {name} v{version}...")

    # Get previous tag to scope PR search
    prev_tag = get_previous_release_tag(repo)
    if prev_tag:
        print(f"Previous release: {prev_tag.get('tagName', 'none')}")
    else:
        print("No previous release found — including all merged PRs")

    # Fetch own PRs
    prs = get_merged_prs(repo, since_tag=prev_tag)
    print(f"Found {len(prs)} merged PRs for {name}")

    # Fetch upstream PRs
    upstream_deps = UPSTREAM_DEPS.get(repo, [])
    upstream_prs_by_repo = {}
    for dep_repo in upstream_deps:
        dep_name = REPO_NAMES.get(dep_repo, dep_repo)
        dep_prs = get_merged_prs(dep_repo, since_tag=prev_tag)
        upstream_prs_by_repo[dep_repo] = dep_prs
        print(f"Found {len(dep_prs)} merged PRs for upstream {dep_name}")

    # Generate notes
    notes = generate_notes(repo, version, prs, upstream_prs_by_repo)

    if args.dry_run:
        print("\n" + "=" * 60)
        print(notes)
        print("=" * 60)
        print(f"\nDry run — no release created. Notes length: {len(notes)} chars")
        return

    # Create GitHub Release
    print(f"Creating GitHub Release {version} on {repo}...")
    try:
        result = subprocess.run(
            ["gh", "release", "create", version,
             "--repo", repo,
             "--title", f"v{version}",
             "--notes", notes],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            release_url = result.stdout.strip()
            print(f"Release created: {release_url}")
        else:
            # Tag may already exist as a release — try editing instead
            if "already exists" in result.stderr:
                print("Release already exists, updating notes...")
                result = subprocess.run(
                    ["gh", "release", "edit", version,
                     "--repo", repo,
                     "--notes", notes],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0:
                    print(f"Release notes updated for {version}")
                else:
                    print(f"Failed to update release: {result.stderr}", file=sys.stderr)
                    sys.exit(1)
            else:
                print(f"Failed to create release: {result.stderr}", file=sys.stderr)
                sys.exit(1)
    except FileNotFoundError:
        print("gh CLI not found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
