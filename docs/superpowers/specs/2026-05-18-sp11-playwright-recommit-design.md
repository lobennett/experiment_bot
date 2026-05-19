# SP11 — Playwright re-commit: input-layer-honest adversary

**Date:** 2026-05-18
**Parent tag:** `sp9c-investigation-complete` (commit `9886362`)
**Worktree:** `.worktrees/sp11` off the parent tag
**Branch:** `sp11/playwright-recommit`
**Target tag:** `sp11-complete`

> This spec doc is the **pre-registration** for SP11. The success-criterion
> thresholds in §6 are committed BEFORE any validation data exists. The
> Phase 7 writeup reports against these thresholds — no post-hoc retargeting.

## 1. Origin and motivation

The project's abstract (`Task Turing Bot Abstract.md`) claims a *general-
purpose agentic AI bot* that completes online cognitive tasks with humanlike
behavior given only a URL. The strongest defensible version of that claim
is: a browser-only adversary using Playwright + Claude can produce humanlike
data across multiple platforms with no platform-specific code.

SP10 went the opposite direction. It built `JsPsychDriver` (jsPsych 7.3.1 +
6.0.5 version-tolerant), `vendor/jspsych/7.3.1/` anchor files, an
`_INSTALL_HOOK_JS` monkey-patch of `pluginAPI.getKeyboardResponse`, and
ultimately achieved 100% per-trial fidelity by *synthesizing a `(key, rt)`
tuple directly into the platform's data export* via the captured callback.
A reviewer will correctly say: once you have platform-internal access, of
course the data export matches. That is **not** the claim the paper makes.

A concrete signal in `docs/sp10-results.md` that the input-layer path is
fixable: SP10 succeeded on the two jsPsych 7.3.1 paradigms but had to fall
back to `DiagnosticDriver` on `stopit_stop_signal` (jsPsych 6.0.5, separate
driver required) and declared `cognitionrun_stroop` out of scope (closed
source — no driver writable). One driver per platform per version is not
the architecture an "agentic AI generalizes" paper should defend.

SP11 returns to the Playwright (input-layer) path that SP6–SP8 was on,
fixes the two failure modes SP7 named, ports the genuinely paradigm-
agnostic improvements from SP10, and validates on the original four
paradigms — including the two SP10 punted on.

## 2. Hypothesis

A browser-only adversary that

- presses keys through Chromium's real input pipeline (CDP-level
  `Input.dispatchKeyEvent` with proper `key`/`code`/`keyCode`),
- calibrates its sampled-RT-to-recorded-RT offset per session per platform,
- reads correct-response state from a multi-source fallback chain
  (page runtime variables first, DOM-derived second, static keymap last),
- and applies literature-grounded temporal effects on top of an ex-Gaussian
  sampler,

can produce data on each of the four original paradigms that lands within
human reference distributions on the metrics enumerated in §6, with NO
platform-specific driver code in the bot library or Reasoner.

Per-trial fidelity will be LOWER than SP10's 100% (target ≥ 85% on
`pressed == platform_recorded`). That is the price of platform-agnosticism,
and we name it explicitly in `docs/scope-of-validity.md` before validation.

## 3. Branch base + sp10 cherry-pick policy

