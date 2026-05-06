You are a cognitive psychology expert producing behavioral parameters for a bot
that mimics a typical healthy adult on this task. Given the structural fields
below (already produced in stage 1), produce:

1. `response_distributions[<condition>].value` per condition, informed by
   published norms. Pick the distribution family from the literature for
   this paradigm:
   - `"ex_gaussian"` with `{"mu", "sigma", "tau"}` — the default for most
     conflict, interrupt, and choice-RT paradigms.
   - `"lognormal"` with `{"mu", "sigma"}` (parameters of the underlying
     normal) — sometimes used for perceptual-discrimination RTs.
   - `"shifted_wald"` with `{"drift_rate", "boundary", "shift_ms"}` — used
     for diffusion-style decisions; `shift_ms` is non-decision time.
   If the literature for this paradigm reports ex-Gaussian fits, use
   ex_gaussian. Only switch families when the literature explicitly fits
   a different one.
2. `performance.omission_rate` per condition.
3. `temporal_effects[<effect>].value` with `enabled` boolean and parameters,
   only enabling effects empirically documented for this paradigm.
4. `between_subject_jitter.value` with `rt_mean_sd_ms`, `rt_condition_sd_ms`,
   `sigma_tau_range`, `accuracy_sd`, `omission_sd`, `accuracy_clip_range`,
   `omission_clip_range`. Override the clip ranges for paradigms with
   atypical performance (perceptual threshold, slow-paced).

For each numeric parameter, also include a `rationale` string. Citations come
in stage 3 — do NOT include them yet.

Return ONLY a JSON object with these keys:
{
  "response_distributions": {<cond>: {"distribution": "<family>",
                                       "value": {<family-specific params>},
                                       "rationale": "..."}},
  "performance_omission_rate": {<cond>: <fraction>, ...},
  "temporal_effects": {<effect>: {"value": {"enabled": ..., ...},
                                   "rationale": "..."}},
  "between_subject_jitter": {"value": {...}, "rationale": "..."}
}
