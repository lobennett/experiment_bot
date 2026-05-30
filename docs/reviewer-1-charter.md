# Reviewer-1 Charter — Adversarial audit of the Task Turing Bot

**Audience:** A fresh Claude session (or other capable agentic reviewer). You are not a teammate. You have been dispatched to interrogate this project from a skeptic's perspective and produce a sharp, evidence-backed verdict.

**Your incentive:** This review is more valuable if it finds a real gap than if it confirms the project's claims. A "looks good" verdict with high confidence requires having run at least one probe that *could have* broken the claim and didn't. If you find yourself agreeing with the project's framing, you have not yet adversarially tested it.

**Maintenance:** This document is updated alongside the project. Re-read §10 on every review pass — the framework state and known unresolved issues evolve.

---

## 1. The core claims under test

The project asserts that an agentic AI bot, given only an experiment URL, can complete web-based cognitive tasks with humanlike behavior, with no task-specific or platform-specific code in the bot's library, and with minimal hand-tuning from the researcher.

Three claim families are at stake. Treat them as separable — one can hold while the others fail.

**C1 — Generalization.** A novel paradigm URL (one the framework has never been tuned against) can be ingested and produce a working TaskCard end-to-end without code changes to the bot's library. Cross-platform variants of the same paradigm produce comparable behavior.

**C2 — Behavioral fidelity.** The bot's outputs match human reference data on RT distributions (ex-Gaussian shape per condition), accuracy and omission rates, and sequential effects (post-error slowing, lag-1 autocorrelation, conflict adaptation where the literature predicts it). "Match" means within published meta-analytic ranges or within the IQR of a human reference dataset, depending on availability.

**C3 — Threat realism.** A malicious actor with a Claude API key and a few hours can deploy this bot against a real online experiment and evade the bot-detection screens an average researcher would deploy.

Scrutinize the *themes*, not specific numbers. Numbers in the project documents will drift as the framework evolves; the claim is that the *pattern* holds, not that any particular z-score sits where it currently sits.

---

## 2. Two adjacent claims you should also evaluate

These are not in the abstract but are load-bearing for the project's stated purpose. The team would like to know if they hold.

**C4 — Architectural task-agnosticism.** The bot's library should contain no task-specific or platform-specific logic. Where such logic is unavoidable (e.g., the validator needs paradigm-specific parsers), it should be quarantined and named, not diffused through the codebase. Audit whether this holds. Greps for paradigm names across `src/experiment_bot/` are a cheap starting probe.

**C5 — Minimal prior-knowledge encoding.** The framework should not bake in psychological-science priors that pre-determine the bot's behavior on a given paradigm. The bot's humanlikeness should emerge from Claude reading the page and reasoning, not from a lookup table of "for Stroop, do X." This is subtle to test — look for hard-coded paradigm-class behavior, distribution-family assumptions baked into code rather than configured per-run, and effect menus that are narrow enough to constitute prior commitment.

C4 and C5 are the claims that distinguish this project from prior work that "tailored a solution to a single online task." If they fail, the generalization claim collapses to "we have a configurable framework," which is much weaker.

---

## 3. Glossary

Read this before the reading list.

- **TaskCard** — the artifact the offline pipeline produces. Fully specifies how the runtime executor should run a paradigm: stimulus selectors, response keys, trial structure, target distributions, sequential effects.
- **Stage 1–6** — the offline pipeline stages that produce a TaskCard from a URL. Stage 1 ingests the page source; Stage 6 runs a pilot session to validate the TaskCard against the live experiment.
- **Executor** — the runtime bot. Reads a TaskCard, drives a browser through the experiment, emits a bot_log.
- **Validator** — the post-hoc analysis pipeline. Reads bot output and platform output, computes metrics per "pillar" (rt_distribution, individual_differences, sequential), checks each metric against a norms file or reports it descriptively.
- **Norms file** — `norms/<paradigm_class>.json`. Published meta-analytic ranges for a paradigm class. Gates the validator's pass/fail on covered metrics.
- **Pillar** — a category of validator metrics. Currently: rt_distribution, individual_differences, sequential.
- **Held-out paradigm** — a paradigm the framework was not tuned against during development. The fair test of C1.
- **Dev paradigm** — a paradigm the framework was tuned against. Use these only to establish baselines, never as evidence of generalization.
- **SP** — sub-project. The unit of incremental work. SP-results docs in `docs/` record what shipped, what failed, and what was deferred.

