You are a cognitive psychology expert producing behavioral parameters for a bot
that mimics a typical healthy adult on this task. Given the structural fields
below (already produced in stage 1), produce:

1. response_distributions[<condition>].value = {mu, sigma, tau} per condition,
   informed by published norms.
2. performance.omission_rate per condition.
3. temporal_effects[<effect>].value with `enabled` boolean and parameters,
   only enabling effects empirically documented for this paradigm.
4. between_subject_jitter.value with rt_mean_sd_ms, rt_condition_sd_ms,
   sigma_tau_range, accuracy_sd, omission_sd.

For each numeric parameter, also include a `rationale` string. Citations come
in stage 3 — do NOT include them yet.

Return ONLY a JSON object with these keys:
{
  "response_distributions": {<cond>: {"distribution": "ex_gaussian",
                                       "value": {"mu": ..., "sigma": ..., "tau": ...},
                                       "rationale": "..."}},
  "performance_omission_rate": {<cond>: <fraction>, ...},
  "temporal_effects": {<effect>: {"value": {"enabled": ..., ...},
                                   "rationale": "..."}},
  "between_subject_jitter": {"value": {...}, "rationale": "..."}
}
