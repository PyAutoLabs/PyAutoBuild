"""Per-script environment variable configuration.

Loads env_vars.yaml and builds a tailored environment dict for each script,
applying defaults and per-pattern overrides.
"""

import os
import shlex
from pathlib import Path
from typing import Dict, List, Optional

import yaml


# The workspace-behavioural env family (PYAUTO_*) is owned by the profiles,
# never by the runner's shell: a PYAUTO_ var's value for a script run must be a
# function of (profile, script), and absence must mean "the library default",
# not "whatever leaked from a developer's rc or an unrelated CI step". So the
# whole prefix is scrubbed from the base env before the profile is layered on
# (docs/env_profile_redesign.md §5, #161 step 3).
#
# Only PYAUTO_* is scrubbed — NOT infrastructure/reproducibility vars (PATH,
# PYTHONPATH, JAX_ENABLE_X64, NUMBA_CACHE_DIR, MPLCONFIGDIR, …). Those are set
# identically by the profiles and the CI step env, so ambient-vs-profile never
# causes a reproducibility bug for them, and a deny-by-default allowlist over
# them would risk breaking the least-exercised, highest-consequence release
# path on a single missed key. The audit's actual leak is the PYAUTO_ family.
MANAGED_ENV_PREFIXES = ("PYAUTO_",)


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

    The ambient environment is inherited EXCEPT for the managed PYAUTO_* family
    (see ``MANAGED_ENV_PREFIXES``), which is stripped before defaults/overrides
    are applied — so an ambient ``PYAUTO_DISABLE_JAX`` / ``PYAUTO_SKIP_*`` the
    profile is silent on cannot leak into the script run.
    """
    if env_config is None:
        return None

    env = os.environ.copy()
    for key in list(env):
        if key.startswith(MANAGED_ENV_PREFIXES):
            del env[key]

    return apply_profile(env, file, env_config)


def apply_profile(
    env: Dict[str, str],
    file: Path,
    env_config: dict,
) -> Dict[str, str]:
    """Apply a profile to a base env dict: defaults, then overrides in order,
    then the JAX-marker derivation (when the profile opts in).

    The single resolution path shared by the runner (``build_env_for_script``,
    base = scrubbed ambient env) and the validator (``resolve_clean``, base =
    empty dict) — docs/env_profile_redesign.md §5. Mutates and returns ``env``.
    """
    for key, value in (env_config.get("defaults") or {}).items():
        env[key] = str(value)

    file = Path(file)

    for override in env_config.get("overrides") or []:
        pattern = override["pattern"]
        if _pattern_matches(file, pattern):
            for var_name in override.get("unset") or []:
                env.pop(var_name, None)
            for key, value in (override.get("set") or {}).items():
                env[key] = str(value)

    # The derivation rule (docs/env_profile_redesign.md §3): a profile that
    # declares `derive_jax_markers: true` runs JAX-marked scripts with JAX on.
    # Applied last — the marker set is derived from names, never enumerated,
    # so a profile override cannot (and must not) carve exceptions out of it.
    if env_config.get("derive_jax_markers") and is_jax_marked(file):
        env["PYAUTO_DISABLE_JAX"] = "0"

    return env


def args_for_script(
    file: Path,
    env_config: Optional[dict],
) -> List[str]:
    """Return CLI args to append after the script path, based on env_config.

    Reads the ``args_default`` field of env_vars.yaml — a single string
    that is shlex-split into argv tokens and appended to every
    ``python <script>`` invocation. Used by workspaces whose scripts
    require CLI args (e.g. euclid needs ``--dataset`` and ``--sample``).
    Mirrors the semantics of ``args_default`` in the ``/smoke_test`` skill.

    Returns ``[]`` when env_config is None, args_default is missing, or
    args_default is empty/whitespace — making this a no-op for every
    workspace that does not opt in.
    """
    if env_config is None:
        return []
    raw = env_config.get("args_default", "")
    if not raw or not str(raw).strip():
        return []
    return shlex.split(str(raw))


def is_jax_marked(script: Path) -> bool:
    """The derivation rule: a script is JAX-intent iff a path segment starts
    with ``jax_`` or a segment/stem ends with ``_jax`` or ``_jit``
    (docs/env_profile_redesign.md §3). A mid-stem marker (``*_jit_*``) does
    NOT match — files carry the marker as a prefix/suffix, by convention."""
    for part in Path(script).parts:
        stem = part[:-3] if part.endswith(".py") else part
        if stem.startswith("jax_") or stem.endswith("_jax") or stem.endswith("_jit"):
            return True
    return False


def _pattern_matches(file: Path, pattern: str) -> bool:
    """Match a pattern against a file path.

    Patterns containing '/' are substring-matched against the file's full
    path **including extension** — so a pattern may include ``.py`` to anchor
    against the script form (e.g. ``imaging/visualization.py`` matches
    ``scripts/imaging/visualization.py`` but not
    ``scripts/imaging/visualization_jax.py``). Patterns without '/' match the
    file stem exactly. Same convention as build_util.should_skip().
    """
    if "/" in pattern:
        return pattern in str(file)
    else:
        return file.stem == pattern
