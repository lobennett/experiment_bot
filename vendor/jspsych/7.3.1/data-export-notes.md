# jsPsych 7.3.1 data export notes

The data export API used by the driver lives across multiple files in the
upstream `packages/jspsych/src/modules/data/`. Rather than vendoring the
full data subsystem, this note documents the parts the JsPsychDriver
relies on.

## Key methods (called via `window.jsPsych.data.get()`)

- `jsPsych.data.get()` — returns a `DataCollection` of all trial data
  recorded across the session.
- `DataCollection.csv()` — serialize to CSV (string).
- `DataCollection.json()` — serialize to JSON (string).
- `DataCollection.values()` — return the underlying array of trial-data
  objects (per-trial `{trial_index, response, rt, stimulus, ...}` dicts
  plus whatever the experiment's `data:` properties contributed).
- `DataCollection.filter({key: value})` — chainable filter (the
  validation oracle's adapters use this conceptually but we read the
  raw export instead).

## Driver usage

```python
# In JsPsychDriver.retrieve_data:
raw_json = await page.evaluate("window.jsPsych.data.get().json()")
trials = json.loads(raw_json)
return ExperimentData(trials=trials, format="json", raw=raw_json, metadata=...)
```

## Per-trial data fields

Default fields jsPsych adds to every trial:
- `trial_type`: e.g. "html-keyboard-response"
- `trial_index`: zero-based ordinal across the timeline
- `time_elapsed`: ms since session start
- `internal_node_id`: tree-path identifier
- (plugin-specific) `rt`, `response`, `stimulus`, etc.

Experiment-defined fields:
- Anything in the trial's `data: {...}` property — common ones:
  - `condition`: e.g. "congruent", "go", "match_1back"
  - `correct_response`: the key the experiment considers correct
  - `stim_color`, `stim_word`, etc.: paradigm-specific stimulus props

The driver's `get_trial_context` reads from these conventional fields
when available; `expected_correct` comes from `trial.data?.correct_response`
or the per-trial `correct_response` field if present.

## Provenance

Source: https://github.com/jspsych/jsPsych/tree/jspsych%407.3.1/packages/jspsych/src/modules/data/
License: MIT (see vendor/LICENSES.md)
Retrieved: 2026-05-17
