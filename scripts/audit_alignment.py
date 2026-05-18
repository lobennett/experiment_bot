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


def report(session_dir: Path) -> dict:
    bot, plat = load_session(session_dir)
    bot_test = [t for t in bot if is_bot_test_trial(t)]
    plat_test = [r for r in plat if is_real_test_trial(r)]
    if not bot_test or not plat_test:
        print(f"[{session_dir.name}] EMPTY — bot_test={len(bot_test)} plat_test={len(plat_test)}")
        return {
            "session": session_dir.name, "status": "empty",
            "n_bot": len(bot_test), "n_plat": len(plat_test),
        }
    offset, n, c = find_best_offset(bot_test, plat_test)
    pct = {k: 100.0 * v / n for k, v in c.items()}
    print(f"=== {session_dir.parent.name}/{session_dir.name} ===")
    print(f"  bot_test={len(bot_test)}, plat_test={len(plat_test)}, "
          f"best_offset={offset}, n_compared={n}")
    print(f"  pressed_eq_recorded: {pct['pressed_eq_recorded']:.1f}%  "
          f"(G0 target ≥ 90.0%)")
    print(f"  pressed_eq_expected: {pct['pressed_eq_expected']:.1f}%  "
          f"(=accuracy)")
    print(f"  condition_match:     {pct['condition_match']:.1f}%  "
          f"(should be 100% at correct offset)")
    return {
        "session": f"{session_dir.parent.name}/{session_dir.name}",
        "status": "ok", "best_offset": offset, "n_compared": n,
        "n_bot_test": len(bot_test), "n_plat_test": len(plat_test),
        "pressed_eq_recorded_pct": pct["pressed_eq_recorded"],
        "pressed_eq_expected_pct": pct["pressed_eq_expected"],
        "condition_match_pct": pct["condition_match"],
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
                  f"(offset={r['best_offset']}, n={r['n_compared']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
