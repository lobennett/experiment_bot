# Generalization Audit

**Date:** 2026-05-06
**Scope:** Identify every place in the codebase where paradigm-specific or
cognitive-control-shaped assumptions live, vs. universal mechanisms that
generalize to any speeded-decision task. The chief concern: a reviewer asks
*"how do we know this isn't overfit to your team's four dev paradigms?"*
and we have a defensible answer.

The bot has three layers, each of which can leak assumptions:

1. **Reasoner** — reads source + literature, emits a TaskCard. Runs offline.
2. **Executor + Sampler** — reads TaskCard + DOM, generates trial-level behavior.
3. **Oracle** — scores sessions against canonical norms.

A change is "good for generalization" when it moves a decision from layer 2/3
**code** into layer 1 **reasoning**. A change is "bad for generalization" when
the bot relies on a value, label, or shape that we wrote down ourselves.

## Findings

Ranked by generalization risk: **HIGH** = will silently break or warp results
on a paradigm we haven't yet built; **MEDIUM** = constrains expressiveness but
won't hide failure; **LOW** = limited scope or already partially mitigated.

---

### H1. `apply_cse` hardcodes `"incongruent"` / `"congruent"` condition strings

**Location:** `src/experiment_bot/effects/handlers.py:130-135`

```python
if state.condition != "incongruent":
    return 0.0
if state.prev_condition == "incongruent":
    return -float(params.get("sequence_facilitation_ms", 0.0))
if state.prev_condition == "congruent":
    return float(params.get("sequence_cost_ms", 0.0))
```

A conflict task whose Reasoner picks `"compatible" / "incompatible"`,
`"same" / "different"`, or any other label set silently produces zero CSE.
The handler is invisible without those exact strings. Same shape problem in
`effects/validation_metrics.py::cse_magnitude` (lines 28–33).

**Fix:** the TaskCard already names conditions. Promote `congruent_condition`
and `incongruent_condition` into the CSE config (or generalize to "low-conflict"
and "high-conflict" labels chosen by the Reasoner). Handler dispatches on
TaskCard labels, not magic strings.

---

### H2. Closed paradigm-class taxonomy in prompts and norms extractor

**Locations:**
- `src/experiment_bot/prompts/system.md:11-16` — Stage 1 prompt enumerates
  `"conflict"`, `"interrupt"`, `"speeded_choice"` as the universe of classes.
- `src/experiment_bot/reasoner/prompts/norms_extractor.md:31-43` — hardcodes
  `Required metrics for class "conflict"` / `"interrupt"` templates.

A novel paradigm (e.g. n-back working memory, perceptual discrimination,
two-alternative forced choice with confidence) has no defined class. The
Reasoner either fits it into an existing class (lossy) or leaves
`paradigm_classes` empty (Stage 2 silently defaults to `["speeded_choice"]`,
oracle has zero gates).

**Fix:** the taxonomy itself should be Reasoner-derived. The Stage 1 prompt
should describe the *idea* of a paradigm class (high-level grouping that shares
canonical effects + literature) and let the LLM either pick from existing
norms files in `norms/` or propose a new class. The norms extractor should
operate on whatever class name the LLM emits, with the metric set negotiated
from the literature scrape — not hardcoded per-class templates.

---

### H3. Cognitive-control numerical priors quoted directly in Stage 1 prompt

**Location:** `src/experiment_bot/prompts/system.md:162`

> "A value of 0.85 is typical for stop-signal tasks — set this explicitly..."

This is exactly the failure mode the user flagged: we are *telling* the LLM
the answer instead of letting it derive from literature. There may be other
instances; need a full prompt sweep.

**Fix:** replace numerical anchors with a description of what to look for in
the source ("read the task's stop-signal delay or response-window definition;
estimate the failure-RT cap as the fraction of max RT below which most
commission errors fall, citing the paper that defines it"). The literature
scrape supplies the value, not us.

---

### H4. Validator-rigidity drives alias whack-a-mole in `normalize.py`

**Location:** `src/experiment_bot/reasoner/normalize.py` (entirety)

Each time the LLM emits a non-canonical key (`type` for `method`, `expression`
or `value` for `selector`, `detect` for `detection`, `step` for `steps`,
`duration` for `duration_ms`), we hand-add an alias mapping. Today's count: 7
aliases across stimulus + navigation. We can't predict the next one (`query`?
`target`? `expr`?). Each undiscovered alias produces a silently empty field.

