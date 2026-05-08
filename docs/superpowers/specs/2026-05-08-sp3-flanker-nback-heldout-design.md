# SP3 — Held-out generalization test (Flanker + n-back)

## Goal

Produce empirical evidence that the experiment-bot framework generalizes
to paradigms whose iteration loop never touched. SP1, SP1.5, and SP2
were built and tuned against four "dev" paradigms (two Stroop, two
stop-signal). Whether the framework's claimed generalizability holds
beyond that set is unknown until tested. SP3 is that test.

Two held-out paradigms:

- **Flanker** — `https://deploy.expfactory.org/preview/3/`
  Conflict class. Within-class held-out for the conflict paradigm
  family already represented by Stroop in the dev set. Tests whether
  the framework overfit to Stroop-specific structure.

- **N-back** — `https://deploy.expfactory.org/preview/5/`
  Working-memory class. Cross-class held-out — distinct paradigm
  class from anything in the dev set. Tests whether the open
  paradigm-class taxonomy (audit finding H2) actually generalizes.
  N-back was previously held-out tested on 2026-05-06 and surfaced
  gaps; the audit refactors that followed addressed those gaps.
  Re-running n-back closes that loop under the post-audit framework.

## Definition of held-out

The held-out paradigm's prompts, TaskCards, and Reasoner-stage
configuration are NEVER iterated against during SP3. The point of
held-out is that failure tells us something we can't otherwise know;
"fix it to pass" defeats the purpose. Per CLAUDE.md G5: failures get
named in the SP3 report (which framework component is implicated),
but fixes ride later.

## Success criteria

Two pass-types reported separately, neither one gating the other:

**Operational pass.** Framework runs end-to-end. Reasoner produces a
TaskCard. Executor runs the TaskCard against the live URL and
produces a non-empty bot_log.json. Bot's trial count matches the
platform's (within practice-vs-test bookkeeping margin). Validation
oracle returns finite metric values rather than crashing or producing
NaN-everywhere.

**Behavioral pass.** Validation oracle reports per-paradigm metrics
(post_error_slowing, lag1_autocorr, rt_distribution, plus paradigm-
class signature metrics) within the literature ranges in the
corresponding norms file (`norms/conflict.json` for Flanker;
`norms/working_memory.json` for n-back). Behavioral pass is reported
descriptively; it does not gate SP3 completion. Sample size N=5 per
paradigm gives noisy individual metrics; out-of-range metrics may be
sampler jitter rather than a fidelity gap.

The cleanest reading is: operational pass is the binary
generalization claim, behavioral pass is descriptive evidence of
behavioral fidelity.

## Interpretation table

| Outcome | Reading |
|---|---|
| Both paradigms operationally pass | Framework generalizes within and across paradigm classes. |
| Flanker operationally fails | Framework is overfit even within the conflict class. Catalog gap, defer fix. |
| N-back operationally fails | Cross-class generalization is weak. Either the paradigm-class taxonomy isn't doing its job or the framework relies on speeded-choice assumptions that don't hold for working-memory tasks. Catalog gap, defer fix. |
| Operational pass + behavioral metrics out of range | Framework runs but bot doesn't reproduce the paradigm's hallmark effects. Could be sampler/jitter noise (N=5 is small) or real fidelity gap. Reported descriptively. |
| Behavioral metrics in literature ranges | Strongest evidence: bot reproduces literature-consistent effects on a paradigm we never tuned for. |

## Sample size

5 sessions per paradigm. 10 total. Sequential, headless. ~30–50 min
of unattended runtime.

Why N=5: two sessions (smoke v3 default) is enough to confirm
operational pass but inadequate for behavioral metrics — per-session
jitter (`between_subject_sd[mu]≈50`) makes single-session metric
estimates noisy. Five sessions is a clear improvement on noise
without becoming a multi-hour batch. If N=5 results are promising
and a larger-N replication is desired before publication, that's a
separate decision after SP3.

## Allowed code changes

