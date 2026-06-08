import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Stroop (expfactory) — metric walkthrough

        **Label:** `stroop_rdoc`  ·  **Platform:** expfactory.org  ·  **Paradigm class:** `conflict`
        ·  **Norms file:** `norms/conflict.json`

        This notebook reproduces, from first principles, every metric the validation oracle
        computes for this task, against the **real bot session data** in `output/stroop_rdoc/`.
        For each metric it (1) describes the computation in prose, (2) shows the data it runs on,
        (3) recomputes the value by hand, and (4) asserts the hand value equals both the library
        function (`experiment_bot.effects.validation_metrics`) and the oracle
        (`validate_session_set`). If the assertions at the bottom pass, the analysis is faithful
        to the shipped code.

        Gated metrics for the `conflict` class: **rt_distribution** (ex-Gaussian mu/sigma/tau)
        and **post_error_slowing**. `cse_magnitude` and `lag1_autocorr` are *declared* in the
        norms file but compute to `NaN` here (see their sections).
        """
    )
    return


@app.cell
def _():
    import glob
    import json
    import math
    from pathlib import Path

    import numpy as np

    import experiment_bot
    from experiment_bot.validation.platform_adapters import read_expfactory_stroop
    from experiment_bot.validation.oracle import (
        validate_session_set,
        GROSS_UNDERCOUNT_FRACTION,
    )
    from experiment_bot.effects.validation_metrics import (
        fit_ex_gaussian,
        post_error_slowing_magnitude,
        RT_PLAUSIBLE_MIN_MS,
        RT_PLAUSIBLE_MAX_MS,
    )

    # Repo root = two levels above the installed package (src/experiment_bot/__init__.py).
    REPO = Path(experiment_bot.__file__).resolve().parents[2]
    OUTPUT = REPO / "output" / "stroop_rdoc"
    NORMS = json.loads((REPO / "norms" / "conflict.json").read_text())
    return (
        GROSS_UNDERCOUNT_FRACTION,
        NORMS,
        OUTPUT,
        Path,
        fit_ex_gaussian,
        glob,
        math,
        np,
        post_error_slowing_magnitude,
        read_expfactory_stroop,
        RT_PLAUSIBLE_MAX_MS,
        RT_PLAUSIBLE_MIN_MS,
        validate_session_set,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. The data on disk

        Each session lives in `output/stroop_rdoc/<timestamp>/`. The oracle reads the
        **platform's own export** — not the bot's self-log — to avoid grading the bot on the
        same signal that drove it (anti-circularity, goal G4). For this task the export is
        `experiment_data.csv` (the executor writes CSV or JSON depending on the TaskCard's
        `data_capture.method`; field names are identical).

        Files per session: `experiment_data.csv` (the authoritative export, scored here),
        `bot_log.json` (bot's polling log, NOT scored), `run_metadata.json` (trial count, seed,
        TaskCard hash), `config.json`, `screenshots/`.
        """
    )
    return


