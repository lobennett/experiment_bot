#!/usr/bin/env python3
"""SP11 Phase 6 per-trial fidelity audit (paradigm-aware).

For a given session directory (containing bot_log.json and
experiment_data.{json,csv}), compute the per-trial alignment between
what the bot pressed and what the platform recorded.

Two pairing methods (per Phase 6 user note 5 + Phase 5a wiring):

  - **trial_counter** (SP11 input-layer path): bot fires record
    ``delivery.trial_marker_at_fire`` per trial; platform records
    carry a ``trial_index`` field. Pair by exact match. Robust to
    interstitial trials (ITIs, fixations) and to off-by-one timing
    artifacts.
  - **rt_match** (SP10 driver path): bot trials carry sampled
    ``rt_ms``; platform rows carry ``rt`` with sub-ms precision.
    Pair by minimum |bot_rt − plat_rt| within tolerance. Used for
    legacy SP10-era logs that lack ``delivery.trial_marker_at_fire``.

Pairing method is auto-selected from ``bot_log[*].delivery`` presence
and can be overridden via ``--pairing``. Per-paradigm test-row
filtering is via
:func:`experiment_bot.validation.platform_adapters.test_row_predicate_for_label`.
Channel breakdown (``cdp_dispatchKeyEvent`` vs
``keyboard_press_fallback`` vs ``page_keyboard_press``) appears in
the JSON output.

Usage:
  uv run python scripts/audit_alignment.py output/<task>/<timestamp>/ --label expfactory_stroop
  uv run python scripts/audit_alignment.py output/.../ --label stopit_stop_signal --pairing rt_match
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from experiment_bot.validation.platform_adapters import (
    test_row_predicate_for_label,
)


def load_session(session_dir: Path) -> tuple[list[dict], list[dict]]:
    bot = json.loads((session_dir / "bot_log.json").read_text())
    plat_json = session_dir / "experiment_data.json"
    plat_csv = session_dir / "experiment_data.csv"
    if plat_json.exists():
        plat = json.loads(plat_json.read_text())
    elif plat_csv.exists():
        import csv
        with plat_csv.open() as f:
            plat = list(csv.DictReader(f))
    else:
        plat = []
    return bot, plat


def is_bot_test_trial(t: dict) -> bool:
    """Bot-side filter: a trial entry that looks like a real test trial.

    Two signals:
      - condition is not None / 'default' (paradigms whose
        trial.data.condition resolves at runtime)
      - OR response_key is not None and not 'Enter' (paradigms where
        condition stays undefined but the bot still fires real test
        keys)
    """
    if t.get("condition") not in (None, "default"):
        return True
    rk = t.get("response_key")
    if rk is not None and rk != "Enter":
        return True
    return False


def detect_pairing_method(bot: list[dict]) -> str:
    """Auto-detect: trial_counter if any bot trial carries a
    delivery.trial_marker_at_fire, else rt_match."""
    for t in bot:
        d = t.get("delivery")
        if isinstance(d, dict) and d.get("trial_marker_at_fire") is not None:
            return "trial_counter"
    return "rt_match"


def _canonicalize_key(value) -> str | None:
    """Map a bot or platform key string to a canonical lowercase form
    so that ``ArrowLeft`` (CDP / jsPsych v7) and ``leftarrow``
    (jsPsych v6 recorded form) compare equal. Generic-enough to keep
    G1 (no per-paradigm baked-in conventions): lowercases, strips any
    leading 'arrow' prefix from v7 names and treats v6's 'leftarrow'
    form as already-canonical.

    Examples (canonical form on the right):
      ArrowLeft   → left
      ArrowRight  → right
      leftarrow   → left
      rightarrow  → right
      ' '         → space
      Space       → space
      ','         → ,
    """
    if value is None or value == "":
        return None
    raw = str(value)
    # Normalize space variants BEFORE stripping (otherwise " " → "")
    if raw == " " or raw.strip().lower() == "space":
        return "space"
    s = raw.strip().lower()
    if not s:
        return None
    if s.startswith("arrow"):
        s = s[len("arrow"):]
    elif s.endswith("arrow"):
        s = s[: -len("arrow")]
    return s


def _keys_equivalent(a, b) -> bool:
    """True iff the two keys canonicalize to the same string. ``None``
    or empty on either side returns False (treat as missing — not
    equivalent)."""
    ca = _canonicalize_key(a)
    cb = _canonicalize_key(b)
    if ca is None or cb is None:
        return False
    return ca == cb


def _normalize_marker(value) -> int | None:
    """Coerce a trial marker / trial_index to int. Platform records
    read from CSV arrive as strings ('245'); records read from JSON
    arrive as ints (245). Bot-side markers are always ints. Normalize
    everything to int for set-membership lookup."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def trial_counter_audit(
    bot_trials: list[dict], plat_test: list[dict],
) -> dict:
    """Pair by ``delivery.trial_marker_at_fire`` ↔ ``trial_index``.
    The Phase 4a spike confirmed 100% fidelity under this pairing on
    expfactory Stroop; the SP10-era index-pairing approach gave
    26%/2%/0% on the same runs because of trial-boundary races.
    """
    plat_by_idx: dict[int, dict] = {}
    for r in plat_test:
        idx = _normalize_marker(r.get("trial_index"))
        if idx is not None:
            plat_by_idx[idx] = r
    c: Counter[str] = Counter()
    per_channel: dict[str, Counter] = defaultdict(Counter)
    paired_details: list[dict] = []
    for t in bot_trials:
        delivery = t.get("delivery") or {}
        marker = _normalize_marker(delivery.get("trial_marker_at_fire"))
        channel = delivery.get("channel") or "unknown"
        if delivery.get("skipped"):
            c["bot_skipped"] += 1
            per_channel[channel]["bot_skipped"] += 1
            continue
        if marker is None:
            c["bot_no_marker"] += 1
            continue
        plat = plat_by_idx.get(marker)
        if plat is None:
            c["plat_no_match"] += 1
            per_channel[channel]["plat_no_match"] += 1
            continue
        c["paired"] += 1
        per_channel[channel]["paired"] += 1
        bot_key = t.get("response_key")
        plat_key = plat.get("response")
        plat_correct = plat.get("correct_response")
        if _keys_equivalent(bot_key, plat_key):
            c["pressed_eq_recorded"] += 1
            per_channel[channel]["pressed_eq_recorded"] += 1
        if _keys_equivalent(bot_key, plat_correct):
            c["pressed_eq_expected"] += 1
            per_channel[channel]["pressed_eq_expected"] += 1
        paired_details.append({
            "trial_marker": marker,
            "bot_key": bot_key,
            "plat_key": plat_key,
            "plat_correct": plat_correct,
            "channel": channel,
            "match_recorded": _keys_equivalent(bot_key, plat_key),
            "match_expected": _keys_equivalent(bot_key, plat_correct),
        })
    return {
        "method": "trial_counter",
        "total_bot_trials": len(bot_trials),
        "total_plat_test": len(plat_test),
        "counts": dict(c),
        "per_channel": {k: dict(v) for k, v in per_channel.items()},
        "paired_details": paired_details,
    }


