# CSE Sign-Flip Diagnostic

**Date:** 2026-05-06
**Question:** Why did `cse_magnitude` flip sign between the bot_log
read (-38.6, suggesting facilitation) and the platform read (+19,
suggesting interference) on `expfactory_stroop`?

## Findings

Two distinct bugs interact to produce the apparent disagreement. The
platform read is honest; the bot_log read was a misleading artifact.

### Bug 1: bot_log over-counts trials by ~3×, biasing CSE toward zero

For one stroop session (`output/stroop_rdoc/2026-05-06_16-01-05`):

- bot_log entries: 340
- platform test trials: 120
- Ratio: 2.83×
- **Consecutive same-condition entries in bot_log: 81.1%**
  (275 of 339 adjacent pairs)
- Same statistic in platform: 47.9% (57 of 119)

The platform's 47.9% matches what we'd expect from a roughly balanced
60/60 randomized sequence. The bot_log's 81.1% reflects that the bot
is detecting the same stimulus on multiple poll cycles and writing a
new bot_log entry each time. Adjacent entries in bot_log are mostly
the *same real trial* counted multiple times.

Effect on CSE: when the "previous" entry is the same trial as the
current entry, the (prev, current) pair contributes (RT_x, RT_x) — same
condition, same RT. The "iI pairs" set becomes dominated by these
zero-difference duplicates plus a small number of genuine
incongruent-after-incongruent pairs. The "cI pairs" set is similar.
Computing `mean(iI) - mean(cI)` produces a value driven by sampling
noise on the small genuine-pair counts, with a systematic bias toward
the global mean. On this session bot_log gave −51.5; on a different
session it could equally have given +30. The bot_log CSE estimate is
not a reliable signal of CSE.

### Bug 2: The CSE handler is registered but never called at runtime

`apply_cse` is in `src/experiment_bot/effects/handlers.py:114`, wired
into `EFFECT_REGISTRY["congruency_sequence"]` in
`effects/registry.py:99–110`, and unit-tested. But:

- `core/distributions.py:_apply_temporal_effects` iterates
  `_SAMPLER_EFFECT_ORDER`, which is the literal list
  `["autocorrelation", "condition_repetition", "pink_noise",
  "fatigue_drift"]`. **`"congruency_sequence"` is not in this list.**
- The sampler reads each effect's config via
  `getattr(self._effects, name, None)` where `self._effects` is a
  `TemporalEffectsConfig`. **`TemporalEffectsConfig` does not have a
  `congruency_sequence` field.**
- The executor (`core/executor.py`) has post-sampler invocation sites
  for `post_error_slowing` and `post_interrupt_slowing`, but **no
  invocation site for CSE**.

Net: the CSE handler is unreachable at runtime. The bot's actual RTs
do not include any CSE modulation. On the platform, `cse_magnitude`
of +17 to +19 is a noisy estimate of zero (no real effect), which is
the truthful value for this bot's behavior.

The audit's H1 fix (commit `cc72cc5`) generalized the CSE handler to
read condition labels from the TaskCard instead of magic strings,
which is correct in principle, but did not detect that the handler
was never being called. H1 generalized a piece of dead code.

## Implication

The platform-data validation results we generated are honest. The
"CSE sign flip" between bot_log and platform was the platform
correctly reporting "this bot does not exhibit CSE" while the bot_log
estimate was random noise inflated by 3× over-counting.

Two follow-up fixes are warranted, in order of impact on
defensibility:

### Fix A: wire CSE into the sampler

Without this, the bot doesn't produce CSE on any conflict task, and
the `cse_magnitude` validation gate (which is the only paradigm-
specific gating metric for the conflict class) cannot meaningfully
pass or fail.

Required changes:

1. Add a `congruency_sequence: ConfigType = field(...)` to
   `TemporalEffectsConfig` in `core/config.py`. The shape must match
   what `apply_cse` reads (a dict-like with `enabled`,
   `sequence_facilitation_ms`, `sequence_cost_ms`,
   `high_conflict_condition`, `low_conflict_condition`).
2. Add `"congruency_sequence"` to `_SAMPLER_EFFECT_ORDER` in
   `core/distributions.py`.
3. Reconcile the handler's `params: dict` signature with the sampler's
   typed-config call convention (either change `apply_cse` to accept
   a `ConfigType`, or change the sampler to pass a dict for this
   handler).
4. Update tests to exercise the sampler-applied CSE path end-to-end
   (sample many trials, verify iI mean < cI mean for non-zero
   facilitation).

### Fix B: tighten the bot's stimulus-detection granularity

Less critical now that the oracle reads platform data, but the bot's
own log is still informational. The over-counting suggests the
selector matches across multiple poll cycles within one trial. Two
plausible fixes:

- After matching a stimulus and pressing a key, wait until the
  selector no longer matches before resuming polls.
- Add a "trial advance" detection that treats consecutive matches as
  one trial unless the page has visibly transitioned.

This is a separate executor-side concern; doesn't affect data
validity now that the oracle bypasses bot_log.

## Reproducer

```bash
python3 -c '
import json
session = "output/stroop_rdoc/2026-05-06_16-01-05"
bot = json.load(open(f"{session}/bot_log.json"))
platform = json.load(open(f"{session}/experiment_data.json"))
plat_test = [r for r in platform if r.get("trial_id") == "test_trial"]
print(f"bot_log: {len(bot)}, platform test: {len(plat_test)}")
bot_same = sum(1 for i in range(1, len(bot))
               if bot[i]["condition"] == bot[i-1]["condition"])
plat_same = sum(1 for i in range(1, len(plat_test))
                if plat_test[i]["condition"] == plat_test[i-1]["condition"])
print(f"bot consecutive same: {100*bot_same/(len(bot)-1):.1f}%")
print(f"platform consecutive same: {100*plat_same/(len(plat_test)-1):.1f}%")
'
```
