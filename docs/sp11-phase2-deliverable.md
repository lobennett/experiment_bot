# SP11 Phase 2 deliverable — effects library audit + gap-fill

**Date:** 2026-05-18
**Branch:** `sp11/playwright-recommit`
**Commits:** `03e325e` (pink_noise α), `ac9ec50` (condition_repetition deprecation), `be4c89a` (practice_effect + vigilance_decrement), `aa798d4` (Gratton 2×2 tests)
**Phase status:** complete, awaiting approval to start Phase 3

## What landed

Phase 2 was scoped as verification + gap-fill (sp9c-baseline already has
`EFFECT_REGISTRY`). Per the spec §4 Phase 2, sp11's effects library now
holds **seven** distinct mechanisms, not six — `vigilance_decrement` is
kept separate from `fatigue_drift` per the design decision in the spec.

### Mechanism inventory after Phase 2

| Mechanism | sp9c baseline | SP11 disposition |
|---|---|---|
| `autocorrelation` | present, AR(1) phi | unchanged |
| `fatigue_drift` | present, linear drift_per_trial_ms | unchanged, kept separate from vigilance_decrement |
| `condition_repetition` | present, single-param facilitation/cost | **deprecated** — handler stays functional, `from_dict` prints loud stderr warning when enabled=True, replacement is `lag1_pair_modulation` |
| `pink_noise` | present, `hurst` parameter (alpha = 2*hurst − 1) | **parameter renamed** to `alpha` (spectrum slope directly); from_dict accepts legacy `hurst` with loud deprecation warning |
| `lag1_pair_modulation` | present, modulation_table-based 2×2 | unchanged; **Gratton 2×2 cell tests added** to lock cell arithmetic before Phase 5 TaskCard regeneration |
| `post_event_slowing` | present, trigger-list based, applied by executor | unchanged |
| `practice_effect` | absent | **added** — exponential block-wise RT reduction approaching asymptote_block |
| `vigilance_decrement` | absent | **added** — zero-mean Gaussian RT noise with linearly-growing SD (RT-variance only; see §"Scope decision" below) |

Total: 7 active mechanisms + 1 deprecated alias.

### Test count

| Stage | pytest count |
|---|---|
| Phase 1 (after Appendix C + URL-label aliases) | 575 collected, 572 passed, 3 skipped |
| Phase 2.1 (pink_noise α) | 579 |
| Phase 2.2 (condition_repetition deprecation) | 582 |
| Phase 2.3 + 2.4 (practice + vigilance) | 598 |
| Phase 2.5 (Gratton 2×2 tests) | **609 passed, 3 skipped** |

Net Phase 2 addition: **+34 tests**, all passing. The 3 skips are
unchanged from Phase 1 (env-gated: `RUN_LIVE_LLM=1`, internal Stage-6
refactor verification, multi-source norms_extractor input bundle).

## User-note resolutions

**Note 1 — condition_repetition loud-during-window discipline.** Done:
`ConditionRepetitionConfig.from_dict` prints `DEPRECATION (SP11
Phase 2): ...` to stderr whenever `enabled=True`. The warning names
`lag1_pair_modulation` as the replacement and "Phase 5" as the
deadline. Test
`test_condition_repetition_enabled_prints_loud_deprecation` confirms
the message format. The warning will fire on every load of the
current sp9c-era dev paradigm TaskCards (which all still emit
condition_repetition) until Phase 5 regeneration replaces them with
lag1_pair_modulation. That's the intent — the noise during the window
is the signal that there's work to do.

**Note 2 — practice_effect block-counter session-restart semantics.**
SP11 runs single-shot sessions; the block counter is derived from
`sampler._trial_index`, which restarts at 0 each time a
`ResponseSampler` is constructed. There's no cross-session-restart
state to preserve. The invariant is covered by
`test_practice_effect_block_counter_resets_on_new_sampler` — a new
`ResponseSampler` instance has its own counter starting at 0 even
when re-built with identical config.

**Note 3 — vigilance_decrement interface extension.** Not required.
The mechanism is implemented as an additive zero-mean Gaussian
handler fitting the existing `handler(state, cfg, rng) → float`
contract. SD grows linearly with `trial_index`; mean RT is
unchanged; variance grows. The handler interface stays additive,
no per-trial-variance multiplier or omission-flag return channel
added. **Scope decision (recorded for Phase 8 reconciliation):**
SP11 Phase 2 implements only the RT-variance aspect of
vigilance_decrement. The omission-rate aspect (lapses growing
across the session) is a separate executor-side mechanism that
would need to modify the accuracy gate. Deferred to a future SP;
not in SP11 scope, not in §6 pre-registration.

**Note 4 — Live-LLM-gated test.** Will run during Phase 5 TaskCard
regeneration. Phase 2 didn't invoke the LLM at all (library work
only); deferring the live-LLM test to Phase 5 is the right
coupling. Tracking item for Phase 5 deliverable: confirm the
`RUN_LIVE_LLM=1` test ran cleanly during Phase 5 LLM calls — if
upstream API drift caused it to fail, surface in the Phase 5
write-up.

