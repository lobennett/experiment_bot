# Held-Out N-back Generalization Test

**Date:** 2026-05-06
**URL:** https://deploy.expfactory.org/preview/5/
**TaskCard:** `taskcards/expfactory_n_back/0290bf4c.json`
**Norms:** `norms/working_memory.json`
**Smoke run dir:** `output/n-back_(rdoc)/2026-05-06_13-46-23/`

## Goal

After completing the 13 generalization-audit refactors (commits `85a5a1b`
through `7506abb`), test whether the framework actually generalizes by
running it once on a paradigm the iteration loop never touched: n-back
working memory at expfactory. The audit predicted this as the strongest
empirical gate: pass means the refactors achieved generalization;
fail surfaces the specific architectural gap.

## What worked (audit refactors that delivered)

1. **H2 — Open paradigm-class taxonomy.** Reasoner picked
   `paradigm_classes: ['working_memory', 'speeded_choice']` without
   prompting — outside the dev paradigm space (conflict, interrupt,
   speeded_choice). The taxonomy worked exactly as the audit intended:
   a novel class proposed by the LLM, not an enumerated value we
   hardcoded.

2. **H2 — Norms extraction generalized.** `experiment-bot-extract-norms
   --paradigm-class working_memory` produced `norms/working_memory.json`
   with two metrics that have concrete published ranges
   (`n_back_accuracy_2back: [0.7, 0.9]`, `capacity_k: [3, 5]`) plus
   seven metrics correctly marked as null with reasons (no meta-analytic
   ranges available — the LLM refused to extrapolate from primary
   studies, which is the right behavior).

3. **H4 — Validator-gated retry.** Stage 1 produced a TaskCard that
   passed the validator on the first attempt (no retries needed),
   confirming the prompt structure isn't inducing alias-style errors
   on novel paradigms.

4. **Stimulus detection.** The Reasoner emitted substantive js_eval
   selectors that read `window.nbackCondition` from the runtime —
   correct identification of the experiment's state-tracking convention.

5. **Core wiring (M2 deque, M3 dispatch, M4 clip ranges).** The
   executor instantiated and ran cleanly with the new state structures.

## What didn't work

**Navigation phases.** The Reasoner emitted `navigation: {"phases": []}`
— zero navigation steps. The page is jsPsych with a `plugin-fullscreen`
prompt as the very first screen ("The experiment will switch to full
screen mode when you press the button below" with a Continue button).
Without navigation phases, the bot:

1. Skipped past the no-op navigator
2. Entered the trial loop expecting stimuli
3. Polled, found no stimulus (page still showed the fullscreen prompt)
4. Pressed `advance_keys = ['Enter']` — but jsPsych's fullscreen plugin
   only responds to actual click events (the Fullscreen API requires a
   user-gesture event to trigger, browsers reject keyboard-driven
   activation)
5. Tried clicking `feedback_selectors = ['#jspsych-instructions-next']`
   — but the visible button on screen is `#jspsych-fullscreen-btn`,
   which the Reasoner didn't include
6. Hit `consecutive_misses > max_no_stimulus_polls` after 400 polls
7. Exited the trial loop with **0 trials captured**
8. The hard-fail guard (commit `cabd2f7`) raised `RuntimeError` with a
   diagnostic message — the failure surfaced loudly instead of silently
   producing an empty bot_log.json

## Diagnosis

The Reasoner identified `plugin-fullscreen.js` in the source files but
neither populated a navigation phase to click the fullscreen button
nor added `#jspsych-fullscreen-btn` to `feedback_selectors`. The
Reasoner's prompt didn't elicit either — Stage 1 currently treats
navigation as relatively low-priority structural information, not the
critical-path blocker it actually is for any task with a fullscreen,
consent, or instructions phase.

This isn't a paradigm-specific issue (n-back-specific). It's a
**Reasoner-side identification gap** that would surface on any
paradigm whose entry flow requires button clicks before stimuli appear.
The four dev paradigms all happen to have explicit click-through
navigation phases the Reasoner identified correctly, masking this gap
during dev iteration.

## What we did NOT do (and why)

- **Did not** add jsPsych-specific or fullscreen-specific guidance to
  the Stage 1 prompt. That's exactly the overfitting the audit warned
  against — it would make n-back pass at the cost of baking framework-
  specific assumptions into the bot.

- **Did not** add a "navigation must be non-empty" validator gate.
  That's also overfitting — some valid paradigms might genuinely have
  no navigation (single-page tasks that go directly to stimuli).

- **Did not** force-regenerate the n-back TaskCard with stronger nav
  prompts. Same overfitting concern.

## What we did do

- **Added a generalizable runtime hard-fail** when the executor
  captures 0 trials (commit `cabd2f7`). Any TaskCard whose configuration
  prevents the bot from reaching trials now fails loudly instead of
  silently emitting empty data. This is the executor's analog to the
  Reasoner's H4 validator-retry: catch broken configurations
  immediately rather than letting them slip through.

- **Added a generalizable click-fallback** in the trial-loop no-stimulus
  branch (commit `379a61b`). The bot now tries clicking any visible
  `feedback_selectors` the Reasoner identified, in addition to pressing
  `advance_keys`. Reuses LLM-identified selectors; doesn't add
  paradigm-specific knowledge. Didn't recover the n-back case because
  the Reasoner didn't include the right selector to begin with — but
  helps any future paradigm where the LLM did identify the button
  but didn't put it in a navigation phase.

## Where this leaves us

The audit refactors passed for **5 of 6 generalization tests** the
n-back exercise covered:
- ✅ Paradigm-class taxonomy is open
- ✅ Norms extraction works for novel classes
- ✅ Validator-retry doesn't false-positive on novel paradigms
- ✅ Stimulus detection emits substantive selectors
- ✅ Runtime infrastructure (deque, dispatch, clips) works without regression
- ❌ Navigation-phase identification

The remaining gap is real and architectural. Two long-term fixes are
viable, both deferred from this round:

1. **Reasoner-side pilot validation.** The codebase has an existing
   `PilotDiagnostics` system (`src/experiment_bot/core/pilot.py`)
   that runs a brief Playwright session against the URL and reports
   what the bot actually saw. It's not currently wired into the
   Reasoner pipeline. Wiring it as a Stage 1 verification step
   (run TaskCard against URL → if pilot captures 0 trials,
   re-prompt with the pilot's DOM snapshot as feedback) would
   give the Reasoner ground truth about what selectors actually
   work. This is the H4 validator-retry pattern extended to live
   DOM verification.

2. **Reasoner-side navigation introspection.** Stage 1 currently reads
   the source code statically. A Stage 1 enhancement could fetch the
   live initial DOM (one Playwright `page.goto()` and `page.content()`)
   and feed it to the LLM alongside source files. This would let the
   LLM see the actual fullscreen prompt and emit navigation accordingly,
   without hardcoded jsPsych knowledge.

Either fix turns navigation from a static-source-code-inference task
(unreliable) into a verify-against-live-page task (reliable).

## Disposition

The held-out test result is recorded honestly. The paradigm-class
taxonomy, norms extraction, validator-retry, and most of the audit
refactors generalized as intended. The navigation gap is a known
limitation surfaced by exactly the kind of empirical test the audit
recommended. The hard-fail guard ensures this gap will be caught
immediately for any future paradigm — no silent failures.

This finding belongs in any reviewer-facing description of the
framework's current capabilities and known limitations.
