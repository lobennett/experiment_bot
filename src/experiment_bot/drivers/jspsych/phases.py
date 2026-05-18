"""SP10 jsPsych phase recognition.

Reads jsPsych.getCurrentTrial() + jsPsych.progress() + the
__bot_hook armed-state to classify what the driver should do next.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


# JS that reads enough state to classify the current loop state.
_LOOP_STATE_JS = """
(() => {
  if (!window.jsPsych) return { state: 'unknown' };
  let percent = null;
  try {
    // jsPsych 7+ renamed progress() to getProgress(). We probe both
    // names defensively — the v7 getter for the legacy `progress`
    // property throws MigrationError (not just returns undefined),
    // so we have to use typeof + try/catch.
    let prog = null;
    if (typeof window.jsPsych.getProgress === 'function') {
      prog = window.jsPsych.getProgress();
    } else {
      try {
        if (typeof window.jsPsych.progress === 'function') {
          prog = window.jsPsych.progress();
        }
      } catch (e) {}
    }
    percent = prog && prog.percent_complete;
  } catch (e) {}
  if (percent !== null && percent >= 100) return { state: 'complete' };
  let trial = null;
  try {
    // v7: getCurrentTrial(). v6: currentTrial().
    if (typeof window.jsPsych.getCurrentTrial === 'function') {
      trial = window.jsPsych.getCurrentTrial();
    } else if (typeof window.jsPsych.currentTrial === 'function') {
      trial = window.jsPsych.currentTrial();
    }
  } catch (e) {}
  if (!trial) {
    // Between trials or before timeline started. Treat as needs_navigation
    // — bot library will poll again shortly.
    return { state: 'needs_navigation', reason: 'no_current_trial' };
  }
  // v7: trial.type is a class instance with .info.name. v6: it's a string.
  let type_name = null;
  try {
    if (typeof trial.type === 'string') {
      type_name = trial.type;
    } else if (trial.type && trial.type.info && trial.type.info.name) {
      type_name = trial.type.info.name;
    } else if (trial.type && trial.type.name) {
      type_name = trial.type.name;
    }
  } catch (e) {}
  type_name = type_name || 'unknown';
  // Instructions plugin uses pluginAPI.getKeyboardResponse for nav keys
  // — we don't want to treat that as a trial-body, so the reading-pace
  // navigation path can run.
  if (/instructions/i.test(type_name)) {
    return { state: 'needs_navigation', type: type_name };
  }
  // Trial-body plugins arm the keyboard hook via getKeyboardResponse.
  // This covers html-keyboard-response, audio-keyboard-response,
  // poldracklab-stop-signal, custom-stop-signal-plugin, and any other
  // trial plugin that registers a keyboard callback through the
  // standard pluginAPI.
  if (window.__bot_hook && window.__bot_hook.current) {
    return { state: 'ready_for_trial', type: type_name };
  }
  // Keyboard-response trial whose hook hasn't been armed yet (between
  // plugin start and the getKeyboardResponse call). Reported with a
  // distinct reason so navigation can avoid dispatching keys.
  if (/keyboard-response|stop-signal/.test(type_name)) {
    return {
      state: 'needs_navigation',
      type: type_name,
      reason: 'hook_not_yet_armed',
    };
  }
  // Everything else (button-response, html-display, fullscreen, etc.)
  // is a navigation phase.
  return { state: 'needs_navigation', type: type_name };
})()
"""


# JS that reads the active trial + hook state for get_trial_context.
# Returns null if no active trial / no armed hook.
_GET_CONTEXT_JS = """
(() => {
  if (!window.jsPsych) return null;
  let trial = null;
  try {
    if (typeof window.jsPsych.getCurrentTrial === 'function') {
      trial = window.jsPsych.getCurrentTrial();
    } else if (typeof window.jsPsych.currentTrial === 'function') {
      trial = window.jsPsych.currentTrial();
    }
  } catch (e) {}
  const hook = window.__bot_hook && window.__bot_hook.current;
  if (!trial || !hook) return null;
  // Some experiments declare `data: jsPsych.timelineVariable('data')` so
  // by the time the plugin starts running, trial.data is still the
  // TimelineVariable wrapper (not the resolved object). Other
  // experiments use a function `data: () => ({...})`. Resolve both.
  let data = trial.data;
  if (typeof data === 'function') {
    try { data = data(); } catch (e) { data = trial.data; }
  }
  if (!data || typeof data !== 'object' || Array.isArray(data) ||
      (data.constructor && data.constructor.name &&
       data.constructor.name.indexOf('TimelineVariable') !== -1)) {
    // Wrapper; try the live evaluator if jsPsych exposes one.
    if (typeof window.jsPsych.evaluateTimelineVariable === 'function') {
      try {
        const resolved = window.jsPsych.evaluateTimelineVariable('data');
        if (resolved && typeof resolved === 'object') data = resolved;
      } catch (e) {}
    }
  }
  if (!data || typeof data !== 'object') data = {};
  // Per-field fallback: some experiments don't wrap under a single
  // `data:` key but instead expose individual timeline variables
  // (data: { condition: jsPsych.timelineVariable('condition'), ... }).
  // For each field we read, if the value is still a TimelineVariable
  // wrapper or undefined, evaluate the same-named timeline variable.
  const _resolveField = (key) => {
    let v = data[key];
    const isWrapper = v && typeof v === 'object' && v.constructor &&
                      v.constructor.name &&
                      v.constructor.name.indexOf('TimelineVariable') !== -1;
    if ((v == null || isWrapper) &&
        typeof window.jsPsych.evaluateTimelineVariable === 'function') {
      try {
        const ev = window.jsPsych.evaluateTimelineVariable(key);
        if (ev != null) v = ev;
      } catch (e) {}
    }
    return v;
  };
  const cond_resolved = _resolveField('condition');
  let corr_resolved = _resolveField('correct_response');
  const stim_resolved_id = _resolveField('stimulus_id');
  // Some paradigms don't write correct_response into trial.data at
  // trial-start (n_back stores it in a window-level global before each
  // trial; poldracklab-stop-signal stores it as a closure-local var
  // but exposes it on the trial spec under `correct_choice`, often as
  // a function reference). Try the additional channels here.
  if (corr_resolved == null) {
    // 1. Top-level trial.correct_response (some experiments use this
    //    rather than data.correct_response).
    if (trial.correct_response != null) {
      corr_resolved = trial.correct_response;
    }
  }
  if (corr_resolved == null) {
    // 2. trial.correct_choice — poldracklab-stop-signal trial spec.
    //    May be a string (direct) or a function (call to resolve).
    try {
      const cc = trial.correct_choice;
      if (typeof cc === 'function') {
        const r = cc();
        if (r != null) corr_resolved = r;
      } else if (cc != null) {
        corr_resolved = cc;
      }
    } catch (e) {}
  }
  if (corr_resolved == null) {
    // 3. window-level globals. SP8 found `window.correctResponse` is
    //    the expfactory n_back convention; some paradigms use
    //    `window.correct_response` (snake_case) instead. Both are
    //    set by the experiment's pre-trial setup.
    try {
      if (window.correctResponse != null) corr_resolved = window.correctResponse;
      else if (window.correct_response != null) corr_resolved = window.correct_response;
    } catch (e) {}
  }
  const stimulus_id = String(
    stim_resolved_id != null ? stim_resolved_id :
    (typeof trial.stimulus === 'string' ? trial.stimulus.slice(0, 200) :
     (trial.stimulus != null ? 'stim' : 'unknown'))
  );
  const condition = String(
    cond_resolved != null ? cond_resolved :
    (trial.condition != null ? trial.condition : 'default')
  );
  const expected_correct =
    (corr_resolved != null) ? String(corr_resolved) :
    (trial.correct_response != null ? String(trial.correct_response) :
     null);
  // valid_responses from the hook may be 'ALL_KEYS', 'NO_KEYS', or array.
  let allowed_responses = [];
  const vr = hook.valid_responses;
  if (Array.isArray(vr)) {
    allowed_responses = vr.map(String);
  }
  // type name — v7: trial.type is a class instance with .info.name;
  // v6: trial.type is a string directly.
  let type_name = null;
  try {
    if (typeof trial.type === 'string') {
      type_name = trial.type;
    } else if (trial.type && trial.type.info && trial.type.info.name) {
      type_name = trial.type.info.name;
    } else if (trial.type && trial.type.name) {
      type_name = trial.type.name;
    }
  } catch (e) {}
  type_name = type_name || 'unknown';
  // Stop-signal trial detection. Only meaningful for the
  // poldracklab-stop-signal plugin, which tags each trial via
  // `SS_trial_type` ('go' or 'stop'), typically a function reference
  // (`getCondition`) that returns the current trial's type from the
  // experiment's `stims` queue. We deliberately do NOT fall back to
  // window-level globals: those persist across trials and would mark
  // every following non-stop-signal trial as is_stop_trial=true.
  let is_stop_trial = false;
  if (type_name && /poldracklab-stop-signal|stop-signal/.test(type_name)) {
    try {
      let sst = trial.SS_trial_type;
      if (typeof sst === 'function') sst = sst();
      if (typeof sst === 'string' && sst.toLowerCase() === 'stop') {
        is_stop_trial = true;
      }
    } catch (e) {}
  }
  return {
    stimulus_id,
    condition,
    allowed_responses,
    expected_correct,
    response_window_ms: trial.trial_duration != null ? Number(trial.trial_duration) : null,
    metadata: {
      type_name,
      valid_responses_raw: typeof vr === 'string' ? vr : null,
      is_stop_trial,
    },
  };
})()
"""


async def read_loop_state(page: Page) -> dict:
    try:
        return await page.evaluate(_LOOP_STATE_JS)
    except Exception as e:
        logger.warning("read_loop_state: page.evaluate raised: %s", e)
        return {"state": "unknown"}


async def read_trial_context(page: Page) -> dict | None:
    try:
        return await page.evaluate(_GET_CONTEXT_JS)
    except Exception as e:
        logger.warning("read_trial_context: page.evaluate raised: %s", e)
        return None
