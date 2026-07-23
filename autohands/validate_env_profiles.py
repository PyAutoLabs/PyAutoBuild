"""Validate a workspace's env profiles at PR time — no script execution.

Migration step 1 of docs/env_profile_redesign.md (#161): parse BOTH profiles
(``config/build/profile_smoke.yaml`` and ``profile_release.yaml``), resolve
every script under each, and fail loudly on config errors that today surface
only as the next nightly's red run (~24h feedback → seconds). Since #161 step-6
stage 3 a legacy ``env_vars*.yaml`` file in ``config/build/`` is itself an
error — the old names died and must not creep back.

Error tier (exit 1) — always on:
  - a profile that fails to parse, or parses to a non-mapping
  - unknown top-level keys (allowed: defaults, overrides, args_default)
  - malformed override entries (missing ``pattern``; keys outside
    pattern/set/unset; non-mapping ``set``; non-list ``unset``)
  - dead patterns: an override whose pattern matches zero scripts — a typo or
    a stale entry, the silent-over-match failure mode's cousin
  - declaration syntax: an unknown token or a duplicate ``__Env__`` section in any
    script (docs/env_profile_redesign.md §10)
  - resolver round-trip: a declared script whose fully resolved env still
    carries a var its declaration unsets — a resolver bug, not a config error

Warning tier (exit 0; flips to error at migration steps 4-5 via flags):

  - ``--strict-declarations``: any profile override whose entire effect is an
    unset of only the four declarable vars (no ``set:``) — expressible as an
    in-file declaration instead (default off; CI flips it on post-migration)
  - ``--strict-derivation``: any ``PYAUTO_DISABLE_JAX`` override in a release
    profile (dies when the derivation rule replaces enumeration)
  - ``--strict-markers``: a JAX-marked script (``jax_*``/``*_jax``/``*_jit``
    path segment or stem) resolving ``PYAUTO_DISABLE_JAX=1`` under the
    release profile, or an unmarked script resolving ``0`` — the vacuous-pass
    killer, decidable from path + config alone

Resolution here starts from an EMPTY base (profile defaults + overrides
only), never ``os.environ`` — a validator's verdict must not depend on the
runner's ambient state (docs/env_profile_redesign.md §5).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from env_config import (  # noqa: F401
    DECLARABLE_ENV_VARS,
    ENV_DECLARATION_TOKENS,
    LEGACY_PROFILE_NAMES,
    PROFILE_NAMES,
    _pattern_matches,
    apply_profile,
    is_jax_marked,
    read_env_declaration,
)

ALLOWED_TOP_KEYS = {"defaults", "overrides", "args_default", "derive_jax_markers"}
ALLOWED_OVERRIDE_KEYS = {"pattern", "set", "unset"}


def resolve_clean(script: Path, cfg: dict) -> dict[str, str]:
    """Resolve a script's profile env from an empty base (no ambient env),
    through the same ``apply_profile`` path the runner uses — defaults,
    overrides, then the JAX-marker derivation."""
    return apply_profile({}, script, cfg)


def check_declarations(scripts: list[Path]) -> list[str]:
    """Return declaration-syntax errors across the workspace's scripts.

    Independent of any profile: an unknown token or a duplicate ``__Env__`` section
    is a config error regardless of which profile is resolved. ``read_env_
    declaration`` raises ``ValueError`` for both; we catch and report so the
    validator surfaces the whole set rather than crashing on the first.
    """
    errors: list[str] = []
    for script in scripts:
        try:
            read_env_declaration(script)
        except ValueError as e:
            errors.append(str(e))
    return errors


def check_profile(
    profile_path: Path,
    scripts: list[Path],
    strict_derivation: bool = False,
    strict_markers: bool = False,
    strict_declarations: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for one profile file."""
    errors: list[str] = []
    warnings: list[str] = []
    name = profile_path.name
    try:
        cfg = yaml.safe_load(profile_path.read_text())
    except yaml.YAMLError as e:
        return [f"{name}: YAML parse error: {e}"], []
    if not isinstance(cfg, dict):
        return [f"{name}: top level is not a mapping"], []

    for key in cfg:
        if key not in ALLOWED_TOP_KEYS:
            errors.append(f"{name}: unknown top-level key '{key}'")

    if "derive_jax_markers" in cfg and not isinstance(cfg["derive_jax_markers"], bool):
        # A quoted "true"/"false" is a truthy str either way — the resolver
        # would silently do the wrong thing for "false", so fail loudly here.
        errors.append(
            f"{name}: derive_jax_markers must be a YAML bool, "
            f"got {cfg['derive_jax_markers']!r}"
        )

    overrides = cfg.get("overrides") or []
    if not isinstance(overrides, list):
        errors.append(f"{name}: 'overrides' is not a list")
        overrides = []
    for i, ov in enumerate(overrides):
        if not isinstance(ov, dict) or "pattern" not in ov:
            errors.append(f"{name}: overrides[{i}] missing 'pattern'")
            continue
        for key in ov:
            if key not in ALLOWED_OVERRIDE_KEYS:
                errors.append(f"{name}: overrides[{i}] unknown key '{key}'")
        if "set" in ov and not isinstance(ov["set"], dict):
            errors.append(f"{name}: overrides[{i}].set is not a mapping")
        if "unset" in ov and not isinstance(ov["unset"], list):
            errors.append(f"{name}: overrides[{i}].unset is not a list")
        matched = [s for s in scripts if _pattern_matches(s, ov["pattern"])]
        if not matched:
            errors.append(
                f"{name}: overrides[{i}] pattern '{ov['pattern']}' matches no script "
                "(typo or stale entry)"
            )
        if "release" in name and "PYAUTO_DISABLE_JAX" in (
            set((ov.get("set") or {})) | set(ov.get("unset") or [])
        ):
            msg = (
                f"{name}: overrides[{i}] touches PYAUTO_DISABLE_JAX — the derivation "
                "rule (docs/env_profile_redesign.md §3) replaces enumeration"
            )
            (errors if strict_derivation else warnings).append(msg)
        # --strict-declarations: an override whose ENTIRE effect is an unset of
        # only declarable vars (no set: clause) is expressible as an in-file
        # `__Env__` declaration and should live there instead (docs §10). Default
        # OFF — the migration PRs land first; CI flips it on afterwards.
        if strict_declarations:
            unset_list = ov.get("unset") or []
            # Exception: an override that unsets PYAUTO_DISABLE_JAX and matches
            # any NON-jax-marked script is NOT migratable — a `jax` declaration
            # is profile-agnostic, so on a non-marked script it would flip the
            # release resolution "1" -> absent (numpy -> JAX), a real behaviour
            # change outside the verified "0" -> absent equivalence class. Such
            # an override legitimately stays pattern-keyed.
            _jax_on_unmarked = "PYAUTO_DISABLE_JAX" in unset_list and any(
                _pattern_matches(s, ov["pattern"]) and not is_jax_marked(s)
                for s in scripts
            )
            if (
                unset_list
                and not (ov.get("set") or {})
                and set(unset_list) <= DECLARABLE_ENV_VARS
                and not _jax_on_unmarked
            ):
                errors.append(
                    f"{name}: overrides[{i}] pattern '{ov['pattern']}' unsets only "
                    f"declarable vars {sorted(set(unset_list))} with no set: — "
                    "declare this in-file via an '__Env__' docstring section instead "
                    "(--strict-declarations)"
                )

    if "release" in name:
        for script in scripts:
            try:
                env = resolve_clean(script, cfg)
            except ValueError:
                # A bad `__Env__` declaration — reported by check_declarations;
                # skip the marker check for it rather than crashing the run.
                continue
            disabled = env.get("PYAUTO_DISABLE_JAX")
            marked = is_jax_marked(script)
            if marked and disabled == "1":
                msg = (
                    f"{name}: JAX-marked script resolves PYAUTO_DISABLE_JAX=1: {script}"
                )
                (errors if strict_markers else warnings).append(msg)
            elif not marked and disabled == "0" and (cfg.get("defaults") or {}).get(
                "PYAUTO_DISABLE_JAX"
            ) == "1":
                # Only flag re-enables that bypass the marker convention; a
                # profile whose DEFAULT is 0 (autofit) is JAX-on by policy.
                msg = (
                    f"{name}: unmarked script resolves PYAUTO_DISABLE_JAX=0: {script}"
                )
                (errors if strict_markers else warnings).append(msg)

    # Round-trip: a declared script's fully resolved env must NOT contain any
    # var its declaration unsets — declarations apply last, so a leaked var is a
    # resolver bug, not a config error (docs §10). Syntax errors are reported by
    # check_declarations; skip them here.
    for script in scripts:
        try:
            tokens = read_env_declaration(script)
        except ValueError:
            continue
        if not tokens:
            continue
        env = resolve_clean(script, cfg)
        unset_vars = {
            var for token in tokens for var in ENV_DECLARATION_TOKENS[token]
        }
        leaked = sorted(var for var in unset_vars if var in env)
        if leaked:
            errors.append(
                f"{name}: declared script {script} still resolves {leaked} "
                "after its declaration unsets them — resolver bug"
            )
    return errors, warnings


