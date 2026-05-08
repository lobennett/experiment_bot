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

## Concrete shape examples (read carefully — schema rejects variants)

The schema validator strictly enforces the exact field names and types shown below. Variants like alternate field names or extra properties cause refinement loops. Use these examples verbatim as templates.

### temporal_effects.post_event_slowing.triggers[]

Each item must be an object with an `event` enum, two numeric bounds, and an optional exclusivity flag.

```json schema-example: temporal_effects.post_event_slowing.triggers[]
{"event": "error", "slowing_ms_min": 30, "slowing_ms_max": 60}
```

```json schema-example: temporal_effects.post_event_slowing.triggers[]
{"event": "interrupt", "slowing_ms_min": 80, "slowing_ms_max": 140, "exclusive_with_prior_triggers": true}
```

Do NOT emit:

```json schema-anti-example: temporal_effects.post_event_slowing.triggers[]
"error"
```

```json schema-anti-example: temporal_effects.post_event_slowing.triggers[]
{"slowing_ms": 50}
```

### temporal_effects.lag1_pair_modulation.modulation_table[]

Each item names the condition transition with `prev` and `curr` (NOT `prev_condition` / `curr_condition`), plus a delta. Use either a fixed `delta_ms` or a uniform-random `delta_ms_min`/`delta_ms_max` pair.

```json schema-example: temporal_effects.lag1_pair_modulation.modulation_table[]
{"prev": "incongruent", "curr": "incongruent", "delta_ms": -25}
```

```json schema-example: temporal_effects.lag1_pair_modulation.modulation_table[]
{"prev": "congruent", "curr": "incongruent", "delta_ms_min": 5, "delta_ms_max": 30}
```

Do NOT emit:

```json schema-anti-example: temporal_effects.lag1_pair_modulation.modulation_table[]
{"prev_condition": "incongruent", "curr_condition": "incongruent", "rt_offset_ms": -25}
```

### performance.accuracy.<condition>

Each per-condition value may be either a bare number OR a `{value, rationale}` envelope. Both are accepted; pick one.

```json schema-example: performance.accuracy.<condition>
0.95
```

```json schema-example: performance.accuracy.<condition>
{"value": 0.95, "rationale": "Population mean for go-condition accuracy."}
```

Do NOT emit `null`. If the literature does not give a clean point estimate, choose the midpoint of the reported range.

```json schema-anti-example: performance.accuracy.<condition>
null
```

The same rule applies to `performance.omission_rate.<condition>` and `performance.practice_accuracy`.

### task_specific.key_map

A flat condition→key map. Each value is a literal Playwright key, the sentinel `"dynamic"`, or a withhold sentinel like `"withhold"`/`"null"`. Do NOT include rationale fields, prose, or parentheticals — the executor presses the value as a literal key.

```json schema-example: task_specific.key_map
{"congruent": "f", "incongruent": "j"}
```

```json schema-example: task_specific.key_map
{"go": "Space", "stop": "withhold"}
```

Do NOT emit:

```json schema-anti-example: task_specific.key_map
{"match": ".", "mismatch": ",", "rationale": "Counterbalanced across participants..."}
```

If you need to document how the key mapping is resolved, place the rationale in the per-stimulus `response_key_js` or in the parent's `rationale` field — never as a value inside `key_map`.