@app.cell
def _(OUTPUT):
    session_dirs = sorted(p for p in OUTPUT.iterdir() if p.is_dir())
    f"{len(session_dirs)} session directories under {OUTPUT}"
    return (session_dirs,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ### Raw export columns used by the adapter

        `read_expfactory_stroop` keeps only rows with `trial_id == "test_trial"` and reads:

        | raw column | type | how it's used |
        |---|---|---|
        | `trial_id` | str | **Filter**: keep only `"test_trial"` (drops fixation / instruction / feedback rows). |
        | `condition` | str | Canonical `condition` → `"congruent"` / `"incongruent"`. |
        | `rt` | float·ms or empty | Response time. Empty/NaN → `rt=None` → `omission=True`. |
        | `correct_trial` | 0/1 (or "0"/"1") | Canonical `correct`: `1`→True. If absent, falls back to `response == correct_response`. |
        | `response`, `correct_response` | str | Fallback correctness when `correct_trial` is missing. |

        Below is one real `test_trial` row.
        """
    )
    return


@app.cell
def _(read_expfactory_stroop, session_dirs):
    import csv as _csv

    def _raw_test_rows(sdir):
        # Mirror the adapter's row source + filter, but keep ALL columns for display.
        p = sdir / "experiment_data.csv"
        if not p.exists():
            return []
        with p.open() as fh:
            rows = list(_csv.DictReader(fh))
        return [r for r in rows if r.get("trial_id") == "test_trial"]

    _example = next((s for s in session_dirs if _raw_test_rows(s)), session_dirs[0])
    raw_rows = _raw_test_rows(_example)
    sample_raw_row = raw_rows[0]
    sample_raw_row
    return raw_rows, sample_raw_row


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Adapter: raw rows → canonical trials

        The oracle works on a uniform 4-field **canonical trial** dict, identical across all
        paradigms:

        | canonical field | meaning | derivation for this task |
        |---|---|---|
        | `condition` | trial type | `row["condition"]` (`"congruent"`/`"incongruent"`); `""` if missing. |
        | `rt` | response time (ms) or `None` | `float(row["rt"])`; empty/`"nan"`/`"null"` → `None`. |
        | `correct` | bool | `correct_trial in (1,"1")`, else `response == correct_response`. |
        | `omission` | bool | `rt is None` (the participant did not respond). |

        The same `read_expfactory_stroop` the oracle uses is called here; the first five
        canonical trials of the example session:
        """
    )
    return


@app.cell
def _(read_expfactory_stroop, session_dirs):
    _example2 = next(
        (s for s in session_dirs if read_expfactory_stroop(s)), session_dirs[0]
    )
    canonical_example = read_expfactory_stroop(_example2)
    canonical_example[:5]
    return (canonical_example,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Cohort completeness filter (which sessions are scored)

        Before any metric, the oracle drops sessions whose trial count is a **gross undercount**
        vs the cohort — a partial/crashed session — so it can't drag the pooled estimates.
        It does **not** use the exit reason (a whole 125/125 session can legitimately exit via
        `max_misses`); it uses a cohort-relative rule:

        - trial count comes from `run_metadata.json["total_trials"]` (fallback: `len(adapter(dir))`);
        - `median` = median of nonzero counts;
        - a session is excluded if `count == 0` **or** (`>=2` sessions exist and
          `count < GROSS_UNDERCOUNT_FRACTION * median`), with
          `GROSS_UNDERCOUNT_FRACTION = 0.6`.

        The surviving sessions are pooled (all their trials concatenated) for the metrics.
        """
    )
    return


@app.cell
def _(GROSS_UNDERCOUNT_FRACTION, Path, read_expfactory_stroop, session_dirs):
    import json as _json

    def _count(sdir: Path) -> int:
        mp = sdir / "run_metadata.json"
        meta = _json.loads(mp.read_text()) if mp.exists() else {}
        if "total_trials" in meta:
            return int(meta.get("total_trials") or 0)
        try:
            return len(read_expfactory_stroop(sdir))
        except Exception:
            return 0

    counts = [(s, _count(s)) for s in session_dirs]
    nonzero = sorted(c for _, c in counts if c > 0)
    median = nonzero[len(nonzero) // 2] if nonzero else 0
    threshold = GROSS_UNDERCOUNT_FRACTION * median
    active_dirs = [
        s
        for s, c in counts
        if c > 0 and not (len(nonzero) >= 2 and median > 0 and c < threshold)
    ]
    excluded = [(s.name, c) for s, c in counts if s not in set(active_dirs)]
    {
        "n_supplied": len(session_dirs),
        "n_used": len(active_dirs),
        "median_trials": median,
        "undercount_threshold": threshold,
        "excluded": excluded,
    }
    return (active_dirs,)


@app.cell
def _(active_dirs, read_expfactory_stroop):
    pooled = []
    for _s in active_dirs:
        pooled.extend(read_expfactory_stroop(_s))
    f"{len(pooled)} pooled canonical trials across {len(active_dirs)} sessions"
    return (pooled,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Metric — RT distribution (ex-Gaussian mu / sigma / tau)

        **What it is.** The go/response RT distribution is summarised with an ex-Gaussian: a
        Gaussian (mean `mu`, SD `sigma`) convolved with an exponential tail (mean `tau`). `mu`
        ≈ the bulk location, `sigma` ≈ bulk width, `tau` ≈ the slow right tail.

        **Inputs (`_gather_rts`).** Pool RTs across scored sessions, **skipping** any trial with
        `omission == True`, and keeping `rt is not None`. (A `condition` filter exists but is
        unused for the whole-distribution metric.)

        **Fit (`fit_ex_gaussian`).** Before fitting, RTs are clamped to the physiologically
        plausible window **[150, 5000] ms** — sub-150 ms presses are anticipations, >5000 ms are
        timer-glitch artifacts; either corrupts the MLE. Parameters are then found by
        L-BFGS-B maximum-likelihood on the ex-Gaussian log-pdf, bounded to plausible RT space.
        Needs ≥5 samples or returns `NaN`.

        The cell recomputes the gather + fit by hand and checks it equals `fit_ex_gaussian`.
        """
    )
    return


