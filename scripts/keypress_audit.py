#!/usr/bin/env python3
"""SP7 keypress audit — paradigm-agnostic 4-way alignment analysis.

Compares, per trial:
  - bot_intended_correct_key (bot's resolved_key_pre_error)
  - bot_pressed_key          (bot's response_key, after _pick_wrong_key)
  - page_received_key        (first event in page_received_keys)
  - platform_recorded_resp   (platform CSV 'response' column)
  - platform_expected_resp   (platform CSV 'correct_response' column)

Uses PLATFORM_ADAPTERS dispatch so it works for any registered
paradigm (Flanker, n-back, stop-signal, stroop, future paradigms).

Usage:
  uv run python scripts/keypress_audit.py --label <task-name> [--output-dir output]
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from experiment_bot.validation.platform_adapters import PLATFORM_ADAPTERS


def _bot_stimulus_entries(bot_log: list[dict]) -> list[dict]:
    """Filter bot_log to actual stimulus-response entries."""
    return [
        t for t in bot_log
        if t.get("intended_error") in (True, False)
        and t.get("response_key") is not None
    ]


def _first_key(events) -> str | None:
    """Return the first {key} from a page_received_keys list, or None."""
    if not events:
        return None
    try:
        return events[0].get("key")
    except (AttributeError, IndexError, TypeError):
        return None


def _audit_session(ses_dir: Path, label: str) -> dict:
    """Run the 4-way audit on a single session. Returns counts."""
    bot_log = json.loads((ses_dir / "bot_log.json").read_text())
    csv_path = ses_dir / "experiment_data.csv"
    if not csv_path.exists():
        return {"error": f"no experiment_data.csv in {ses_dir}"}
    plat_rows = list(csv.DictReader(open(csv_path)))
    adapter = PLATFORM_ADAPTERS.get(label)
    if not adapter:
        return {"error": f"no adapter registered for label {label!r}"}
    test_rows = [r for r in plat_rows if r.get("trial_id") == "test_trial"]
    bot = _bot_stimulus_entries(bot_log)

    n = min(len(bot), len(test_rows))
    counts = Counter()
    for i in range(n):
        b = bot[i]
        p = test_rows[i]
        bot_intended = b.get("resolved_key_pre_error")
        bot_pressed = b.get("response_key")
        page_received = _first_key(b.get("page_received_keys"))
        plat_recorded = p.get("response")
        plat_expected = p.get("correct_response")

        counts["bot_pressed == page_received"] += (bot_pressed == page_received)
        counts["page_received == platform_recorded"] += (page_received == plat_recorded)
        counts["bot_pressed == platform_recorded"] += (bot_pressed == plat_recorded)
        counts["bot_intended == platform_expected"] += (bot_intended == plat_expected)

    return {
        "n_trials": n,
        "n_bot_log_entries": len(bot),
        "n_platform_trials": len(test_rows),
        "agreements": dict(counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True,
                        help="Paradigm label (matches output/<label>/ and PLATFORM_ADAPTERS key)")
    parser.add_argument("--output-dir", default="output",
                        help="Top-level output directory (default: output)")
    args = parser.parse_args()

    label_dir = Path(args.output_dir) / args.label
    if not label_dir.exists():
        raise SystemExit(f"no output directory: {label_dir}")

    print(f"=== SP7 keypress audit: {args.label} ===")
    print()
    total = Counter()
    total_n = 0
    for ses in sorted(label_dir.iterdir()):
        if not ses.is_dir():
            continue
        result = _audit_session(ses, args.label)
        if "error" in result:
            print(f"  {ses.name}: ERROR — {result['error']}")
            continue
        n = result["n_trials"]
        total_n += n
        a = result["agreements"]
        print(f"  {ses.name}: n={n} (bot_log={result['n_bot_log_entries']}, plat={result['n_platform_trials']})")
        for key, val in a.items():
            pct = 100 * val / n if n else 0
            print(f"    {key}: {val}/{n} = {pct:.1f}%")
            total[key] += val
        print()

    print(f"AGGREGATE across {total_n} trials:")
    for key, val in total.items():
        pct = 100 * val / total_n if total_n else 0
        print(f"  {key}: {val}/{total_n} = {pct:.1f}%")


if __name__ == "__main__":
    main()
