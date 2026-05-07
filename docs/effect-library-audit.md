# Effect Library Audit

**Date:** 2026-05-06
**Question:** Is the implementation of `EFFECT_REGISTRY` and the
sampler's effect-iteration loop truly generalizable, or have I baked
paradigm-specific concepts (like "congruency sequence effect") into
the bot's core vocabulary?

**Verdict: it's still partially baked-in.** The infrastructure for
adding/removing effects is now generic (open registry, dict-keyed
configs, paradigm-class filtering), but the **set of effects that
ships in the registry today still includes paradigm-shaped names and
paradigm-shaped logic**. The bot's standard library knows about CSE
specifically.

## What is actually generic

- `TemporalEffectsConfig` is open-ended (audit fix).
- `register_effect()` lets a new effect be added without editing the
  config dataclass (audit fix).
- The sampler iterates the registry filtered by paradigm class, so
  effects only apply to applicable paradigms (audit fix).
- The 5 universal effects — autocorrelation (AR(1) on RT),
  fatigue_drift (linear monotone), pink_noise (1/f), PES (post-error
  uniform-random slowing), condition_repetition (Gratton-style same-
  condition facilitation) — describe **mechanisms** that any speeded
  task could exhibit. Their parameter values are Reasoner-derived. ✅

## What is still paradigm-baked

### B1. `congruency_sequence` exists as a first-class effect name

`effects/registry.py:159` registers `EFFECT_REGISTRY["congruency_sequence"]`
with `applicable_paradigms=frozenset({"conflict"})`. The bot's
standard library has a CSE concept, even though paradigm-class
filtering keeps it from running on non-conflict tasks. Reviewers can
correctly say: "your bot's code knows about CSE specifically. Does it
know about Wisconsin Card Sorting's perseveration error pattern?
About Sternberg's set-size slope? About task-switching's mixing cost?
What about whatever paradigm I throw at it next month?"

The honest answer today is: it knows about CSE because we wrote it in.
It knows about whatever else I and the literature have pre-loaded.
That's the overfitting concern in concrete form.

### B2. `apply_cse` is paradigm-shaped logic, not a generic mechanism

`effects/handlers.py:174`. The handler reads `high_conflict_condition`
and `low_conflict_condition` from cfg. The CONCEPT of "high-conflict
vs low-conflict" is conflict-paradigm vocabulary. A more generic
mechanism would be: "lag-1 trial-pair interaction effect" — a 2D
modulation table indexed by (prev_condition, current_condition) →
RT delta. CSE is one paradigm-specific configuration of that mechanism.

### B3. `post_interrupt_slowing` is similarly paradigm-shaped

Specific to interrupt/stop-signal paradigms. The mechanism is "RT
slowing after a particular kind of preceding event". A generic
post-event-slowing handler would subsume both PES and post-interrupt
slowing under one mechanism, with the "what counts as the triggering
event" being a per-task config.

### B4. `cse_magnitude` validation metric is paradigm-named

`effects/validation_metrics.py:14`. It computes
`mean(high-after-high) - mean(high-after-low)` — a generic 2-back
interaction quantity, but the name and conventional sign are
conflict-paradigm specific. A novel paradigm class with a similar
2-back interaction (e.g. some priming paradigm with target/non-target
labels) would compute the same quantity but want it called something
different.

## What this implies architecturally

**Two levels of generalization are possible:**

### Level 1 — rename + parameterize, don't introduce new mechanisms

Replace the paradigm-named effects with generic-mechanism names. The
bot's library becomes:

| Generic name | Mechanism | Subsumes |
|---|---|---|
| `lag1_pair_modulation` | RT delta indexed by (prev_condition, current_condition) | CSE, Gratton, sequential priming, condition_repetition |
| `post_event_slowing` | RT slowing after triggering event N back | PES (event=error), post_interrupt_slowing (event=interrupt) |
| `linear_drift` | RT drift = trial_index × per_trial_ms | fatigue_drift |
| `ar1_carryover` | RT pulled toward prev_RT × phi | autocorrelation |
| `fractional_noise` | 1/f noise indexed by trial number | pink_noise |