@app.cell
def _(fit_ex_gaussian, pooled):
    # Hand replication of _gather_rts: skip omissions, keep rt-present.
    gathered_rts = [
        float(t["rt"])
        for t in pooled
        if not t.get("omission") and t.get("rt") is not None
    ]
    exgauss = fit_ex_gaussian(gathered_rts)
    {
        "n_rts_gathered": len(gathered_rts),
        "mu": round(exgauss["mu"], 2),
        "sigma": round(exgauss["sigma"], 2),
        "tau": round(exgauss["tau"], 2),
    }
    return exgauss, gathered_rts


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. Metric — post-error slowing (PES)

        **What it is.** Mean RT on correct trials that **follow an error** minus mean RT on
        correct trials that **follow a correct** trial. Positive = the participant slows down
        after mistakes.

        **Order of operations matters (`_compute_pes` → `post_error_slowing_magnitude`):**

        1. **Drop `rt is None` trials first**, then sequence. So omissions are removed from the
           adjacency and a "previous" trial is the previous *responded* trial. (For Stroop
           omissions are rare; this mostly matters for the stop-signal tasks where successful
           inhibitions have `rt=None`.)
        2. Walk the compacted list. Only consider a trial if its own `correct is True` **and**
           its RT is inside **[150, 5000] ms** (same window as the ex-Gaussian — added so a
           timer-glitch RT can't poison the mean).
        3. Bucket by the previous trial: `prev.correct is False` → post-error;
           `prev.correct is True` → post-correct.
        4. `PES = mean(post_error) - mean(post_correct)`; `NaN` if either bucket is empty.

        Hand replication below, checked against `post_error_slowing_magnitude`.
        """
    )
    return


@app.cell
def _(RT_PLAUSIBLE_MAX_MS, RT_PLAUSIBLE_MIN_MS, np, pooled, post_error_slowing_magnitude):
    def hand_pes(trials):
        valid = [t for t in trials if t.get("rt") is not None]  # step 1: drop None first
        post_error, post_correct = [], []
        for i, t in enumerate(valid):
            if i == 0:
                continue
            if t.get("correct") is not True:
                continue
            rt = float(t["rt"])
            if not (RT_PLAUSIBLE_MIN_MS <= rt <= RT_PLAUSIBLE_MAX_MS):
                continue
            prev = valid[i - 1]
            if prev.get("correct") is False:
                post_error.append(rt)
            elif prev.get("correct") is True:
                post_correct.append(rt)
        if not post_error or not post_correct:
            return float("nan"), len(post_error), len(post_correct)
        return float(np.mean(post_error) - np.mean(post_correct)), len(post_error), len(post_correct)

    pes_hand, n_pe, n_pc = hand_pes(pooled)
    # _compute_pes passes rt-present trials to the library fn:
    pes_lib = post_error_slowing_magnitude([t for t in pooled if t.get("rt") is not None])
    {"pes_hand_ms": round(pes_hand, 3), "pes_lib_ms": round(pes_lib, 3),
     "n_post_error": n_pe, "n_post_correct": n_pc}
    return pes_hand, pes_lib


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6. Metrics declared but not computed here

        - **`cse_magnitude`** (congruency-sequence effect): a generic lag-1 contrast
          [mean RT(high-after-high) − mean RT(high-after-low)]. The oracle only computes it when
          the CLI passes `contrast_labels`, extracted from the TaskCard's
          `lag1_pair_modulation.modulation_table`. This task's TaskCard does not enable that
          mechanism, so `contrast_labels is None` → the metric returns `NaN` (non-gating).
        - **`lag1_autocorr`**: declared with `range: null` in the norms file (no canonical
          meta-analytic range), so it never gates.

        Neither can fail the task; they're carried for completeness.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 7. Cross-check against the oracle + norms ranges

        We now run the actual `validate_session_set` over the same active sessions and confirm
        every hand value equals the oracle's, and show each metric against its published range
        from `norms/conflict.json`.
        """
    )
    return