---

## 4. Reading list (orient before testing)

Spend ~15–30 minutes on orientation. Don't skip this; it prevents misinterpreting findings later.

### Project documents
- `Task Turing Bot Abstract.md` — the abstract whose claims you are testing.
- `CLAUDE.md` — project goals and operational rules.
- `docs/scope-of-validity.md` — what the framework does and does not claim (reviewer-facing spec).

### Sub-project trajectory
- `docs/validation-results.md` — the framework's current self-assessment (latest results and failure modes). Read this in place of the per-SP results docs.
- `docs/scope-of-validity.md` — the claims and limits (L1–L20 list). Already in the project documents list above; re-read the limits section specifically here.
- `CLAUDE.md` § "Sub-project history" — chronological record of what each SP shipped, failed, and deferred. Use this to understand the trajectory without reading individual SP docs.

### Code orientation
- `src/experiment_bot/reasoner/` — the offline pipeline that produces TaskCards.
- `src/experiment_bot/core/executor.py` — the runtime bot.
- `src/experiment_bot/validation/` — the validator, including any paradigm-specific code (which should be quarantined here if anywhere).
- `src/experiment_bot/effects/handlers.py` — generic behavioral mechanisms.

### What to skim, not read
The CLAUDE.md "Sub-project history" section covers the full trajectory. Individual SP-results docs have been consolidated into `docs/validation-results.md`; you do not need to locate per-SP files.

---

## 5. Time budget and minimum-viable review

Target **4–8 hours of reviewer effort**. If you find a fatal gap in the first hour, write it up and stop. Don't keep digging for more.

**Minimum viable review (≈3 hours):**
1. Read the abstract, CLAUDE.md, scope-of-validity, and `docs/validation-results.md` (45 min).
2. State your prior: which of C1–C5 do you expect to hold, which to fail, before running anything. One paragraph. (15 min.)
3. Pick **one** held-out paradigm the project documentation has never mentioned. Regenerate the TaskCard and run 5 sessions. (60–90 min wall time, mostly waiting.)
4. Run the validator and the alignment audit (`scripts/audit_alignment.py`) on the output. (15 min.)
5. Run **Probes A, C, and G** from §7. (30 min.)
6. Write findings per §8. (30 min.)

Everything beyond the MVR is the reviewer choosing to go deeper. Probes B, D, E, F, H are higher-effort and reveal subtler issues; spend time on them only if the MVR didn't already produce a confident verdict.

---

## 6. Methodology

### Hands-on validation protocol

For each paradigm you test:

1. **Pick a held-out paradigm.** The fair probe is a paradigm the framework has never seen. Do not use paradigms named in any SP-results doc, in §10 of this charter, or in `taskcards/`. Pick from any web-deployed cognitive task: paradigm previews from common task batteries, jsPsych demos, or a paradigm you compose yourself. The further from the dev set, the stronger the evidence about C1.

2. **Find the current framework state.** Check the latest SP-complete tag:
   ```bash
   git tag -l "sp*-complete" | sort -V | tail -5
   ```
   Check out the latest tag's branch or create a worktree.

3. **Regenerate the TaskCard:**
   ```bash
   rm -rf taskcards/<your-paradigm>/ .reasoner_work/<your-paradigm>/
   uv run experiment-bot-reason "<URL>" --label <your-paradigm> --pilot-max-retries 3 -v \
     > .reasoner-logs/review_<your-paradigm>_regen.log 2>&1
   ```
   Wall time: 5–25 min. **Pipeline failure here is itself a finding** — it's a generalization failure, possibly the most informative one you can produce.

4. **Run 5 smoke sessions:**
   ```bash
   for seed in 9001 9002 9003 9004 9005; do
     uv run experiment-bot "<URL>" --label <your-paradigm> --headless --seed "$seed"
   done
   ```
   ~5–15 min per session.

