# Nightly live releases behind an activity gate — design

**Status:** phase-1 design, for human review (the review of this document's PR
*is* the design review). Issue:
[PyAutoBuild#127](https://github.com/PyAutoLabs/PyAutoBuild/issues/127).
Prompt: `PyAutoMind/issued/nightly_release_activity_gate.md`. Date: 2026-07-09.

**Decided endpoint (user, 2026-07-09):** once the next manual live release
succeeds, nightly runs perform **full live PyPI releases unattended** — no
per-release human approval. The human's role becomes: a kill switch, paging
response on any red/anomaly, and reviewing the morning digest of what shipped.
This is a scoped exception to the autonomy contract's "release is always
human-required" invariant; the dated doctrine edit ships alongside this note
(`PyAutoBrain/AUTONOMY.md`, same task).

---

## 1. What already exists (the design builds on, not around, these)

| Piece | Where | What it gives the nightly |
|-------|-------|---------------------------|
| Release cron | `release.yml` `schedule: 0 2 * * 1-5` + `resolve_mode` | A scheduled run path that rehearses (TestPyPI-only) until repo var `RELEASE_MODE=live` |
| Date version scheme | `release.yml` `version_number` | Scheduled runs already auto-derive `YYYY.M.D.1`; `run_attempt` suffixes re-runs; no run-number footgun |
| M1 rehearsal | `release.yml` `rehearsal=true` → `rehearsal_version` job | TestPyPI wheels + `testpypi-rehearsal-version` artifact (version, packages, build SHA) |
| M3 release-fidelity validation | `PyAutoHeart` `workspace-validation.yml` `mode=release` | Runs the workspace script matrix + `verify_install` against the rehearsed wheels; emits a `{"stage": "integrate"}` report |
| M4 orchestrator | `pyauto-brain release validate` (`agents/conductors/release/validate.sh`) | Full Stages 0–3: preflight → unit → rehearse → integrate → ingest → verdict, with commit-SHA authority and stable exit codes |
| The release door | `pyauto-brain release` → Build Agent release mode | The single gate implementation: vitals refresh, GREEN/YELLOW(`--force`)/RED, on pass runs `autobuild pre_build` → dispatches `release.yml` |
| Readiness verdict | `PyAutoHeart/heart/readiness.py` | The authoritative gate; **releases require GREEN**, which requires a fresh passing release-validation report whose `commit_shas` match current `main` |
| Live-release Slack | `release.yml` `announce_release` (`PYAUTO_RELEASE_WEBHOOK_URL`) | Success/failure announcement for live releases, including failure paging |

The nightly is therefore **composition, not new machinery**: schedule the
existing validate-then-release choreography, put an activity gate and a kill
switch in front of it, and make every terminal outcome loud.

## 2. Orchestration shape (decision)

**Decision: the nightly is a scheduled Brain-orchestrated driver — a cron
workflow in PyAutoBrain that sequences the existing conductors — and the cron
in Build's `release.yml` is removed.**

Two shapes were considered:

- **(A) Gate jobs inside `release.yml`'s scheduled path** — add
  `activity_gate` / `heart_gate` jobs that everything downstream `needs`.
  Rejected: Build is a pure executor by doctrine (it holds no readiness
  logic — that was deliberately removed in the Heart/Build split), and
  `release.yml` cannot run the validate choreography *of itself* (the
  rehearsal it must gate on is a dispatch of the same workflow). Any honest
  version of (A) still needs an external scheduler to have produced a fresh
  validation verdict — i.e. it needs (B) to exist anyway.
- **(B) A scheduled Brain release routine** — exactly the consumer the
  M1–M4 redesign was built for: *"dispatching it, polling it, and feeding its
  artifacts to `pyauto-heart validate --ingest` is the Brain Release Agent's
  job — Heart itself never dispatches a workflow"*
  (`workspace-validation.yml` header), and *"the orchestrator consults this
  verdict via `pyauto-heart readiness --json` and only dispatches Build's
  `release.yml` when it is green"* (`readiness.py`). **Chosen.**

Consequence for `release.yml`: the `schedule:` trigger and the
schedule-handling branch of `resolve_mode` are **deleted** in phase 2. This
closes a live hazard in the current tree: the moment `RELEASE_MODE` flips to
`live`, today's 2 AM cron performs a full live release gated on nothing but
the TestPyPI build — no activity gate, no Heart. Scheduling authority moves
wholly to the Brain driver; `release.yml` keeps only `workflow_dispatch`
(manual and driver-dispatched runs are then indistinguishable to Build,
which is the point — Build executes, it does not decide *when*).

The driver itself is **deterministic shell in CI** (`gh` + the existing
conductor scripts) — no LLM in the release gate. `validate.sh` was written as
"plan-emission for an agent's `gh`" because local bash could not call MCP; in
Actions, `gh` is right there, so the driver runs the emitted dispatch plans
directly. A thin `nightly.sh` under `agents/conductors/release/` sequences
Phases A→C and is invoked by the workflow — logic stays in the conductor
(testable locally), the workflow stays a scheduler.

## 3. The nightly sequence

Workflow: `PyAutoBrain/.github/workflows/nightly-release.yml`,
`schedule: 0 2 * * *` (every night — quiet nights exit at step 2 in seconds,
so weekend scheduling costs nothing and weekend merges release on time) +
`workflow_dispatch` for manual runs. Secrets: `PAT_PYAUTOLABS` (dispatch/poll
Build + Heart workflows, read commit history), `PYAUTO_RELEASE_WEBHOOK_URL`.

| Step | Action | On stop |
|------|--------|---------|
| 0 | **Kill switch** — repo var `NIGHTLY_RELEASES` ≠ `true` → exit | silent (pausing is a human act; the pause itself was the notification) |
| 1 | **Same-day guard** — a live release tag `YYYY.M.D.*` already exists today → exit | notify: `already released today, skipped` |
| 2 | **Activity gate** (§4) — no qualifying activity in the window → exit | notify: `no activity, skipped` |
| 3 | **Known-red check** (§5) — open release-blocking issue → stop | **page**: `stopped — release-blocked by <issue>` |
| 4 | **Validate** — run the Stages 0–3 choreography (`release validate` Phases A→C: preflight, rehearsal dispatch+poll, `mode=release` validation dispatch+poll, ingest) | **page** on any stage failure, naming the stage + run URL |
| 5 | **Gate** — `pyauto-heart readiness --json` over the in-run snapshot (§5): verdict must be **GREEN**. STALE/YELLOW/RED all stop — no `--force` on the nightly path, ever | **page**: `stopped — Heart <verdict>: <reasons>` |
| 6 | **Release** — dispatch `release.yml` (`rehearsal=false`, `minor_version=1`); poll to completion | `announce_release` already pages on live failure; the driver adds its own page if the dispatched run cannot be found/polled |
| 7 | **Report** — `released YYYY.M.D.1` with run URL; the morning digest picks it up | — |

Every terminal outcome except the kill switch emits exactly one Slack message
(§6). **Silence therefore always means the nightly itself broke** — which the
morning digest surfaces (it knows the schedule and can flag a missing nightly
outcome).

## 4. The activity gate

**Definition: qualifying activity = at least one commit on `main`, in any of
the 11 release-relevant repos, since the last nightly outcome (shipped or
skipped), that is not a pipeline self-commit.**

- **Repo set** (from `repos.yaml` roles; the set `release.yml` builds or
  regenerates): libraries `PyAutoNerves, PyAutoFit, PyAutoArray, PyAutoGalaxy,
  PyAutoLens`; workspaces `autofit_workspace, autogalaxy_workspace,
  autolens_workspace`; tutorials `HowToFit, HowToGalaxy, HowToLens`.
- **Signal**: commits to `main` (`GET /repos/{owner}/{repo}/commits?sha=main&since=<window>`).
  Merged PRs need no separate query — a merged PR *is* commits on `main`;
  direct pushes count too, which matches how this organism actually works.
- **Window**: since the previous nightly run's window-end timestamp, persisted
  by the driver as the PyAutoBrain repo Actions variable
  `NIGHTLY_LAST_WINDOW_END` (fallback: last 24 h). *(Phase-2 refinement: a
  repo variable, not the artifact/cache key phase 1 sketched — durable across
  runner evictions and one API call.)* The anchor advances **only** on
  shipped or empty-skip outcomes — a night stopped at a gate, or a dry-run
  night, leaves it, so unshipped activity is never silently swallowed from
  the next night's judgement.
- **Self-commit exclusion** — a release must never count as the next night's
  activity. Post-#118/#120 the pipeline no longer stamps versions into
  library repos, so self-commits are only: workspace notebook regeneration,
  Colab URL bumps, and the assistant API-baseline commit. All are authored by
  the pipeline identity and messaged `Release <version>: …`. Exclusion rule:
  **commit message matches `^Release [0-9]{4}\.` OR committer is the pipeline
  bot identity** (`GitHub Actions bot` / `richard@rghsoftware.co.uk` as
  configured in `release.yml`). Both conditions are pipeline-controlled, so
  drift is a phase-2 unit-testable contract, not a hope.
- Empty result across all 11 repos → skip, loudly.

## 5. Heart GREEN in CI (the honest part of the gate)

`readiness.compute` is a pure function of the Heart state snapshot; today that
snapshot lives on the dev box (`HEART_STATE_DIR`). The nightly runs in CI with
no dev box, so **what snapshot does step 5 evaluate?**

**Design: the driver assembles the snapshot in-run** — the same approach
`validate.sh` Stage 0 already takes, extended to the full release-gate
evidence set:

- **CI-refreshable evidence, refreshed in-run**: `ci_status` + `open_prs`
  (the cloud-safe checks `heart-health.yml` already runs), the Stage 2/3
  release-validation report + `verify_install` (produced by step 4 minutes
  earlier, `commit_shas`-matched by construction), version/library state as
  read from the GitHub API.
- **Dev-box-local checks** (`repo_state`, `worktree_drift`, `script_timing`,
  local `test_run` cache): these gate *the dev box's working tree*, not the
  published state of `main` that a release ships. For the nightly gate they
  are **out of scope by definition, not silently green**. This needs a small,
  explicit Heart change in phase 2: a release-gate evaluation profile
  (`pyauto-heart readiness --profile release-ci` or equivalent) that names
  which checks are required evidence and marks the dev-box-local set
  n-a-by-scope — mirroring how the cloud dashboard already renders
  "not observed here" rather than fake green. Unknowns among *required*
  evidence stay YELLOW and stop the run, exactly as today.
- **Known-red items**: an open release-blocking issue (the current live
  example: [PyAutoBuild#126](https://github.com/PyAutoLabs/PyAutoBuild/issues/126),
  the pipeline committing smoke-regenerated workspace datasets) must stop the
  run *before* any dispatch. Mechanism: a `release-blocker` label checked by
  the driver at step 3 across the release-relevant repos + PyAutoBuild/
  PyAutoHeart; #126 gets the label as part of phase 2. This is deliberately a
  label, not prose-parsing — a human marks an issue release-blocking with one
  click, and that click is the paging trigger for every scheduled night until
  it closes.

**Invariant preserved: STALE and YELLOW do not pass for releases.** The
freshness tier exists so evidence gaps say "re-run the check"; on the nightly
path the driver just *did* re-run everything refreshable, so a residual
non-GREEN verdict is a real reason to stop and page. There is no `--force`
input on the nightly workflow at all.

## 6. Notifications — skip must be loud

One channel (the existing `PYAUTO_RELEASE_WEBHOOK_URL` Slack webhook), one
message per nightly outcome, three severities:

| Outcome | Tone | Content |
|---------|------|---------|
| `released` | 📦 info | version, repos with activity (the gate's evidence), run URL — `announce_release` already covers the release itself; the driver's message adds the *why* (activity summary) |
| `skipped — no activity` / `already released today` | 💤 info | window checked, "quiet night" |
| `stopped` (blocked / stage failure / not GREEN / dispatch lost) | 🚨 **page** | which step, verdict + reasons or failing stage, run URL, "no release was made" |

The morning digest (PyAutoMind `morning_health`) adds the second layer: it
reads last night's outcome and **flags the absence of any outcome** — the
watchdog for "the nightly itself died", which no self-report can cover.

## 7. Kill switch and the human role

- **Kill switch**: PyAutoBrain repo var `NIGHTLY_RELEASES`. Only `true` arms
  the schedule; anything else exits at step 0. One-variable pause, no commit,
  independent of Build's `RELEASE_MODE` (which stays the rehearsal/live
  semantic for *dispatched* runs and is not consulted by the driver).
- **Human role after arming**: pause via the kill switch; respond to 🚨
  pages; review the morning digest. Merge/close of PRs and issues remain
  human acts everywhere — the grant covers precisely the scheduled
  release pipeline execution, nothing else.
- **Doctrine**: the dated `PyAutoBrain/AUTONOMY.md` edit (shipped with this
  note) scopes the standing grant: *scheduled-nightly path only,
  activity-gated + Heart-GREEN-gated + kill-switchable; manual and
  agent-initiated releases stay `human-required`; no autonomy level may
  acknowledge YELLOW on this path.*

## 8. Version scheme and `pre_build`

- Nightly versions are `YYYY.M.D.1` — already what `version_number` derives
  when no `minor_version` input arrives. The driver passes `minor_version=1`
  explicitly (the dispatch input is required) — the date scheme *derives* the
  human's former minor-version answer, which is the automation of
  `pre_build`'s version ask the endpoint requires. The interactive
  `pre_build` skill is untouched for manual releases.
- **Same-day cases**: step 1's guard means the nightly never double-releases
  a date. A manual same-day release before 2 AM UTC causes the nightly to
  skip (`already released today`); a manual same-day release *after* a
  nightly must pick `minor_version ≥ 2` (unchanged from today — twine
  loudly rejects duplicates, and `pre_build`'s human ask is where that choice
  already lives). Re-run attempts of a failed nightly get the existing
  `.run_attempt` suffix behaviour.

## 9. Rehearsal / live composition and the arming checklist

- The nightly's step 4 **is** a TestPyPI rehearsal (Stage 2) — the dry-run is
  built into every night's path, not a separate mode. Before arming, the
  whole driver can run with the step-6 dispatch replaced by a log line
  (workflow input `dry_run=true`, default `true` until arming) — the
  TestPyPI-only "nightly rehearsal era" the prompt asks for.
- `RELEASE_MODE` is not consulted by the driver; after phase 2 removes the
  cron from `release.yml` it governs nothing (schedule-only semantics) and
  can be retired in a cleanup — noted, not part of this design's scope.

**Arming checklist (human, in order):**
1. The next manual live release succeeds end-to-end (the decided
   precondition).
2. PyAutoBuild#126 fixed + closed (or explicitly de-labelled) — while open
   and labelled `release-blocker` it stops every nightly at step 3.
3. Phase-2 implementation merged; a `dry_run=true` nightly observed
   end-to-end GREEN on a real activity night.
4. Set `NIGHTLY_RELEASES=true` and flip `dry_run` default to `false`.

## 10. Phase 2 implementation sketch

Mechanical once this note is approved; own prompt/issue, not started before.

- **PyAutoBrain** — `agents/conductors/release/nightly.sh` (steps 0–7,
  sequencing `validate.sh` Phases A→C and the `gh` dispatch plans;
  kill-switch/activity/label/notify logic unit-testable);
  `.github/workflows/nightly-release.yml` (cron + dispatch, secrets, calls
  `nightly.sh`); `bin/pyauto-brain release nightly` passthrough for local
  runs.
- **PyAutoBuild** — `release.yml`: delete the `schedule:` trigger + the
  schedule branch of `resolve_mode`; no other behaviour change.
- **PyAutoHeart** — the release-gate evaluation profile (§5): named required
  evidence set, dev-box-local checks n/a-by-scope, CI-assemblable snapshot.
- **Process** — `release-blocker` label created + applied to #126; morning
  digest taught to expect a nightly outcome (missing-outcome flag).

## 11. Open questions for the reviewer

1. **2 AM UTC nightly vs weekdays-only** — §3 proposes every night (quiet
   nights are free). Keep the weekday-only habit instead?
2. **Activity-gate window anchor** — persisted last-run timestamp (proposed)
   vs a plain fixed 24 h lookback. The former never drops a merge into a gap;
   the latter is simpler and self-healing. Either is fine; the note commits
   to the former.
3. **Known-red mechanism** — the `release-blocker` label (proposed) is a
   human-curated signal. Comfortable that "known red" = "someone labelled
   it", or should the driver also hard-stop on any open issue in PyAutoBuild
   referencing the previous release version?
