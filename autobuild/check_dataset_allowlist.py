#!/usr/bin/env python3
"""Leg 4 of PyAutoBuild#126 — dataset allowlist guard.

Asserts that every tracked file under `dataset/` in the current workspace is
covered by that workspace's `.gitignore` allowlist (the `!dataset/...` re-include
lines). This makes the `git add -f` leak (fixed in pre_build) unable to recur: if
a simulated dataset is ever force-committed again, a `pre_build` release run fails
loudly here instead of shipping ~10 MB of runtime-generated data to users.

Allowlist-based, NOT `git check-ignore`-based: `git check-ignore` never flags an
already-tracked file (a tracked file is by definition not ignored) and mishandles
`!`-negated paths, so it cannot detect this leak. We compare tracked paths against
the parsed allowlist directly.

Allowlist-presence-gated: a workspace whose `.gitignore` has a bare `dataset/`
rule with no `!dataset/...` re-includes has not yet adopted the allowlist regime
(Group B, PyAutoBuild#126) — the guard skips it with a notice rather than
failing, until that repo opts in.

Run from a workspace root. Exit 0 = clean/skipped, 1 = violation.
"""
import re
import subprocess
import sys
from pathlib import Path


def allowlist_prefixes(gitignore: Path):
    prefixes = []
    has_dataset_ignore = False
    if not gitignore.exists():
        return prefixes, has_dataset_ignore
    for line in gitignore.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if re.match(r"^/?dataset(/\*\*|/)?\s*$", s):
            has_dataset_ignore = True
        if s.startswith("!") and "dataset" in s:
            p = re.sub(r"/\*+$", "", s[1:].strip().lstrip("/")).rstrip("/")
            prefixes.append(p)
    return prefixes, has_dataset_ignore


def tracked_dataset_files():
    out = subprocess.run(
        ["git", "ls-files", "dataset/"], capture_output=True, text=True
    ).stdout
    return [f for f in out.splitlines() if f and not f.endswith("dataset/.gitignore")]


def main() -> int:
    prefixes, has_dataset_ignore = allowlist_prefixes(Path(".gitignore"))
    tracked = tracked_dataset_files()

    if not tracked:
        print("[dataset-allowlist] no tracked dataset/ files — OK")
        return 0

    if not prefixes:
        # bare `dataset/` (or none) with no re-includes: Group B, not yet in regime
        note = "bare `dataset/` ignore" if has_dataset_ignore else "no dataset allowlist"
        print(
            f"[dataset-allowlist] SKIP — {note}; workspace has not adopted the "
            f"allowlist regime (Group B, PyAutoBuild#126). {len(tracked)} tracked files."
        )
        return 0

    def allowed(f: str) -> bool:
        return any(f == p or f.startswith(p + "/") for p in prefixes)

    violations = sorted({"/".join(f.split("/")[:3]) for f in tracked if not allowed(f)})
    if violations:
        print(
            "[dataset-allowlist] FAIL — tracked dataset dirs outside the "
            f".gitignore allowlist ({len(violations)}):",
            file=sys.stderr,
        )
        for d in violations:
            print(f"    {d}", file=sys.stderr)
        print(
            "\nThese are simulated datasets that must be generated at runtime, not "
            "committed. Purge them (`git rm -r`) — they self-provision via "
            "should_simulate()/`.exists()` — or add a `!dataset/<dir>/**` allowlist "
            "line if the data is real/committed-by-design. See PyAutoBuild#126.",
            file=sys.stderr,
        )
        return 1

    print(
        f"[dataset-allowlist] OK — {len(tracked)} tracked dataset files, all within "
        f"the allowlist ({len(prefixes)} patterns)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