5. **Validate against norms (if a `norms/<paradigm_class>.json` exists for your paradigm class):**
   ```bash
   uv run experiment-bot-validate --paradigm-class <class> --label <output-label> \
     --output-dir output --reports-dir validation/reviewer_audit
   ```
   If no norms file exists for your paradigm class, the validator returns descriptive-only metrics. **Note this explicitly in your findings** — the claim that the bot is humanlike on that paradigm is unfalsifiable without norms.

6. **Run the per-trial alignment audit:**
   ```bash
   uv run python scripts/audit_alignment.py --label <output-label> --output-dir output
   ```

7. **Read `bot_log.json` directly** for a handful of trials. Compare to the platform's `experiment_data.csv` row-by-row.

### Fallback if you can't run a session

If the API is unavailable, paradigm URLs are down, or the environment won't bootstrap: analyze the bot_log and platform CSV files already in `output/` from prior runs. You can still execute Probes C, D, F, and parts of H without running anything new. Note in your findings that the analysis is on archived runs.

### What to measure

**Required (in every paradigm tested):**
- rt_distribution metrics (ex-Gaussian mu, sigma, tau per condition).
- Aggregate accuracy and omission rate.
- Sequential metrics where the paradigm-class predicts them (post-error slowing, lag-1 autocorrelation, conflict adaptation).

**Required where post-SP7 instrumentation supports it:**
- Per-trial alignment: bot.intended_error vs platform.correct_trial.
- Per-trial key fidelity at three layers: bot_pressed vs page_received vs platform_recorded vs platform_expected.

**Recommended where time allows:**
- Cross-paradigm comparison: does the bot perform similarly on your held-out paradigm vs. an archived dev-paradigm run? Divergence here is a generalization signal.

### Thresholds

State the threshold for "meaningful" before computing. Suggested defaults — adjust with reasoning if you depart from them:

- **z-score within ±1.5** of the human reference distribution mean → consistent with C2.
- **|z| > 2** → inconsistent with C2 unless the metric is descriptive-only or based on a sparse norms file.
- **Cross-platform divergence**: if ex-Gaussian mu differs by more than ~30 ms between two implementations of the same paradigm, treat C1's cross-platform claim as suspect.
- **Per-trial alignment**: anything < 70% on a paradigm class where the bot has access to the correct-response variable is a real gap. Anything ≈ 50% is at chance.

---

## 7. Adversarial probes

Roughly ordered cheap-to-expensive. Probes A, C, and G are the MVR set. Probes B, D, E, F, H are optional deep-dives.

### Probe A — Generalization on a fully-novel paradigm
The MVR probe for C1. Pick a paradigm URL that does not appear in any SP doc, taskcard directory, or this charter's §10. Run the full pipeline. Did Stage 2 produce a schema? Did Stage 6 pilot pass? If the framework dies, that is an extension boundary the generalization claim does not yet cover. **Specific things to watch for:** does the pipeline fail gracefully or crash? Does it write a TaskCard despite the pilot failing (silent failure)? Does it produce a TaskCard that runs but generates noise?

### Probe B — Bot-detection screen analog (deep-dive)
Probe of C3. Compare bot sessions against human reference data on aggregate features (mean RT, RT SD, accuracy, PES, autocorrelation).

**Sample-size note:** with n=5 bot sessions, a logistic regression on 4–5 features will overfit and produce a meaningless classifier. Don't do that. Instead: for each feature, check whether the bot's value falls inside the human distribution's IQR. Report each feature separately. If you want a real classifier, you need n ≥ 30 per group; flag that as out of scope for this review if so.

### Probe C — Per-trial keypress audit deep-dive
Probe of behavioral fidelity at the per-trial level. For 50 trials of the held-out paradigm, manually align bot_log entries to platform CSV rows. For each, check:
- Did the bot's logged `response_key` equal the platform's `response`?
- Did `intended_error=True` trials correspond to `correct_trial=0`?
- When the bot intended a specific key, did the platform record that key?

