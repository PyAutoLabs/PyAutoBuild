"""Validate a workspace's env profiles at PR time — no script execution.

Migration step 1 of docs/env_profile_redesign.md (#161): parse BOTH profiles
(``config/build/env_vars.yaml`` and ``env_vars_release.yaml``), resolve every
script under each, and fail loudly on config errors that today surface only as
the next nightly's red run (~24h feedback → seconds).

Error tier (exit 1) — always on:
  - a profile that fails to parse, or parses to a non-mapping
  - unknown top-level keys (allowed: defaults, overrides, args_default)
  - malformed override entries (missing ``pattern``; keys outside
    pattern/set/unset; non-mapping ``set``; non-list ``unset``)
  - dead patterns: an override whose pattern matches zero scripts — a typo or
    a stale entry, the silent-over-match failure mode's cousin

Warning tier (exit 0; flips to error at migration steps 4-5 via flags):
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

from env_config import _pattern_matches, apply_profile, is_jax_marked  # noqa: F401

ALLOWED_TOP_KEYS = {"defaults", "overrides", "args_default", "derive_jax_markers"}
ALLOWED_OVERRIDE_KEYS = {"pattern", "set", "unset"}
PROFILE_FILES = ("env_vars.yaml", "env_vars_release.yaml")


def resolve_clean(script: Path, cfg: dict) -> dict[str, str]:
    """Resolve a script's profile env from an empty base (no ambient env),
    through the same ``apply_profile`` path the runner uses — defaults,
    overrides, then the JAX-marker derivation."""
    return apply_profile({}, script, cfg)


def check_profile(
    profile_path: Path,
    scripts: list[Path],
    strict_derivation: bool = False,
    strict_markers: bool = False,
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

    if "release" in name:
        for script in scripts:
            env = resolve_clean(script, cfg)
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
    return errors, warnings


def validate_workspace(
    root: Path, strict_derivation: bool = False, strict_markers: bool = False
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
    for fname in PROFILE_FILES:
        p = root / "config" / "build" / fname
        if not p.is_file():
            errors.append(f"{fname}: missing")
            continue
        e, w = check_profile(p, scripts, strict_derivation, strict_markers)
        errors += e
        warnings += w
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workspace", type=Path, help="workspace repo root")
    ap.add_argument("--strict-derivation", action="store_true")
    ap.add_argument("--strict-markers", action="store_true")
    ns = ap.parse_args(argv)
    errors, warnings = validate_workspace(
        ns.workspace.resolve(), ns.strict_derivation, ns.strict_markers
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
