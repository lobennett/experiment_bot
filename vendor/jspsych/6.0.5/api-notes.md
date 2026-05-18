# jsPsych 6.0.5 API notes

This version is supported by the same `JsPsychDriver` that targets
7.3.1; the driver detects which API surface is live and uses the
appropriate function names. The hook target —
`pluginAPI.getKeyboardResponse` — is the same in both versions.

## Differences from 7.3.1

| Aspect | v6.0.5 | v7.3.1 |
|---|---|---|
| `version` accessor | property (string) | function (callable) |
| Current trial | `jsPsych.currentTrial()` | `jsPsych.getCurrentTrial()` |
| Progress | `jsPsych.progress()` | `jsPsych.getProgress()` |
| `trial.type` | string (`"html-keyboard-response"`) | class instance with `.info.name` |
| Init | `jsPsych.init({timeline, ...})` | `initJsPsych({...}); jsPsych.run(timeline)` |
| `evaluateTimelineVariable` | absent | absent |
| Data export | `jsPsych.data.get().json()` | `jsPsych.data.get().json()` |
| `pluginAPI.getKeyboardResponse` | same signature | same signature |

The `init`/`run` distinction matters only for code that constructs
experiments, not for the bot, which attaches to an already-running
page.

## Plugin source layout (v6)

Plugins are loaded as classic `<script src="...">` modules that
attach handlers to `jsPsych.plugins.<name>`. The relevant ones for
stopit kywch:

- `jsPsych.plugins.html-keyboard-response`
- `jsPsych.plugins.instructions`
- `jsPsych.plugins.fullscreen`
- `jsPsych.plugins.call-function`
- `custom-stop-signal-plugin` (kywch-authored, attaches as
  `jsPsych.plugins['custom-stop-signal']`)

Upstream source for v6 core:
https://github.com/jspsych/jsPsych/tree/v6.0.5
(MIT license; not vendored verbatim — see `vendor/jspsych/7.3.1/`
for the format used when a version needs deeper anchoring.)
