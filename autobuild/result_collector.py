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

    def write(self, output_dir: Path):
        self.completed_at = datetime.datetime.now().isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_dir = self.directory.replace("/", "__")
        filename = f"{self.project}__{safe_dir}__{self.run_type}.json"
        path = output_dir / filename
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path


def parse_no_run_reasons(yaml_path: Path, project: str) -> dict:
    """
    Parse no_run.yaml and extract pattern -> reason mappings.

    Since PyYAML strips comments, we parse the raw file line-by-line
    to capture the inline # reason comments.
    """
    reasons = {}
    in_project = False
    with open(yaml_path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.endswith(":") and not stripped.startswith("-"):
                in_project = stripped.rstrip(":").strip() == project
                continue
            if in_project and stripped.startswith("- "):
                entry = stripped[2:]
                if "#" in entry:
                    pattern, reason = entry.split("#", 1)
                    reasons[pattern.strip()] = reason.strip()
                else:
                    reasons[entry.strip()] = "No reason documented"
    return reasons