def validate_workspace(
    root: Path,
    strict_derivation: bool = False,
    strict_markers: bool = False,
    strict_declarations: bool = False,
) -> tuple[list[str], list[str]]:
    scripts_dir = root / "scripts"
    # __init__.py files are package plumbing, not runnable scripts — the
    # runner never executes them, so the marker check must not count them.
    scripts = (
        sorted(p for p in scripts_dir.rglob("*.py") if p.name != "__init__.py")
        if scripts_dir.is_dir()
        else []
    )
    errors: list[str] = []
    warnings: list[str] = []
    # Declaration syntax (unknown token / duplicate line) — profile-independent,
    # checked once over the real scripts/ tree (docs §10).
    errors += check_declarations(scripts)
    build_dir = root / "config" / "build"
    for legacy, canonical in LEGACY_PROFILE_NAMES.items():
        if (build_dir / legacy).is_file():
            errors.append(
                f"legacy {legacy} found — renamed to {canonical} (#161 step 6); "
                "rename the file"
            )
    for kind, canonical in PROFILE_NAMES.items():
        p = build_dir / canonical
        if not p.is_file():
            # The smoke profile is the universal contract — every workspace in
            # the PR gate carries one. The release profile is optional: smoke-
            # only workspaces exist (HowTo*, excluded from mode=release runs),
            # and a *_test repo that loses its release profile still fails
            # loudly in the release runner itself (--env-config on a missing
            # file), so absence here is not silent rot.
            if kind == "smoke":
                errors.append(f"{canonical}: missing")
            continue
        e, w = check_profile(
            p, scripts, strict_derivation, strict_markers, strict_declarations
        )
        errors += e
        warnings += w
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workspace", type=Path, help="workspace repo root")
    ap.add_argument("--strict-derivation", action="store_true")
    ap.add_argument("--strict-markers", action="store_true")
    ap.add_argument(
        "--strict-declarations",
        action="store_true",
        help="error on any profile override whose whole effect is expressible "
        "as an in-file '__Env__' declaration (default off; CI flips it on "
        "after the migration PRs)",
    )
    ns = ap.parse_args(argv)
    errors, warnings = validate_workspace(
        ns.workspace.resolve(),
        ns.strict_derivation,
        ns.strict_markers,
        ns.strict_declarations,
    )
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(
        f"validate_env_profiles: {ns.workspace.name}: "
        f"{len(errors)} error(s), {len(warnings)} warning(s)"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