def rt_match_audit(
    bot_trials: list[dict], plat_test: list[dict],
    rt_tolerance_ms: float = 1.0,
) -> dict:
    """Pair by RT proximity. Each bot trial's actual_rt_ms (or rt_ms)
    is compared to each platform trial's ``rt``; best match within
    tolerance wins. SP10 fallback path.
    """
    bot_indexed: list[tuple[int, float]] = []
    for i, t in enumerate(bot_trials):
        rt = t.get("actual_rt_ms") or t.get("rt_ms")
        if rt is not None:
            bot_indexed.append((i, float(rt)))
    if not bot_indexed:
        return {
            "method": "rt_match",
            "total_bot_trials": len(bot_trials),
            "total_plat_test": len(plat_test),
            "counts": {"total": len(plat_test), "matched": 0, "plat_none": 0},
            "per_channel": {},
            "paired_details": [],
        }
    c: Counter[str] = Counter()
    per_channel: dict[str, Counter] = defaultdict(Counter)
    paired_details: list[dict] = []
    c["total"] = len(plat_test)
    for p in plat_test:
        prt_raw = p.get("rt")
        if prt_raw in (None, "None", "", "NaN"):
            c["plat_none"] += 1
            continue
        try:
            prt = float(prt_raw)
        except (TypeError, ValueError):
            c["plat_none"] += 1
            continue
        best_i, best_rt = min(bot_indexed, key=lambda x: abs(x[1] - prt))
        if abs(best_rt - prt) >= rt_tolerance_ms:
            continue
        c["matched"] += 1
        bot = bot_trials[best_i]
        channel = (bot.get("delivery") or {}).get("channel") or "rt_legacy"
        per_channel[channel]["paired"] += 1
        bot_key = bot.get("response_key")
        if _keys_equivalent(bot_key, p.get("response")):
            c["pressed_eq_recorded"] += 1
            per_channel[channel]["pressed_eq_recorded"] += 1
        if _keys_equivalent(bot_key, p.get("correct_response")):
            c["pressed_eq_expected"] += 1
            per_channel[channel]["pressed_eq_expected"] += 1
        paired_details.append({
            "bot_index": best_i,
            "bot_rt_ms": best_rt,
            "plat_rt_ms": prt,
            "bot_key": bot_key,
            "plat_key": p.get("response"),
            "channel": channel,
            "match_recorded": _keys_equivalent(bot_key, p.get("response")),
        })
    return {
        "method": "rt_match",
        "total_bot_trials": len(bot_trials),
        "total_plat_test": len(plat_test),
        "counts": dict(c),
        "per_channel": {k: dict(v) for k, v in per_channel.items()},
        "paired_details": paired_details,
    }


