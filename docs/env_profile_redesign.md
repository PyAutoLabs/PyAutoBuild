# Env-profile + validation-gate redesign

**Status:** design deliverable for PyAutoBuild#161 (build-chain campaign #155,
Phase 3). **Decided invariant (human, 2026-07-16):** in `mode=release`, the
NumPy path is the deliberately-validated reference surface for ag/al; JAX
coverage is a derived, loud, bounded set — not a hand-maintained list.
Companion audits: `docs/pre_build_failure_audit.md` (Phase 1),
`PyAutoHeart/docs/readiness_evidence_audit.md` (Phase 2).

## 1. The verified map (measured 2026-07-16 — corrects the brief and one wrong checkpoint)

- **Profiles.** All three `*_workspace_test` repos carry both
  `config/build/env_vars.yaml` (smoke: `TEST_MODE "2"`, `DISABLE_JAX "1"`,
  per-pattern `unset:` lists) and `env_vars_release.yaml`. The release
  profiles differ by design lineage: autofit pins `DISABLE_JAX "0"` with no
  overrides (#47); **ag/al pin `DISABLE_JAX "1"` in defaults with ~10
  hand-enumerated JAX re-enable folders**. A session-1 claim that "no release
  profile pins DISABLE_JAX" was wrong (a `head -4` grep saw only the top of
  the defaults block) — recorded here because the correction method (resolve
  a real script and look) is the design's own point.
- **Consequence.** Production ag/al defaults `use_jax=True`; `mode=release`
  validates NumPy for everything outside the enumerated folders. This is now
  a **stated policy** (§2), not an accident — but the enumeration mechanism is
  the same failure mode 3 that caused the five-night seed incident, and it is
  replaced (§3).
- **Resolvers.** `autohands/env_config.py` and
  `autofit_workspace_test/.github/scripts/run_smoke.py` duplicate the
  resolution. The `build_env` cores are line-identical; the real drift is
  `load_env_config` (run_smoke hardcodes `ENV_VARS_FILE=config/build/
  env_vars.yaml` and tolerates a missing file). The hardcode is failure mode
  4 made structural: **the per-PR gate can never read the release profile.**
- **Ambient inheritance.** Both resolvers start from `os.environ.copy()`: a
  var absent from the profile means "whatever the runner's ambient env
  carries", not a defined value. (Measured the hard way: a probe first
  attributed a profile pin to ambient env; both directions of that confusion
  are possible today.)
- **`PYAUTO_DISABLE_JAX` readers: exactly 2** — `af.Analysis.__init__` and
  `al.AnalysisDataset` (which applies it *before* `super().__init__()`,
  failure mode 8). `SimulatorImaging` does not read it (the static-guard
  false-positive class).
