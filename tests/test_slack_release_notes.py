import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "autohands"))

from slack_release_notes import (
    build_failure_text,
    build_payload,
    build_success_text,
    md_to_mrkdwn,
    release_links,
)


# A representative PyAutoLens release body, matching what
# generate_release_notes.py produces (banner + headings + links + upstream).
LENS_BODY = """# PyAutoLens v2026.7.9.1

> 📣 **Major Milestones Announcement** — PyAutoLens now ships an AI assistant. \
[Read the announcement →](https://github.com/PyAutoLabs/PyAutoLens/discussions/603)

## What's New

### New Features
- Add source pixelization ([#494](https://github.com/PyAutoLabs/PyAutoLens/pull/494))

## Upstream Changes

### PyAutoArray
- Kernel-CDF meshes ([#375](https://github.com/PyAutoLabs/PyAutoArray/pull/375))

---
Full changelog: https://github.com/PyAutoLabs/PyAutoLens/compare/2026.7.8.1...2026.7.9.1
"""


def test_md_to_mrkdwn_links():
    out = md_to_mrkdwn("See [the PR](https://example.com/1) for details.")
    assert "<https://example.com/1|the PR>" in out
    assert "[the PR]" not in out


def test_md_to_mrkdwn_headings():
    out = md_to_mrkdwn("## What's New\n### New Features")
    assert "*What's New*" in out
    assert "*New Features*" in out
    assert "#" not in out


def test_md_to_mrkdwn_bold():
    out = md_to_mrkdwn("**Major Milestones Announcement**")
    assert "*Major Milestones Announcement*" in out
    assert "**" not in out


def test_md_to_mrkdwn_strips_rules():
    out = md_to_mrkdwn("above\n---\nbelow")
    assert "---" not in out
    assert "above" in out and "below" in out


def test_md_to_mrkdwn_keeps_blockquote_and_code():
    out = md_to_mrkdwn("> quoted line\n`pip install autolens`")
    assert "> quoted line" in out
    assert "`pip install autolens`" in out


def test_release_links_all_four():
    links = release_links("2026.7.9.1")
    for name in ("PyAutoFit", "PyAutoArray", "PyAutoGalaxy", "PyAutoLens"):
        assert f"|{name}>" in links
    assert "releases/tag/2026.7.9.1" in links
    assert links.count("·") == 3


def test_build_success_text_embeds_notes_and_links():
    release = {"body": LENS_BODY, "url": "https://github.com/PyAutoLabs/PyAutoLens/releases/tag/2026.7.9.1"}
    text = build_success_text("2026.7.9.1", "https://run", release)
    assert "released to PyPI" in text
    assert "*Releases:*" in text
    assert "|PyAutoLens>" in text
    # Full notes embedded and converted.
    assert "*What's New*" in text
    assert "<https://github.com/PyAutoLabs/PyAutoLens/pull/494|#494>" in text
    assert "Upstream Changes" in text
    assert "<https://run|Release run>" in text
    assert "**" not in text  # bold converted


def test_build_success_text_fallback_when_no_release():
    text = build_success_text("2026.7.9.1", "https://run", None)
    assert "released to PyPI" in text
    assert "<https://run|Release run>" in text
    assert "*Releases:*" not in text  # no enrichment without a release


def test_build_success_text_truncates_giant_notes():
    huge = {"body": "# H\n" + ("- filler line\n" * 10000),
            "url": "https://github.com/PyAutoLabs/PyAutoLens/releases/tag/v1"}
    text = build_success_text("v1", "https://run", huge)
    assert len(text) < 39000
    assert "notes truncated" in text
    assert "|PyAutoLens release>" in text


def test_build_failure_text_unchanged():
    text = build_failure_text("2026.7.9.1", "failure", "https://run")
    assert ":rotating_light:" in text
    assert "did NOT complete" in text
    assert "(release job: failure)" in text
    assert "<https://run|Inspect the run>" in text


def test_build_payload_success_is_valid_json(monkeypatch):
    import slack_release_notes as srn
    monkeypatch.setattr(srn, "fetch_release",
                        lambda repo, version: {"body": LENS_BODY, "url": "https://u"})
    payload = build_payload("2026.7.9.1", "success", "https://run", "PyAutoLabs/PyAutoLens")
    assert set(payload) == {"text"}
    # Round-trips through JSON (webhook contract).
    assert json.loads(json.dumps(payload))["text"] == payload["text"]


def test_build_payload_failure_does_not_fetch(monkeypatch):
    import slack_release_notes as srn

    def _boom(repo, version):
        raise AssertionError("fetch_release must not run on failure")

    monkeypatch.setattr(srn, "fetch_release", _boom)
    payload = build_payload("2026.7.9.1", "failure", "https://run", "PyAutoLabs/PyAutoLens")
    assert "did NOT complete" in payload["text"]