## Pink-noise α convention details

**Before:** `PinkNoiseConfig.hurst`, generator interpreted via
`alpha = 2*hurst − 1` (fBm convention). hurst=1 → alpha=1 (pink),
hurst=0.5 → alpha=0 (white). Non-obvious.

**After:** `PinkNoiseConfig.alpha`, generator uses alpha directly.
alpha=0 (white), alpha=1 (pink), alpha=2 (Brownian). The
`_generate_pink_noise` function signature is now
`(n, alpha, rng)` and the docstring states the spectrum-slope
calibration explicitly.

**Compatibility:** TaskCards still emitting the legacy `hurst` field
(any pre-Phase-5 dev paradigm card) are accepted via from_dict
which converts using the pre-SP11 fBm formula and prints a loud
deprecation warning. **The warning never fires on the four SP11 dev
paradigms after Phase 5 TaskCard regeneration**; if it does, the
regenerated card needs a re-emission.

**Spectrum verification:** `test_pink_noise_spectrum_slope_matches_alpha_one`
synthesizes a long alpha=1 buffer, fits a log-log slope to the body
of the power spectrum, asserts slope ∈ (-1.25, -0.75). Test for
alpha=2 (slope ∈ (-2.3, -1.7)) also lands. The spectrum machinery is
behaving as designed; the SP11 wiring is just a parameter rename.

## practice_effect implementation notes

**Mathematical form:** RT delta at trial N is

```
block_idx = N // trials_per_block
if block_idx >= asymptote_block: return 0
else: return initial_offset_ms * exp(-decay_rate * block_idx)
```

**Defaults** (overridable per task in TaskCard config):
- `asymptote_block = 3` — humans plateau by ~30-90 trials in
  speeded paradigms (about 3 blocks of 30)
- `trials_per_block = 30` — matches typical practice-block length
  in RDoC paradigms
- `decay_rate = 0.7` — gives ~half offset at block 1, ~quarter at
  block 2, zero at block 3

**Literature anchor:** Logan (1988), Smith & Mewhort (1998), Ratcliff
& Tuerlinckx (2002) all report ~30-60ms reduction across the first
~30 trials of speeded paradigms. The Reasoner emits paradigm-
specific `initial_offset_ms` magnitudes from the literature.

## vigilance_decrement implementation notes

**Mathematical form:** RT delta at trial N is

```
sd_at_N = sd_per_100_trials_ms * (N / 100)
return rng.normal(0, sd_at_N)
```

Mean preserved (zero-mean Gaussian), SD grows linearly. End-to-end
test verifies that for `sd_per_100_trials_ms = 30`, late-session RT
SD exceeds early-session RT SD by ≥ 1.5×.

**Literature anchor:** Mackworth (1948), See et al. (1995), Robertson
et al. (1997). The exact magnitude is paradigm-dependent (sustained-
attention paradigms ~15ms per 100 trials; n-back/Stroop typically
smaller, ~5-10ms per 100 trials). The Reasoner emits paradigm-
specific magnitudes.

## What did not change

- Handler interface: still `handler(state, cfg, rng) → float`. No
  extension required.
- `SamplerState`: unchanged. block_index is derived inside
  `apply_practice_effect`; trial_index drives `apply_vigilance_decrement`.
- The sampler's `_apply_temporal_effects` loop: practice_effect and
  vigilance_decrement go through the standard path (both read only
  trial_index — no prev_error coupling, so not in
  `_EXECUTOR_APPLIED_EFFECTS`).
- The validation oracle: not touched in Phase 2. Phase 7 results
  will be scored against §6's pre-registered criteria using the
  existing `effects/validation_metrics.py` functions.
- TaskCards: NOT regenerated in Phase 2. Regeneration is Phase 5's
  sub-task (per spec).

## What's now expected to fire during Phase 3 onward

Loading any of the four dev paradigm TaskCards will print:
1. `DEPRECATION (SP11 Phase 2): temporal_effects.condition_repetition is deprecated...` — once per session, every session, until Phase 5.
2. Possibly `DEPRECATION (SP11 Phase 2): PinkNoiseConfig.hurst is renamed...` — if any TaskCard's pink_noise still uses the `hurst` field.

Both warnings are the loud-during-window discipline. Their absence
after Phase 5 confirms the regenerated TaskCards have switched to
the new conventions.

## Ready for Phase 3?

- Effects library covers all 7 mechanisms with passing per-mechanism
  invariant tests.
- Spec freeze still holds: no edits to §6 pre-registered criteria
  or Appendix C. Phase 2 only added new mechanisms; §6.2 S7 PES
  range stays the §6 target.
- Test count pinned: 609 passed, 3 skipped.
- All changes committed on `sp11/playwright-recommit`; branch
  pushed to origin.

**Awaiting approval to start Phase 3 (calibration pass).**
