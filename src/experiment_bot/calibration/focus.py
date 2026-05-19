"""Listener-target focus helpers.

Phase 4b user note 5: pre-press DOM probe for ``document.activeElement``,
``jspsych-display-element``, or similar; ``await target.focus()`` before
each press. The CDP and keyboard deliverers accept a ``listener_focus_js``
string at construction. This module ships paradigm-agnostic JS helpers
that the caller can pass in.

Per G1, the deliverers themselves don't know about jsPsych. The default
helpers here are jsPsych-shaped because all four SP11 dev paradigms run
on jsPsych — but they're caller-supplied, not deliverer-baked.
"""
from __future__ import annotations

# JS arrow that focuses jsPsych's display element if present. Falls back
# to focusing document.body if not. This is the recommended default for
# the four SP11 dev paradigms.
JSPSYCH_DISPLAY_FOCUS_JS = """() => {
  const el = document.getElementById('jspsych-display-element')
            || document.body;
  if (el && typeof el.focus === 'function') {
    try { el.focus(); } catch(e) {}
  }
}"""


# JS arrow that focuses document.body. Generic catch-all for platforms
# that don't expose a known display element. Most browsers route
# keyboard events to document.activeElement, and an unfocused page
# (e.g. just after iframe swap) routes nowhere.
BODY_FOCUS_JS = """() => {
  if (document.body && typeof document.body.focus === 'function') {
    try { document.body.focus(); } catch(e) {}
  }
}"""


# JS arrow that probes ``document.activeElement`` and, if it's an
# iframe, focuses the iframe's content body. Useful for paradigms
# embedded in an iframe (Gorilla, some commercial deployments).
IFRAME_CONTENT_FOCUS_JS = """() => {
  const active = document.activeElement;
  if (active && active.tagName === 'IFRAME') {
    try {
      const doc = active.contentDocument || active.contentWindow.document;
      if (doc && doc.body && typeof doc.body.focus === 'function') {
        doc.body.focus();
      }
    } catch(e) {}
  }
}"""
