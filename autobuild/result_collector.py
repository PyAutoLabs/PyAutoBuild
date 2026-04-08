import dataclasses
import datetime
import json
from enum import Enum
from pathlib import Path
from typing import List, Optional


class Status(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


@dataclasses.dataclass
class ScriptResult:
    file: str
    status: Status
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    traceback: Optional[str] = None
    skip_reason: Optional[str] = None

    def to_dict(self):
        d = {
            "file": self.file,
            "status": self.status.value,
            "duration_seconds": round(self.duration_seconds, 2),
        }
        if self.error_message is not None:
            d["error_message"] = self.error_message
        if self.traceback is not None:
            # Keep last 100 lines to avoid bloating JSON
            lines = self.traceback.splitlines()
            d["traceback"] = "\n".join(lines[-100:])
        if self.skip_reason is not None:
            d["skip_reason"] = self.skip_reason
        return d


@dataclasses.dataclass
class RunReport:
    project: str
    directory: str
    run_type: str  # "script", "notebook", or "generate"
    results: List[ScriptResult] = dataclasses.field(default_factory=list)
    started_at: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )
    completed_at: Optional[str] = None

    @property
    def summary(self):
        counts = {}
        for r in self.results:
            counts[r.status.value] = counts.get(r.status.value, 0) + 1
        return counts

    @property
    def has_failures(self):
        return any(
            r.status in (Status.FAILED, Status.TIMEOUT) for r in self.results
        )

    def to_dict(self):
        return {
            "project": self.project,
            "directory": self.directory,
            "run_type": self.run_type,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Test Report: {self.project} / {self.directory} ({self.run_type})",
            "",
        ]

        s = self.summary
        total = sum(s.values())
        lines.append(f"**{total} scripts** | "
                      + " | ".join(f"{v} {k}" for k, v in sorted(s.items())))
        lines.append("")

        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        for status, count in sorted(s.items()):
            lines.append(f"| {status} | {count} |")
        lines.append("")

        failures = [r for r in self.results
                     if r.status in (Status.FAILED, Status.TIMEOUT)]
        if failures:
            lines.append("## Failures")
            lines.append("")
            for r in failures:
                duration = f"{r.duration_seconds:.1f}s" if r.duration_seconds else ""
                lines.append(f"### `{r.file}` — {r.status.value.upper()} ({duration})")
                lines.append("")
                if r.error_message:
                    lines.append(f"{r.error_message}")
                    lines.append("")
                if r.traceback:
                    tb_lines = r.traceback.strip().splitlines()[-20:]
                    lines.append("```")
                    lines.extend(tb_lines)
                    lines.append("```")
                    lines.append("")

        skipped = [r for r in self.results if r.status == Status.SKIPPED]
        if skipped:
            lines.append("## Skipped")
            lines.append("")
            lines.append("| Script | Reason |")
            lines.append("|--------|--------|")
            for r in skipped:
                name = Path(r.file).name
                reason = r.skip_reason or "No reason documented"
                lines.append(f"| `{name}` | {reason} |")
            lines.append("")

        passed = [r for r in self.results if r.status == Status.PASSED]
        if passed:
            lines.append("## Passed")
            lines.append("")
            for r in passed:
                duration = f"{r.duration_seconds:.1f}s" if r.duration_seconds else ""
                lines.append(f"- `{r.file}` ({duration})")
            lines.append("")

        return "\n".join(lines)

    def write(self, output_dir: Path):
        self.completed_at = datetime.datetime.now().isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_dir = self.directory.replace("/", "__")
        base = f"{self.project}__{safe_dir}__{self.run_type}"

        json_path = output_dir / f"{base}.json"
        with open(json_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

        md_path = output_dir / f"{base}.md"
        with open(md_path, "w") as f:
            f.write(self.to_markdown())

        return json_path


def parse_no_run_reasons(yaml_path: Path, project: str) -> dict:
    """
    Parse no_run.yaml and extract pattern -> reason mappings.

    Since PyYAML strips comments, we parse the raw file line-by-line
    to capture the inline # reason comments.

    Supports both formats:
    - Flat list (workspace): every ``- entry`` line is relevant
    - Keyed dict (legacy autobuild): only entries under the matching project key
    """
    reasons = {}
    has_project_keys = False
    in_project = False
    with open(yaml_path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith(":") and not stripped.startswith("-"):
                has_project_keys = True
                in_project = stripped.rstrip(":").strip() == project
                continue
            if stripped.startswith("- "):
                if has_project_keys and not in_project:
                    continue
                entry = stripped[2:]
                if "#" in entry:
                    pattern, reason = entry.split("#", 1)
                    reasons[pattern.strip()] = reason.strip()
                else:
                    reasons[entry.strip()] = "No reason documented"
    return reasons
