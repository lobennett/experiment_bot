# SP11 Phase 5a.0 — stopit_stop_signal jsPsych 6 marker probe

**Probed at:** 2026-05-18T23:08:45-0700
**URL:** `https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html`
**Verdict:** **works_with_swap**

## Verdict summary

stopit_stop_signal exposes jsPsych v6-style progress() (function accessor). Swap trial_marker_js to '() => window.jsPsych.progress().current_trial_global' at deliverer construction. Pairing is identical via trial_index. NOT an escalation.

## Detected engine version

- Initial probe: `unknown`
- Post-advance probe: `unknown`

## Marker API surface

- `jsPsych.getProgress()` (v7): False
- `jsPsych.progress()`    (v6): True
- `jsPsych.getCurrentTrial()`: False
- `jsPsych.currentTrial()`:   True

## Data API

- `jsPsych.data.get()` exists: True
- Records observed post-advance: `6`
- Records have `trial_index` field: `True`

## Recommended `trial_marker_js`

```js
() => (window.jsPsych && window.jsPsych.progress && window.jsPsych.progress().current_trial_global) || null
```

## Phase 5a decision

- Phase 5a will pass the recommended marker JS at
  CDPDeliverer construction when the executor wires stopit.
- The TaskCard for stopit will pin its `runtime.timing.cdp_dwell_ms`
  to a stop-signal-appropriate value (200ms default keeps stop trials
  inside the 250ms-min SSD window for the earliest trials).
- Phase 7's stopit measurement run proceeds as planned.
