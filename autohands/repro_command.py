"""Emit the shell reproduction command for a single workspace script.

Given a path to a workspace script (e.g.
`autogalaxy_workspace_test/scripts/imaging/visualization.py`), print the
exact shell command `autohands run_python` would have used to execute
it — including all environment variables from the workspace's
`config/build/env_vars.yaml` (defaults + matching per-pattern overrides).

Output format (single line):

    (cd <workspace_name> && env KEY=val ... python3 <script_relpath>)

Run from the PyAutoLabs base directory. The output is portable as long
as the caller `cd`s to PyAutoLabs root first.

Usage:
    autohands repro_command <script_path>

Exit codes:
    0  on success (command printed to stdout)
    2  on usage error (script not found, workspace root not found)
"""

import argparse
import shlex
import sys
from pathlib import Path
from typing import Dict, Optional

from env_config import _pattern_matches, load_env_config


def _find_workspace_root(script: Path) -> Optional[Path]:
    """Walk up from `script` to find a dir containing config/build/env_vars.yaml."""
    for candidate in (script.parent, *script.parents):
        if (candidate / "config" / "build" / "env_vars.yaml").is_file():
            return candidate
    return None


def canonical_env_for_script(file: Path, env_config: Optional[dict]) -> Dict[str, str]:
    """Like `env_config.build_env_for_script`, but starts from `{}` instead of
    `os.environ.copy()`.

    The result is what autohands *adds* to the environment, independent of the
    developer's local shell. This is the right form for a portable reproduction
    command — the chat-side reader inherits their shell's env and just gets the
    autohands-specific overrides prepended.
    """
    if env_config is None:
        return {}

    env: Dict[str, str] = {}

    for key, value in env_config.get("defaults", {}).items():
        env[key] = str(value)

    for override in env_config.get("overrides", []):
        pattern = override["pattern"]
        if _pattern_matches(file, pattern):
            for var_name in override.get("unset", []):
                env.pop(var_name, None)
            for key, value in override.get("set", {}).items():
                env[key] = str(value)

    return env


def repro_command(script_path: str) -> str:
    """Compute the one-line shell repro command for `script_path`.

    Raises FileNotFoundError if the script doesn't exist or no workspace
    root with env_vars.yaml is found walking up.
    """
    script = Path(script_path).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"script not found: {script_path}")

    workspace_root = _find_workspace_root(script)
    if workspace_root is None:
        raise FileNotFoundError(
            f"no workspace root with config/build/env_vars.yaml found "
            f"walking up from {script_path}"
        )

    env_config_path = workspace_root / "config" / "build" / "env_vars.yaml"
    env_config = load_env_config(env_config_path)
    env = canonical_env_for_script(script, env_config)

    workspace_name = workspace_root.name
    script_rel = script.relative_to(workspace_root)

    env_parts = [f"{k}={shlex.quote(v)}" for k, v in env.items()]
    if env_parts:
        env_prefix = "env " + " ".join(env_parts) + " "
    else:
        env_prefix = ""

    return f"(cd {shlex.quote(workspace_name)} && {env_prefix}python3 {shlex.quote(str(script_rel))})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="autohands repro_command",
        description=__doc__.strip().splitlines()[0],
    )
    parser.add_argument(
        "script_path",
        help="Path to a workspace script (absolute or relative to cwd).",
    )
    args = parser.parse_args(argv)

    try:
        print(repro_command(args.script_path))
    except FileNotFoundError as e:
        print(f"autohands repro_command: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
