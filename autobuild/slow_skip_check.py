"""
Scan workspace no_run.yaml files for entries tagged as SLOW-skips or
NEEDS_FIX-skips and surface them so they cannot be silently forgotten.

A SLOW-skip entry has an inline comment of the form:

    - scripts/foo/bar.py # SLOW 2026-04-10 - reason text

A NEEDS_FIX entry has the same shape but with the `NEEDS_FIX` marker:

    - scripts/foo/bar.py # NEEDS_FIX 2026-04-10 - reason text

The date is optional in both cases (entries with just `# SLOW - reason` or
`# NEEDS_FIX - reason` are still picked up, but will report `date unknown`).
Anything else in no_run.yaml is treated as a permanent skip and ignored by
this scanner.

SLOW entries indicate scripts that exceed the 60s per-script timeout cap
and need a performance fix. NEEDS_FIX entries indicate scripts that are
broken and parked for later investigation — a to-do list surfaced on every
mega-run so fixes don't get forgotten.
"""

import dataclasses
import datetime
import re
from pathlib import Path
from typing import List, Optional

SLOW_RE = re.compile(
    r"^\s*SLOW(?:\s+(\d{4}-\d{2}-\d{2}))?\s*-\s*(.*)$"
)
NEEDS_FIX_RE = re.compile(
    r"^\s*NEEDS_FIX(?:\s+(\d{4}-\d{2}-\d{2}))?\s*-\s*(.*)$"
)

STALE_THRESHOLD_DAYS = 30


@dataclasses.dataclass
class TaggedSkip:
    workspace: str
    pattern: str
    reason: str
    marked_date: Optional[datetime.date] = None
    category: str = "slow"

    @property
    def age_days(self) -> Optional[int]:
        if self.marked_date is None:
            return None
        return (datetime.date.today() - self.marked_date).days

    @property
    def is_stale(self) -> bool:
        age = self.age_days
        return age is not None and age >= STALE_THRESHOLD_DAYS

    def to_dict(self) -> dict:
        return {
            "workspace": self.workspace,
            "pattern": self.pattern,
            "reason": self.reason,
            "marked_date": self.marked_date.isoformat() if self.marked_date else None,
            "age_days": self.age_days,
            "is_stale": self.is_stale,
            "category": self.category,
        }


SlowSkip = TaggedSkip


def _parse_entries(yaml_path: Path) -> List[tuple]:
    """Return a list of (pattern, inline_comment_or_empty) from a no_run.yaml file.

    We parse line-by-line rather than using PyYAML so we can recover the
    inline comments (which PyYAML strips).
    """
    entries = []
    for line in yaml_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        entry = stripped[2:]
        if "#" in entry:
            pattern, comment = entry.split("#", 1)
            entries.append((pattern.strip(), comment.strip()))
        else:
            entries.append((entry.strip(), ""))
    return entries


def _scan_for_tag(
    workspace_dirs: List[Path],
    regex: re.Pattern,
    category: str,
) -> List[TaggedSkip]:
    """Scan every workspace's config/build/no_run.yaml for entries matching regex."""
    out: List[TaggedSkip] = []
    for ws_dir in workspace_dirs:
        no_run = ws_dir / "config" / "build" / "no_run.yaml"
        if not no_run.exists():
            continue
        for pattern, comment in _parse_entries(no_run):
            m = regex.match(comment)
            if not m:
                continue
            date_str, reason = m.group(1), m.group(2).strip()
            marked_date = None
            if date_str:
                try:
                    marked_date = datetime.date.fromisoformat(date_str)
                except ValueError:
                    marked_date = None
            out.append(TaggedSkip(
                workspace=ws_dir.name,
                pattern=pattern,
                reason=reason,
                marked_date=marked_date,
                category=category,
            ))
    return out


def find_slow_skips(workspace_dirs: List[Path]) -> List[TaggedSkip]:
    """Scan every workspace's config/build/no_run.yaml for SLOW-tagged entries."""
    return _scan_for_tag(workspace_dirs, SLOW_RE, category="slow")


def find_needs_fix_skips(workspace_dirs: List[Path]) -> List[TaggedSkip]:
    """Scan every workspace's config/build/no_run.yaml for NEEDS_FIX-tagged entries."""
    return _scan_for_tag(workspace_dirs, NEEDS_FIX_RE, category="needs_fix")


