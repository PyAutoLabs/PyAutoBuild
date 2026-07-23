"""Regression tests for ``clone_seed.substitute`` — the Clone Agent's name
substitution.

The skill-prefix rule (``al_ -> ac_``, built from the package initials in
``PyAutoBrain/agents/conductors/clone/_clone.py``) exists to rename skill files
at birth: ``al_fit_model.md -> ac_fit_model.md``. As a bare ``str.replace`` it
also rewrote the ``al_`` *inside* ordinary identifiers, which is how
autocti_assistant was born with ``totac_draws``, ``externac_shear.yaml`` and
``radiac_minimum`` (PyAutoBrain#150). Two of those were live config keys that
silently stopped overriding; five were prior files that could no longer be found
for their classes.

The rule must still apply to file *text*, because skills cross-reference each
other by name in prose — a path-only rule would leave broken links in every
newborn. So it is word-anchored instead: it may start a token, never continue
one.
"""

import pytest

from autobuild.clone_seed import substitute

SKILL_PREFIX = ("al_", "ac_", "word")
FULL_NAME = ("autolens_assistant", "autocti_assistant")
PACKAGE = ("autolens", "autocti")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("al_fit_model.md", "ac_fit_model.md"),           # start of string
        ("skills/al_fit_model.md", "skills/ac_fit_model.md"),  # after a path separator
        ("see `al_audit` for details", "see `ac_audit` for details"),  # after a backtick
        ("run al_audit now", "run ac_audit now"),         # after a space
        ("(al_audit)", "(ac_audit)"),                     # after a bracket
    ],
)
def test_word_anchored_rule_renames_at_a_token_boundary(text, expected):
    assert substitute(text, [SKILL_PREFIX]) == expected


@pytest.mark.parametrize(
    "text",
    [
        "total_draws",        # the PyAutoFit Drawer param — was corrupted to totac_draws
        "total_contours",     # the autoarray plot key — was corrupted to totac_contours
        "external_shear",     # was corrupted to externac_shear
        "isothermal_core",    # was corrupted to isothermac_core
        "exponential_core",   # was corrupted to exponentiac_core
        "virial_mass_conc",   # was corrupted to viriac_mass_conc
        "radial_minimum",     # was corrupted to radiac_minimum
        "  total_draws: 50",  # as it appears in a yaml body
        "config/priors/mass/sheets/external_shear.yaml",  # as it appears in a path
    ],
)
def test_word_anchored_rule_never_matches_mid_token(text):
    assert substitute(text, [SKILL_PREFIX]) == text


def test_two_element_rules_keep_plain_replace_semantics():
    """Existing plan JSON has no third element — those rules must be unchanged,
    including where they legitimately match inside a longer token."""
    assert substitute("autolens_workspace", [PACKAGE]) == "autocti_workspace"
    assert substitute("PyAutoLens", [("PyAutoLens", "PyAutoCTI")]) == "PyAutoCTI"


def test_full_substitution_list_on_a_realistic_body():
    """The four rules in _clone.py order, over text containing both a skill
    reference (must rename) and ordinary identifiers (must not)."""
    subs = [FULL_NAME, SKILL_PREFIX, ("PyAutoLens", "PyAutoCTI"), PACKAGE]
    body = (
        "# autolens_assistant\n"
        "See `al_fit_model.md`. Built on PyAutoLens (autolens).\n"
        "total_draws: 50\n"
        "external_shear: 0.05\n"
    )
    assert substitute(body, subs) == (
        "# autocti_assistant\n"
        "See `ac_fit_model.md`. Built on PyAutoCTI (autocti).\n"
        "total_draws: 50\n"
        "external_shear: 0.05\n"
    )
