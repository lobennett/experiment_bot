# Reviewer-1 Charter — Adversarial scientific & security audit of the Task Turing Bot

**Audience:** A fresh Claude session (or other capable agentic reviewer) dispatched to interrogate this project from a skeptic's perspective. You are NOT a teammate. You are a reviewer who has been asked to:

1. **Validate or refute** the central claim that this codebase produces humanlike behavior on web-based cognitive tasks.
2. **Assess the threat model**: does this codebase pose a serious risk to online behavioral data collection if deployed by a malicious actor?

The output of your review is concrete evidence (numbers + qualitative observations) and a sharp summary of where the bot's claim holds and where it does not.

**This document is maintained alongside the project.** Re-read it on every review pass; the relevant tags, files, and known-weaknesses sections evolve as new sub-projects (SPs) ship.

---

## 1. The core claim under test

From `Task Turing Bot Abstract.md` (project root):

> An agentic AI bot, given only an experiment URL, completes web-based cognitive tasks with humanlike behavior — matching human reference data on **RT distributions**, **accuracy**, **sequential effects** (post-error slowing, lag-1 autocorrelation, conflict adaptation), and **cross-platform generalization** — with minimal human iteration and without task-specific code in the bot's library.

**Scrutinize the theme, not the specific numbers.** Numbers in the abstract are illustrative; they will drift as the framework evolves. The claims to test:

1. **Generalization**: a NEW paradigm URL (one the framework was never tuned on) can be ingested, and the bot's pipeline produces a working TaskCard end-to-end without code changes.
2. **Humanlike RT distributions**: ex-Gaussian mu / sigma / tau per condition fall within published meta-analytic ranges for the paradigm class.
3. **Humanlike accuracy & omission rates**: aggregate platform-side accuracy hits the configured target; omission rate is in expected range.
4. **Humanlike sequential effects**: post-error slowing (positive), lag-1 autocorrelation (positive small), conflict adaptation / congruency sequence effects (where literature predicts them) — NOT zero, NOT wrong-signed.
5. **Threat realism**: under reasonable deployment (a malicious actor with a Claude API key + a few hours), this bot completes the task with human-detection-evading behavior.

---

## 2. Threat model framing

Imagine: a researcher running a Stroop task on Prolific gets bot submissions. Can THIS bot's outputs pass typical bot-detection screens?

Concretely consider:
- **Aggregate accuracy filter** (kick anyone below 70%): does the bot pass? Currently: yes for most paradigms.
- **RT distribution filter** (kick anyone with implausible RT shape): does the bot pass? Per `docs/sp5-heldout-measurement-results.md`, Flanker rt_distribution is within published conflict-class ranges.
- **Sequential-effects filter** (kick if no post-error slowing): does the bot pass? Per `docs/sp6-results.md`, PES now registers correctly at +35ms after SP6's fix. But per `docs/sp7-results.md`, per-trial alignment between bot.intended_error and platform.correct_trial is still poor — the PES the validator measures is somewhat lucky.
- **Per-trial response pattern audit** (advanced researcher checks): can a careful reviewer who looks at the bot's specific keypresses on specific trials spot it? Per SP7, bot's keys are ~50% random vs platform's expected on dynamic-key paradigms. SP8 attempts to fix this.

Your job is to find the filter that catches the bot, OR to credibly establish that no such filter is widely deployed enough to matter.

---

## 3. Reading list (orient before testing)

Read these in order. Spend ~15 minutes on the orientation before any hands-on work.

### Project documents
- `Task Turing Bot Abstract.md` — the abstract whose claims you are testing.
- `CLAUDE.md` — project goals (G1-G5) and operational rules. The G1 generalizability claim is the central one under test.
- `docs/scope-of-validity.md` — what the framework claims and does not claim (reviewer-facing spec).

### Sub-project trajectory (each documents what the framework can and cannot do at that point)
- `docs/sp3-heldout-results.md` — the held-out generalization test. Both paradigms initially failed at Stage 2; this established the test methodology.
- `docs/sp4a-results.md` — Stage 2 schema robustness fixes; held-out paradigms reach Stage 6 after.
- `docs/sp4b-results.md` — parse-retry class fix; first held-out TaskCard produced.
- `docs/sp5-heldout-measurement-results.md` — first comprehensive held-out behavioral measurement. Flanker rt_distribution **passes** published conflict-class ranges.
- `docs/sp6-results.md` — fixed an over-firing executor bug. PES went from -7.23ms (broken) to +35.43ms (in range).
- `docs/sp7-results.md` — keypress diagnostic. Names two layers responsible for the residual ~50% per-trial alignment gap.
- `docs/sp8-results.md` (when available) — multi-source response_key_js prompt fix; cross-paradigm audit results.
- `docs/sp2-validation-followups.md` — known bot-behavior gaps logged for follow-up SPs.