_BANNER_CONFIG = {
    "slow": {
        "header": "WARNING: {n} SLOW-SKIPPED SCRIPT(S) - needs performance fix",
        "footer": [
            "  These scripts are skipped because they exceed the 60s per-script",
            "  cap. Fix the performance issue and remove the SLOW marker from",
            "  the workspace's config/build/no_run.yaml.",
        ],
    },
    "needs_fix": {
        "header": "WARNING: {n} NEEDS-FIX SCRIPT(S) - broken, parked for investigation",
        "footer": [
            "  These scripts are broken and parked as a to-do list. Investigate",
            "  the failure, fix the underlying bug, and remove the NEEDS_FIX",
            "  marker from the workspace's config/build/no_run.yaml.",
        ],
    },
}

_REPORT_CONFIG = {
    "slow": {
        "title": "## Slow-Skipped Scripts (needs performance fix)",
        "intro": (
            "**{n} script(s)** are being skipped because they exceed the 60s "
            "per-script timeout cap. These are NOT permanent skips — they need "
            "the underlying performance issue fixed and the `SLOW` marker "
            "removed from the workspace's `config/build/no_run.yaml`."
        ),
    },
    "needs_fix": {
        "title": "## Needs-Fix Scripts (parked for investigation)",
        "intro": (
            "**{n} script(s)** are being skipped because they are broken and "
            "parked as a to-do list. These are NOT permanent skips — investigate "
            "the failure, fix the underlying bug, and remove the `NEEDS_FIX` "
            "marker from the workspace's `config/build/no_run.yaml`."
        ),
    },
}


def format_warning_banner(
    skips: List[TaggedSkip], *, category: str = "slow"
) -> str:
    """Return a loud, hard-to-miss plain-text banner listing every tagged skip."""
    if not skips:
        return ""

    config = _BANNER_CONFIG[category]
    width = 72
    bar = "=" * width
    lines = [
        "",
        bar,
        f"  {config['header'].format(n=len(skips))}",
        bar,
    ]

    by_ws: dict = {}
    for s in skips:
        by_ws.setdefault(s.workspace, []).append(s)

    for ws in sorted(by_ws):
        lines.append(f"  {ws}:")
        for s in sorted(by_ws[ws], key=lambda x: x.pattern):
            lines.append(f"    {s.pattern}")
            if s.marked_date:
                age = s.age_days
                stale_tag = "  [STALE]" if s.is_stale else ""
                lines.append(f"      marked {s.marked_date.isoformat()} ({age} days ago){stale_tag}")
            else:
                lines.append("      marked date unknown")
            lines.append(f"      {s.reason}")
        lines.append("")

    lines.append(bar)
    lines.extend(config["footer"])
    lines.append(bar)
    lines.append("")
    return "\n".join(lines)


def format_report_section(
    skips: List[TaggedSkip], *, category: str = "slow"
) -> str:
    """Return a markdown section for inclusion in the aggregated report.md."""
    if not skips:
        return ""
    config = _REPORT_CONFIG[category]
    lines = [
        config["title"],
        "",
        config["intro"].format(n=len(skips)),
        "",
        "| Workspace | Script | Marked | Age | Reason |",
        "|-----------|--------|--------|-----|--------|",
    ]
    for s in sorted(skips, key=lambda x: (x.workspace, x.pattern)):
        date_str = s.marked_date.isoformat() if s.marked_date else "unknown"
        age_str = f"{s.age_days}d" if s.age_days is not None else "—"
        if s.is_stale:
            age_str += " **STALE**"
        lines.append(f"| {s.workspace} | `{s.pattern}` | {date_str} | {age_str} | {s.reason} |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    pyautobase = Path(__file__).resolve().parent.parent.parent
    default_workspaces = [
        pyautobase / name for name in (
            "autofit_workspace",
            "autogalaxy_workspace",
            "autolens_workspace",
            "autofit_workspace_test",
            "autolens_workspace_test",
        )
    ]
    targets = [Path(p) for p in sys.argv[1:]] or default_workspaces
    slow = find_slow_skips(targets)
    needs_fix = find_needs_fix_skips(targets)
    print(format_warning_banner(slow, category="slow") or "No SLOW-skipped scripts found.")
    print(format_warning_banner(needs_fix, category="needs_fix") or "No NEEDS_FIX-skipped scripts found.")