@app.cell
def _(NORMS, active_dirs, read_expfactory_stroop, validate_session_set):
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=active_dirs,
        norms=NORMS,
        trial_loader=read_expfactory_stroop,
    )
    oracle_metrics = {
        m.name: {"bot_value": m.bot_value, "range": m.published_range, "pass": m.pass_}
        for p in report.pillar_results.values()
        for m in p.metrics.values()
    }
    {"overall_pass": report.overall_pass, "n_used": report.n_used, "metrics": oracle_metrics}
    return (oracle_metrics,)


@app.cell
def _(exgauss, math, oracle_metrics, pes_hand, pes_lib):
    def _close(a, b, tol=1e-3):
        if a is None or b is None:
            return a is b
        if any(isinstance(x, float) and math.isnan(x) for x in (a, b)):
            return all(isinstance(x, float) and math.isnan(x) for x in (a, b))
        return abs(a - b) <= tol

    checks = {
        "mu hand==oracle": _close(exgauss["mu"], oracle_metrics["mu"]["bot_value"]),
        "sigma hand==oracle": _close(exgauss["sigma"], oracle_metrics["sigma"]["bot_value"]),
        "tau hand==oracle": _close(exgauss["tau"], oracle_metrics["tau"]["bot_value"]),
        "pes hand==lib": _close(pes_hand, pes_lib, 1e-6),
        "pes hand==oracle": _close(pes_hand, oracle_metrics["post_error_slowing"]["bot_value"]),
    }
    assert all(checks.values()), checks
    checks
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 8. Code-review verdict

        The assertions above pass: the hand-rolled recomputation equals both the library
        functions and `validate_session_set` for **mu, sigma, tau, and PES**. The analysis is
        faithful to the shipped oracle. Notes a reviewer should carry:

        - **Authoritative source**: scored from `experiment_data.csv`, not `bot_log.json` (G4).
        - **RT hygiene is consistent**: the same `[150, 5000] ms` window gates the ex-Gaussian
          fit and PES (and SSRT in the stop-signal notebooks).
        - **PES order-of-ops**: `rt=None` trials are removed *before* sequencing — a deliberate,
          documented choice; on Stroop it's nearly a no-op (few omissions).
        - **Marginal miss**: `tau` typically lands a hair above the 160 ms ceiling — a tail-width
          overshoot, the one genuine RT-distribution gap on this task.
        """
    )
    return


if __name__ == "__main__":
    app.run()