Discrepancies at each layer point to different failure modes (the taxonomy of bot→page→platform→expected layers is documented in `docs/validation-results.md`; refer to that rather than re-deriving it).

### Probe D — Off-axis behavioral signatures (deep-dive)
The validator computes a fixed set of metrics. The adversarial version of "is the bot humanlike" looks at signatures the validator *doesn't* check, which are exactly the signatures the bot has had no incentive to match. Suggested off-axis diagnostics:
- **Within-block RT drift.** Humans speed up across a block, then sometimes slow at fatigue points. Does the bot's RT change as a function of trial index within block?
- **Response-key bias.** When two responses are equally valid (or equally likely under the design), does the bot favor one key? Humans show small but real key biases.
- **RT conditional on previous-trial RT** (not just previous-trial accuracy). Compute lag-1 RT autocorrelation conditional on previous correctness.
- **Keystroke inter-arrival times** at the input layer. Is the time between keydown and keyup human-plausible?
- **Practice-vs-test block differences.** Humans show learning curves. Does the bot's behavior in practice trials differ from test trials, or is it flat?

These probes will find issues. The question is whether the issues matter for the threat model.

### Probe E — Stress-test paradigm classes outside the framework's coverage
Probe of C1's outer envelope. Test paradigm classes the framework has not been built around:
- Decision-from-experience (Iowa Gambling, bandits): non-speeded, sequential learning. Does the framework handle "learn-and-decide" structure, or does it just sample RTs as if there were no learning signal?
- Free-response paradigms (no stimulus, button press at will).
- Visual search where RT scales with set size.

If any of these fail, the generalization claim is bounded — say where.

### Probe F — Between-session variance (deep-dive)
Run 10 sessions with consecutive seeds. Compute between-session variance for the key metrics. Compare to between-subject variance reported in the human reference data. If between-session variance is far below between-subject variance, the bot is too "tight" — a single bot run might look human but a cohort of bot runs will look unmistakably like a cohort of one person. With n=10, you can compare orders of magnitude; you cannot do a statistical test. Frame findings accordingly.

### Probe G — Forensic / non-behavioral detection
**This is the highest-leverage probe for C3.** The abstract's claim is behavioral, but a real-world deployment hits non-behavioral detection surfaces first. If the bot fails forensics, the behavioral fidelity is moot from a threat-model standpoint.

Check:
- **Mouse movement.** Does the bot move the mouse, or only emit key events? "No mouse movement, ever" is a trivial bot signal.
- **Window focus / blur events.** Real humans alt-tab, scroll, briefly look away. Does the bot generate any of these events?
- **Browser fingerprint.** Is the launched browser flagged by standard bot-detection libraries (e.g., `navigator.webdriver === true`, missing plugins, headless UA strings)?
- **Network timing.** Is the timing of API calls / page loads suspiciously uniform?
- **Keystroke biomechanics.** Is the time between keydown and keyup constant, or does it vary as humans' do?

Cost: 30–60 min if you know what to look for. Output: a list of forensic tells with severity ratings. **If the bot fails Probe G badly, escalate this to a top-line finding** — the threat model claim has a forensic floor that the behavioral claim sits on top of.

### Probe H — Failure-mode reverse-engineering (conditional)
Only run this if you've read `docs/validation-results.md` carefully. For each failure mode that doc claims was resolved, verify the resolution holds on your held-out paradigm. For each residual documented there, check whether it has grown or stayed bounded.

### Probe I — Code-design audit (probes C4 and C5)
Walk the codebase looking for violations of the task-agnosticism and minimal-prior-knowledge claims.

For C4 (task-agnosticism):
- `grep -ri` for known paradigm names across `src/`. Where do they appear? Should they?
- Are conditionals on paradigm-class scattered, or quarantined?
- Could a new paradigm class be added without modifying core executor code?

For C5 (prior-knowledge encoding):
- Are response distributions, accuracy targets, and effect parameters generated per-run by Claude reading the page, or are they pulled from a lookup table?
- Is the "menu of available sequential effects" narrow enough to constitute strong prior commitment? Six effects is a small set — is the claim that Claude *selects from* a menu meaningfully different from "the framework knows what effects to use"?
- Is the ex-Gaussian distribution family a configurable choice or a hard-coded assumption? Would a paradigm that doesn't fit ex-Gaussian RT structure be handled?