**Base:** `sp9c-investigation-complete` (commit `9886362`). This is the
last point on the development trunk with the SP2–SP9 framework intact
(effects registry, validation oracle, platform_adapters dispatch,
SP8's multi-source response_key_js prompt, SP6 trial-end fallback,
SP7's keypress audit + diagnostic) and BEFORE SP10's driver pivot.

The user's directive "off main (not off sp10)" is interpreted as
"don't carry SP10's drivers/ and vendor/". Forking literally from
`main` (`4293a6f`, essentially pre-SP2-implementation) would require
re-doing two months of completed framework work. The intent of the
directive is preserved by basing on `sp9c-investigation-complete`,
which excludes all sp10 commits.

**Cherry-picks from sp10** (paradigm-agnostic only — drivers/ + vendor/
must NOT appear on sp11):

| sp10 commit | What it adds | sp11 disposition |
|---|---|---|
| `170b4ba` | `scripts/audit_alignment.py` initial | port, generalize per Phase 6 |
| `15ca378` | RT-matching pairing logic | port |
| `f9d5252` | CSE label loader fix in `validation/cli.py` | port + verify against existing SP8 TaskCards |
| `3ce27c9` | Writer microsecond-precision run dirs | port |

Everything else SP10 introduced (`drivers/`, `vendor/`, slimmed Stage 1 /
Stage 6 / pipeline / validate, `recommended_driver` TaskCard field, the
stop-trial withhold + per-trial wait_for_trial_end driver fixes, the
correct_response fallback chain in `_GET_CONTEXT_JS`) stays on the
sp10 branch.

**SP9a SessionAgent disposition** (per user Q2):
delete `src/experiment_bot/agent/` from sp11's Phase 1 starting state.
SP9a's empirical result was negative; the `LLM.complete(images=...)`
multimodal protocol change is preserved on the `sp9a/session-agent`
branch and recoverable. If Phase 3 (calibration) or Phase 5 (pilot-time
alignment check) wants `agent/page_probe.py`, cherry-pick it then —
don't carry speculatively.

## 4. Approach — 8 phases, gate at each transition

Each phase ends with a deliverable + user-approval checkpoint. No phase
starts before the previous phase has user sign-off.

### Phase 1 — Branch creation + sp10 cherry-pick

- Push 4 missing local sp* branches to origin (`sp1`, `sp9a`, `sp9b`,
  `sp9c`) so the development history is durable. **Do this before
  anything else.** No branches or tags get deleted.
- Worktree: `.worktrees/sp11` off `sp9c-investigation-complete`.
- Branch: `sp11/playwright-recommit`.
- Cherry-pick the 4 sp10 commits listed in §3. The CSE-label-loader port
  must be verified against the existing SP8-regenerated stroop TaskCard
  (`taskcards/expfactory_stroop/f099a88b.json`) — pre-existing parse
  bug. Add unit test.
- Delete `src/experiment_bot/agent/`. Update `cli.py` to drop SessionAgent
  injection if present on sp9c base.
- `pytest` must pass after every cherry-pick. **Test count is pinned
  empirically, not predictively**: after Phase 1's cherry-picks land,
  run `pytest --collect-only -q | tail -1` and record the exact count
  in the Phase 1 deliverable doc. Subsequent phases must not break
  that pinned count without explanation. If a Phase-1 cherry-pick
  fails to bring expected tests over (the audit-script tests, the
  CSE-loader test), investigate before declaring Phase 1 done.
- **Platform-adapter inventory** (pre-checks Phase 6's dispatch
  refactor). Verify `experiment_bot.validation.platform_adapters`
  has entries for the 4 dev paradigms:
  `expfactory_stroop`, `expfactory_stop_signal`, `stopit_stop_signal`,
  `cognitionrun_stroop`. If any is missing (likely `cognitionrun_stroop`
  given sp9c's jsPsych focus), name it as a Phase 6 sub-task: write
  the adapter at that point rather than discovering it during Phase 7
  validation.
- **Populate Appendix C** (sp9c baseline metrics for non-degradation
  tracking). Read through `docs/sp5-heldout-measurement-results.md`,
  `docs/sp6-results.md`, `docs/sp7-results.md`, `docs/sp8-results.md`,
  `docs/sp9a-results.md` (and `sp9c-investigation.md` for the layer-d
  findings). Extract every reported metric with a z-score or
  literature-range pass/fail, by paradigm. Tabulate as Appendix C
  rows: metric name, paradigm, sp9c value, in-band/out-of-band status,
  source doc reference. This is the enumerated baseline that §6.3's
  global non-degradation clause checks against. Without enumeration,
  §6.3 is aspirational; with enumeration, it's a checklist. Estimated
  ~30 min of reading + tabulation.
- **Deliverable:** sp11 branch created; cherry-picks landed; empirical
  test count recorded; adapter inventory documented; Appendix C
  populated; sp10 history untouched.
- **Stop, ask for approval before Phase 2.**

### Phase 2 — Effects-library audit + gap-fill

sp9c already has `EFFECT_REGISTRY` and the open-registry pattern, so this
is mostly verification + targeted additions, not rewriting.

- Audit existing handlers in `src/experiment_bot/effects/handlers.py`:
  `autocorrelation`, `fatigue_drift`, `condition_repetition` (single-
  parameter — replace with `lag1_pair_modulation`), `pink_noise`,
  `lag1_pair_modulation`, `post_event_slowing`. Verify each matches
  literature parameterization.
- Add three missing mechanisms:
  - **`practice_effect`** — block-wise RT reduction with asymptote
    block. Literature target: ~50ms total reduction across first ~30
    trials. Parameters from literature (RDoC task papers + general
    speeded-task learning curves).
  - **`vigilance_decrement`** (kept SEPARATE from `fatigue_drift`,
    per spec decision below) — per-trial *RT variance and omission
    rate* increase over session length, modeling attentional lapses.
    Literature: increase in omission rate by ~1-2% per 100 trials in
    sustained-attention paradigms; RT variance inflation accompanies
    omissions. **Decision (committed in this spec, not deferred):**
    vigilance_decrement and fatigue_drift remain SEPARATE mechanisms
    because they model conceptually distinct phenomena —
    vigilance_decrement is attentional (lapses → omissions →
    variance↑), fatigue_drift is effort/motor (mean RT slowly rising
    without omission rate change). The literature parameterizes them
    differently. The sp11 effects library is therefore SEVEN
    mechanisms, not six.
  - **`conflict_adaptation` (proper Gratton 2×2)** — covered by
    `lag1_pair_modulation` with the `modulation_table` parameter
    structure already in the TaskCard schema. Verify the
    `cI > iI, cC ≈ iC` cell pattern lands correctly. The CSE-label
    loader fix (cherry-picked in Phase 1) enables this metric to
    parse the table.
- Fix `_generate_pink_noise` convention: rename `hurst` → `alpha`,
  document `alpha = 2*hurst - 1` is the fBm convention. Add a unit
  test that the synthesized spectrum's log-log slope is `-alpha` ±
  tolerance.
- Tests: per-mechanism invariant tests (mock sampler, verify magnitude
  lands in literature range under the configured parameters).
- **Deliverable:** sp11 effects library covers all six published
  mechanisms (autocorrelation, fatigue_drift, lag1_pair_modulation,
  pink_noise, practice_effect, post_event_slowing) plus
  vigilance_decrement (or merged into fatigue_drift, decision logged).
  Pink-noise convention fixed and tested.
- **Stop, ask for approval before Phase 3.**

### Phase 3 — Calibration pass

- **Design.** At session start, before the experiment's real timeline
  begins, the bot enters a calibration phase: it fires a known sequence
  of key presses at known intervals via the chosen delivery channel
  (Phase 4), then reads back `experiment_data.{csv,json}` for the
  calibration entries. Compute `(mean, sd)` of
  `platform_recorded_rt − bot_intended_rt` per session per platform.
  Store in `run_metadata.json` and use to adjust sampled RTs at trial
  time so that `recorded_rt ≈ sampler_target_rt`.
- **Calibration is computed ONLY on correctly-recorded events.** SP7
  found that `page_received == platform_recorded` is 44% on Flanker
  — the platform sometimes records a *different* key entirely or
  null. RTs on those mis-recorded trials are not on the same scale
  as correctly-recorded trials. A naive across-all-calibration-trials
  offset will be polluted by mis-recording cases and the resulting
  fixed offset won't help. The calibration filter is:
  1. `platform_recorded_response != null` (platform recorded
     something), AND
  2. `platform_recorded_response == bot_pressed_key` (the recorded
     key matches what the bot intended)
- **Bimodality sanity check.** Before fitting `(mean, sd)`, test the
  filtered offset distribution for unimodality. **Hartigan's dip
  test at the n=30 sample size has weak power** — it will see
  spurious bimodality from sampling variance and miss real bimodality
  except in egregious cases. We use a simpler explicit criterion
  tuned for catching the failure mode we care about:
  > Compute the gap-statistic clustering of the offsets into k=2
  > clusters. Declare bimodal iff (a) the two cluster means are
  > separated by > 50 ms, AND (b) the smaller cluster contains
  > ≥ 20% of the points. Both conditions must hold.
  The 50-ms separation threshold corresponds to "two distinct
  recording paths" (one jsPsych listener vs. one fallback timing
  off by half a typical RT). The 20% mass threshold prevents a
  single outlier from triggering the alarm.
  If bimodal by this criterion → **escalate to project owner**
  before proceeding — do not silently fit a mean to two distinct
  paths.
- **Sample size.** Minimum 30 calibration keypresses; 50 if the
  initial probe of a paradigm shows offset SD > 20ms (more samples
  needed to discriminate bimodality from variance). 5 keys (as
  originally proposed) gives sample SD with ~2 degrees of freedom —
  useless. Session-start cost at 30 keys × ~400ms = ~12 seconds;
  acceptable. Layout: 6 keys per second-of-elapsed-time group, 5
  groups at 200/400/600/800/1000ms target intervals.
- **Variance check.** Report calibration offset SD per platform in
  scope-of-validity. **If offset SD > 30 ms in absolute units**
  (not relative to anything; the threshold corresponds to roughly
  half of typical within-condition RT SD across the dev paradigms,
  past which the post-calibration recorded distribution's sigma
  re-inflates noticeably), switch to per-trial dynamic correction:
  regress `recorded_rt` onto `bot_intended_rt` over the calibration
  trials, store regression coefficients in `run_metadata`, apply
  the regression-based adjustment at trial time. This is documented
  in scope-of-validity as the platform's "calibration variance
  ceiling."
- **Platform RT-resolution disclosure.** Document each platform's
  underlying RT timer resolution (jsPsych uses `performance.now()`,
  sub-ms; cognition.run TBD by probe). The calibration cannot
  eliminate offset variance below this resolution; the limit is
  noted in scope-of-validity.
- **Pre-trial gate.** Some paradigms (cognition.run?) gate keyboard
  input until a "click to start" button is dismissed. Calibration
  needs a UI-interaction step before key presses are accepted.
  Design: bot tries keyboard.press immediately; if first 3 presses
  don't register on the platform (no row appears in the data export),
  attempt to dismiss any visible button via DOM probe + click, then
  retry. Document this as `pre_calibration_click_gate` behavior.
- Tests: unit test the offset estimator against synthetic data
  (including bimodal cases — verify the dip test fires); an
  integration test against a mock page that records keydown events
  with known platform offsets and verifies the calibration converges.
- **Deliverable:** calibration pass runs before each session; offset
  + SD reported in run_metadata; bimodality sanity check fires;
  per-trial dynamic correction fires when SD > 30ms; scope-of-validity
  entries written for offset variance + platform RT resolution.
- **Stop, ask for approval before Phase 4.**

### Phase 4 — Keypress delivery: CDP-level dispatch + focus

Phase 4 has a **gating spike (4a)** before the full build-out
(4b). The spike answers the load-bearing question: does CDP-level
delivery actually reach the listeners that `page.keyboard.press`
misses? If not, the entire input-layer path is in trouble and SP11
should know on day three, not after Phase 7's 120-session validation.

#### Phase 4a — Feasibility spike (kill-switch gate)

- **Scope:** ~50 keypresses fired via `Input.dispatchKeyEvent` (with
  proper `key`/`code`/`keyCode`/`windowsVirtualKeyCode`/`text`)
  into expfactory Stroop's first real trial-accepting state. No
  trial logic; just key fire + read back what the platform recorded.
- **Implementation:** ad-hoc script under `scripts/probe_cdp_delivery.py`.
  Delete after the gate (probe scripts don't live in the committed tree).
- **Metric:** `bot_pressed == platform_recorded` over the 50 keypresses.
- **Graduated kill-switch thresholds.** The relevant comparison is
  SP7's 44% baseline via `page.keyboard.press`, not SP10's 100% via
  callback hook. CDP, focus management, and listener-target detection
  are three additive mechanisms; the spike only isolates the first.
  Single-mechanism CDP is unlikely to hit 100%, and a high bar would
  cause premature kill on otherwise-reasonable improvements.
  - **≥ 85%**: CDP alone is materially closing the gap → proceed to
    Phase 4b as planned.
  - **60–85%**: CDP helps but isn't sufficient on its own → proceed
    to Phase 4b, but acknowledge in the spike report that focus
    management + listener-target detection (the "+ focus" parts of
    Phase 4b) are now doing more lifting than CDP alone. Phase 7
    expectations for §6 fidelity gates may need re-examination after
    Phase 4b lands.
  - **< 60%**: CDP gives no meaningful improvement over
    `page.keyboard.press` → **escalate to project owner**. Options:
    (i) try alternative CDP key fields (`Input.insertText`, modifier
    variations), (ii) hybrid CDP + targeted JS dispatch for the cases
    CDP misses, (iii) reconsider whether the input-layer claim is
    achievable on platforms where the recording mechanism is
    fundamentally divorced from keydown.
- **Deliverable:** spike report in `docs/sp11-phase4a-spike.md` —
  raw numbers, which threshold band the result fell into, kill-switch
  decision, sample of mismatch rows if any.
- **Stop, ask for approval before Phase 4b regardless of which band.**

#### Phase 4b — Full delivery channel build-out

Conditional on Phase 4a passing the kill-switch. Two delivery channels:

- **Primary:** Chrome DevTools Protocol `Input.dispatchKeyEvent` with
  proper `key`/`code`/`keyCode`/`windowsVirtualKeyCode`/`text`. This
  is lower-level than `page.keyboard.press` and bypasses certain
  Playwright synthesis behaviors that some jsPsych listeners ignore.
  Implemented via `page.context().new_cdp_session(page)` and
  `cdp_session.send("Input.dispatchKeyEvent", {...})`.
- **Fallback:** existing `page.keyboard.press`. Use when CDP path
  fails (non-Chromium browsers — Firefox, WebKit). Per
  scope-of-validity, sp11's validation targets Chromium; other
  engines accept the fallback's lower fidelity.

**Listener-target focus.** Pre-press, locate the listener target:
inspect `document.activeElement`, check for `jspsych-display-element`
or other known focus-claiming patterns. Call `await target.focus()`
if found. This is paradigm-agnostic — generic DOM probing.

**Delivery-channel logging** (user-requested refinement): every
`bot_log.json` trial entry records `delivery.channel` —
either `cdp_dispatchKeyEvent` or `keyboard_press_fallback`. Audit
script (Phase 6) surfaces channel distribution; Phase 8 writeup
breaks down per-trial fidelity by channel.

Tests: integration tests against an in-browser fixture that records
`keydown` events at various target elements. Verify CDP delivery
reaches jsPsych's listener anchor.

- **Deliverable:** CDP delivery channel works on Chromium; fallback
  exists for other engines; per-trial channel logged.
- **Stop, ask for approval before Phase 5.**

### Phase 5 — Multi-source response_key_js + pilot-time alignment check + TaskCard regen

- Verify sp9c's `src/experiment_bot/prompts/system.md` contains the
  `## Multi-source response_key_js extraction` section landed in SP8.
  The three pattern examples (runtime-variable, dom-plus-state,
  static-keymap) and the anti-example should be intact.
- **Pilot-time alignment check** (new in SP11). During Stage 6 pilot,
  the bot runs ~20 trials, evaluates its own `response_key_js`,
  reads `correct_response` from the platform's recorded data on the
  next trial, and computes `bot_intended == platform_expected`
  alignment over the 20 trials. If alignment < 90%, the pilot fails
  loudly with a structured diagnostic including bot's resolved key,
  platform's expected key, and the stim_id for each mismatch. The
  diagnostic feeds a Claude refinement pass (Stage 1 retry with the
  discrepancy in context). Cap retries at 2; failing past retries
  marks the paradigm as unsupported on sp11 (vs the SP10 pattern of
  silently degrading).
- **TaskCard regeneration** (per user Q3): regenerate all four dev
  paradigm TaskCards
  (`expfactory_stroop`, `expfactory_stop_signal`,
  `stopit_stop_signal`, `cognitionrun_stroop`) after the pilot-time
  alignment check lands. Mixing TaskCards generated under different
  prompt regimes is a confound for Phase 7 results. Regenerate
  clean.
- **TaskCard quality filter — methodological framing.** TaskCard
  generation includes a pilot-time alignment quality filter with up
  to 2 refinement retries per paradigm, modeling a realistic
  adversary workflow where a researcher would not deploy a non-
  functional TaskCard onto a paid platform. A real adversary
  iterates on a misbehaving configuration before running a full
  session; SP11's pipeline reproduces that iteration explicitly,
  with a bounded retry budget. Phase 7 results therefore reflect
  this filtered generation process, which is the operationally
  relevant performance for the threat model. This is documented in
  scope-of-validity as part of the method, not as a caveat.
  - Future work could separately quantify *unfiltered* TaskCard
    performance (N generations per paradigm with no retry, report
    the distribution) — that would answer a different question
    ("how often does Claude get a fresh URL right on the first
    pass") which complements the threat-model question but is not
    SP11's claim.
- Tests: mock the pilot loop; verify the alignment threshold + retry
  trigger; verify the diagnostic format.
- **Deliverable:** 4 regenerated TaskCards passing the pilot-time
  alignment check at ≥ 90%; refinement loop exercised on at least
  one paradigm (stop_signal expected to need it per SP7 finding).
- **Stop, ask for approval before Phase 6.**

### Phase 6 — Audit-script generalization

- `scripts/audit_alignment.py` (cherry-picked in Phase 1) currently
  has jsPsych-shaped `is_real_test_trial` logic. Refactor: take
  `--label` argument, use
  `experiment_bot.validation.platform_adapters.adapter_for_label(label)`
  to load the per-paradigm test-row filter. The adapter dispatch
  already exists in sp9c's validation oracle; the audit script just
  defers to it.
- Audit reports break out `pressed == platform_recorded` separately
  for the two delivery channels (CDP vs keyboard_press_fallback)
  per Phase 4.
- Tests: parametrized over all 4 dev paradigms; mock the trial dicts.
- **Deliverable:** audit script works on all 4 paradigms via
  adapter dispatch; CDP vs fallback channel breakdown in audit output.
- **Stop, ask for approval before Phase 7.**

### Phase 7 — Validation: N=30 per paradigm, calibrated comparison

- **N=30 per paradigm** (per user revision; the abstract's N=27–29
  plus margin). 4 paradigms × N=30 = 120 total sessions.
- **Run sequentially. No parallelization.** The earlier draft proposed
  parallel main validation + sequential calibration arms with a
  regression-based confound check. After deliberation: the extra
  wall-time of full-sequential is ~18 additional hours; the
  alternative is committing to a Phase 8 analysis sub-task that
  detects-and-corrects for parallelization confounds, which adds
  complexity to the writeup and creates a discretion seam ("we
  declared the parallel_count coefficient non-systematic") that
  pre-registration should avoid. Cleanest discipline: just go
  sequential, eliminate the confound by construction. The wall-time
  cost is real but bounded.
- Per-session CPU load is still logged in `run_metadata.json` per
  session for descriptive reporting (verify `psutil.cpu_percent`
  available in sp9c's run_metadata), but is not gated on.
- **Wall-time estimate (revised, sequential).**
  - Stroop sequential ~5 min × 30 = 2.5 hr per arm; both arms (pre +
    post calibration) = 5 hr.
  - Stop_signal sequential ~10–12 min × 30 = 5–6 hr per arm; both
    arms = ~12 hr.
  - Stopit and cognitionrun_stroop, ~5 min × 30 = 2.5 hr each.
  - Total: **~22–24 hr of sequential validation**, spanning 2–3
    calendar days (overnight runs work for the long arms; shorter
    paradigms can fit in a workday). Plan for 3 days from
    Phase 7 start to "all 180 sessions complete," not overnight.
- Each session writes its `bot_log.json` + `experiment_data.*` to a
  microsecond-stamped run dir; audit script (Phase 6) tabulates.
- Per-paradigm report (against §6 pre-registered criteria):
  - Per-condition mean RT, with z-score against human reference
    (`data/human/archive_rdoc` for stroop and stop_signal; flag
    cognition.run if no reference exists — drop z-score, report
    descriptive only)
  - Effect sizes: Stroop interference (incongruent − congruent),
    SSRT (integration method), with z-scores
  - Sequential effects: post-error slowing magnitude, CSE 2×2 cell
    table, lag-1 autocorrelation (sp10's `validation_metrics`
    functions, already in `effects/validation_metrics.py` on sp9c
    base)
  - Per-trial fidelity from generalized audit script — break down
    by delivery channel (CDP vs keyboard_press_fallback)
- **Pre/post-calibration comparison**, symmetric arms:
  - **Stroop:** N=30 without Phase 3 calibration + N=30 with
    calibration. Compare z-score delta on absolute congruent /
    incongruent RT. (Asymmetric N=10 vs N=30 — as in the previous
    spec version — has wider CIs on the smaller arm, polluting the
    delta inference; symmetric N=30 cleans it up.)
  - **Stop-signal:** N=30 without + N=30 with. The abstract reports
    go-RT z=−0.27 (below human mean, opposite direction from Stroop
    which is +1.95). If calibration improves Stroop by removing
    positive offset but worsens stop_signal by removing a negative
    offset that was masking something else, that's a real finding.
- Pre-calibration N=30 arms reuse the post-calibration paradigm
  TaskCards (no TaskCard regen confound between arms — the only
  changing variable is calibration on/off).
- Total session count: 120 (post-cal × 4) + 30 (Stroop pre-cal) +
  30 (stop_signal pre-cal) = **180 sessions**.
- **Per-session crash handling.** With 180 sequential sessions, the
  probability of at least one Playwright / browser / network /
  platform-side failure is non-trivial. **If a session fails
  (Playwright timeout, browser crash, network error, platform error
  page, etc.), re-run that session only — do NOT re-run the full
  arm.** The seed for the re-run uses a deterministic policy:
  `original_seed + 10_000` for the first retry, `+20_000` for the
  second; cap at 2 retries per session. Document the retry count in
  the run_metadata and surface it in Phase 8 ("N=30 with K
  session-level retries"). This is operational discretion that
  belongs in pre-registration, not Phase 8 narrative.
- **Deliverable:** validation data for the 180 sessions, all run
  sequentially. All raw `bot_log.json` + `experiment_data` exports
  retained per the existing gitignore-but-archived pattern.
  `cpu_percent` logged per session for descriptive reporting only.
  Per-session retry counts logged.
- **Stop, ask for approval before Phase 8.**

### Phase 8 — Writeup `docs/sp11-results.md` + abstract reconciliation

- Honest writeup. Pass/fail per §6 criterion stated explicitly.
- If post-calibration RT z-score stays elevated, say so; offer
  candidate causes (calibration variance ceiling, sampler tau
  inflation, etc.) as the next-SP backlog.
- Frame sp10 as the secondary "worst-case adversary" tier — the
  hook-based approach achieves 100% fidelity but represents the
  upper bound, not the headline claim.
- Update `Task Turing Bot Abstract.md` only AFTER sp11 results are
  in. Calibrate claims to data; if N=30 results justify the
  abstract's existing numbers, leave them; if not, revise to what
  sp11 actually achieved. NO abstract edits before Phase 8 writeup.
- Tag `sp11-complete` at the writeup-landing commit. Push branch +
  tag to origin.

## 5. What changes vs sp9c-investigation-complete baseline (excluding sp10 cherry-picks)

| Area | sp9c baseline | sp11 after Phase 2-5 |
|---|---|---|
| Effects library | autocorrelation, fatigue_drift, condition_repetition (single-param), pink_noise (hurst convention with α=2H−1), lag1_pair_modulation, post_event_slowing | + practice_effect, + vigilance_decrement (kept separate from fatigue_drift — see Phase 2), condition_repetition deprecated in favor of lag1_pair_modulation, pink_noise param renamed to `alpha` |
| Keypress delivery | `page.keyboard.press` only | CDP `Input.dispatchKeyEvent` primary + page.keyboard.press fallback + listener-target focus |
| Session lifecycle | navigate → trial loop → completion | + calibration pass before trial loop |
| Stage 6 pilot | runs ~20 trials, no alignment check | + pilot-time `response_key_js` alignment check + ≤2 refinement retries |
| Audit script | not present (sp10 introduction) | present, generalized via `platform_adapters.adapter_for_label` |
| SP9a SessionAgent | present (deprecated) | deleted (cherry-pick `page_probe.py` if Phase 3/5 needs it) |
| TaskCards (4 dev paradigms) | SP8 prompt regime | regenerated post-Phase-5 with pilot alignment check |

## 6. Pre-registered success criteria (committed BEFORE Phase 7)

These are the thresholds Phase 8 writes against. They are committed to
this spec doc dated 2026-05-18, BEFORE any validation data exists.
Phase 7 results are reported pass/fail against these explicit targets.
Any post-hoc relaxation is flagged in the writeup as a deviation.

**Design principle.** Pre-registration must commit to what would make
SP11 *better* than SP9c, not status-quo certification. Three classes
of criterion:

- **(A) Improvement gates** for metrics where sp9c-baseline already
  fails the human-range bar — sp11 must close the gap by an explicit
  delta from baseline.
- **(B) Non-degradation gates** for metrics where sp9c-baseline
  already passes — sp11 must not lose ground.
- **(C) New-mechanism gates** for behaviors sp9c doesn't model at
  all (e.g., calibration variance ceiling, per-paradigm fidelity).

### 6.1 Hard gates (must pass for SP11 to be considered successful)

| # | Metric | Scope | Target | Class |
|---|---|---|---|---|
| H1 | Per-trial fidelity (`pressed == platform_recorded`) — mean | all 4 paradigms over N=30 | **≥ 85%** | C |
| H2 | Per-trial fidelity — per-paradigm floor | each paradigm individually | **≥ 75%** | C |
| H3 | Pilot-time alignment (Phase 5) | each paradigm | ≥ 90% over 20 pilot trials, ≤ 2 retries | C |
| H4 | Sequential effects exist with correct sign | all 4 | PES > 0; lag-1 autocorr > 0 | B (sign-check) |

H1 + H2 together prevent the "95/95/95/55 mean = 85" failure mode the
user flagged: an 85% mean across paradigms could hide one broken
paradigm. The per-paradigm floor catches this.

### 6.2 Soft gates with delta + non-degradation requirements (z-score targets)

The sp9c baseline column is from the project abstract's reported
numbers (which are sp9c-era data) plus the SP5 results for absolute
Stroop RT. Targets are the **stricter** of the |z| < 1 absolute
target and the delta-improvement requirement.

| # | Metric | Paradigm | sp9c baseline z | Target | Class |
|---|---|---|---|---|---|
| S1 | Stroop congruent absolute RT z-score (post-cal) | stroop | +1.95 | **z ≤ +0.95** (improve by ≥ 1.0) | A |
| S2 | Stroop incongruent absolute RT z-score (post-cal) | stroop | +1.93 | **z ≤ +0.93** (improve by ≥ 1.0) | A |
| S3 | Stroop interference effect z-score | stroop (both impls) | +0.61 | **\|z\| < 1** (non-degradation) | B |
| S4 | Mean go-trial RT z-score | stop_signal (both impls) | −0.27 | **\|z\| < 1** (non-degradation) | B |
| S5 | SSRT z-score (integration method) | stop_signal (both impls) | −0.46 | **\|z\| < 1** (non-degradation) | B |
| S6 | Stop accuracy z-score | stop_signal (both impls) | +0.45 | **\|z\| < 1** (non-degradation) | B |
| S7 | PES magnitude | all 4 | (varies, mostly in range) | 10–50 ms (literature range) | B |

S3–S6 are non-degradation: sp9c is already in the |z| < 1 band on
those four. The pre-registration commits to NOT losing that ground.
Without S3–S6, the calibration pass could plausibly fix Stroop
absolute RT (S1/S2) while introducing variance elsewhere — and the
spec as previously written would have called that a pass.

S1/S2 are the improvement gates the calibration pass exists to
achieve. If post-cal Stroop RT z ≥ +0.95, calibration didn't move
the needle enough and SP11's headline claim weakens.

### 6.3 Global non-degradation clause

For ANY metric enumerated in **Appendix C** (the sp9c-baseline
metrics table, populated in Phase 1 by reading
`docs/sp5-heldout-measurement-results.md` through
`docs/sp9a-results.md`) that currently lands in the |z| < 1 band
or in its literature range, **sp11 results must not drift outside
that band/range** on the same paradigm.

If a metric in Appendix C drifts out, that's a regression and counts
as a soft-gate failure regardless of whether the metric is named
in §6.1 or §6.2.

**This clause is operational only because Appendix C enumerates the
metrics explicitly.** Without the enumeration, the clause is
aspirational. Phase 1's Appendix C sub-task is the converter from
hope to check.

### 6.4 Descriptive-only metrics (reported, not gated)

- CSE 2×2 cell table values (already a literature-range gate on the
  derived `cse_magnitude` metric, but the cell-level pattern is
  descriptive)
- Practice-effect block-1 vs block-asymptote RT delta
- Per-paradigm CDP vs `keyboard.press` channel distribution
- Calibration offset (mean, SD, unimodality test result) per platform
- Platform RT timer resolution
- `cpu_percent` per session — descriptive only, since Phase 7 runs
  sequentially and parallelization is not in play

## 7. Out of scope

- jsPsych v6 platforms beyond stopit_stop_signal (sp10 supported by
  driver; sp11 supports by Playwright path, but other v6 paradigms
  may have idiosyncratic listener targets — defer until they appear).
- PsychoJS / PsychoPy / lab.js. Different platforms entirely.
- Custom recruitment-platform variants (Prolific-only, mTurk-only
  layouts) — sp11 targets the experiment URL directly.
- Stop-signal stop-trial withhold semantics — sp9c-baseline behavior
  is bot fires on every trial; SSRT is computed from the resulting
  failed-inhibition RT distribution. If the SSRT z-score fails §6
  target, withhold semantics become an SP12 backlog item.
- Re-validation of cognition.run beyond Stroop. The platform only
  hosts one of our 4 paradigms.
- Abstract revision before Phase 8.

## 8. Open questions for the implementer

These don't block Phase 1 but should be resolved during the indicated
phase. (Items previously deferred — vigilance_decrement / fatigue_drift
merge, calibration sample size — are now decided in §4 Phases 2 and 3
respectively.)

1. **(Phase 4)** For non-Chromium engines (Firefox / WebKit), is
   keyboard.press fallback acceptable for scope, or should sp11 hard-
   require Chromium and document the constraint in scope-of-validity?
   Default: accept the fallback's lower fidelity on non-Chromium with
   explicit scope-of-validity disclosure.
2. **(Phase 5)** Refinement retry budget — ≤2 is the proposed cap.
   Higher = more chances to recover; lower = faster failure detection.
   Stay at 2 unless an empirical case argues otherwise.
3. **(Phase 5)** Best-of-N TaskCard regen disclosure (in scope-of-
   validity) — phrasing TBD when writing the disclosure, but the
   substance is fixed: results reflect post-filter, up-to-3 generations
   per paradigm.

## 9. Risks

| Risk | Mitigation |
|---|---|
| `Input.dispatchKeyEvent` doesn't reach some platform listener types either | Phase 4 integration tests against in-browser fixture before committing the CDP path |
| Calibration offset SD too high → fixed offset doesn't help | Phase 3 reports SD; pivot to per-trial dynamic correction if needed |
| TaskCard regeneration produces worse `response_key_js` than SP8 | Pilot-time alignment check catches this before Phase 7 starts |
| N=30 validation hits unexpected timeouts on some paradigms | Sequential per-paradigm runs; pause and diagnose between paradigms |
| Cognition.run's response-recording mechanism is so different that even calibrated CDP delivery hits low fidelity | Documented as scope-of-validity boundary; sp11 reports the failure honestly per pre-registration |

## 10. Spec ownership

- **Project owner / approver:** Logan Bennett.
- **Spec drafted via:** Claude Code (Opus 4.7, this session).
- **Implementation responsibility:** Claude Code, per Logan's
  approval at each phase transition. **Approval is active, not
  passive:** Logan reviews and may edit any code Claude Code commits
  before phase transitions are approved. Phase transitions don't
  fire on a timer or on Claude Code's self-declaration of "done" —
  they fire on Logan's explicit "approved, proceed to Phase N+1."
- **Approval required before:** Phase 1 start; Phase 4a/4b transition;
  every phase transition (1→2, 2→3, …, 7→8).
- **Spec freeze:** §6 pre-registered criteria and Appendix C locked
  at this spec's first commit on sp11 (Phase 1). No edits to either
  after Phase 7 data exists.

## 11. Recovery plan if §6 gates fail

Phase 8's "honest writeup of failure" is the right discipline, but it
leaves the project's scientific claim in a degraded state without a
clear next step. The following maps each gate failure to a concrete
remediation path. This makes SP11 a real engineering document, not
just a successful-path narrative.

| Failure | Likely root cause | Remediation |
|---|---|---|
| **H1 fails** (mean per-trial fidelity < 85%) | Phase 4 CDP delivery insufficient for one or more platforms | First check H2 per-paradigm breakdown. If concentrated on one paradigm, treat as that paradigm's scope limit. If spread across paradigms, the input-layer architecture itself is in trouble; escalate before Phase 8 writeup. Candidate sp12: hybrid CDP + targeted JS dispatch with platform-specific listener-target detection. |
| **H2 fails on one paradigm** (per-paradigm fidelity < 75%) | Platform-specific behavior — that platform's recording mechanism diverges from what Phase 4 handles | Document as scope limit in `docs/scope-of-validity.md`. Drop that paradigm from the headline claim. Do NOT relax H2; the failure is the finding. Candidate sp12: platform-specific support for that paradigm only, with explicit "this is the worst-case adversary" framing per the SP10 secondary tier. |
| **H2 fails on multiple paradigms** | Architecture-wide fidelity problem | Same as H1 architectural failure — escalate. |
| **H3 fails on a paradigm** (pilot alignment < 90% after 2 retries) | Stage 1 prompt insufficient for that paradigm's `response_key_js` derivation | Mark paradigm unsupported on sp11 (per Phase 5 design). Note in writeup. Candidate sp12: per-paradigm Stage 1 prompt refinement OR runtime-LLM key resolution (SP9a revisit). |
| **H4 fails** (PES sign wrong or lag-1 autocorr ≤ 0) | Effects machinery silently disabled — likely executor's `prev_error` wiring regressed, or sampler stopped consuming the effect config | **This is a regression, not an SP11 failure.** Debug before declaring SP11 finished. The sp9c-baseline `recent_errors[0]` pattern is the correct one; verify it survived the cherry-picks and Phase 2 effects-library work. |
| **S1/S2 fails** (Stroop absolute RT z doesn't improve by ≥ 1.0 from sp9c baseline) | Calibration pass not closing the offset gap | Check Phase 3 reports: (i) is offset SD > 30ms (calibration variance ceiling)? (ii) is the offset distribution bimodal (two recording paths)? If either, the fixed-offset model is insufficient and per-trial dynamic correction (already specced as fallback in Phase 3) must replace it. Candidate sp12: per-trial regression-based correction with on-the-fly calibration updates. |
| **S3–S6 fails** (non-degradation — a metric currently in |z| < 1 drifted out) | sp11 introduced a regression in a metric sp9c was passing | Bisect cherry-picks + Phase 2/3/4 changes. The non-degradation clause exists to catch unintended side effects; treat S3–S6 failure as serious. Identify the regressing commit; fix or revert before declaring SP11 finished. |
| **S7 fails** (PES magnitude outside 10–50ms range) | Either sampler RT scale off (correlated with S1/S2) or the `post_event_slowing` mechanism's literature parameterization is wrong on the regenerated TaskCard | Check the regenerated TaskCard's `post_event_slowing.triggers.slowing_ms_*` — Stage 1 may have emitted an out-of-range value. If parameter is right but observed magnitude is off, the executor's `apply_post_event_slowing` wiring is suspect. |
| **§6.3 global non-degradation** (some other sp9c-era metric in |z| < 1 drifts out) | Same as S3–S6 — sp11 introduced a regression on a non-headline metric | Same remediation. The clause exists to catch unintended side effects on metrics not specifically named in §6.1/§6.2. |
| **Calibration itself fails on a paradigm** (Phase 3 can't compute an offset — e.g., the platform's data export doesn't include the calibration entries, or the bimodality criterion fires with no clean resolution, or the pre-trial gate can't be dismissed) | Platform's data-export format or input-acceptance behavior diverges from what Phase 3 assumes | This is an earlier-phase failure that propagates into Phase 7. Two options, **decision made by project owner**: (a) flag as scope limit in `docs/scope-of-validity.md`; run Phase 7 on that paradigm without calibration with explicit disclosure that S1/S2-equivalent gates do not apply; OR (b) drop the paradigm from Phase 7 entirely. Cognition.run is the obvious candidate (closed-source, unknown data-export shape until probed). Probe it in early Phase 3 to surface this issue before Phase 7 commits. |

**Escalation protocol.** Whenever a failure is named as "escalate
to project owner": Claude Code stops Phase 8 writeup, drafts a
failure-analysis memo (~500 words) in `docs/sp11-phase7-failures.md`
naming the gate, the observed numbers, the suspected root cause from
the table above, and the proposed remediation. Logan reviews the memo
and decides: (a) implement remediation as an SP11 fix, (b) accept the
failure and document the scope limit, (c) abandon SP11 and reframe
the scientific claim.

The point of §11 is to ensure failure modes have pre-thought
remediations so SP11's writeup isn't "we failed and don't know what
to do." It is.

## Appendix A: sp10 commits explicitly NOT ported to sp11

For provenance — these are valuable on the sp10 branch as the secondary
"worst-case adversary" tier but stay buried:

- `f6caa7f` — Stage 1 slim (dropped platform extractions). SP11 keeps
  the SP8 multi-source extraction prompt.
- `5e3619c` — Stage 6 thin pilot. SP11 expands Stage 6 with pilot-time
  alignment check.
- `562e86a` — Stage 1 `recommended_driver` field. Not relevant
  without drivers/.
- `e0df7b5`, `6797a18`, `a9ec9a5`, `372f1ee`, `ee7dead`, `ede0eb0`,
  `d9f5fe8`, `db9981e`, `d0dd719`, `7aa11e9`, `62de914` — all
  JsPsychDriver internals (response delivery hook, navigate-per-plugin,
  reading-pace gate, stop-trial withhold, v6 version tolerance, hook
  re-install, PES wiring restore). SP11 path uses CDP delivery and
  doesn't have a driver to attach this logic to.

## Appendix B: branch-state confirmation (taken 2026-05-18)

**Local sp* branches (14) with HEAD commits:**

| Branch | HEAD short SHA |
|---|---|
| `sp1/taskcard-reasoner` | `d9efd8d` |
| `sp2/behavioral-fidelity` | `0240e9e` |
| `sp3/heldout-validation` | `1b1255b` |
| `sp4a/stage2-robustness` | `00dc015` |
| `sp4b/parse-retry-class-fix` | `54397df` |
| `sp5/heldout-measurement` | `13c75fa` |
| `sp6/trial-end-fallback` | `939541d` |
| `sp7/keypress-diagnostic` | `9b14ea8` |
| `sp8/stage1-response-key-prompt` | `b06122e` |
| `sp9a/session-agent` | `120a4cd` |
| `sp9b/openalex-defensive-fix` | `270d003` |
| `sp9c/layer-d-investigation` | `9886362` |
| `sp10/driver-architecture` | `7aa11e9` |
| `main` | `4293a6f` |

**Origin sp* branches (10):** sp10, sp2, sp3, sp4a, sp4b, sp5, sp6,
sp7, sp8, plus main. **Missing from origin: sp1, sp9a, sp9b, sp9c.**
These get pushed in Phase 1 so the development history is durable
before any sp11 work begins.

**Tags on origin (16):** `sp1-complete`, `sp1.5-complete`,
`sp2-complete`, `sp2.5-complete`, `sp3-complete`, `sp4a-complete`,
`sp4b-complete`, `sp5-complete`, `sp6-complete`, `sp7-complete`,
`sp8-complete`, `sp9a-complete`, `sp9b-complete`,
`sp9c-investigation-complete`, `sp10-complete`. No tags get
touched on sp11.

**sp11 base point:** `sp9c-investigation-complete` = commit `9886362`
"docs(sp9c): Phase B.3 — per-trial analysis confirms listener-target
mismatch".

## Appendix C: sp9c baseline metrics — non-degradation tracking

This appendix is the enumerated baseline for §6.3's global non-
degradation clause. **It is populated as the final Phase 1 sub-task**
by reading the sp9c-era results docs and extracting every reported
metric with a z-score or literature-range pass/fail.

Until Phase 1 fills this in, §6.3 is unfalsifiable; afterward, §6.3
becomes a checklist that Phase 8 runs through metric-by-metric.

### Population procedure (Phase 1, ~30 min)

For each of the following result docs, extract every reported metric
with either (a) a z-score against human reference data, or (b) a
literature-range pass/fail:

- `docs/sp5-heldout-measurement-results.md` — Flanker, n-back
  rt_distribution validation
- `docs/sp6-results.md` — Flanker PES post-fix
- `docs/sp7-results.md` — keypress diagnostic, 4-way agreement
- `docs/sp8-results.md` — multi-source response_key_js, alignment
  pre/post-fix
- `docs/sp9a-results.md` — SessionAgent cross-paradigm
- `docs/sp9c-investigation.md` — layer-d listener-target findings

For each metric record: name, paradigm, sp9c value (number),
in-band/out-of-band status, source doc + section reference.

### Table (populated 2026-05-18, Phase 1 sub-task)

Values are the most-recent reported numbers across the sp9c-era result
docs. Where a later doc supersedes an earlier doc (e.g., SP6's PES
supersedes SP5's), the later value is used. Abstract values are
authoritative for headline z-score metrics where reported there.

**Held-out paradigm Flanker — `expfactory_flanker` (sp5/sp6/sp7 era):**

| Metric | sp9c value | Published range | In-band? | Source |
|---|---|---|---|---|
| `rt_distribution.mu` | 486 ms | [400, 550] | ✓ in-band | SP6 |
| `rt_distribution.sigma` | 73 ms | [25, 60] | ✗ out-of-band | SP6 (drifted out post-trial-end-fix) |
| `rt_distribution.tau` | 86 ms | [70, 160] | ✓ in-band | SP6 |
| `lag1_autocorr` | 0.27 | descriptive (no range) | ✓ sign-positive | SP6 |
| `post_error_slowing` magnitude | +35.43 ms | [10, 50] (literature) | ✓ in-band | SP6 |
| `cse_magnitude` | uncomputable | [-45, -10] | n/a (SP6 flagged uncomputable due to label vocabulary mismatch) | SP6 |
| Aggregate accuracy | 92.3 % | target ~95 %, range 90-95.8 % | ✓ in-band | SP5 |
| `bot_intended == platform_expected` | 49.8 % | n/a — chance for 2-key paradigm | ✗ at chance | SP7 (5 sessions, 600 trials) |
| `bot_pressed == page_received` | 93.3 % | n/a — SP11 target ≥ 85 % per H1 | ✓ above floor | SP7 |
| `page_received == platform_recorded` | 44.0 % | n/a — SP11 target ≥ 85 % per H1 | ✗ below floor (SP7 layer-d gap) | SP7 |
| `bot_pressed == platform_recorded` | 47.7 % | n/a — SP11 target ≥ 85 % per H1 | ✗ below floor (compounded a + d) | SP7 |

**Held-out paradigm N-back — `expfactory_n_back` (sp5/sp8 era):**

| Metric | sp9c value | Published range | In-band? | Source |
|---|---|---|---|---|
| `rt_distribution.mu` | 584 ms | descriptive (no published range) | descriptive | SP5 |
| `rt_distribution.sigma` | 149 ms | descriptive | descriptive | SP5 |
| `rt_distribution.tau` | 160 ms | descriptive | descriptive | SP5 |
| `lag1_autocorr` | 0.00 | descriptive | descriptive (sign-flat) | SP5 |
| `post_error_slowing` magnitude | +16.30 ms | [10, 50] (literature) | ✓ in-band | SP5 |
| Aggregate accuracy | 89.3 % | target 86-93 % | ✓ in-band | SP5 (post-warmup-filter) |
| `bot_intended == platform_expected` | 72.1 % | n/a — SP11 target ≥ 85 % per H1 | ✗ below SP11 target but best of sp9c | SP8 (multi-source prompt fix) |

**Dev paradigm Stroop expfactory — `expfactory_stroop` (sp9a era + abstract):**

Abstract reports numbers from a larger N=29 run; some overlap with
sp9c-era smaller runs. Abstract values used where reported there.

| Metric | sp9c value | Published range | In-band? | Source |
|---|---|---|---|---|
| Stroop interference effect | +93 ms (bot) | human 67 ± 41 ms; z = +0.61 | ✓ in-band (\|z\| < 1) | Abstract |
| Congruent absolute RT | 706 ± 42 ms (bot) | human 575 ± 67 ms; z = +1.95 | ✗ out-of-band (\|z\| > 1) | Abstract — SP11's S1 improvement target |
| Incongruent absolute RT | 798 ± 56 ms (bot) | human 642 ± 81 ms; z = +1.93 | ✗ out-of-band | Abstract — SP11's S2 improvement target |
| Congruent accuracy | 95.1 % (bot) | human 96.1 ± 4.7 % | ✓ in-band (\|z\| ≈ −0.21) | Abstract |
| `lag1_autocorr` | r = 0.16 ± 0.10 (bot) | descriptive | ✓ sign-positive | Abstract |
| `post_error_slowing` magnitude | 60 ± 59 ms (bot) | [10, 50] (literature, conflict-class) | ✗ slightly above range | Abstract — known sp9c-era anomaly; see Special Note below |
| `bot_intended == platform_expected` per-trial | 32.2 % mean | n/a | ✗ at chance (3-key counterbalance) | SP9a |

**Dev paradigm Stop-signal expfactory — `expfactory_stop_signal` (sp9a + abstract):**

| Metric | sp9c value | Published range | In-band? | Source |
|---|---|---|---|---|
| Mean go RT | 622 ± 47 ms (bot) | human 649 ± 100 ms; z = −0.27 | ✓ in-band (\|z\| < 1) | Abstract |
| Stop-signal accuracy | 53.2 % (bot) | human 52.1 ± 2.4 %; z = +0.45 | ✓ in-band | Abstract |
| Integration-method SSRT | 214 ms (bot) | human 234 ± 45 ms; z = −0.46 | ✓ in-band | Abstract |
| `post_error_slowing` magnitude | 37 ± 54 ms (bot) | [10, 50] (literature) | ✓ in-band | Abstract |
| `lag1_autocorr` | r = 0.10 ± 0.09 (bot) | descriptive | ✓ sign-positive | Abstract |
| `bot_intended == platform_expected` per-trial | 59.4 % | n/a | ✗ below SP11 target H1 | SP9a (1 session) |

**Dev paradigm STOP-IT — `stopit_stop_signal` (sp9a + abstract):**

Abstract reports "pattern replicated across the STOP-IT implementation
without modification" but doesn't give specific z-scores. Treat as
descriptively in-band on the abstract's key metrics (mean go RT, stop
accuracy, SSRT) until SP11 measures them directly. STOP-IT is also
the v6 paradigm SP10 had to route to DiagnosticDriver — the SP11
Playwright path is the first real-input attempt at it.

| Metric | sp9c value | Published range | In-band? | Source |
|---|---|---|---|---|
| Mean go RT, stop accuracy, SSRT | "pattern replicated" | as ExpFactory above | ✓ in-band per abstract narrative | Abstract |
| `bot_intended == platform_expected` per-trial | ~29 % | n/a | ✗ at chance | SP8 |

**Dev paradigm Cognition.run Stroop — `cognitionrun_stroop` (very limited sp9c data):**

Abstract reports N=28 cognition.run Stroop sessions but the exact
numbers tracked across the sp9c-era result docs were sparse — the
platform's pilot crashed multiple times during SP8 regeneration.
Abstract reports the same stroop-class headline numbers as
expfactory_stroop. SP11 Phase 3's calibration probe of cognition.run
will surface its data-export format; Appendix C is updated at that
point if the data shape supports a finer breakdown.

| Metric | sp9c value | Published range | In-band? | Source |
|---|---|---|---|---|
| Stroop interference, accuracy | reported as in-line with expfactory_stroop | conflict-class | ✓ presumed in-band per abstract | Abstract (N=28) |
| `bot_intended == platform_expected` per-trial | not measured at sp9c | n/a | unknown | n/a |
| All other metrics | not specifically isolated for cognitionrun_stroop in sp9c-era docs | — | — | n/a |

### Non-degradation rule

For every row marked "In-band: ✓" — across all 5 paradigm sub-tables
above — sp11 results on the same metric and paradigm must remain
in-band. Out-of-band rows are either explicitly named in §6.1/§6.2
(e.g., Stroop absolute RT in S1/S2) or are documented as known sp9c
gaps that sp11 doesn't commit to fixing in this iteration.

### Special note on Stroop PES

The abstract reports Stroop `post_error_slowing = 60 ± 59 ms`,
slightly above the 10-50ms conflict-class range. The number is from
a larger N=29 run; the conflict-class range may be conservative, or
sp9c's autocorrelation mechanism may have amplified PES beyond the
configured `slowing_ms_max=50`. Phase 8 of sp11 should check whether
the post-Phase-2 effects-library reconciliation changes this number,
and whether the published range itself merits revisit — but per §6.2
S7 the 10-50ms range stands as the pre-registered target.

### Special note on cross-paradigm metric availability

SP11's headline paradigms (the four in §6) have asymmetric sp9c
coverage. Held-out Flanker has rich SP5/SP6/SP7 data including
rt_distribution + sequential metrics. The dev paradigms have less
exhaustive sp9c-era reporting because they were the focus of the
sp10 driver-architecture detour rather than systematic measurement
under the Playwright path. SP11's Phase 7 produces the
measurement-systematic dev-paradigm baseline that sp9c lacked.
