# SP11 Phase 3.1 — cognition.run data-export probe

**Probed at:** 2026-05-18T19:47:01-0700
**URL:** `https://strooptest.cognition.run/`
**Outcome:** `data_store_accessible_pre_trial`

## Verdict

window.jsPsych.data accessor is present and callable; during this probe no trials had accumulated yet because the bot's keypresses didn't advance past the instructions phase. Calibration on this platform is feasible via the standard jsPsych data API (jsPsych.data.get().values()). The underlying jsPsych version is the same as expfactory paradigms (jspsych-7.3.1, loaded from static.cognition.run/js/), so the calibration estimator does NOT need a platform-specific data-read function.

## Initial probe (pre-keypress)

```json
{
  "title": "Stroop Online",
  "url": "https://strooptest.cognition.run/",
  "buttons": [],
  "scripts": [
    "https://static.cognition.run/js/jspsych-7.3.1/jspsych.js",
    "https://static.cognition.run/js/jspsych-7.3.1/plugin-html-keyboard-response.js",
    "https://static.cognition.run/js/jspsych-7.3.1/plugin-instructions.js",
    "https://strooptest.cognition.run/code.js?id=1776252865"
  ],
  "body_data_attrs": {},
  "window_globals": {
    "jsPsych": {
      "type": "object",
      "constructor": "JsPsych",
      "has_data_prop": true,
      "keys": [
        "extensions",
        "turk",
        "randomization",
        "utils",
        "opts",
        "global_trial_index",
        "current_trial",
        "current_trial_finished",
        "paused",
        "waiting",
        "file_protocol",
        "simulation_mode",
        "webaudio_context",
        "internal",
        "progress_bar_amount",
        "version",
        "run",
        "simulate",
        "getProgress",
        "getStartTime",
        "getTotalTime",
        "getDisplayElement",
        "getDisplayContainerElement",
        "finishTrial",
        "endExperiment",
        "endCurrentTimeline",
        "getCurrentTrial",
        "getInitSettings",
        "getCurrentTimelineNodeID",
        "timelineVariable"
      ]
    }
  },
  "iframes": [],
  "body_text_len": 51,
  "body_text_preview": "Welcome to the experiment.\nPress Space to continue."
}
```

## Gate dismissal

- Attempted: False
- Button text clicked: `None`

## Keypress fire log

```json
[
  {
    "key": "Space",
    "fired_at_s": 801414.563147916,
    "ok": true
  },
  {
    "key": "ArrowLeft",
    "fired_at_s": 801414.972335333,
    "ok": true
  },
  {
    "key": "ArrowRight",
    "fired_at_s": 801415.380356041,
    "ok": true
  },
  {
    "key": "Space",
    "fired_at_s": 801415.789074666,
    "ok": true
  },
  {
    "key": "Enter",
    "fired_at_s": 801416.195529708,
    "ok": true
  }
]
```

## Post-keypress probe

```json
{
  "jspsych_data_count": 0,
  "jspsych_data_sample": [],
  "localStorage_keys": [],
  "sessionStorage_keys": [],
  "body_text_preview_after": "As soon as you see a new word, press its first letter.\nFor example, press the B key for blue.\nPress Space to continue."
}
```

## Errors (if any)