**Fix:** validator-gated retry. Stage 1 calls LLM → validates → on failure,
appends the validator error to the prompt and re-calls (max N retries). The
retry loop converges or hard-fails with a clear error. Removes the need for
alias maps for any future paradigm.

---

### M1. Effect taxonomy is a closed set of seven

**Location:** `src/experiment_bot/effects/registry.py`

Six universal + one paradigm-specific (CSE). A novel paradigm whose literature
describes an effect we haven't named (e.g. *response-locked attentional
blink*, *Bayesian belief-update RT modulation*) cannot be represented unless
we add a new handler in Python.

**Fix:** keep handlers in code (they implement math), but make the registry
*extensible from TaskCard*. The Reasoner declares effect mechanisms by
referencing handler names that exist OR by emitting a JS-eval / formula-based
effect that the executor evaluates generically. Treat handlers as a "standard
library" and let TaskCards opt in to ad-hoc effects. Lower-priority than H1–H4
because the existing 7 cover most speeded-task literature.

---

### M2. Effect mechanisms locked to 1-back / linear shapes

**Location:** `src/experiment_bot/effects/handlers.py`

- `apply_post_error_slowing`: only `state.prev_error` checked. Multi-trial
  decay (Notebaert 2009; Danielmeier & Ullsperger 2011) cannot be represented.
- `apply_fatigue_drift`: linear monotone (`trial_index * drift_per_trial_ms`).
  Real fatigue is non-linear with breaks.
- `apply_autocorrelation`: AR(1) only. Higher-order autoregression unavailable.
- `apply_condition_repetition`: 1-back only.

**Fix:** carry a sliding window of recent N trials in `SamplerState` (already
have `prev_*`; extend to `recent_*`). Each handler can express its decay
profile via TaskCard parameters. Risk: more degrees of freedom in the
parameter space. Tradeoff: only do this when literature for a specific
paradigm calls for it; otherwise default decay = 1 trial.

---

### M3. Single distribution family

**Locations:**
- `src/experiment_bot/core/distributions.py:17` — only `ExGaussianSampler`.
- `core/distributions.py:73` — silently skips non-`ex_gaussian` distributions.
- `reasoner/prompts/stage2_behavioral.md:18` — output schema forces
  `"distribution": "ex_gaussian"`.

Most speeded tasks fit ex-Gaussian, but not all (e.g., shifted-Wald for
diffusion-style decisions, log-normal for some perception tasks).

**Fix:** add `LogNormalSampler` and `ShiftedWaldSampler` (~30 lines each). Let
Stage 2 choose. Lower priority — only matters for paradigms outside
go/conflict/interrupt families.

---

### M4. Hardcoded performance bounds

**Location:** `src/experiment_bot/core/distributions.py:196-205`

```python
np.clip(acc_base + rng.normal(0, bsj.accuracy_sd), 0.60, 0.995)
np.clip(om_base + rng.normal(0, bsj.omission_sd), 0.0, 0.04)
```

Accuracy floor of 0.60 assumes "human performance is well above chance" —
fails for perceptual-threshold tasks (~0.50–0.55), psychophysics staircases,
or signal-detection tasks at d′ ~ 0.5. Omission ceiling of 0.04 fails for
slow-paced or dual-task paradigms.

**Fix:** move bounds into TaskCard (Reasoner derives from the source's stated
performance goals + literature). Code uses the TaskCard's bounds.

---

### M5. Closed pillar taxonomy in oracle

**Location:** `src/experiment_bot/validation/oracle.py:116-118`

Three hardcoded pillars: `rt_distribution`, `sequential`,
`individual_differences`. New pillars (e.g. `speed_accuracy_tradeoff`,
`learning_curve`, `confidence_calibration`) require code changes.

**Fix:** norms file declares pillars; oracle iterates whatever pillars the
norms file defines. Each pillar names the metrics it includes. Oracle becomes
data-driven.

---

### M6. Hardcoded sequential metrics in oracle

**Location:** `src/experiment_bot/validation/oracle.py:142-186`

