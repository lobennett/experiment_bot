#!/usr/bin/env python3
"""SP10 per-trial fidelity audit.

For a given session directory (containing bot_log.json and
experiment_data.json), compute the per-trial alignment between what the
bot pressed and what the platform recorded.

Auto-detects the bot-side offset so that practice / attention / warmup
trials don't shift the index alignment. Reports the offset that
maximizes condition_match.

Usage:
  uv run python scripts/audit_alignment.py output/<task>/<timestamp>/
  uv run python scripts/audit_alignment.py output/expfactory_stroop/2026-05-17_22-19-47/
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


def load_session(session_dir: Path) -> tuple[list[dict], list[dict]]:
    bot = json.loads((session_dir / "bot_log.json").read_text())
    plat = json.loads((session_dir / "experiment_data.json").read_text())
    return bot, plat


def is_real_test_trial(row: dict) -> bool:
    """Platform-side filter: rows that are the paradigm's actual test
    trials (not instructions, fixations, ITIs, feedback, attention checks,
    practice).

    Two paradigm conventions in expfactory:
    - stroop / flanker / n_back: trial_type='html-keyboard-response',
      filter by trial_id == 'test_trial'.
    - stop_signal: trial_type='poldracklab-stop-signal',
      filter by exp_stage == 'test' (no trial_id).
    """
    tt = (row.get("trial_type") or "").lower()
    if tt == "poldracklab-stop-signal":
        return row.get("exp_stage") == "test"
    tid = row.get("trial_id") or ""
    if "test_trial" in tid:
        # Defensive filter; expfactory keeps display rows separate from
        # the test_trial response rows, but stay strict in case a
        # paradigm reuses trial_id loosely.
        if "fixation" in tid or "ITI" in tid or "feedback" in tid:
            return False
        if "attention_check" in tid:
            return False
        return True
    return False


def is_bot_test_trial(t: dict) -> bool:
    """Bot-side filter: type='trial' entries that look like a real test
    trial. Two signals:

    - Condition is a non-default label (stroop, flanker — paradigms
      whose trial.data.condition resolves at runtime).
    - OR the bot delivered a non-Enter key (n_back, stop_signal —
      paradigms where data.condition stays undefined but the bot still
      fires real test keys via random fallback).

    Instruction-screen trials use Enter; filtering those out separates
    the test phase reliably.
    """
    if t.get("type") != "trial":
        return False
    if t.get("condition") not in (None, "default"):
        return True
    rk = t.get("response_key")
    if rk is not None and rk != "Enter":
        return True
    return False


def score_alignment(
    bot_test: list[dict], plat_test: list[dict], offset: int,
) -> tuple[int, dict[str, int]]:
    """Return (n_compared, counter) for the given bot-side offset."""
    sliced = bot_test[offset:]
    n = min(len(sliced), len(plat_test))
    c: Counter[str] = Counter()
    for i in range(n):
        b, p = sliced[i], plat_test[i]
        c["pressed_eq_recorded"] += (b.get("response_key") == p.get("response"))
        c["pressed_eq_expected"] += (b.get("response_key") == p.get("correct_response"))
        c["condition_match"] += (b.get("condition") == p.get("condition"))
    return n, dict(c)


def find_best_offset(
    bot_test: list[dict], plat_test: list[dict], max_offset: int = 50,
) -> tuple[int, int, dict[str, int]]:
    """Use pressed_eq_recorded as the optimization signal (works whether
    or not the bot can read trial.data.condition). Condition_match is
    secondary because paradigms like n_back don't expose condition at
    runtime, even when the hook delivers perfectly.
    """
    best = (0, *score_alignment(bot_test, plat_test, 0))
    for k in range(1, max_offset + 1):
        if len(bot_test) - k < 10:
            break
        n, c = score_alignment(bot_test, plat_test, k)
        if c["pressed_eq_recorded"] > best[2]["pressed_eq_recorded"]:
            best = (k, n, c)
    return best


def rt_match_audit(
    bot_trials: list[dict], plat_test: list[dict], rt_tolerance_ms: float = 1.0,
) -> dict:
    """For each platform test trial with a non-null rt, find the bot
    trial whose rt_ms matches within tolerance. RT is a near-unique
    per-trial signature (sub-millisecond precision), so a match here
    is strong evidence the same physical trial.

    Returns counts: total, plat_none (platform recorded no response,
    typically a withhold or timeout), matched (rt-matched fired
    trials), pressed_eq_recorded (bot.key == plat.response on
    rt-matched trials).
    """
    bot_rts = [(i, t["rt_ms"]) for i, t in enumerate(bot_trials)
                if t.get("rt_ms") is not None]
    c = Counter()
    c["total"] = len(plat_test)
    for p in plat_test:
        prt_raw = p.get("rt")
        if prt_raw is None or prt_raw == "None":
            c["plat_none"] += 1
            continue
        prt = float(prt_raw)
        best_i, best_rt = min(bot_rts, key=lambda x: abs(x[1] - prt))
        if abs(best_rt - prt) >= rt_tolerance_ms:
            continue
        c["matched"] += 1
        b = bot_trials[best_i]
        if b.get("response_key") == p.get("response"):
            c["pressed_eq_recorded"] += 1
        if b.get("response_key") == p.get("correct_response"):
            c["pressed_eq_expected"] += 1
    return dict(c)


def report(session_dir: Path) -> dict:
    bot, plat = load_session(session_dir)
    bot_trials = [t for t in bot if t.get("type") == "trial"]
    plat_test = [r for r in plat if is_real_test_trial(r)]
    if not bot_trials or not plat_test:
        print(f"[{session_dir.name}] EMPTY — bot_trials={len(bot_trials)} plat_test={len(plat_test)}")
        return {
            "session": session_dir.name, "status": "empty",
            "n_bot": len(bot_trials), "n_plat": len(plat_test),
        }
    c = rt_match_audit(bot_trials, plat_test)
    total = c["total"]
    matched = c.get("matched", 0)
    plat_none = c.get("plat_none", 0)
    n_with_rt = total - plat_none
    # Score fidelity on rt-matched (fired) trials. Withhold trials
    # (plat.rt=None) aren't measured here — they're reported as a
    # separate count for paradigms like stop-signal where withholding
    # is the intended behavior on some trials.
    pressed_eq_recorded_pct = (100.0 * c.get("pressed_eq_recorded", 0) / matched) if matched else 0.0
    pressed_eq_expected_pct = (100.0 * c.get("pressed_eq_expected", 0) / matched) if matched else 0.0
    matched_pct = (100.0 * matched / n_with_rt) if n_with_rt else 0.0
    print(f"=== {session_dir.parent.name}/{session_dir.name} ===")
    print(f"  bot_trials={len(bot_trials)}, plat_test={total} "
          f"(with_rt={n_with_rt}, plat_none={plat_none})")
    print(f"  bot rt-matched to fired trials:        {matched}/{n_with_rt} ({matched_pct:.1f}%)")
    print(f"  pressed_eq_recorded (over matched):    {pressed_eq_recorded_pct:.1f}%  (G0 target ≥ 90.0%)")
    print(f"  pressed_eq_expected (over matched):    {pressed_eq_expected_pct:.1f}%  (=accuracy)")
    if plat_none:
        print(f"  platform withhold trials:              {plat_none} ({100*plat_none/total:.1f}% of test rows)")
    return {
        "session": f"{session_dir.parent.name}/{session_dir.name}",
        "status": "ok",
        "n_bot": len(bot_trials), "n_plat_test": total,
        "n_matched": matched, "n_plat_none": plat_none,
        "pressed_eq_recorded_pct": pressed_eq_recorded_pct,
        "pressed_eq_expected_pct": pressed_eq_expected_pct,
    }


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    rows = [report(Path(a).resolve()) for a in args]
    if len(rows) > 1:
        print("\n=== summary ===")
        for r in rows:
            if r["status"] != "ok":
                print(f"  {r['session']}: {r['status']}")
                continue
            print(f"  {r['session']}: pressed_eq_recorded="
                  f"{r['pressed_eq_recorded_pct']:5.1f}% "
                  f"accuracy={r['pressed_eq_expected_pct']:5.1f}% "
                  f"(matched={r['n_matched']}/{r['n_plat_test']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
