"""SP11 Phase 7.0 — baseline URL snapshots.

Per Phase 7 user note 2: paranoia step. Before the N=30 sweep starts,
capture HTML + screenshot for each of the four dev paradigm URLs. If
any URL has changed mid-Phase-7 (e.g., expfactory pushes a new
revision), the runs straddling that change must be re-done or flagged.

Outputs land under `docs/phase7-baselines/<label>/`:
  - `landing.html` — page source as Playwright sees it post-load
  - `landing.png` — full-page screenshot
  - `meta.json` — URL, timestamp, sha256 of HTML, viewport

Usage:
  uv run python scripts/phase7_baseline_snapshots.py

After the sweep, run with --compare to diff the snapshot against the
current page state; any mismatch is flagged.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright


PARADIGM_URLS: dict[str, str] = {
    "expfactory_stroop": "https://deploy.expfactory.org/preview/10/",
    "expfactory_stop_signal": "https://deploy.expfactory.org/preview/9/",
    "stopit_stop_signal": (
        "https://kywch.github.io/STOP-IT/jsPsych_version/"
        "experiment-transformed-first.html"
    ),
    "cognitionrun_stroop": "https://strooptest.cognition.run/",
}

DEFAULT_DIR = Path("docs/phase7-baselines")


async def snapshot_one(label: str, url: str, out_dir: Path) -> dict:
    """Capture HTML + screenshot + meta for one URL."""
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "landing.html"
    png_path = out_dir / "landing.png"
    meta_path = out_dir / "meta.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await ctx.new_page()
            t0 = time.monotonic()
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            html = await page.content()
            png_bytes = await page.screenshot(type="png", full_page=True)
        finally:
            await browser.close()

    html_path.write_text(html)
    png_path.write_bytes(png_bytes)
    h = hashlib.sha256(html.encode("utf-8")).hexdigest()
    meta = {
        "label": label,
        "url": url,
        "captured_at_iso": time.strftime(
            "%Y-%m-%dT%H:%M:%S%z", time.localtime()
        ),
        "html_sha256": h,
        "html_bytes": len(html.encode("utf-8")),
        "load_time_s": round(time.monotonic() - t0, 2),
        "viewport": {"width": 1280, "height": 800},
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


async def compare_one(label: str, url: str, baseline_dir: Path) -> dict:
    """Re-snapshot ``url`` and compare against the baseline.

    Returns a dict with HTML-hash equality + size delta. A reviewer
    can additionally open landing.png side-by-side if needed.
    """
    baseline_meta_path = baseline_dir / "meta.json"
    if not baseline_meta_path.exists():
        return {"label": label, "error": "no_baseline"}
    baseline = json.loads(baseline_meta_path.read_text())
    current = await snapshot_one(label, url, baseline_dir.parent / f"{baseline_dir.name}__current")
    hash_match = baseline.get("html_sha256") == current.get("html_sha256")
    size_delta = current.get("html_bytes", 0) - baseline.get("html_bytes", 0)
    return {
        "label": label,
        "url": url,
        "baseline_captured_at": baseline.get("captured_at_iso"),
        "current_captured_at": current.get("captured_at_iso"),
        "html_hash_match": hash_match,
        "html_size_delta_bytes": size_delta,
    }


async def main_async(args: argparse.Namespace) -> int:
    base_dir = args.dir
    base_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []
    for label, url in PARADIGM_URLS.items():
        target = base_dir / label
        if args.compare:
            res = await compare_one(label, url, target)
            summary.append(res)
            tag = "MATCH" if res.get("html_hash_match") else "DRIFT"
            delta = res.get("html_size_delta_bytes", 0)
            print(f"  {label:<30s} {tag}  (Δbytes={delta:+d})")
        else:
            meta = await snapshot_one(label, url, target)
            summary.append(meta)
            print(f"  {label:<30s} captured "
                  f"({meta['html_bytes']} bytes, "
                  f"sha256={meta['html_sha256'][:16]}…)")
    summary_path = base_dir / ("compare_summary.json" if args.compare else "baseline_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"[ok] wrote {summary_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", type=Path, default=DEFAULT_DIR,
                   help="Where to write baseline snapshots (default: docs/phase7-baselines/).")
    p.add_argument("--compare", action="store_true",
                   help="Compare current URL state against existing baselines.")
    args = p.parse_args(argv)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
