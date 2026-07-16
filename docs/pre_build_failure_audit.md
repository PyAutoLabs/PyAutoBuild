# pre_build.sh failure-class audit — and what its local commit is for

**Status:** audit deliverable for PyAutoBuild#156 (build-chain campaign #155, Phase 1).
**Method:** every claim below is measured (2026-07-16), read-only (`git add -n`,
sed-to-stdout, `black --check`, origin-verified), against the real repos — both
`.gitignore` dialect groups. Re-measure before relying on any number here.

## 1. The verified map (division of labour, as it actually is)

What actually modifies files during a `pre_build.sh` run, and who commits what:

| artifact | modified by (local) | staged by (local) | committed on the runner | net owner |
|---|---|---|---|---|
| `scripts/**/*.py` formatting | `black .` | `git add scripts/` | never | **pre_build (genuine)** |
| notebooks (`*.ipynb`) | `generate.py` | `git add notebooks/` | regenerated + committed explicitly (`release_workspaces` → `git add *.ipynb`) | runner (local copy redundant) |
| `llms-full.txt`, `workspace_index.json` | `generate.py` (root) | **never** — `:88` is dead (§2) | swept by `git add -A` inside the *"bump Colab URL tag refs"* commit | **unowned — rides along, mislabeled** |
| README Colab URLs | not touched locally | — | `bump_colab_urls.sh` + the same `git add -A` | runner |
| README version pin (`<pkg> vX`) | `:55` sed (edits where a pin exists) | **never** — `:88` is dead | **nothing** — the runner-side step was deliberately removed (#120/#121; see the comment in `release.yml`) | **orphaned** |
| `dataset/`, `config/` | nothing in the run | `git add dataset|config/` | never | vestigial (stages only pre-existing human dirt) |
| black collateral outside staged dirs | `black .` | never (no rule covers them) | never | perpetual churn (§4) |

**Proven consequence of the orphaned README pin** (origin-verified): after the
2026.7.15.1 release, `autofit_workspace` README.md pins `PyAutoFit v2026.7.9.1`
(the 07-13 hand-bump value); `autofit_workspace_test` and `autolens_workspace_test`
pin `v2026.5.14.1` (~2 months stale). The other 7 repos passed a `readme_pkg`
but have **no pin pattern in README.md at all** — for them the banner + sed are
semantically empty on every run. The `"Bumping README version → …"` banner has
printed a false claim, 13/13 repos, on every release for months.

## 2. Complete enumeration of the failure class

The shape: a command whose failure is handled wrongly in one of two opposite
directions — fatal under `set -e` when a no-op is legitimate, or swallowed by
`|| true`/`2>/dev/null`/ignored return when a real failure matters.

| site | direction | measured (13 repos) |
|---|---|---|
| `:55` `sed … README.rst README.md 2>/dev/null \|\| true` | swallow | exit **2 in 13/13** (no repo has `README.rst`); `\|\| true` permanently load-bearing; real sed failure indistinguishable |
| `:79` `git add dataset/ 2>/dev/null \|\| true` | swallow (post-#154) | exit 1 in 5 repos (whole-dir ignore), 0 in 4 (allowlist dialect), nodir in 4 — correct direction *today*, but a real failure (index.lock, perms) is also silent |
| `:82` `[ -d "$d" ] && git add "$d/"` (config/notebooks/scripts) | **fatal, latent** | exit 0 wherever present today; a present-but-fully-ignored dir = bug-1 redux, kills the release |
| `:88` root-glob `git add -- *.py *.md … 2>/dev/null \|\| true` | swallow | exit **128 in 13/13** — a **global no-op**. Six patterns (`*.cfg *.ini *.toml *.yml *.yaml setup*`) match nothing in ANY repo; each unmatched glob stays literal and poisons the whole pathspec list |
| `:50` `black .` | fatal | plus unstaged collateral (§4) |
| `:60` `generate.py` | fatal | pre_build calls it with `report=None` → any single script conversion error raises and kills the release |
| `generate.py:107` `os.system(f"git add -f {notebook}")` | **ignored return** | a hidden 4th tolerant site, in a callee, using `-f` — staging responsibility is smeared across two files |
| `:125` `git add -A` on PyAutoBuild, current branch | — | commits onto whatever branch is checked out (documented trap) |
| `:142` `gh workflow run` | fatal at the end | after 14 repos already pushed — no atomicity anywhere: any mid-sequence fatal leaves earlier repos released-committed and later repos untouched |

Original brief's "three sites, three hits" **understated it**: with `:82`'s
latent class, `generate.py:107`, and the atomicity gap, the file has ~6 members
of the class, and the two live "safety nets" (`:55`, `:88`) are both dead weight
(one masks an orphaned artifact, one is a global no-op).

## 3. The design question, answered per artifact

**"If release.yml regenerates and commits these artifacts on the runner anyway,
what is pre_build's local commit for?"** — it decomposes; the aggregate answer
is *mostly redundant, one genuine product, one broken orphan*:

- **Genuine:** committing black's reformat of `scripts/` (and `slam_pipeline/`).
  This is the only artifact the run itself produces that only the local commit
  ships. (The runner regenerates notebooks *from the pushed scripts*, so the
  formatting does reach notebooks via the runner.)
- **Redundant:** notebooks staging — the runner rebuilds and commits them.
- **Broken/unowned:** everything on the root-glob line. `llms-full.txt` /
  `workspace_index.json` reach main only as **accidental `git add -A` sweep**
  inside the runner's Colab commit (works only for `bump_colab_urls: true`
  repos — autofit/ag/al workspace + HowTo*; euclid + assistants opted out, and
  correspondingly `generate_notebooks: false` there, so nothing goes stale).
  The README version pin reaches main **never** (§1).
- **Vestigial:** `dataset/` and `config/` staging — nothing in the run modifies
  them; they exist to sweep pre-existing human-uncommitted work into a release
  commit. That "feature" is how #126 leaked simulated datasets; the organism
  has been deliberately retiring it (#150).

## 4. Black collateral (measured)

`black --check` on current mains: **13 files** are reformatted by every release
and never staged by any rule — `.github/scripts/check_tutorials_complete.py` in
each HowTo repo (3) and 10 `autoassistant/*.py` files in `autolens_assistant`.
They churn dirty-local every release until a clean-slate wipes them, forever.
Answer to the brief's open question: this is a **third instance of the class**
(work done, claim implied, result dropped), not intended behaviour.

## 5. Target design (proposal — argue with it)

Principles the enumeration supports: a no-op and a failure must be different
events; a log line must not claim work that did not happen; one side owns each
artifact; if the runner is the real producer, the local script stops pretending.

**Recommended shape (the #47 / delete-the-trap outcome), as three landable steps:**

1. **Delete the dead lines** (no behaviour change, measured): the `:88` root
   glob (a 13/13 no-op — deleting it changes nothing on main) and the `:55`
   README bump (its artifact is orphaned; deleting the *false signal* beats
   keeping a banner that lies). Decide the README pin's fate in Phase 4 of the
   campaign (`release_version_sync_back_to_main.md`): either the runner owns it
   again (one sed in `release_workspaces`, next to the Colab bump, committed
   explicitly) or the pins come out of the READMEs in favour of "install the
   latest release" + floors. **Either way the owner is the runner or nobody —
   not a local sed whose output nothing stages.**
2. **Give the swept artifacts an owner:** in `release_workspaces`, replace the
   Colab step's `git add -A` with explicit paths (`llms-full.txt`,
   `workspace_index.json`, README, notebooks dir) and an honest commit message.
   `git add -A` on a runner checkout is the same unowned-sweep idiom that made
   bug 2 invisible for months.
3. **Shrink pre_build to what it genuinely produces:** black + generate +
   allowlist check + stage the named dirs the run actually modified
   (`scripts/`, `slam_pipeline/`, `notebooks/` if kept) + explicit
   "matched nothing (expected)" vs "failed" handling on the dataset add. Move
   the black-collateral files inside a staged rule or stop black'ing them
   (black a fixed dir list, not `.`). Fix `generate.py:107` to use a checked
   call, not `os.system`, and decide deliberately whether `-f` is needed.

**Not proposed:** `shopt -s nullglob` on `:88` — it would make a redundant line
silently succeed, which is the trap wearing a new hat (the brief's own
rejection reasoning, confirmed: the line stages nothing anyone needs).

## 6. Rejected / open decisions for the human

- **Rejected: hardening every line with better error handling.** The class
  keeps reappearing because the file does jobs it doesn't own; fewer jobs beats
  more armour, and 2 of its 3 "safety nets" were dead weight on measurement.
- **Open (Phase 4 fork):** where the README version pin should live, if
  anywhere. This audit only proves nobody owns it today.
- **Open:** whether pre_build's "sweep human dirt in dataset/config into the
  release" vestige should be deleted (recommended — it is #126's mechanism) or
  kept deliberately. Deleting it makes releases require clean mains, which
  Heart already checks.
- **Open:** atomicity — a mid-sequence fatal leaves a half-pushed release
  surface. Worth a fail-fast pre-pass (all repos validated before any push)?
  Costed as a follow-up, not this PR.

## Trust nothing here

Written by an agent, same day as the measurements. Three instrument errors were
made *during this audit* and caught only by re-checking (a piped `$?` that read
`head`'s exit status instead of grep's, twice, and a `black --check -q` whose
silence was mistaken for cleanliness). Every table above is cheap to re-measure
and the commands are stated — re-measure before acting.