| Change | Allowed? |
|---|---|
| Add `read_expfactory_flanker` adapter + dispatch entry | Yes |
| Add adapter for n-back if needed (mechanical export-format parsing) | Yes |
| Defensive bug fixes when validator crashes on Flanker/n-back data | Yes |
| Tweak any Stage prompt to make a held-out paradigm pass | No |
| Hand-edit a held-out TaskCard JSON to fix specific failures | No |
| Generic framework improvements (better phase detection, etc.) | Defer to post-SP3 sub-project |

The boundary: SP3 is a measurement sub-project, not a fix sub-project.
Adapters are mechanically necessary because the validation oracle
dispatches by output-directory name; without an adapter, the validator
falls back to `bot_log.json` and double-counts platform trials.

If a held-out test reveals a generalizable framework gap, that gap
is logged in the SP3 results doc and triaged into a future SP4 backlog.
This mirrors the n-back-test → generalization-audit → SP1.5 flow that
established the pattern.

## Procedure (per paradigm)

1. **Regenerate TaskCard.** `experiment-bot-reason <URL> --label <label>`
   with `--pilot-max-retries 3`. Use the framework as it stands at
   commit `577f685` (= tag `sp2-complete`). No prompt overrides.
2. **Add platform adapter** if the paradigm's data export schema
   doesn't fit existing adapters. For Flanker, expect to add
   `read_expfactory_flanker` mirroring `read_expfactory_stroop`.
   For n-back, check if `read_expfactory_*` patterns work; otherwise
   add one.
3. **Run 5 smoke sessions** sequentially:
   `experiment-bot <URL> --label <label> --headless`. Each session
   produces a session directory under `output/<task-name>/<timestamp>/`.
4. **Validate.** `experiment-bot-validate --paradigm-class <class>
   --label <label> --output-dir output --reports-dir validation/sp3_heldout`.

Run order: Flanker first (newer code path through the new adapter,
higher risk), then n-back (re-test).

## Deliverables

- `taskcards/expfactory_flanker/<hash>.json` + `pilot.md` +
  refinement diffs
- `taskcards/expfactory_n_back/<hash>.json` + `pilot.md` +
  refinement diffs
- 10 session directories under `output/<task-name>/<timestamp>/`,
  each with `bot_log.json`, `experiment_data.{csv,json}`,
  `run_metadata.json` (with session_seed, session_params,
  taskcard_sha256), and screenshots.
- 2 validation reports under `validation/sp3_heldout/`.
- Platform adapter code in `validation/platform_adapters.py` (and
  tests in `tests/test_platform_adapters.py`).
- `docs/sp3-heldout-results.md` — combined Flanker + n-back results
  with comparison against smoke v3 dev paradigms. Sections: per-
  paradigm operational result, per-paradigm behavioral metrics
  table, interpretation per the table above, framework gaps logged
  for SP4 backlog.
- Branch `sp3/heldout-validation` off `sp2-complete`. Tag
  `sp3-complete` once the report lands. Push to origin.

## Out of scope

- Deep comparison / analysis scripts beyond what the report includes.
  Per user request: "analysis code can be written after." The
  comparison-script work is a separate sub-project.
- Adding Eisenberg-style human reference data for Flanker. Not
  blocking; if such data is found, it's optional descriptive context.
- Larger-N replication (15+ sessions) before publication. Decided
  after SP3 results are in.
- Any prompt or TaskCard-level tuning. SP3 is a measurement, not a
  tune-up.

## Sub-project boundary check

This spec is appropriately scoped to a single implementation plan:
- One concrete deliverable (the SP3 report).
- One bounded set of code changes (adapters + defensive fixes).
- One pre-defined success criterion (operational pass on both
  paradigms; behavioral metrics reported descriptively).
- A clear hand-off rule for findings (catalog into SP4 backlog,
  don't fix in SP3).

If the test reveals systemic generalization failures, the resulting
SP4 sub-project would be its own brainstorm/spec/plan cycle.
