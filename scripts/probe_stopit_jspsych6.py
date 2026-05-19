"""SP11 Phase 5a.0 — stopit jsPsych 6 marker probe.

CRITICAL-PATH probe per Phase 5a user note 3: resolve stopit's
jsPsych 6 marker JS EARLY so escalation can land before 5b's
TaskCard regeneration.

Tests against the live stopit URL:
  (a) is window.jsPsych present? what version surface?
  (b) is there a per-atomic-trial monotonic marker accessible?
     - try jsPsych.progress()
     - try jsPsych.getProgress()  (would be v7)
     - try jsPsych.currentTrial()  (v6 style)
     - try jsPsych.getCurrentTrial()  (v7 style)
  (c) is jsPsych.data.get().values() shape similar enough to v7
      that the existing pairing field (trial_index) works?

Verdict bands (per Phase 5a user note 3):
  - works_clean        — jsPsych 6 has equivalent API; just swap names
  - works_with_swap    — different method names but same semantics
  - escalate           — no monotonic marker available; stopit moves
                          to scope §11 limit pre-registered for sp11

Writes findings to docs/sp11-phase5a-stopit-probe.md.
Run: uv run python scripts/probe_stopit_jspsych6.py
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright


STOPIT_URL = "https://kywch.github.io/STOP-IT/jsPsych_version/experiment-transformed-first.html"
PROBE_TIMEOUT_S = 240.0


PROBE_JS = """
(() => {
  const findings = {
    has_jsPsych: typeof window.jsPsych !== 'undefined',
  };
  if (!findings.has_jsPsych) return findings;
  const jp = window.jsPsych;
  // Version: jsPsych 6 exposes `version` as a function; v7 exposes a
  // property `version`. Both return strings like '6.0.5' or '7.3.1'.
  try {
    if (typeof jp.version === 'function') {
      findings.version_value = jp.version();
      findings.version_access = 'function';
    } else if (typeof jp.version === 'string') {
      findings.version_value = jp.version;
      findings.version_access = 'string';
    } else if (typeof jp.version !== 'undefined') {
      findings.version_value = String(jp.version);
      findings.version_access = 'unknown_type';
    }
  } catch(e) { findings.version_error = String(e.message || e); }

  // Marker API #1: v7 jsPsych.getProgress().current_trial_global
  try {
    findings.v7_getProgress_exists = typeof jp.getProgress === 'function';
    if (findings.v7_getProgress_exists) {
      const p = jp.getProgress();
      findings.v7_getProgress_value = p ? p.current_trial_global : null;
      findings.v7_getProgress_keys = p ? Object.keys(p) : null;
    }
  } catch(e) { findings.v7_getProgress_error = String(e.message || e); }

  // Marker API #2: v6 jsPsych.progress() (note: function-style accessor)
  try {
    findings.v6_progress_exists = typeof jp.progress === 'function';
    if (findings.v6_progress_exists) {
      const p = jp.progress();
      findings.v6_progress_value = p ? p.current_trial_global : null;
      findings.v6_progress_keys = p ? Object.keys(p) : null;
    }
  } catch(e) { findings.v6_progress_error = String(e.message || e); }

  // Marker API #3: jsPsych.currentTrial() / getCurrentTrial()
  try {
    findings.v6_currentTrial_exists = typeof jp.currentTrial === 'function';
    findings.v7_getCurrentTrial_exists = typeof jp.getCurrentTrial === 'function';
    if (findings.v6_currentTrial_exists) {
      const t = jp.currentTrial();
      findings.v6_currentTrial_keys = t ? Object.keys(t).slice(0, 20) : null;
    } else if (findings.v7_getCurrentTrial_exists) {
      const t = jp.getCurrentTrial();
      findings.v7_getCurrentTrial_keys = t ? Object.keys(t).slice(0, 20) : null;
    }
  } catch(e) { findings.currentTrial_error = String(e.message || e); }

  // Data API: both v6 and v7 expose jsPsych.data.get().values()
  try {
    findings.data_get_exists = typeof jp.data !== 'undefined'
                            && typeof jp.data.get === 'function';
    if (findings.data_get_exists) {
      const values = jp.data.get().values();
      findings.data_values_length = values.length;
      if (values.length > 0) {
        findings.data_values_first_keys = Object.keys(values[0]).slice(0, 30);
        // Check for trial_index field (jsPsych's canonical pairing field)
        findings.has_trial_index_field = 'trial_index' in values[0];
      }
    }
  } catch(e) { findings.data_get_error = String(e.message || e); }

  return findings;
})()
"""


async def main() -> dict:
    findings = {
        "probed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "url": STOPIT_URL,
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            print(f"[1/3] Navigating to {STOPIT_URL}…")
            await page.goto(STOPIT_URL, wait_until="networkidle", timeout=30_000)
            # Initial probe — pre-instruction
            initial = await page.evaluate(PROBE_JS)
            findings["initial_probe"] = initial

            print("[2/3] Advancing through instructions to reach a trial state…")
            # Dismiss welcome / instructions with up to 90s of advancing
            from experiment_bot.calibration.playwright_gate_dismisser import (
                PlaywrightGateDismisser,
            )
            dismisser = PlaywrightGateDismisser(page)
            deadline = time.monotonic() + 90.0
            last_records_n = initial.get("data_values_length", 0)
            iters = 0
            while time.monotonic() < deadline:
                iters += 1
                await dismisser.dismiss()
                await asyncio.sleep(2.5)
                state = await page.evaluate(PROBE_JS)
                if (state.get("data_values_length", 0)
                        > last_records_n + 1):
                    findings["post_advance_probe"] = state
                    findings["advance_iters"] = iters
                    break
                last_records_n = state.get("data_values_length", 0)
            else:
                # Timed out advancing — record whatever state we have
                findings["post_advance_probe"] = await page.evaluate(PROBE_JS)
                findings["advance_iters"] = iters
                findings["advance_timeout"] = True

            print("[3/3] Computing verdict…")
            post = findings.get("post_advance_probe", initial)
            verdict, blurb = compute_verdict(initial, post)
            findings["verdict"] = verdict
            findings["verdict_summary"] = blurb
            findings["recommended_marker_js"] = recommended_marker_js(post)

            print(json.dumps({
                "verdict": verdict,
                "version": post.get("version_value")
                           or initial.get("version_value"),
                "v7_getProgress_exists": post.get("v7_getProgress_exists"),
                "v6_progress_exists": post.get("v6_progress_exists"),
                "data_get_exists": post.get("data_get_exists"),
                "data_values_length": post.get("data_values_length"),
                "has_trial_index_field": post.get("has_trial_index_field"),
            }, indent=2))
            print(blurb)
        finally:
            await browser.close()
    write_report(findings)
    return findings


def compute_verdict(initial: dict, post: dict) -> tuple[str, str]:
    has_v7 = post.get("v7_getProgress_exists") or initial.get("v7_getProgress_exists")
    has_v6 = post.get("v6_progress_exists") or initial.get("v6_progress_exists")
    has_data = post.get("data_get_exists") or initial.get("data_get_exists")
    has_trial_idx = post.get("has_trial_index_field")

    # Marker availability decides whether trial-counter pairing is feasible
    if has_v7 and has_data and has_trial_idx:
        return ("works_clean",
                "stopit_stop_signal exposes jsPsych v7-style "
                "getProgress() and standard data.get() with trial_index. "
                "No API swap needed — default deliverer config works.")
    if has_v6 and has_data and has_trial_idx:
        return ("works_with_swap",
                "stopit_stop_signal exposes jsPsych v6-style progress() "
                "(function accessor). Swap trial_marker_js to "
                "'() => window.jsPsych.progress().current_trial_global' "
                "at deliverer construction. Pairing is identical via "
                "trial_index. NOT an escalation.")
    if has_v6 and has_data and not has_trial_idx:
        return ("partial_works",
                "stopit has progress() but record schema may lack "
                "trial_index. Need to inspect post-trial-start record "
                "shape — pair on alternate field (e.g., trial_global) "
                "if available, else escalate.")
    if has_data and not (has_v6 or has_v7):
        return ("escalate",
                "stopit exposes data.get() but no monotonic progress "
                "API. Trial-counter pairing INFEASIBLE — fall back "
                "to RT-based pairing for stopit ONLY (with explicit "
                "delivery-method disclosure in §6 of Phase 8 writeup), "
                "or move stopit to §11 scope-limit pre-registered for "
                "sp11.")
    return ("escalate",
            "Neither marker API nor data API is reliably available on "
            "stopit. Cannot proceed with stopit on input-layer path. "
            "Move to §11 scope limit and document.")


def recommended_marker_js(post: dict) -> str | None:
    if post.get("v7_getProgress_exists"):
        return ("() => (window.jsPsych && window.jsPsych.getProgress && "
                "window.jsPsych.getProgress().current_trial_global) || null")
    if post.get("v6_progress_exists"):
        return ("() => (window.jsPsych && window.jsPsych.progress && "
                "window.jsPsych.progress().current_trial_global) || null")
    return None


def write_report(findings: dict) -> None:
    out = Path("docs/sp11-phase5a-stopit-probe.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    verdict = findings.get("verdict", "unknown")
    summary = findings.get("verdict_summary", "")
    rec = findings.get("recommended_marker_js")

    initial = findings.get("initial_probe", {})
    post = findings.get("post_advance_probe", {})
    ver_initial = initial.get("version_value") or "unknown"
    ver_post = post.get("version_value") or ver_initial

    lines = [
        "# SP11 Phase 5a.0 — stopit_stop_signal jsPsych 6 marker probe",
        "",
        f"**Probed at:** {findings.get('probed_at_iso')}",
        f"**URL:** `{findings.get('url')}`",
        f"**Verdict:** **{verdict}**",
        "",
        "## Verdict summary",
        "",
        summary,
        "",
        "## Detected engine version",
        "",
        f"- Initial probe: `{ver_initial}`",
        f"- Post-advance probe: `{ver_post}`",
        "",
        "## Marker API surface",
        "",
        f"- `jsPsych.getProgress()` (v7): "
        f"{post.get('v7_getProgress_exists') or initial.get('v7_getProgress_exists')}",
        f"- `jsPsych.progress()`    (v6): "
        f"{post.get('v6_progress_exists') or initial.get('v6_progress_exists')}",
        f"- `jsPsych.getCurrentTrial()`: "
        f"{post.get('v7_getCurrentTrial_exists') or initial.get('v7_getCurrentTrial_exists')}",
        f"- `jsPsych.currentTrial()`:   "
        f"{post.get('v6_currentTrial_exists') or initial.get('v6_currentTrial_exists')}",
        "",
        "## Data API",
        "",
        f"- `jsPsych.data.get()` exists: "
        f"{post.get('data_get_exists') or initial.get('data_get_exists')}",
        f"- Records observed post-advance: "
        f"`{post.get('data_values_length', 0)}`",
        f"- Records have `trial_index` field: "
        f"`{post.get('has_trial_index_field')}`",
        "",
        "## Recommended `trial_marker_js`",
        "",
        f"```js\n{rec or '(none — escalate)'}\n```",
        "",
        "## Phase 5a decision",
        "",
    ]
    if verdict == "works_clean" or verdict == "works_with_swap":
        lines.extend([
            "- Phase 5a will pass the recommended marker JS at",
            "  CDPDeliverer construction when the executor wires stopit.",
            "- The TaskCard for stopit will pin its `runtime.timing.cdp_dwell_ms`",
            "  to a stop-signal-appropriate value (200ms default keeps stop trials",
            "  inside the 250ms-min SSD window for the earliest trials).",
            "- Phase 7's stopit measurement run proceeds as planned.",
        ])
    elif verdict == "partial_works":
        lines.extend([
            "- Inspect `post_advance_probe.data_values_first_keys` to find the",
            "  pairing-eligible field. If none, this becomes `escalate`.",
            "- 5b TaskCard regeneration proceeds for stopit, but Phase 7 must",
            "  use the alternate pairing in audit_alignment.py.",
        ])
    else:  # escalate
        lines.extend([
            "- **Pre-register stopit_stop_signal as a §11 scope limit.** The",
            "  abstract's cross-deployment claim drops from 4 → 3 paradigms.",
            "  Phase 7 still runs the 3 jsPsych-7 paradigms × N=30 sequentially;",
            "  stopit either:",
            "    (a) runs with RT-based pairing only, disclosed as a measurement",
            "        limitation in §6.3 of the Phase 8 writeup, OR",
            "    (b) is dropped from the SP11 deliverable, deferred to a future SP.",
            "- 5a does NOT regenerate stopit's TaskCard if (b). 5b regenerates 3,",
            "  not 4.",
        ])
    out.write_text("\n".join(lines) + "\n")
    print(f"\n[report] wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
