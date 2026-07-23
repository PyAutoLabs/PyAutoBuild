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

## Trust nothing here

Same authorship as the campaign's other documents, same instruction: the map
in §1 was verified by resolving and reading full files *after* a wrong
session-1 claim from a truncated grep — re-measure before acting; the
migration's empty-resolve-diff gates (§8 steps 3-4) are the mechanical form
of that lesson.
