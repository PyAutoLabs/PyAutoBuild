"""Per-script environment variable configuration.

Loads the profile yaml and builds a tailored environment dict for each script,
applying defaults and per-pattern overrides.
"""

import os
import re
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


# --- In-file env declarations (docs/env_profile_redesign.md §10) --------------
#
# A script declares the workspace-behaviour vars it wants RELEASED (unset) via a
# single anchored `# ENV: <tokens>` comment line. Each token unsets its managed
# var(s) AFTER the profile's defaults/overrides/derivation are applied, so the
# var falls back to the library default — which for all four vars is the "absent
# == off == '0'" state (verified against the reader code, docs §10). This is
# exactly the semantics of today's profile `unset:` lists, which is what makes
# the later profile->declaration migration a provable no-op (empty resolved-env
# diff). The token map (a token may release more than one var):
ENV_DECLARATION_TOKENS: Dict[str, tuple] = {
    "jax": ("PYAUTO_DISABLE_JAX",),
    "full_datasets": ("PYAUTO_SMALL_DATASETS",),
    "real_plots": ("PYAUTO_FAST_PLOTS",),
    "real_search": ("PYAUTO_TEST_MODE",),
    "real_output": (
        "PYAUTO_DISABLE_JAX",
        "PYAUTO_SMALL_DATASETS",
        "PYAUTO_FAST_PLOTS",
        "PYAUTO_TEST_MODE",
    ),
}

# The four vars a declaration can release — the union of every token's targets.
# Used by the validator's --strict-declarations gate to decide whether a profile
# override's effect is fully expressible as an in-file declaration.
DECLARABLE_ENV_VARS = frozenset(
    var for vars_ in ENV_DECLARATION_TOKENS.values() for var in vars_
)

# The declaration line: `# ENV:` anchored at column 0, then whitespace-separated
# tokens. At most one such line per file (more is a validator/resolver error).
_ENV_DECLARATION_RE = re.compile(r"^# ENV:(?P<tokens>.*)$")


def read_env_declaration(path) -> Optional[List[str]]:
    """Return the declared env tokens for a script, or None if it declares none.

    Scans the whole file line-by-line (scripts are small) for the single
    anchored ``# ENV: <tokens>`` line. Returns the list of token strings (each a
    key of ``ENV_DECLARATION_TOKENS``); an empty ``# ENV:`` line returns ``[]``.

    Raises
    ------
    ValueError
        If the file carries more than one ``# ENV:`` line, or a token is not in
        ``ENV_DECLARATION_TOKENS`` — loud beats silent, in both the resolver and
        the validator (which catches and reports it as a config error).
    """
    path = Path(path)
    tokens: Optional[List[str]] = None
    for line in path.read_text().splitlines():
        m = _ENV_DECLARATION_RE.match(line)
        if m is None:
            continue
        if tokens is not None:
            raise ValueError(
                f"{path}: more than one '# ENV:' declaration line "
                "(at most one is allowed)"
            )
        tokens = m.group("tokens").split()
        for token in tokens:
            if token not in ENV_DECLARATION_TOKENS:
                raise ValueError(
                    f"{path}: unknown env declaration token '{token}' "
                    f"(allowed: {', '.join(sorted(ENV_DECLARATION_TOKENS))})"
                )
    return tokens


def _declaration_source_path(file: Path) -> Optional[Path]:
    """Resolve the on-disk source file whose ``# ENV:`` line governs ``file``.

    The ``file`` argument reaches us in different forms from different callers
    (all keeping the fixed positional signature — no vendored copy is edited):

    * per-PR gate (``run_smoke.py``): a path RELATIVE to ``scripts/``, e.g.
      ``imaging/model_fit.py`` (or ``imaging/model_fit.ipynb`` for a notebook),
      with cwd = workspace root;
    * mega-run script runner (``build_util.execute_scripts_in_folder`` via
      ``run_python.py``): an ABSOLUTE path under ``scripts/``;
    * mega-run notebook runner (``build_util.execute_notebooks_in_folder`` via
      ``run.py``): an ABSOLUTE path under ``notebooks/``.

    A ``.ipynb`` entry is first mapped to its ``.py`` source — notebooks are
    generated from scripts and the declaration lives in the script.

    Candidate order (first existing wins):
      1. ``Path(file)`` as given — the absolute script path from the mega-run
         script runner, or any scripts/-prefixed path;
      2. ``Path("scripts") / file`` relative to cwd — the per-PR gate's
         scripts-relative path;
      3. the ``notebooks/`` -> ``scripts/`` mirror path — the mega-run notebook
         runner's absolute path under ``notebooks/`` maps to the source script
         under ``scripts/``.

    Returns None when no candidate exists on disk (no declaration). The
    validator, which walks the real ``scripts/`` tree, is the drift catcher —
    the resolver stays silent so a moved/absent file never crashes a run.
    """
    src = Path(file)
    if src.suffix == ".ipynb":
        src = src.with_suffix(".py")

    candidates = [src, Path("scripts") / src]

    parts = src.parts
    if "notebooks" in parts:
        # Swap the LAST 'notebooks' segment for 'scripts' (mirror layout).
        idx = len(parts) - 1 - parts[::-1].index("notebooks")
        candidates.append(Path(*parts[:idx], "scripts", *parts[idx + 1 :]))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# The per-script env profile filename for each kind. The legacy env_vars*.yaml
# names died at #161 step-6 stage 3 — canonical names only.
PROFILE_NAMES = {
    "smoke": "profile_smoke.yaml",
    "release": "profile_release.yaml",
}

# The legacy env_vars*.yaml names, kept only so the validator can raise a
# targeted "you renamed away from this" error if one creeps back.
LEGACY_PROFILE_NAMES = {
    "env_vars.yaml": "profile_smoke.yaml",
    "env_vars_release.yaml": "profile_release.yaml",
}


def find_profile(build_dir: Path, kind: str) -> Optional[Path]:
    """Return the canonical profile file of the given kind ("smoke"/"release")
    in ``build_dir``, or None if it does not exist.

    The legacy ``env_vars*.yaml`` names died at #161 step-6 stage 3.
    """
    candidate = build_dir / PROFILE_NAMES[kind]
    return candidate if candidate.is_file() else None


def load_env_config(config_path: Path) -> dict:
    """Load and return the parsed profile yaml."""
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
    then the JAX-marker derivation (when the profile opts in), then the script's
    own in-file ``# ENV:`` declaration.

    The single resolution path shared by the runner (``build_env_for_script``,
    base = scrubbed ambient env) and the validator (``resolve_clean``, base =
    empty dict) — docs/env_profile_redesign.md §5. Mutates and returns ``env``.

    Precedence (last wins): scrub -> defaults -> overrides -> derivation ->
    declarations. Declarations are applied LAST so no profile pattern can
    silently defeat a script's declared intent (docs §10).
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

    # In-file declaration (docs/env_profile_redesign.md §10), applied LAST. Each
    # token UNSETS its managed var(s), so the var falls back to the library
    # default (== absent == "0"/off). read_env_declaration RAISES on an unknown
    # token or a duplicate line — loud beats silent in the resolver too.
    source = _declaration_source_path(file)
    if source is not None:
        for token in read_env_declaration(source) or []:
            for var in ENV_DECLARATION_TOKENS[token]:
                env.pop(var, None)

    return env


def args_for_script(
    file: Path,
    env_config: Optional[dict],
) -> List[str]:
    """Return CLI args to append after the script path, based on env_config.

    Reads the ``args_default`` field of the profile yaml — a single string
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
