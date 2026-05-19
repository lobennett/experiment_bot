"""Phase 4a feasibility spike — CDP-level keypress fidelity.

Kill-switch gate per spec §4 Phase 4. Fires 50 keypresses via Chrome
DevTools Protocol Input.dispatchKeyEvent into expfactory Stroop's
test-phase trial-accepting state. Reads back jsPsych.data.get().values()
and measures pressed_eq_recorded.

Per Phase 4a user note 1: the spike fires into the TEST PHASE only.
Instructions/practice listener targets may differ, and the gate
number must generalize to where Phase 7 trials land. Practice trials
are skipped by NOT firing keys during them — they time out naturally.

Thresholds (per spec §4 Phase 4a):
- ≥ 85% : proceed to Phase 4b as planned
- 60-85%: proceed with flag (focus + target detection do more lifting)
- < 60% : escalate to project owner before continuing

Writes findings to docs/sp11-phase4a-spike.md and prints verdict to
stdout. Run: `uv run python scripts/probe_cdp_delivery.py`
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright


EXPFACTORY_STROOP_URL = "https://deploy.expfactory.org/preview/10/"
N_KEYPRESSES = 50
PROBE_TIMEOUT_S = 300.0  # 5 min hard cap
TEST_PHASE_WAIT_S = 240.0  # 4 min to reach test phase


# Stroop response keys. jsPsych v7 stroop typically uses some subset
# of [',', '.', '/']. We cycle through them for the calibration fires.
STROOP_KEYS = [",", ".", "/"]
KEY_TO_CDP_FIELDS = {
    " ":  {"key": " ",  "code": "Space",        "windowsVirtualKeyCode": 32,  "text": " "},
    ",":  {"key": ",",  "code": "Comma",        "windowsVirtualKeyCode": 188, "text": ","},
    ".":  {"key": ".",  "code": "Period",       "windowsVirtualKeyCode": 190, "text": "."},
    "/":  {"key": "/",  "code": "Slash",        "windowsVirtualKeyCode": 191, "text": "/"},
    "Enter":      {"key": "Enter",      "code": "Enter",      "windowsVirtualKeyCode": 13},
    "ArrowRight": {"key": "ArrowRight", "code": "ArrowRight", "windowsVirtualKeyCode": 39},
}


READ_STATE_JS = """
(() => {
  if (!window.jsPsych) return { error: 'no_jsPsych' };
  let trial = null;
  try { trial = window.jsPsych.getCurrentTrial(); } catch(e) {}
  let prog = null;
  try { prog = window.jsPsych.getProgress(); } catch(e) {}
  const out = {
    has_current: !!trial,
    current_type: trial && trial.type && trial.type.info && trial.type.info.name,
    current_choices: trial && trial.choices,
    current_trial_id: trial && trial.data && trial.data.trial_id,
    current_exp_stage: trial && trial.data && trial.data.exp_stage,
    // current_trial_global is a monotonic per-trial counter; unique
    // per atomic trial (including ITIs / fixations). This lets the
    // spike pair fires with trials via stable identifier rather than
    // index-into-recorded-array.
    current_trial_global: prog && prog.current_trial_global,
  };
  try {
    const all = window.jsPsych.data.get().values();
    out.recorded_count = all.length;
    out.recorded_last_5 = all.slice(-5).map(r => ({
      trial_id: r.trial_id, exp_stage: r.exp_stage,
      response: r.response, rt: r.rt, correct_response: r.correct_response,
      trial_index: r.trial_index,
    }));
    out.recorded_test_trial_count = all.filter(r => r.trial_id === 'test_trial').length;
  } catch(e) { out.data_error = e.message; }
  return out;
})()
"""


READ_DATA_JS = """
(() => {
  if (!window.jsPsych || !window.jsPsych.data) return null;
  return window.jsPsych.data.get().values().filter(
    r => r && r.trial_id === 'test_trial'
  ).map(r => ({
    response: r.response, rt: r.rt, correct_response: r.correct_response,
    trial_index: r.trial_index, condition: r.condition,
  }));
})()
"""


def _pair_by_trial_index(fires: list[dict], records: list[dict]) -> list[dict]:
    """Pair each fire with the platform record whose trial_index matches
    the trial_global the bot was on when it fired. Handles the off-by-
    one diagnosed in the earlier spike run (where naive index-pairing
    misattributed bot fires).

    The platform's per-test_trial record has a ``trial_index`` field
    (the jsPsych global trial index for that atomic trial). The bot's
    ``trial_global_at_fire`` is the value of getProgress().current_trial_global
    at fire time. They should match.
    """
    by_idx = {r.get("trial_index"): r for r in records}
    pairs = []
    for i, ev in enumerate(fires):
        ti = ev.get("trial_global_at_fire")
        rec = by_idx.get(ti)
        pairs.append({
            "i": i,
            "key_fired": ev["key"],
            "trial_index_fired_on": ti,
            "recorded": rec.get("response") if rec else None,
            "rt_recorded": rec.get("rt") if rec else None,
            "match": (rec is not None and rec.get("response") == ev["key"]),
        })
    return pairs


async def fire_cdp_key(cdp, key: str) -> dict:
    """Fire a single key via CDP Input.dispatchKeyEvent (keyDown +
    keyUp pair). Returns a small event log with fire timestamps."""
    fields = KEY_TO_CDP_FIELDS.get(key, {"key": key, "code": key})
    fire_at = time.monotonic()
    await cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", **fields})
    await asyncio.sleep(0.05)
    await cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", **fields})
    return {"key": key, "fired_at_s": fire_at, "fields": fields}


async def navigate_until_test_phase(page, deadline_s: float) -> dict:
    """Advance the bot through expfactory's instructions + practice
    phases until a test_trial appears AND the current trial is also a
    test_trial. Uses page.keyboard.press (NOT CDP) — advancement is
    incidental, only the spike fires need CDP.

    Strategy per expfactory's instruction-loop behavior:
    - Adult reading-pace dwell between instruction advances (4s/page);
      expfactory rejects super-fast progression and loops the
      instructions back.
    - On each iteration: click visible Next/Start/Begin buttons, dwell,
      fire Space (advance for kbd-driven instructions), dwell, fire
      ArrowRight (also a forward key in some plugins), dwell, fire
      comma/period/slash in case a practice trial is showing (stroop
      response keys — wrong choices time out, correct ones advance
      with feedback).
    - Returns immediately when test phase is detected.
    """
    log = []
    iteration = 0
    last_recorded_count = 0
    while time.monotonic() < deadline_s:
        iteration += 1
        # Check state first — maybe we're already in test phase
        try:
            state = await page.evaluate(READ_STATE_JS)
        except Exception as e:
            log.append({"iter": iteration, "error": str(e)})
            state = {}
        if (state.get("recorded_test_trial_count", 0) > 0
                and state.get("current_trial_id") == "test_trial"):
            log.append({"iter": iteration, "action": "reached_test_phase",
                        "state_snapshot": state})
            return {"reached": True, "state": state, "nav_log": log}
        # If recorded count grew but we're not in test, the bot is
        # advancing through practice — log it for diagnostic
        rc = state.get("recorded_count", 0)
        if rc > last_recorded_count:
            log.append({"iter": iteration, "recorded_count_delta": rc - last_recorded_count,
                        "current_trial_id": state.get("current_trial_id")})
            last_recorded_count = rc

        # Advancement actions for this iteration
        try:
            # Click any Next/Start/Begin/Continue button
            btns = await page.query_selector_all("button")
            for btn in btns:
                bbox = await btn.bounding_box()
                if not bbox or bbox.get("width", 0) < 1:
                    continue
                text = (await btn.text_content() or "").strip().lower()
                if any(t in text for t in
                       ("next", "start", "begin", "continue", "ok", "go", "ready")):
                    await btn.click()
                    log.append({"iter": iteration, "action": "click", "text": text[:40]})
                    break
        except Exception as e:
            log.append({"iter": iteration, "click_error": str(e)})

        # Reading-pace dwell — expfactory's instruction loop rejects
        # superhuman-fast progression. 3s minimum keeps us human-like.
        await asyncio.sleep(3.0)

        # Try keyboard advance for kbd-driven instructions ONLY.
        # CRITICAL: do NOT fire stroop response keys (',', '.', '/') —
        # they would be captured as responses for actual test trials,
        # blazing through the test phase before the spike fires. We
        # let practice trials time out naturally (no responses) and
        # rely on Space + ArrowRight for instruction advancement.
        try:
            for key in ("Space", "ArrowRight"):
                await page.keyboard.press(key)
                await asyncio.sleep(0.6)
        except Exception as e:
            log.append({"iter": iteration, "kbd_error": str(e)})

        # Safety cap on log size for the report
        if len(log) > 200:
            log = log[-200:]
    return {"reached": False, "timeout_s": deadline_s - time.monotonic(),
            "nav_log": log[-20:]}


async def main() -> dict:
    findings = {
        "probed_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "url": EXPFACTORY_STROOP_URL,
        "n_keypresses_target": N_KEYPRESSES,
    }
    deadline = time.monotonic() + PROBE_TIMEOUT_S
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            print(f"[1/5] Navigating to {EXPFACTORY_STROOP_URL}…")
            await page.goto(EXPFACTORY_STROOP_URL, wait_until="networkidle", timeout=30_000)

            # Open the CDP session for keypress fires
            cdp = await ctx.new_cdp_session(page)

            print("[2-3/5] Advancing through instructions + practice until test phase…")
            test_deadline = min(deadline, time.monotonic() + TEST_PHASE_WAIT_S)
            phase_check = await navigate_until_test_phase(page, test_deadline)
            findings["test_phase_check"] = phase_check
            if not phase_check.get("reached"):
                findings["outcome"] = "test_phase_not_reached"
                findings["verdict_summary"] = (
                    "The bot couldn't navigate into the test phase within "
                    f"{TEST_PHASE_WAIT_S}s. Phase 4a spike CANNOT measure "
                    "test-phase fidelity. This blocks Phase 4 — escalate."
                )
                return findings

            phase_state = phase_check["state"]
            findings["test_phase_entry_state"] = phase_state
            print(f"    Test phase reached; current_choices={phase_state.get('current_choices')}")

            print(f"[4/5] Firing {N_KEYPRESSES} CDP keypresses into test trials…")
            # Determine which keys to fire. Read the current trial's
            # choices; cycle through them. Falls back to STROOP_KEYS.
            choices = phase_state.get("current_choices") or STROOP_KEYS
            if not isinstance(choices, list) or not choices:
                choices = STROOP_KEYS
            # Filter to keys we have CDP field mappings for
            usable = [k for k in choices if k in KEY_TO_CDP_FIELDS]
            if not usable:
                usable = STROOP_KEYS
            findings["keys_used"] = usable

            # Snapshot recorded test_trial count BEFORE firing
            data_before = await page.evaluate(READ_DATA_JS) or []
            n_before = len(data_before)
            findings["recorded_before_fire"] = n_before

            fire_log = []
            phase_ended_early = False
            last_fired_trial_global = -1
            for i in range(N_KEYPRESSES):
                key = usable[i % len(usable)]
                # Phase A: wait for a FRESH test_trial — one whose
                # trial_global counter is greater than the last we
                # fired on. This breaks the off-by-one diagnosed in
                # the earlier spike run where the bot's wait-loop
                # detection was catching a trial that was about to
                # end. Pairing by trial_global is robust to
                # interstitials (ITIs, fixations).
                started_trial_global = None
                for _wait in range(80):  # up to 8s
                    state = await page.evaluate(READ_STATE_JS)
                    if (state.get("current_trial_id") == "test_trial"
                            and state.get("current_trial_global") is not None
                            and state.get("current_trial_global") > last_fired_trial_global):
                        started_trial_global = state["current_trial_global"]
                        break
                    await asyncio.sleep(0.1)
                if started_trial_global is None:
                    phase_ended_early = True
                    break
                # Phase B: dwell briefly so we fire well inside the
                # response window, not on trial-start microsecond zero.
                # 200ms is human-reaction-time territory.
                await asyncio.sleep(0.20)
                event = await fire_cdp_key(cdp, key)
                event["trial_global_at_fire"] = started_trial_global
                fire_log.append(event)
                last_fired_trial_global = started_trial_global
                # Phase C: wait for current trial to advance away
                # (we've fired; trial ends; jsPsych transitions). This
                # is detection of "trial done," not just "trial_id
                # changed" — the next test_trial may follow shortly.
                for _wait in range(40):
                    state = await page.evaluate(READ_STATE_JS)
                    if state.get("current_trial_global", -1) > started_trial_global:
                        break
                    await asyncio.sleep(0.05)
            findings["fire_log_count"] = len(fire_log)
            findings["phase_ended_early"] = phase_ended_early

            print("[5/5] Reading back jsPsych.data.get() and comparing…")
            await page.wait_for_timeout(1500)  # let last response register
            data_after = await page.evaluate(READ_DATA_JS) or []
            n_after = len(data_after)
            findings["recorded_after_fire"] = n_after
            new_records = data_after[n_before:n_before + len(fire_log)]
            findings["new_records_count"] = len(new_records)

            # Pair each fire with the platform record whose trial_index
            # matches the trial_global the bot was on at fire time.
            # The earlier index-pairing approach surfaced an off-by-one
            # — the bot's wait-loop detection occasionally caught a
            # trial that ended before the CDP fire landed, so the fire
            # went to the NEXT trial. Pairing by trial_global is robust.
            pairs = _pair_by_trial_index(fire_log, data_after)
            findings["pairs"] = pairs
            # Also compute the naive sequential-pairing for comparison,
            # so we can detect off-by-one and report it.
            naive_pairs = []
            for i, ev in enumerate(fire_log):
                rec = new_records[i] if i < len(new_records) else None
                naive_pairs.append({
                    "key_fired": ev["key"],
                    "recorded": rec.get("response") if rec else None,
                    "match": (rec is not None and rec.get("response") == ev["key"]),
                })
            findings["naive_pairs_match_count"] = sum(
                1 for p in naive_pairs if p["match"]
            )

            n_matched = sum(1 for p in pairs if p["match"])
            fidelity_pct = (100.0 * n_matched / len(pairs)) if pairs else 0.0
            findings["n_matched"] = n_matched
            findings["fidelity_pct"] = fidelity_pct

            # Apply spec thresholds
            if fidelity_pct >= 85.0:
                findings["band"] = "≥85% (proceed_as_planned)"
                findings["outcome"] = "kill_switch_passed_clean"
                findings["verdict_summary"] = (
                    f"CDP fidelity = {fidelity_pct:.1f}% (≥85%). Proceed to "
                    f"Phase 4b as planned. CDP alone is materially closing "
                    f"the gap; focus management + listener-target detection "
                    f"add additive improvements rather than carrying the "
                    f"bulk of the lift."
                )
            elif fidelity_pct >= 60.0:
                findings["band"] = "60-85% (proceed_with_flag)"
                findings["outcome"] = "kill_switch_passed_with_flag"
                findings["verdict_summary"] = (
                    f"CDP fidelity = {fidelity_pct:.1f}% (in [60, 85)). "
                    f"Proceed to Phase 4b, but acknowledge that focus "
                    f"management + listener-target detection (the '+ focus' "
                    f"parts of Phase 4b) are now doing more lifting than "
                    f"CDP alone. Phase 7 §6 fidelity expectations may need "
                    f"re-examination after Phase 4b lands."
                )
            else:
                findings["band"] = "<60% (escalate)"
                findings["outcome"] = "kill_switch_failed"
                findings["verdict_summary"] = (
                    f"CDP fidelity = {fidelity_pct:.1f}% (<60%). CDP alone "
                    f"does NOT materially improve over page.keyboard.press's "
                    f"SP7 44% baseline. Escalate to project owner. Options: "
                    f"(i) alternative CDP fields, (ii) hybrid CDP + targeted "
                    f"JS dispatch, (iii) reconsider input-layer claim."
                )
        finally:
            await browser.close()
    return findings


def render_findings_md(findings: dict) -> str:
    lines = [
        "# SP11 Phase 4a — CDP keypress feasibility spike",
        "",
        f"**Probed at:** {findings.get('probed_at_iso')}",
        f"**URL:** `{findings.get('url')}`",
        f"**N keypresses fired:** {findings.get('fire_log_count', 'n/a')}",
        f"**Outcome:** `{findings.get('outcome')}`",
        f"**Threshold band:** {findings.get('band', 'n/a')}",
        f"**Fidelity (bot_pressed == platform_recorded):** "
        f"**{findings.get('fidelity_pct', 0.0):.1f}%** "
        f"({findings.get('n_matched', 0)}/{findings.get('fire_log_count', 0)})",
        "",
        "## Verdict",
        "",
        findings.get("verdict_summary", "(no summary)"),
        "",
        "## Phase context (per Phase 4a user note 1)",
        "",
        "The spike fired into the **test phase** only, not instructions",
        "or practice. The wait-for-test-phase loop polled",
        "`jsPsych.data.get().values()` until a `trial_id == 'test_trial'`",
        "record appeared AND the current trial was also `test_trial`.",
        "Practice trials timed out naturally (no responses fired during",
        "them).",
        "",
        f"- Test-phase reached: `{findings.get('test_phase_check', {}).get('reached')}`",
        f"- Test trials recorded before spike fired: `{findings.get('recorded_before_fire')}`",
        f"- Test trials recorded after spike fired: `{findings.get('recorded_after_fire')}`",
        f"- Net new records during spike: `{findings.get('new_records_count')}`",
        "",
        "## Keys used",
        "",
        f"`{findings.get('keys_used')}`",
        "",
        "## Per-fire pairing (first 10 of N)",
        "",
        "```json",
        json.dumps(findings.get("pairs", [])[:10], indent=2, default=str),
        "```",
        "",
        "## Per-fire pairing (last 10)",
        "",
        "```json",
        json.dumps(findings.get("pairs", [])[-10:], indent=2, default=str),
        "```",
        "",
        "## Mismatch sample (first 10 non-matching pairs)",
        "",
        "```json",
        json.dumps([p for p in findings.get("pairs", []) if not p.get("match")][:10],
                   indent=2, default=str),
        "```",
        "",
        "## Decision per spec §4 Phase 4a thresholds",
        "",
        "- ≥ 85% → proceed to Phase 4b as planned",
        "- 60-85% → proceed with flag (focus + target detection do more lifting)",
        "- < 60% → escalate to project owner",
        "",
        f"**This run falls in the `{findings.get('band')}` band.**",
        "",
        "## Phase 8 implication",
        "",
        "Phase 4a is a feasibility spike, not a Phase 7 measurement. The",
        "spike's per-fire fidelity number reflects ONE session on ONE",
        "paradigm; Phase 7's N=30 sequential runs will produce the",
        "authoritative §6 H1/H2 numbers per paradigm. The spike's job",
        "is to ensure the rest of Phase 4 isn't built on a fundamentally",
        "broken delivery channel.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    findings = asyncio.run(main())
    print()
    print("=" * 60)
    print(f"OUTCOME: {findings.get('outcome')}")
    print(f"BAND:    {findings.get('band', 'n/a')}")
    print(f"FIDELITY: {findings.get('fidelity_pct', 0.0):.1f}%")
    print(f"SUMMARY: {findings.get('verdict_summary', '(none)')}")
    print("=" * 60)
    out_path = Path("docs/sp11-phase4a-spike.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_findings_md(findings))
    print(f"\nFindings written to {out_path}")