def audit_session(
    session_dir: Path, *, label: str, pairing: str,
) -> dict:
    """Run the audit on one session directory. Returns a structured
    dict with paired counts, per-channel breakdown, and the pairing
    method used."""
    bot, plat = load_session(session_dir)
    predicate = test_row_predicate_for_label(label)
    if predicate is None:
        raise SystemExit(
            f"No test-row predicate registered for label {label!r}. "
            f"Register one in "
            f"experiment_bot.validation.platform_adapters.TEST_ROW_PREDICATES "
            f"before auditing this paradigm."
        )
    plat_test = [r for r in plat if predicate(r)]
    bot_trials = [t for t in bot if is_bot_test_trial(t)]

    if pairing == "auto":
        pairing = detect_pairing_method(bot)
    if pairing == "trial_counter":
        result = trial_counter_audit(bot_trials, plat_test)
    elif pairing == "rt_match":
        result = rt_match_audit(bot_trials, plat_test)
    else:
        raise SystemExit(
            f"Unknown pairing method {pairing!r}. "
            f"Choices: trial_counter, rt_match, auto."
        )
    result["label"] = label
    result["session_dir"] = str(session_dir)
    return result


def print_summary(result: dict) -> None:
    """Human-readable summary printed to stdout."""
    sd = Path(result["session_dir"]).name
    label = result["label"]
    method = result["method"]
    counts = result["counts"]
    print(f"=== {label}: {sd}  (pairing={method}) ===")
    print(f"  bot_trials={result['total_bot_trials']}, "
          f"plat_test={result['total_plat_test']}")
    if method == "trial_counter":
        paired = counts.get("paired", 0)
        ok = counts.get("pressed_eq_recorded", 0)
        eq = counts.get("pressed_eq_expected", 0)
        print(f"  paired by trial_marker: {paired}")
        if paired:
            print(f"  pressed_eq_recorded:    {ok}/{paired} "
                  f"({100.0 * ok / paired:.1f}%)")
            print(f"  pressed_eq_expected:    {eq}/{paired} "
                  f"({100.0 * eq / paired:.1f}%)")
        print(f"  skipped fires:          {counts.get('bot_skipped', 0)}")
        print(f"  bot fires w/o platform: {counts.get('plat_no_match', 0)}")
    else:  # rt_match
        total = counts.get("total", 0)
        matched = counts.get("matched", 0)
        ok = counts.get("pressed_eq_recorded", 0)
        plat_none = counts.get("plat_none", 0)
        print(f"  rt-matched:             {matched}/{total - plat_none}")
        if total:
            print(f"  pressed_eq_recorded:    {100.0 * ok / total:.1f}%")
    per_ch = result.get("per_channel") or {}
    if per_ch:
        print(f"  per-channel breakdown:")
        for chan, sub in per_ch.items():
            paired_ch = sub.get("paired", 0)
            ok_ch = sub.get("pressed_eq_recorded", 0)
            if paired_ch:
                print(f"    {chan:30s} {ok_ch}/{paired_ch} "
                      f"({100.0 * ok_ch / paired_ch:.1f}%)")
            else:
                print(f"    {chan:30s} (no paired fires)")


def main(argv: Iterable[str]) -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("session_dirs", nargs="+", type=Path,
                   help="Session directories (each containing bot_log.json).")
    p.add_argument("--label", required=True,
                   help="Paradigm label (e.g., expfactory_stroop, "
                        "stopit_stop_signal). Drives the per-paradigm "
                        "test-row predicate dispatch.")
    p.add_argument("--pairing", default="auto",
                   choices=("auto", "trial_counter", "rt_match"),
                   help="Pairing method. Default 'auto' detects from "
                        "bot_log delivery.trial_marker_at_fire presence: "
                        "present → trial_counter (SP11 input-layer), "
                        "absent → rt_match (SP10 driver legacy).")
    p.add_argument("--json", action="store_true",
                   help="Emit the structured result as JSON on stdout "
                        "in addition to the human summary.")
    args = p.parse_args(list(argv))

    summaries: list[dict] = []
    for sd in args.session_dirs:
        result = audit_session(
            sd.resolve(), label=args.label, pairing=args.pairing,
        )
        print_summary(result)
        summaries.append(result)
    if args.json:
        print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