Document any violations with file:line references.

---

## 8. Reporting structure

Produce ONE document at `docs/reviewer-<n>-findings-<YYYY-MM-DD>.md`.

1. **Prior** (one paragraph). Written *before* running probes. State which of C1–C5 you expected to hold and which to fail, and why. This is the pre-registration; do not edit it after running probes. Add a brief post-hoc note if your priors were wrong, but don't rewrite the prior itself.

2. **Headline finding** (one paragraph). Reviewer's verdict on each of C1–C5, with confidence rating (high / moderate / low) and the single most load-bearing piece of evidence for each verdict.

3. **Tested configuration**: paradigm URL(s), session count, framework tag/SP, environment notes.

4. **Per-paradigm results**: a table with rt_distribution metrics, accuracy, omission rate, sequential metrics, per-trial alignment, vs. norms or human reference data with z-scores or IQR membership. State explicitly which metrics are descriptive-only.

5. **Probe results**: which probes ran, what they showed, what they ruled out. For each probe, one paragraph maximum.

6. **New failure modes surfaced**: gaps the SP-results docs have not already documented. **This section is the most valuable part of the review.** If it's empty, you have not done an adversarial review.

7. **Threat-model assessment**: assume a researcher running standard quality checks on a real online experiment. Which screens would catch this bot? Which would not? Is the bot a credible threat *today*, or only after specified further work?

8. **Recommendations**: specific further work that would either close gaps or strengthen claims. Order by leverage (which fix would do the most for the central claim per unit effort).

Be specific. Be adversarial. Don't give the framework the benefit of the doubt. If a metric is descriptive-only, say so. If sample sizes are too small, name the noise threshold. If your finding is "everything checks out," explain what would have changed your mind and confirm at least one such test was run.

---

## 9. Maintenance protocol (for the project team)

Update this charter when:
- A new SP-complete tag lands. Update §10 with the new state. Do not list specific findings from that SP in §6 or §7 — keep them in the SP-results docs the reviewer will read independently.
- A new paradigm class is added under `norms/`. Note it in §10's list of available norms files; do not name specific paradigms in §7 probes.
- The abstract is revised. Update §1 to reflect the current claim set.
- A new validator pillar or metric is added or removed. Update §6 "What to measure."

**Critical:** when updating, do not pre-announce findings to the reviewer. The reviewer should rediscover the project's known issues from data, not be handed them. If a finding belongs in the reviewer's hands, it goes in an SP-results doc they read independently, not in this charter.

---

## 10. Latest framework state (auto-updated)

**Last reviewed at:** sp16-complete

**Maintenance log:** 2026-05-30 — docs consolidated (SP12–SP16); per-SP results docs replaced by `docs/validation-results.md`; broken pointers in reading list, Probe C, and Probe H updated; deleted keypress_audit script replaced by `scripts/audit_alignment.py`.

**Validator pillars currently implemented:** rt_distribution, individual_differences, sequential.

**Norms files currently available** (paradigm classes for which gated, not descriptive, validation is possible): [list of paradigm-class names — *not* specific paradigm names].

**Pipeline stages currently shipping:** Stage 1 (ingest) through Stage 6 (pilot validation).

**Held-out paradigm count:** [N paradigms have been used as held-out probes in prior reviews; their identities are recorded in the SP-results docs the reviewer reads independently and are not enumerated here].

**Maintenance note:** §10 deliberately omits per-paradigm pass/fail state and per-metric current values. The reviewer should derive these from running the validator on their own held-out paradigm and reading the latest SP-results doc. If you (the team) catch yourself wanting to add "and Paradigm X currently shows Y" here, that information belongs in an SP-results doc instead.

---

## End of charter

If you find a gap this charter does not anticipate, that is the most valuable kind of finding. Document it precisely. State whether the framework's central claims survive despite the gap, or whether the gap undermines them.