#!/usr/bin/env python
"""Build the #pipreleases Slack payload for a release outcome.

On a successful LIVE release, enrich the Slack post with the **full PyAutoLens
release notes** — which already aggregate upstream Fit/Array/Galaxy changes via
the "Upstream Changes" section written by ``generate_release_notes.py`` — plus
links to all four GitHub release pages (Fit / Array / Galaxy / Lens). The notes
are read back from the GitHub Release the ``publish_release_notes`` job just
created, converted from GitHub markdown to Slack mrkdwn, and embedded in the
message. If that release cannot be fetched (notes leg failed, not yet
published), fall back to the one-line summary. The failure message is unchanged.

Usage:
    python slack_release_notes.py --version <v> --result <success|failure|...> \
        --run-url <url> [--repo PyAutoLabs/PyAutoLens] > payload.json

The output is a Slack webhook JSON payload (``{"text": ...}``) on stdout.
"""

import json
import re
import subprocess
from argparse import ArgumentParser


PACKAGES = "autoconf / autofit / autoarray / autogalaxy / autolens"

# Repos that get a GitHub Release — mirrors the publish_release_notes matrix in
# release.yml. Order sets the "Releases:" link order (upstream → downstream).
RELEASE_REPOS = [
    ("PyAutoFit", "PyAutoLabs/PyAutoFit"),
    ("PyAutoArray", "PyAutoLabs/PyAutoArray"),
    ("PyAutoGalaxy", "PyAutoLabs/PyAutoGalaxy"),
    ("PyAutoLens", "PyAutoLabs/PyAutoLens"),
]

# Slack's per-message `text` ceiling is 40000 chars; stay under it with headroom
# for the truncation footer.
SLACK_TEXT_LIMIT = 38000


def fetch_release(repo, version):
    """Return ``{'body', 'url'}`` for a GitHub release, or None on any failure.

    A None return is the graceful-fallback signal: the caller drops back to the
    one-line summary rather than failing the announcement.
    """
    try:
        result = subprocess.run(
            ["gh", "release", "view", version, "--repo", repo,
             "--json", "body,url"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if data.get("body"):
                return data
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def md_to_mrkdwn(text):
    """Convert GitHub-flavoured markdown to Slack mrkdwn (best-effort).

    Handles the constructs ``generate_release_notes.py`` actually emits:
    headings, links, bold, horizontal rules and blockquotes. Inline code,
    bullets and blockquote markers are already valid Slack mrkdwn and pass
    through unchanged.
    """
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        # Drop horizontal rules (Slack has no equivalent).
        if stripped in ("---", "***", "___"):
            continue
        # Headings (#..######) -> a bold line.
        heading = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading:
            line = f"*{heading.group(1).strip()}*"
        lines.append(line)
    out = "\n".join(lines)
    # Markdown links [text](url) -> Slack <url|text>. Done before bold so link
    # text with bold is handled by the pass below.
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", out)
    # GitHub bold **x** -> Slack bold *x*.
    out = re.sub(r"\*\*(.+?)\*\*", r"*\1*", out)
    # Collapse runs of blank lines.
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def release_links(version):
    """Return an mrkdwn '·'-joined list of GitHub release-page links."""
    parts = [
        f"<https://github.com/{repo}/releases/tag/{version}|{name}>"
        for name, repo in RELEASE_REPOS
    ]
    return " · ".join(parts)


def _headline(version):
    return (
        f":package: *PyAuto {version} released to PyPI* — {PACKAGES}.\n"
        f"Upgrade with: `pip install --upgrade autolens`"
    )


def build_success_text(version, run_url, release):
    """Success message: enriched with notes + links, or the one-line fallback."""
    headline = _headline(version)
    if release is None:
        # Graceful fallback — the pre-enrichment one-liner.
        return f"{headline}\n<{run_url}|Release run>"

    notes = md_to_mrkdwn(release.get("body", ""))
    text = f"{headline}\n\n*Releases:* {release_links(version)}\n\n{notes}"

    if len(text) > SLACK_TEXT_LIMIT:
        lens_url = release.get("url", "")
        keep = SLACK_TEXT_LIMIT - 200
        text = text[:keep].rstrip() + (
            f"\n\n…(notes truncated) — full notes: "
            f"<{lens_url}|PyAutoLens release>"
        )
    return f"{text}\n\n<{run_url}|Release run>"


def build_failure_text(version, result, run_url):
    """Failure message — unchanged from the pre-enrichment payload."""
    return (
        f":rotating_light: *PyAuto release {version} did NOT complete* "
        f"(release job: {result}).\n"
        f"<{run_url}|Inspect the run> — PyPI may hold a partial set of the five "
        f"packages; verify before anyone installs."
    )


def build_payload(version, result, run_url, repo):
    if result == "success":
        release = fetch_release(repo, version)
        text = build_success_text(version, run_url, release)
    else:
        text = build_failure_text(version, result, run_url)
    return {"text": text}


def main():
    parser = ArgumentParser(description="Build the #pipreleases Slack payload")
    parser.add_argument("--version", required=True, help="Release version")
    parser.add_argument("--result", required=True,
                        help="release job result (success|failure|cancelled|…)")
    parser.add_argument("--run-url", required=True, help="Actions run URL")
    parser.add_argument("--repo", default="PyAutoLabs/PyAutoLens",
                        help="repo whose full notes are embedded on success")
    args = parser.parse_args()

    payload = build_payload(args.version, args.result, args.run_url, args.repo)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