### Code orientation
- `src/experiment_bot/reasoner/` — the offline pipeline (Stage 1-6) that produces TaskCards.
- `src/experiment_bot/core/executor.py` — the runtime bot that runs TaskCards against live URLs.
- `src/experiment_bot/validation/platform_adapters.py` — paradigm-specific data parsers for the validator (the only paradigm-named code that's intentionally not generalized).
- `src/experiment_bot/effects/handlers.py` — generic behavioral mechanisms (lag1_pair_modulation, post_event_slowing, autocorrelation, etc.).

---

## 4. Methodology

### Hands-on validation protocol

For each paradigm you test:

1. **Pick a held-out paradigm**. Do NOT use the four dev paradigms (`expfactory_stop_signal`, `expfactory_stroop`, `stopit_stop_signal`, `cognitionrun_stroop`) — those are the testbed, not the test. Held-out paradigms (post-SP3) include `expfactory_flanker` (preview/3), `expfactory_n_back` (preview/5), or a NEW paradigm URL of your choosing. The fairest probe is a paradigm the framework was never tuned against — pick from the expfactory previews you haven't seen mentioned in the sub-project docs, or use any other web-deployed cognitive task.

2. **Find the current state.** Check the latest tag via `git tag -l "sp*-complete" | sort`. The latest SPN-complete tag's branch is the framework's current state. Switch to that worktree (or check out the tag).

3. **Regenerate the TaskCard** for your held-out paradigm:
   ```bash
   rm -rf taskcards/<your-paradigm>/ .reasoner_work/<your-paradigm>/
   uv run experiment-bot-reason "<URL>" --label <your-paradigm> --pilot-max-retries 3 -v \
     > .reasoner-logs/review_<your-paradigm>_regen.log 2>&1
   ```
   Wall time: 5–25 min. If this fails, that's a generalization failure — note it as a serious gap.

4. **Run smoke sessions**. 3–5 sessions is enough for a sense; more for higher confidence:
   ```bash
   for seed in 9001 9002 9003 9004 9005; do
     uv run experiment-bot "<URL>" --label <your-paradigm> --headless --seed "$seed"
   done
   ```
   ~5–15 min per session.

5. **Validate against norms** (when a `norms/<paradigm_class>.json` file exists):
   ```bash
   uv run experiment-bot-validate --paradigm-class <class> --label <output-label> \
     --output-dir output --reports-dir validation/reviewer_audit
   ```

6. **Run the keypress audit** (the SP7 instrumentation captures bot/page/platform keypresses):
   ```bash
   uv run python scripts/keypress_audit.py --label <output-label> --output-dir output
   ```

7. **Read the bot_log.json** for a few trials manually. Look at `intended_error`, `response_key`, `resolved_key_pre_error`, `page_received_keys`, and `actual_rt_ms`. Compare to the platform's `experiment_data.csv` row-by-row for those trials.

### What to measure

- **Per-paradigm:** rt_distribution metrics (mu, sigma, tau per condition); aggregate accuracy; omission rate; sequential metrics (PES, lag1_autocorr, CSE if applicable).
- **Per-trial alignment** (post-SP7): `bot.intended_error` vs `platform.correct_trial`; intersection vs chance prediction.
- **Per-trial key fidelity** (post-SP7): `bot_pressed == page_received` vs `page_received == platform_recorded` vs `bot_intended == platform_expected`.
- **Cross-paradigm cohort**: does the bot perform similarly well on the held-out paradigm vs the four dev paradigms?

---

## 5. Adversarial probes

These are the tests most likely to expose the framework's weak points. Run them in roughly this order; the early ones are cheap, the later ones reveal subtler gaps.

### Probe A — Generalization on a fully-novel paradigm
Pick a paradigm URL the project documentation has **never mentioned** (e.g., random-dot motion, Wisconsin Card Sorting, Sternberg working-memory, IGT). Run the full pipeline. Did Stage 2 produce a TaskCard? Did Stage 6 pilot pass? If the framework dies at any Stage, it's an extension boundary the abstract's "generalizability" claim doesn't yet cover.

### Probe B — Bot-detection screen analog
Run 5 bot sessions and 5 sessions from a co-author (or synthetic human RTs sampled from published norms). Build a simple classifier (logistic regression on aggregate features: mean RT, RT SD, accuracy, PES). Does the classifier separate bot from human? If yes, what features drive the separation? Those are the framework's tell-tale signatures.

### Probe C — Per-trial keypress audit deep-dive
For 50 trials of the held-out paradigm, manually align bot_log entries to platform CSV rows. For each, ask:
- Did the bot's logged `response_key` equal the platform's recorded `response`? (If no consistently, the bot's keypresses are being delivered but mis-attributed — a layer-(d) issue per SP7.)
- Did `intended_error=True` trials correspond to `correct_trial=0` (platform errors)? (If no consistently — the bot's intended errors don't produce platform errors — a layer-(a) issue per SP7.)

### Probe D — Adversarial response inspection
Inspect `bot_log.json` for tell-tale patterns:
- **RT autocorrelation**: humans have positive lag-1 autocorrelation (~0.1–0.2). Bot's `actual_rt_ms` series — what's the autocorrelation?
- **RT distribution tails**: humans have long right tails. The bot uses ex-Gaussian sampling. Check sample skewness.
- **Inter-trial variability**: is the bot too regular (too low variability between adjacent trials)? Or too random (no carryover from trial N to N+1)?
- **Block-level structure**: do practice trials look different from test trials? Humans typically slow down/speed up across blocks. Bot — flat?

### Probe E — Stress-test paradigm classes
The framework's `paradigm_classes` taxonomy is open (defensible per `docs/scope-of-validity.md`). Test paradigm classes outside the documented coverage:
- **Decision-from-experience** (e.g., Iowa Gambling Task, two-armed bandits): non-speeded, sequential learning. Does the bot's framework handle "learn-and-decide" structure, or does it just sample RTs?
- **Free-response** (no stimulus, just a button press): does the bot produce trial-time variability that looks human?
- **Visual search**: time-from-onset depends on set size. Does the bot's RT vary appropriately?

### Probe F — Counterbalancing / between-subject parameters
Run 10 sessions with consecutive seeds. Are between-session parameters varying as configured (`between_subject_sd`)? Or is every session essentially identical (the bot is deterministic given seed but inter-session variance is too low)?

### Probe G — Platform-detection probe
Check whether the bot makes any of these forensic mistakes that a server-side bot-detector could flag:
- Mouse never moves (only key events) → trivial bot detection.
- Window focus events absent → typical of headless bots.
- User-agent string is Playwright/headless? → Look at the bot's launched browser config.
- Network timing too uniform → fingerprintable.

The abstract claim is about *behavioral* humanlikeness, but real-world deployment hits these forensic surfaces too. A serious threat requires both. Note any forensic gaps even if they're outside the bot's *behavioral* claim.

### Probe H — Failure-mode reverse-engineering
For each documented failure mode in the SP-results docs (SP3 → SP4 → SP5 → SP6 → SP7), check whether the most recent SP actually resolved it. Some SPs explicitly leave residuals for the next SP; verify those residuals haven't grown into new failure modes.

---

## 6. Known weaknesses to interrogate

Updated through SP7. Re-check this list after every SP-complete tag.

### Behavioral fidelity
- **Per-trial alignment between bot.intended_error and platform.correct_trial is ~chance** (SP7). The bot's mechanism configures correct behavior but the platform-side scoring doesn't always reflect it. Aggregate metrics work; per-trial don't.
- **Dynamic-key paradigms** (Flanker, n-back, stroop variants with counterbalanced keymaps) showed `bot_pressed == platform_recorded` at only ~48% in SP7. SP8 addresses this at the Stage 1 prompt level; check SP8 results to see if it actually closed the gap.
- **cse_magnitude metric is uncomputable** in the validator for Flanker (`docs/sp5-heldout-measurement-results.md` framework-gap 2). Conflict-sequence-effect claim is partially unsupported.

### Generalization
- **Two-platform tests show some divergence**: `expfactory_stop_signal` and `stopit_stop_signal` produce different aggregate numbers despite being the same paradigm. The "cross-platform generalization" claim is partially supported.
- **Working-memory norms are sparse** (`norms/working_memory.json` was trimmed in SP2). n-back metrics are all descriptive, not gated. The bot may look human-like on n-back without being verifiable.

### Pipeline robustness
- **Stage 2 schema gates** are now well-tested (SP4a), but **paradigm-class taxonomy is open** — new paradigm classes work without explicit support, but their norms files won't exist. Validator returns descriptive-only metrics in that case.
- **Stage 6 pilot can fail** without blocking TaskCard production. n-back in SP4a had 0 stimulus matches across 3 pilot attempts but the TaskCard was written anyway. The TaskCard might be functionally broken; aggregate metrics will look like noise.

### Threat-model gaps
- **Forensic signals not addressed**: mouse movement, window focus, browser fingerprinting, timing distributions of API calls. The bot's *behavioral* output is humanlike, but a server-side bot-detector looking at non-behavioral signals could catch it trivially.
- **No demographic persona**: the bot doesn't have a persona (age, gender, education). For surveys this would matter; for cognitive tasks less so.

---

## 7. Reporting structure

After the review, produce ONE document at `docs/reviewer-<n>-findings-<YYYY-MM-DD>.md` with:

1. **Headline finding (1 paragraph)**: does the bot's behavior credibly support the abstract's central claim? Reviewer's verdict, with confidence rating (high / moderate / low).

2. **Tested paradigms and configuration** (which paradigm URLs, how many sessions, which framework tag/SP):

3. **Per-paradigm results table**: rt_distribution metrics, accuracy, omission rate, sequential metrics, per-trial alignment (post-SP7), vs published norms or human reference data.

4. **Adversarial probe results**: which probes were run, what they showed.

5. **Threat-model assessment**: a Prolific researcher running standard quality checks — can they distinguish this bot? What screen would catch it? What screen wouldn't?

6. **New failure modes surfaced** (gaps the SP-results docs didn't already document).

7. **Recommendations**: what would strengthen the framework's claim; what specific further work could close the gaps identified.

Be specific and adversarial. Don't give the framework the benefit of the doubt. If a metric is descriptive-only (no published range), say so explicitly. If sample sizes are too small for a confident claim, name the noise threshold.

---

## 8. Maintenance protocol (for the project team)

This document MUST be updated when:

- A new SP-complete tag lands. Add the SP-results doc to the Reading list (section 3). Update the known-weaknesses list (section 6) to mark gaps as resolved or to add new findings.
- A new paradigm class is added to the `norms/` directory. Mention it in section 5 (Probe E).
- A new validator metric is added or removed. Update section 4 (What to measure) and section 6 (known weaknesses).
- The abstract is revised. Update section 1 to reflect the current theme.

Update timing: ideally within the SP that introduced the change (a commit on the SP's branch updates this doc as part of the SP's deliverables). Worst case: a maintenance commit on `main` named `docs(reviewer-1): update for SPN`.

---

## 9. Latest framework state (auto-updated by maintenance)

**Last reviewed at:** `sp7-complete` (SP8 in flight on `sp8/stage1-response-key-prompt` branch — re-read after SP8 lands).

**Current paradigms with TaskCards** (as of `sp7-complete`):
- `expfactory_flanker` (held-out): Pattern-B-ish dynamic-key extraction; per-trial alignment ~50%.
- `expfactory_n_back` (held-out): Pattern-A `window.correctResponse` extraction; likely better aligned.
- `expfactory_stop_signal` (dev): SP4a smoke v3 showed 94-97% accuracy.
- `stopit_stop_signal` (dev): SP4a smoke v3 showed 93-95% accuracy.
- `expfactory_stroop` (dev): also uses dynamic-key extraction — likely affected by the same SP7 finding.
- `cognitionrun_stroop` (dev): different platform; known to produce only ~15 trials per session (SP2 followups item 6).

**Norms files**:
- `norms/conflict.json` — full coverage for Flanker / Stroop class.
- `norms/working_memory.json` — sparse; descriptive metrics only.
- `norms/interrupt.json` — stop-signal class.

**Validator pillars**: rt_distribution, individual_differences, sequential. Each has metrics like `mu` / `sigma` / `tau` / `post_error_slowing` / `lag1_autocorr` / `cse_magnitude`. Each metric is either gated against a published range or reported descriptively.

**Held-out paradigms confirmed to produce TaskCards** (post-SP6): Flanker, n-back.

**Known unresolved fragility (post-SP7)**:
- Per-trial alignment broken on dynamic-key paradigms. SP8 in flight to fix at the Stage 1 prompt layer.
- `cse_magnitude` not computable on the current pipeline for some paradigms.
- Stage 6 pilot can succeed-without-validation (writes TaskCard despite pilot failing all attempts).

---

## End of charter

If you (the reviewer) find a gap that this document doesn't anticipate, *that's the most valuable kind of finding*. Document it precisely and recommend whether the framework's central claim survives despite the gap, or whether the gap fundamentally undermines the claim.