The Reasoner picks generic mechanisms by name, configures them with
paradigm-specific parameters from the literature scrape. The bot's
code never says "congruency sequence" — only "lag-1 pair modulation
configured as facilitation on incongruent-after-incongruent for this
particular conflict task."

CSE becomes a *configuration*, not a built-in.

This is mostly a renaming + re-parameterization exercise. The math
of each mechanism is the same.

### Level 2 — declarative effects in the TaskCard

The Reasoner emits a small DSL or expression per effect (e.g. a JS
expression evaluated on per-trial state). The bot evaluates the
expression generically. New effects don't need new handler code at
all.

This is a much larger refactor and introduces a sandboxing /
expression-evaluator complexity. Probably not the right scope for
the current data-sharing milestone.

## Recommendation

**Do Level 1 now.** It removes the user-visible paradigm names from
the bot's library and forces all new paradigms to express themselves
through generic mechanisms. The five generic mechanisms above cover
all seven currently-registered effects without losing expressive
power. Concrete steps:

1. Replace `apply_cse` with `apply_lag1_pair_modulation`. Cfg has a
   `modulation_table: dict[tuple[str, str], float]` mapping
   (prev, curr) condition pairs to RT-delta in ms. Per-cell
   modulation is sampled or fixed depending on cfg.
2. Replace `apply_post_error_slowing` and `apply_post_interrupt_slowing`
   with one `apply_post_event_slowing`. Cfg specifies the event
   trigger predicate (string keys `"error"`, `"interrupt"`, or any
   future event the executor records on `SamplerState`).
3. Rename remaining handlers to mechanism names: `linear_drift`,
   `ar1_carryover`, `fractional_noise`. (autocorrelation and
   pink_noise are mechanism-named already; just rename for
   consistency.)
4. Drop `applicable_paradigms` from registered effects entirely.
   Effects are universal-mechanism; whether they apply to a task is
   determined by whether the TaskCard configures them. A task with
   no `lag1_pair_modulation.modulation_table` simply gets no
   modulation. No paradigm-class filter needed because no effect is
   paradigm-shaped anymore.
5. Rename `cse_magnitude` validation metric to a generic
   `lag1_pair_contrast` that takes the (high, low) labels from the
   norms file. The norms file's metric name still uses "cse_magnitude"
   for the conflict class; the metric implementation is generic.

After this:
- The bot's code does not know about congruency sequence specifically.
- The Reasoner declares per-task that "this paradigm uses
  `lag1_pair_modulation` with modulation table {(incongruent,
  incongruent): -50, (congruent, incongruent): +20}".
- A novel paradigm with a different 2-back pattern uses the same
  mechanism with a different table.
- A paradigm with no 2-back pattern doesn't enable
  `lag1_pair_modulation` and gets no modulation.

The bot's library becomes a small set of universal mechanisms. The
TaskCard becomes the per-task configuration that translates literature
into mechanism parameters. This is closer to the user's "perfect
world" of pointing-Claude-at-a-URL: the bot's vocabulary stays
constant; only the TaskCard varies per task.

## Cost

- Test refactor: existing CSE tests, PES tests, etc. need renaming
  but the assertions stay similar (just different effect names).
- Reasoner Stage 2 prompt: the effect catalog injected into Stage 2
  needs renaming to the generic mechanism names. The Reasoner's job
  is now to translate literature into generic-mechanism configs
  rather than picking from a paradigm-named menu.
- Existing TaskCards still reference `congruency_sequence`. They'd
  need either regen or a name-aliasing shim. The shim is cheap if we
  want backward-compat; otherwise regen the four dev TaskCards.

## What this does NOT change

- Validation oracle's metric registry (already data-driven from
  norms files).
- Pilot integration.
- Held-out paradigm handling.
- The 4-paradigm dataset already collected.

It's a focused rename-and-parameterize that surfaces the right
conceptual abstraction.
