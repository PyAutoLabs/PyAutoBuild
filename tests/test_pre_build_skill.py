"""Keep the pre-build skill's safety preflight aligned with its executor."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pre_build_skill_checks_every_executor_repo():
    script = (ROOT / "pre_build.sh").read_text()
    body = (ROOT / "skills" / "pre_build" / "pre_build.md").read_text()
    executor_repos = set(re.findall(r'^run_workspace "([^"]+)"', script, re.MULTILINE))
    fixed_dependencies = set(re.findall(r'\$PYAUTOBASE/([^/"$]+)', script))
    preflight = body.split("Check that all required repositories exist", 1)[1]
    preflight = preflight.split("For each, verify", 1)[0]
    documented_repos = set(re.findall(r"^- `([^`]+)`", preflight, re.MULTILINE))

    assert documented_repos == executor_repos | fixed_dependencies
