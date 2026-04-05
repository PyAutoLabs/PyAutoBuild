import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "autobuild"))

from generate_release_notes import (
    classify_pr,
    extract_api_changes,
    extract_full_api_details,
    format_pr_line,
    UPSTREAM_DEPS,
)


def _make_pr(title="Test PR", body="", labels=None, number=1, url="https://example.com/1"):
    return {
        "title": title,
        "body": body,
        "labels": [{"name": l} for l in (labels or [])],
        "number": number,
        "url": url,
    }


def test_extract_api_changes():
    body = """## Summary
Some summary

## API Changes
Removed `OldClass` — use `new_function()` instead.
See full details below.

## Test Plan
- [ ] Tests pass
"""
    result = extract_api_changes(body)
    assert "Removed `OldClass`" in result
    assert "Test Plan" not in result


def test_extract_api_changes_none():
    body = """## Summary
Something

## API Changes
None — internal changes only.

## Test Plan
Done
"""
    result = extract_api_changes(body)
    assert "None" in result


def test_extract_api_changes_missing():
    body = "## Summary\nJust a summary"
    result = extract_api_changes(body)
    assert result == ""


def test_extract_full_api_details():
    body = """## API Changes
See below.

<details>
<summary>Full API Changes (for automation & release notes)</summary>

### Removed
- `module.OldClass`

### Added
- `module.new_function()`

</details>
"""
    result = extract_full_api_details(body)
    assert "### Removed" in result
    assert "module.OldClass" in result


def test_classify_breaking():
    pr = _make_pr(body="""## API Changes
Breaking stuff.

<details>
<summary>Full API Changes (for automation & release notes)</summary>

### Removed
- `OldClass`

</details>
""")
    assert classify_pr(pr) == "breaking"


def test_classify_feature():
    pr = _make_pr(body="""## API Changes
New stuff.

<details>
<summary>Full API Changes (for automation & release notes)</summary>

### Added
- `new_function()`

</details>
""")
    assert classify_pr(pr) == "feature"


def test_classify_fix_by_title():
    pr = _make_pr(title="Fix broken authentication", body="## Summary\nFixed a bug")
    assert classify_pr(pr) == "fix"


def test_classify_fix_by_label():
    pr = _make_pr(title="Something", body="", labels=["bug"])
    assert classify_pr(pr) == "fix"


def test_classify_internal():
    pr = _make_pr(body="## API Changes\nNone — internal changes only.")
    assert classify_pr(pr) == "internal"


def test_format_pr_line():
    pr = _make_pr(title="Add feature X", number=42, url="https://github.com/org/repo/pull/42")
    result = format_pr_line(pr)
    assert result == "- Add feature X ([#42](https://github.com/org/repo/pull/42))"


def test_upstream_deps_chain():
    assert UPSTREAM_DEPS["rhayes777/PyAutoFit"] == []
    assert UPSTREAM_DEPS["Jammy2211/PyAutoArray"] == []
    assert "rhayes777/PyAutoFit" in UPSTREAM_DEPS["Jammy2211/PyAutoGalaxy"]
    assert "Jammy2211/PyAutoArray" in UPSTREAM_DEPS["Jammy2211/PyAutoGalaxy"]
    assert len(UPSTREAM_DEPS["Jammy2211/PyAutoLens"]) == 3
    assert "Jammy2211/PyAutoGalaxy" in UPSTREAM_DEPS["Jammy2211/PyAutoLens"]