- **Compile-time constraint (new since the brief).** The jax-compile-time
  research (autolens_profiling#71) established JIT compile dominates wall
  time for complex models. Flipping ag/al release to JAX-by-default would
  multiply nightly wall time unpredictably — this is why option (a)
  ("release fidelity = production defaults") was rejected, not only the
  over-reach guard.

## 2. The decided policy (state it where the verdict can cite it)

`mode=release` validates: **every script on the NumPy path** (deterministic,
bounded wall time, the numerical reference), **plus the derived JAX set** (§3)
at release fidelity. The fidelity gap this leaves — most ag/al scripts are
never release-validated on the backend production users get by default — is
**accepted and stated**, bounded by: (i) the JAX-set derivation guaranteeing
every JAX-*specific* surface is JAX-validated, (ii) the loud-failure guard
(§4) guaranteeing no script *silently* believes it tested JAX when it did
not, and (iii) the workspace_test cross-xp parity scripts remaining the
NumPy↔JAX equivalence witnesses. Revisit the policy if compile times fall
(persistent cache work) — the derivation makes the flip cheap later.

## 3. Derive, don't enumerate

The current release overrides list ~10 folder patterns per repo whose names
already encode the intent: `jax_*/`, `*_jax`, `*_jit`. Replace the per-repo
`overrides:` lists with **one derivation rule in the resolver**:

    a script runs with JAX enabled in mode=release iff any path segment or
    stem matches `jax_*`, `*_jax`, or `*_jit`.

Properties: adding a JAX script to a `jax_*` folder (or naming it `*_jax`)
self-registers — the "remember to add your script" step is deleted, which is
the seed incident's direct cause. The rule lives in the single resolver (§5),
so both gates and any future consumer agree. The profile files keep only
`defaults:`; a lint (part of §6's config check) fails any profile that still
carries a `PYAUTO_DISABLE_JAX` override so the dead mechanism cannot creep
back.

Measured against today's lists: every existing override pattern in both ag/al
release profiles matches the rule except `database/scrape/` (autolens) —
rename that folder's scripts (or folder) to carry the `_jax` marker, or add
it to the parity set; decide at migration time, do not carry an exception
list (an exception list is the trap reborn).

## 4. Loud failure instead of vacuous pass

The vacuous-test failure mode (a script asserting JAX behaviour, silently
running NumPy, passing) dies at the **runner**, not in library warnings (the
loud-warning-in-`af.Analysis` fix was built and killed by adversarial review
— it cannot distinguish "requested" from "defaulted" while ag/al default
`True`):

- The runner already knows, per script, the resolved env. Rule: **a script
  whose path/stem carries the JAX marker (§3) must resolve `DISABLE_JAX=0`,
  and vice versa in mode=release** — any mismatch is a validation *error*
  (config bug), not a script run. This is decidable purely from path + env,
  so the `SimulatorImaging` static-analysis false-positive class never
  arises.
- Long-term (separate cross-repo API decision, flagged as an open item, not
  assumed): thread `use_jax: Optional[bool] = None` through af/ag/al so
  "explicitly requested" becomes representable; then the env downgrade of an
  explicit `True` can warn loudly at the one reader (§5). Until then, the
  runner-level check above covers the release surface.

## 5. One resolver, one reader, defined baseline

- **One resolver:** `autohands/env_config.py` is canonical. `run_smoke.py`
  imports it (the workspace_test repos already vendor a PyAutoBuild checkout
  in CI; where truly unavailable, a pinned copy with a drift-check beats a
  silent fork). Its hardcoded `ENV_VARS_FILE` dies with the merge.
- **Defined baseline:** resolution starts from a **scrubbed** base env (a
  named allowlist of pass-through vars: PATH, HOME, PYTHONPATH, cache dirs) +
  profile defaults + derivation — never `os.environ.copy()`. A var's value is
  then a function of (profile, script), not of the runner's ambient state.
- **One reader:** `al.AnalysisDataset`'s duplicate early read of
  `PYAUTO_DISABLE_JAX` folds into the base-class read (`af.Analysis`), so an
  override happens in exactly one place and the base class can see it.
  (Library PR, behind its own plan; the layered read is failure mode 8 and
  also what killed the loud-warning fix.)

## 6. Close the PR-time gap

A cheap `validate_env_profiles` check (PyAutoBuild-owned, runnable in each
workspace_test PR gate): parse BOTH profiles, resolve every script under
each, and fail on — unknown keys, `DISABLE_JAX` overrides (§3 lint), marker/
env mismatches (§4), and patterns that match zero scripts (a dead pattern is
a typo or a stale entry — the silent over-match failure mode's cousin). This
runs in seconds with no script execution, so release-profile config errors
surface at PR time instead of in the next nightly (~24h → ~1min feedback).

## 7. "Smoke" means one thing

Rename the *profile* pair to what they are: `env_vars.yaml` →
`profile_smoke.yaml`, `env_vars_release.yaml` → `profile_release.yaml` (names
carry the concept; the per-PR curated `smoke_tests.txt` gate keeps the word
"smoke"). Mechanical rename, last migration step, after consumers are on the
single resolver.

**Step 6 status (2026-07-23):** the tooling half landed — every PyAutoHands
reader now accepts BOTH the canonical and legacy names (canonical preferred)
via `env_config.find_profile`, so workspace repos can rename with no breakage
window. A later stage-3 PR removes the legacy `env_vars*.yaml` fallbacks once
every workspace has renamed.

**Stage 3 landed (2026-07-23):** every workspace repo has renamed, so the
migration-window fallbacks are gone — `find_profile` resolves the canonical
`profile_smoke.yaml` / `profile_release.yaml` only, and a legacy `env_vars*.yaml`
file in `config/build/` is now a validator error so the old names cannot creep back.

## 8. Migration path (each step green on its own)

1. `validate_env_profiles` check (§6) against the *current* files — lands
   first, catches drift during the rest.
2. Single resolver (§5): run_smoke imports env_config; delete its fork.
3. Scrubbed baseline (§5) — behaviour change is confined to vars the runner
   ambiently carried; measure a full smoke resolve before/after (diff of
   resolved envs across all scripts must be empty on CI).
4. Derivation rule (§3): replace ag/al release `overrides:` with the rule;
   resolve-diff must be empty except `database/scrape/` (decided then).
5. Marker/env mismatch guard (§4) flips from warn to error after one clean
   nightly.
6. Rename (§7). 7. Library one-reader fold (§5, own plan). 8. The
   `Optional[bool]` sentinel decision (own cross-repo plan, human-gated).

## 9. Rejected / open

- **Rejected: option (a), JAX-by-default release for ag/al** — the brief's
  over-reach guard plus the measured compile-time constraint (§1). Revisit
  when compile cost drops.
- **Rejected (re-confirmed from the brief):** smoke_tests.txt promotion
  (never reads the release profile; deliberately small); the static
  `use_jax=True` config guard (SimulatorImaging false positives); the
  `af.Analysis` loud warning (silent for al, noisy for defaults — replaced by
  the runner-level guard, which is env+path-decidable).
- **Open (human):** the `database/scrape/` disposition at step 4; the
  `Optional[bool]` sentinel API change; whether HowTo*/user-workspace
  profiles (outside the three _test repos) adopt the same shape in the same
  pass or lag one release.

## 10. In-file env declarations (#187, Stage 1 — mechanism)

Pattern-keyed profile overrides are the seed incident's failure mode 3: a
per-pattern rule lives far from the script it governs, drifts silently, and can
be silently defeated by a later, broader pattern. The end state is that a script
declares its own env intent **in-file**, and the pattern overrides that only
express that intent are deleted. Stage 1 lands the mechanism; the workspace
migrations follow in later PRs.

**Syntax — one form.** A script declares its env intent in the `__Env__`
docstring section, **the only form in every repo** (user workspaces and `_test`
repos alike). The legacy `# ENV:` comment form has been **REMOVED** now that
every repo has migrated: a `# ENV:` line anchored at column 0 now **raises**
rather than parsing. A file may carry **exactly one** `__Env__` declaration (a
second header, in any block, is a validator/resolver error).

*Canonical `__Env__` docstring form — a section appended INSIDE an existing
docstring.* Following the workspace doctrine that multiple `__Section__` headers
share **one** docstring (never close-then-reopen — a `"""` immediately followed
by another `"""`), `__Env__` is the **last section of an existing docstring**:
the final docstring in user-facing scripts, the module docstring in `_test`
scripts. The header is a column-0 `__Env__` line (a trailing parenthetical such
as `(Developer Only)` is allowed) appearing **anywhere inside** the block, and
**exactly one** `ENV: <tokens>` line (no leading `#`) must follow it before the
closing delimiter:

```python
"""
Wrap Up
-------

...closing tutorial prose for this script...

__Env__ (Developer Only)

Not user documentation: this section configures the automated test harness.

ENV: jax full_datasets
"""
```

*Fallback — a standalone `__Env__` docstring.* A script with **no adjacent
docstring** to append to may carry the section as its own `"""__Env__ … """`
block. This is the only case where a dedicated `__Env__`-only docstring is
legal; where a docstring already exists, the section is merged into it.

**Placement conventions** (where the section lives depends on the repo's
audience):

| Repos | Placement | Header |
|-------|-----------|--------|
| User-facing workspaces (`autolens_workspace`, `autogalaxy_workspace`) **and the HowTo lectures** (`HowToFit`, `HowToGalaxy`, `HowToLens`) | End of the **final docstring** (bottom of the script) | `__Env__ (Developer Only)` + the developer-only note |
| `_test` repos (`autolens_workspace_test`, `autogalaxy_workspace_test`, `autofit_workspace_test`) | End of the **module docstring** (top of the script) | `__Env__` + a short one-line note |

- **User-facing workspaces and the HowTo lectures** are teaching material read
  top-to-bottom as tutorial prose, so the harness config goes **last**, out of
  the reader's way, and carries the developer-only note. It is **stripped from
  generated notebooks and markdown** by
  `add_notebook_quotes.strip_env_declarations`, applied in the shared
  `build_util.py_to_notebook` path (used by BOTH `generate.py` notebook
  generation and `generate_markdown.py`, for the workspaces and the HowTo repos
  alike) and reused by `navigator.py` — so it never leaks into published docs or
  the LLM catalogue, and a future HowTo declaration is stripped automatically.
  (The HowTo repos currently carry **no** declarations — no declarable overrides
  existed there at the #187 migration — but the rule is fixed for when one is
  added.)
- **`_test` repos** are code-heavy / doc-light and are **not** doc-generated, so
  the section sits at the end of the **module docstring** (top of the script)
  where a developer reading the harness script sees it immediately, with a short
  note (no "stripped from notebooks" claim, which would not apply).

*Legacy `# ENV:` comment form (REMOVED).* The single-comment-line form,
`# ENV: <tokens>` at column 0, has been removed now that every repo carries the
`__Env__` section. A `# ENV:` line anchored at column 0 now **raises**:

```
<path>: the '# ENV:' comment form was removed — declare env requirements in an
'__Env__' docstring section instead (docs/env_profile_redesign.md §10)
```

An indented or trailing `# ENV:` is still prose (only a column-0 match raises).
The parser is
`autohands/env_config.read_env_declaration(path) -> list[str] | None`.

**Token table.** Each token UNSETS the managed var(s) it names:

| Token | Unsets |
|-------|--------|
| `jax` | `PYAUTO_DISABLE_JAX` |
| `full_datasets` | `PYAUTO_SMALL_DATASETS` |
| `real_plots` | `PYAUTO_FAST_PLOTS` |
| `real_search` | `PYAUTO_TEST_MODE` |
| `real_output` | all four of the above |

**Unset semantics, and why.** A token *releases* its var — it removes the var
from the resolved env so the reader falls back to the **library default**. For
all four vars that default is the well-defined "absent == off == `0`" state,
verified against the reader code (2026-07-23):

| Var | Reader (file:line) | absent | `"0"` | `"1"` |
|-----|--------------------|--------|-------|-------|
| `PYAUTO_TEST_MODE` | PyAutoNerves `autonerves/test_mode.py:14` (`int(get("...","0"))`) | level 0 (off) | 0 (off) | level 1 |
| `PYAUTO_DISABLE_JAX` | PyAutoFit `autofit/non_linear/analysis/analysis.py:68` (`get(...) == "1"`) | not disabled | not disabled | disabled |
| `PYAUTO_SMALL_DATASETS` | PyAutoArray `autoarray/mask/mask_2d.py:363` et al. (`get(...) == "1"`) | full | full | small |
| `PYAUTO_FAST_PLOTS` | PyAutoArray `autoarray/plot/utils.py:15` et al. (`get(...) == "1"`) | real | real | fast |

Because absent behaves identically to `"0"`, unsetting is exactly what today's
profile `unset:` lists do — which is what makes the later
profile→declaration migration a **provable no-op**: the resolved-env diff over
every script is empty before and after. That empty-diff is the migration's gate,
the mechanical form of §8 steps 3–4.

**Precedence (last wins):** scrub → defaults → overrides → derivation →
**declarations**. Declarations are applied LAST, in `apply_profile`, so no
profile pattern — however broad — can silently defeat a script's declared
intent.

**Path resolution.** `apply_profile(env, file, env_config)` keeps its fixed
positional signature (the ~10 vendored `run_smoke.py` copies and the mega-run
runners must not change). The declared source is found by candidate resolution
(first existing wins): `Path(file)` as given (absolute mega-run script path);
`scripts/`-relative to cwd (the per-PR gate's `imaging/x.py`); and the
`notebooks/`→`scripts/` mirror (the mega-run notebook runner's absolute
`notebooks/…` path). A `.ipynb` entry maps to its `.py` source first. No
on-disk candidate → no declaration; the validator, which walks the real
`scripts/` tree, is the drift catcher.

**Validator additions** (`autohands/validate_env_profiles.py`): declaration
syntax errors (unknown token, duplicate line); a round-trip check (a declared
script's resolved env must not carry a var it unsets — else resolver bug); and
`--strict-declarations` (default OFF, CI on post-migration) which errors on any
override whose whole effect is an unset of only the four declarable vars with no
`set:` clause — that override should be an in-file declaration instead.

**Triage rule (verbatim).** An env fix must be justified by the script's
declared intent, never by making a failure disappear — at least three July 2026
failures first mis-diagnosed as env gaps were real library bugs
(PyAutoArray#398, PyAutoFit#1415, PyAutoGalaxy#515).

## Trust nothing here

Same authorship as the campaign's other documents, same instruction: the map
in §1 was verified by resolving and reading full files *after* a wrong
session-1 claim from a truncated grep — re-measure before acting; the
migration's empty-resolve-diff gates (§8 steps 3-4) are the mechanical form
of that lesson.
