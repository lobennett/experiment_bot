# SP10 — Proposed CLAUDE.md edits

This document is the proposed diff to `CLAUDE.md`, to land as the first commit on the SP10 branch (before any driver code). The user reviews + approves before the commit.

## Rationale

The user noted during the SP9c brainstorm: "Refine CLAUDE.md based on your new knowledge of my demands. It may have been unclear and misguiding you." Specific gaps in the current CLAUDE.md that misled the SP9a/SP9c work:

- **No explicit adversarial / red-team framing.** The current "What this project is" reads as a cognitive-science research framework. The user's framing — "the bot poses a critical risk to online behavioral data collection on platforms like mTurk or Prolific" — is the actual purpose, with cognitive-control research as the application domain.
- **Ambiguity about runtime intelligence in the bot.** G2 says "the Reasoner does the thinking, the bot does the mechanics." SP9a built a runtime LLM that made a session-time mapping decision — which is "thinking." The user later confirmed runtime intelligence IS welcome when it stays localized in driver-internal decisions. CLAUDE.md should make this distinction explicit.
- **Bot_log not flagged as diagnostic-only.** G4 says "the oracle reads the platform's own data export, not the bot's polling log" — but several SP-level audit scripts (SP7's keypress audit, SP9c diagnostic) consumed bot_log. The user wants this explicit: bot_log is diagnostic; platform export is canonical.
- **No guidance on adding platform support.** Each prior SP has added paradigm-specific code in the wrong places (executor, Stage 1 prompt). The driver architecture introduces an explicit extension point; CLAUDE.md should describe it.

## Proposed diff

### Section: "What this project is" — REPLACE

**Current:**
```
A general-purpose Task Turing Bot that completes web-based cognitive
experiments with human-like behavior. Three layers:

1. **Reasoner** — reads source code + literature, emits a versioned
   `TaskCard` (JSON) with stimulus/response rules, navigation, behavioral
   parameters, and citations.
2. **Executor** — drives the live URL via Playwright using the TaskCard,
   sampling RTs and producing platform-native data + a bot log.
3. **Oracle** — scores the resulting sessions against canonical
   meta-analytic norms.

The user's role is cognitive-control researcher, with a current dataset
share-out goal for four development paradigms (two Stroop, two
stop-signal).
```

**Proposed:**
```
An adversarial-research tool that demonstrates the risk bots pose to
online behavioral-data platforms (Prolific, mTurk, custom university
deployments). The bot autonomously completes web-based cognitive
experiments with data indistinguishable from a human participant's
output at both the per-trial and aggregate levels.

The threat model: if a researcher recruits N participants on a
crowdsourcing platform and pays them to complete a cognitive task, can
the platform reliably distinguish bot data from human data? This
project's empirical claim is "no, not without dedicated bot-detection
infrastructure" — supported by per-trial-faithful response delivery and
literature-calibrated behavioral dynamics.

Four layers:

1. **Reasoner** — reads task source code + literature, emits a versioned
   `TaskCard` (JSON) with paradigm metadata, condition labels,
   literature-derived behavioral parameters (RT distributions, effect
   magnitudes, accuracy targets), and a recommended platform driver.
2. **Platform driver** — per-platform code (one driver per supported
   platform: jsPsych, cognition.run, PsychoJS, ...) that owns ALL
   page-touching concerns: identification, phase recognition, stimulus
   detection, navigation, response delivery, data export retrieval.
   Each driver hooks the platform's own response handler so the bot's
   responses are recorded with high fidelity.
3. **Executor (bot library)** — slim, paradigm-agnostic. Trial-loop
   coordination, RT sampling, effect application, accuracy logic.
   Drives the driver, not the page.
4. **Oracle** — scores the resulting sessions against canonical
   meta-analytic norms. Reads platform data export; never `bot_log.json`.

The cognitive-control research domain is the application — the bot
generates data with realistic temporal dynamics (PES, Gratton effect /
CSE, SSRT, etc.) so the adversarial claim is grounded in scientifically
defensible behavior.
```

### Section: "Core Goals" — REPLACE existing G1, G2; ADD G0; keep G3/G4/G5 with edits

**Current G1, G2:**
```
### G1. Generalizability beyond the dev paradigms

The bot's code must NOT bake in paradigm-specific knowledge.
"Generalizable" means: pointing the bot at a novel paradigm's URL
(e.g., n-back, Flanker, random-dot motion, Wisconsin Card Sorting)
should work *without code changes* to the bot's library.

### G2. The Reasoner does the thinking; the bot does the mechanics

The bot's library is a small set of *generic mechanisms*
(autocorrelation, linear drift, lag-1 pair modulation, post-event
slowing, etc.). The Reasoner translates the literature for each task
into mechanism *configurations* in the TaskCard. The bot's code does
not name CSE, post-error slowing, post-inhibition slowing, or any
paradigm-specific phenomenon.
```

**Proposed:**
```
### G0. Per-trial fidelity to the platform's data export

The bot's response on each trial must be recorded faithfully in the
platform's own data export — not just delivered to the page. SP9c's
finding that synthetic keystrokes reach the page document but not
jsPsych's listener (~50% loss in platform recording) is the kind of
failure G0 forbids. The current measurable target: `bot's pressed key
== platform's recorded response` ≥ 90% on every paradigm. Aggregate
fidelity (RT distributions within published norms) is necessary but
not sufficient — sequential metrics (PES, CSE, SSRT trajectory)
require per-trial fidelity.

### G1. Generalizability beyond the dev paradigms

The bot's LIBRARY must NOT bake in paradigm-specific knowledge.
Pointing the bot at a novel paradigm's URL should work without code
changes to the bot library or executor. **Platform-specific knowledge
lives in platform drivers** — a new platform (e.g., PsychoPy) is
supported by adding a new driver module, not by modifying the
executor or the Reasoner pipeline.

Held-out paradigms verify generalization empirically. A held-out
paradigm running on a supported platform should "just work" once the
Reasoner produces its TaskCard (no executor edits, no driver edits).

### G2. The Reasoner does literature thinking; the bot library does
generic mechanics; the driver does platform mechanics

The Reasoner is responsible for translating literature into mechanism
configurations: which generic effects apply, with what magnitudes,
under what conditions. The Reasoner does NOT extract platform-specific
JS (response_key_js, stimulus detectors, navigation phases) — that
work moves to the driver.

The bot library is a small set of *generic mechanisms*
(autocorrelation, linear drift, lag-1 pair modulation, post-event
slowing). The bot library does NOT name paradigm-specific phenomena
(CSE, post-error slowing, post-inhibition slowing) — those are
mechanism configurations from the Reasoner. The bot library does NOT
read platform-specific runtime state — that's the driver's job.

The driver owns platform-specific runtime decisions: which key does
this trial want, what is the current jsPsych plugin type, when does a
trial end, how does the platform export its data. Runtime LLM
intelligence is permitted in drivers when it improves robustness, but
the bot library and Reasoner stages stay LLM-free at runtime (LLM is
used only at Reasoner-build time and at driver-development time).

In short: Reasoner = literature thinking. Bot library = generic
mechanics. Driver = platform mechanics.
```

### Section: "G4. Scientific defensibility" — APPEND new operational rule

**Append after the existing G4 bullet list:**
```
- **bot_log.json is diagnostic-only.** Per-trial logs the bot writes
  reflect its own polling-loop view, which can drift from the
  platform's actual trial count and response recording. ANY analysis
  script that reads `bot_log.json` for behavioral metrics is suspect
  and must be flagged for review. The platform's data export
  (retrieved via `driver.retrieve_data`) is the only analysis input.
```

### Section: "Specific guardrails for code changes" — ADD new subsection

**Add a new subsection at the end of the existing list:**
```
### When adding platform support

The bot supports a platform via a `PlatformDriver` subclass under
`src/experiment_bot/drivers/<platform>/`. Drivers ARE platform-
specific code; G1 generalizability is preserved because the BOT
LIBRARY remains paradigm-agnostic and platform-agnostic.

Driver development conventions:

- **Vendor selective anchor files** under `vendor/<platform>/<version>/`
  for open-source platforms. The driver references the vendored source
  with provenance comments; this audits the exact API the driver
  targets.
- **`can_handle(page)` must be cheap and side-effect-free.** Cheap
  DOM/window inspection only. No LLM. No slow JS evaluation.
- **Drivers fail loudly to DiagnosticDriver when they encounter an
  unanchored platform version.** Don't guess at unsupported versions.
- **Driver-internal LLM use is permitted but rare.** A driver may
  call out to Claude for a runtime decision it can't resolve
  deterministically (e.g., classify an unfamiliar feedback screen),
  but the bot library and Reasoner pipeline don't reach the LLM at
  runtime.
- **Closed-source platforms can't be vendored.** Drivers for closed
  platforms (e.g., cognition.run) live in `drivers/<platform>/` with
  empty `vendor/<platform>/`. Document the scope-of-validity caveat
  explicitly in the reviewer-1 charter.
```

### Section: "When updating tests" — APPEND

**Append to the existing list of negative-assertion examples:**
```
A driver's test suite verifies platform-specific behavior on that
platform; bot-library tests must not depend on a specific platform.
Negative assertion to maintain:
```python
# Bot library should never name a platform
from experiment_bot.core import executor
assert "jspsych" not in executor.__file__.lower()  # not a real test
# Conceptual: the EXECUTOR module's code reads cleanly without any
# jsPsych / cognition.run / PsychoPy references.
```
```

### Section: "Operational rules" — APPEND

**Append after the existing rules:**
```
- Add a new platform by writing a driver, not by editing the bot
  library or Stage 1 prompt. Stage 1's job is to identify the
  platform and recommend a driver, not to encode the platform's
  internals.
- Never read `bot_log.json` for behavioral metrics. If you need
  trial-level data for analysis, use `driver.retrieve_data` output.
```

### Section: "Sub-project history" — APPEND SP10 placeholder

**Append after the SP9b entry (or wherever appropriate in the current chronology):**
```
- **SP10** (in progress): Driver-based platform architecture. New
  `experiment_bot/drivers/` package — per-platform `PlatformDriver`
  subclasses own all page-touching concerns; bot library becomes
  slim, paradigm- AND platform-agnostic. JsPsychDriver is the first
  driver, hooks `pluginAPI.getKeyboardResponse` for response delivery
  (closes the SP9c layer-d gap structurally). Reasoner pipeline
  shrinks: Stage 1 drops brittle JS extraction; new `recommended_driver`
  field. CLAUDE.md updated with G0 (per-trial fidelity), G2 expanded
  (driver as third tier), G4 strengthened (bot_log diagnostic-only),
  new guardrails for adding platform support. Expected to close
  pressed==recorded gap on all 4 dev paradigms (target ≥ 90%).
  See `docs/sp10-results.md` for empirical outcome.
```

(To be replaced with a final entry at SP10-complete time describing what actually shipped.)

## What's NOT changing

- **G3 (No effects on tasks that don't have them):** unchanged. The effect-library guardrail is correct as written.
- **G5 (Iteration discipline):** unchanged.
- **"Documents to read before starting":** unchanged.
- **Most "Specific guardrails for code changes" subsections:** unchanged — the existing guidance on effect library, prompts, validation oracle, tests stays correct.
- **"Style preferences":** unchanged.

## Estimated impact on misdirection

Re-reading the proposed CLAUDE.md against the SP9a misjudgment I made: would the new text have caught it?

SP9a built `SessionAgent.resolve_key_mapping` — a runtime LLM call in the executor. Under the proposed G2 ("The driver does platform mechanics... Runtime LLM intelligence is permitted in drivers... but the bot library and Reasoner stages stay LLM-free at runtime"), the SP9a SessionAgent would have been flagged as misplaced — it should have been built INSIDE a driver (which didn't exist), not in the executor. The proposed CLAUDE.md would have caught the architectural error before implementation.

Re-reading against the SP9c misjudgment (hardcoded `#jspsych-display-element`): under proposed G1 ("Platform-specific knowledge lives in platform drivers"), the hardcoded selector would be flagged for review — selectors that platform-specific belong in `drivers/jspsych/`, not in `core/executor.py`. The proposed CLAUDE.md would have caught this too.

## Open question for user

Should G0 be elevated above G1 (making it the highest-priority goal), or stay roughly co-equal? Arguments either way:

- **G0 above G1:** per-trial fidelity is the adversarial-research claim's foundation. Generalizability without fidelity is academic.
- **G0 co-equal:** if the bot only works on jsPsych at high fidelity but breaks on PsychoPy, that's a generalizability failure that matters too. G0 and G1 are jointly required.

Default proposal: G0 above G1 in priority order, since the user explicitly framed per-trial fidelity as the central concern. Open to flipping if the user prefers otherwise.