Hardcoded `if "lag1_autocorr" in metrics_def:` / `"post_error_slowing"` /
`"cse_magnitude"` blocks. New metric requires Python change.

**Fix:** register metrics in a small dispatch table (`name → callable`). Norms
file names which metrics to compute, dispatch table looks them up. Adding a
new metric = one entry.

---

### L1. Hardcoded `_SAMPLER_EFFECT_ORDER`

**Location:** `src/experiment_bot/core/distributions.py:111-116`

Effects applied in fixed order. Order matters because `prev_rt` updates after
each effect. Different orders → different distributions.

**Fix:** make the order an explicit, documented choice in TaskCard, OR make
handlers commutative-by-design (apply all to raw_rt then sum, instead of
sequential update). Low priority.

---

### L2. RT floor and 500ms fallback

**Location:** `src/experiment_bot/core/distributions.py:128, 149-155`

`floor_ms = 150.0` (the "fast guess" cutoff) and `rt = 500.0` fallback when
no sampler exists. The 150ms is an empirical convention (Whelan 2008), but
the fallback is magic.

**Fix:** floor → TaskCard (literature-derived). Fallback → assert no missing
samplers (hard fail if a TaskCard references a condition with no
distribution).

---

### L3. Stage 2 system-prompt opening framing

**Location:** `src/experiment_bot/reasoner/prompts/stage2_behavioral.md:1`

> "You are a cognitive psychology expert..."

Probably appropriate. Note for completeness.

---

## Recommended sequence (priority order)

If the goal is "the reviewer cannot say *that's overfit to your four
paradigms*", attack high-leverage items first:

1. **H4** — validator-gated retry. Removes whack-a-mole forever.
   Generalizes to any future paradigm without code change. Smallest patch
   surface (Reasoner-internal). Should ship before any new paradigm tests.

2. **H3** — sweep the prompts for cognitive-control numerical priors. Replace
   each with a derivation rule. ~30 min audit + edits.

3. **H1** — generalize `apply_cse` and `cse_magnitude` to operate on
   TaskCard-named conditions instead of magic strings. The handler still
   represents the *mechanism* (sequential interaction); the *labels* come
   from the Reasoner.

4. **H2** — make paradigm classes Reasoner-emergent rather than enumerated.
   Norms extractor accepts whatever class name + metric list the literature
   scrape produces.

5. **M5/M6** — data-drive the oracle pillars and metrics from the norms file.
   Removes hardcoded pillar/metric lists. Lets norms files define what's
   measured per paradigm class.

6. **M2** — extend `SamplerState` with a sliding window of recent N trials
   when a paradigm's literature requires multi-trial decay (e.g., Notebaert
   PES). Lazy: only do this when a specific paradigm needs it.

7. **M4** — move performance bounds (accuracy floor, omission ceiling) into
   TaskCard.

8. **M1, M3, L1–L3** — opportunistic.

## Generalization gate

After H1–H4 land, the empirical test is:

- **Held-out paradigm.** Pick a paradigm whose dev/iteration loop *never*
  touches the codebase. Recommendation: n-back at expfactory
  (`https://deploy.expfactory.org/preview/5/`). It's a working-memory task
  outside conflict/interrupt — exercises the H2 "new paradigm class" path.
- **First-shot pass.** Run the bot on the held-out paradigm exactly once
  (no iteration on that paradigm's prompt or normalize fixes). Score
  against canonical norms.
- **Pass criteria.** All gateable metrics within published ranges; no
  silent failures (empty trials, zero detection); reasoning chain
  inspectable for paradigm-specific extrapolations we'd want to flag.

A held-out pass is the strongest defense against the overfitting concern.

## What this audit deliberately does NOT recommend

- Removing the effect handlers themselves. Post-error slowing, autocorrelation,
  CSE, etc. are *human cognition we want the bot to mimic*. They need to be
  in code. The fix is making *whether and how much* they apply Reasoner-
  derived, not removing them.
- Removing the paradigm-class concept. It's a useful organizing principle
  for norms files. The fix is making the taxonomy open rather than closed.
- Replacing magic strings with magic tuples. CSE generalization (H1)
  shouldn't replace `"incongruent"` with `("incongruent", "incompatible",
  "high-conflict")` — that just expands the magic. The fix is to read
  labels from the TaskCard the Reasoner produced.
