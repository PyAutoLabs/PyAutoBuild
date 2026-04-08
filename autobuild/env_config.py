"""Per-script environment variable configuration.

Loads env_vars.yaml and builds a tailored environment dict for each script,
applying defaults and per-pattern overrides.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml


def load_env_config(config_path: Path) -> dict:
    """Load and return the parsed env_vars.yaml."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def build_env_for_script(
    file: Path,
    env_config: Optional[dict],
) -> Optional[Dict[str, str]]:
    """Build the environment dict for a given script or notebook.

    Parameters
    ----------
    file
        Path to the script or notebook being executed.
    env_config
        Parsed env config from load_env_config(), or None.

    Returns
    -------
    A dict suitable for subprocess.run(env=...), or None when env_config
    is None (inherit parent environment unchanged).
    """
    if env_config is None:
        return None

    env = os.environ.copy()

    for key, value in env_config.get("defaults", {}).items():
        env[key] = str(value)

    file = Path(file)
    file_path_no_ext = str(file.with_suffix(""))

    for override in env_config.get("overrides", []):
        pattern = override["pattern"]
        if _pattern_matches(file, file_path_no_ext, pattern):
            for var_name in override.get("unset", []):
                env.pop(var_name, None)
            for key, value in override.get("set", {}).items():
                env[key] = str(value)

    return env


def _pattern_matches(file: Path, file_path_no_ext: str, pattern: str) -> bool:
    """Match a pattern against a file path.

    Patterns containing '/' are substring-matched against the full path
    (without extension). Patterns without '/' match the file stem exactly.
    Same convention as build_util.should_skip().
    """
    if "/" in pattern:
        return pattern in file_path_no_ext
    else:
        return file.stem == pattern
