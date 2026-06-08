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
        # Stop-signal (STOP-IT / kywch jsPsych) — metric walkthrough

        **Label:** `stop_signal_kywch_jspsych` (URL alias `stopit_stop_signal`)
        ·  **Platform:** kywch.github.io STOP-IT (jsPsych port)  ·  **Paradigm class:** `interrupt`
        ·  **Norms file:** `norms/interrupt.json`

        Same interrupt-class metrics as the expfactory stop-signal (SSRT + PES gate;
        rt_distribution descriptive). This task is also the **worked example of the RT-hygiene
        fix**: its raw export contains a handful of **timer-glitch trials with multi-second
        “RTs”** (up to ~1,077 s). §5 shows how the pooled PES is `225.7 ms` (nonsense) **without**
        the `[150, 5000] ms` window and `18.5 ms` (in range) **with** it — the inconsistency the
        oracle fix closed by sharing the ex-Gaussian's window with PES and SSRT.

        > **Note on the data directory:** sessions live under
        > `output/stop-it_stop-signal_task_(jspsych)/`, which is the executor's
        > `task.name`-derived folder; the *adapter label* is `stop_signal_kywch_jspsych`. Both
        > map to `read_stopit_stop_signal`.
        """
    )
    return


@app.cell
def _():
    import json
    import math
    from pathlib import Path

    import numpy as np

    import experiment_bot
    from experiment_bot.validation.platform_adapters import read_stopit_stop_signal
    from experiment_bot.validation.oracle import (
        validate_session_set,
        GROSS_UNDERCOUNT_FRACTION,
    )
    from experiment_bot.effects.validation_metrics import (
        fit_ex_gaussian,
        post_error_slowing_magnitude,
        ssrt_integration,
        RT_PLAUSIBLE_MIN_MS,
        RT_PLAUSIBLE_MAX_MS,
    )

    REPO = Path(experiment_bot.__file__).resolve().parents[2]
    OUTPUT = REPO / "output" / "stop-it_stop-signal_task_(jspsych)"
    NORMS = json.loads((REPO / "norms" / "interrupt.json").read_text())
    return (
        GROSS_UNDERCOUNT_FRACTION,
        NORMS,
        OUTPUT,
        Path,
        fit_ex_gaussian,
        math,
        np,
        post_error_slowing_magnitude,
        read_stopit_stop_signal,
        RT_PLAUSIBLE_MAX_MS,
        RT_PLAUSIBLE_MIN_MS,
        ssrt_integration,
        validate_session_set,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. The data on disk

        The scored export is `experiment_data.csv`. `read_stopit_stop_signal` keeps rows where
        `block_i` is one of `"1","2","3","4"` (block 0 is practice).

        ### Raw columns used by the adapter

        | raw column | type | how it's used |
        |---|---|---|
        | `block_i` | "0".."4" | **Filter**: keep test blocks `1–4`. |
        | `signal` | "yes"/"no" | Canonical `condition`: `"yes"`→`"stop"`, `"no"`→`"go"`. |
        | `rt` | float·ms or "NaN" | RT; `"NaN"`/empty → `None` → `omission=True`. |
        | `correct` | truthy str | Canonical `correct` via `_is_truthy_str` (`true`/`1`). |
        | `SSD` | float·ms | Stop-signal delay (SSRT only). |
        """
    )
    return


@app.cell
def _(OUTPUT):
    session_dirs = sorted(p for p in OUTPUT.iterdir() if p.is_dir())
    f"{len(session_dirs)} session directories under {OUTPUT}"
    return (session_dirs,)


@app.cell
def _(Path, session_dirs):
    import csv as _csv

    def _raw_test_rows(sdir: Path):
        cp = sdir / "experiment_data.csv"
        if not cp.exists():
            return []
        with cp.open() as fh:
            rows = list(_csv.DictReader(fh))
        return [r for r in rows if r.get("block_i") in ("1", "2", "3", "4")]

    _ex = next((s for s in session_dirs if _raw_test_rows(s)), session_dirs[0])
    raw_rows = _raw_test_rows(_ex)
    _stop_row = next((r for r in raw_rows if r.get("signal") == "yes"), raw_rows[0])
    {k: _stop_row.get(k) for k in ("block_i", "signal", "rt", "correct", "SSD")}
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Adapter: raw rows → canonical trials

        | canonical field | derivation |
        |---|---|
        | `condition` | `signal == "yes"` → `"stop"`, `signal == "no"` → `"go"`. |
        | `rt` | `float(row["rt"])`; `"NaN"`/empty → `None`. |
        | `correct` | `_is_truthy_str(row["correct"])`. |
        | `omission` | `rt is None` (stop trial → inhibited; go trial → miss). |
        | `ssd` | `float(row["SSD"])`. |

        First five canonical trials:
        """
    )
    return


@app.cell
def _(read_stopit_stop_signal, session_dirs):
    _ex2 = next((s for s in session_dirs if read_stopit_stop_signal(s)), session_dirs[0])
    canonical_example = read_stopit_stop_signal(_ex2)
    canonical_example[:5]
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Cohort completeness filter + pooling

        Same `count == 0` or `count < 0.6 * median` rule. The one session whose live URL never
        produced a CSV (a 0-trial run) is excluded as `zero_trials`.
        """
    )
    return


@app.cell
def _(GROSS_UNDERCOUNT_FRACTION, Path, read_stopit_stop_signal, session_dirs):
    import json as _json

    def _count(sdir: Path) -> int:
        mp = sdir / "run_metadata.json"
        meta = _json.loads(mp.read_text()) if mp.exists() else {}
        if "total_trials" in meta:
            return int(meta.get("total_trials") or 0)
        try:
            return len(read_stopit_stop_signal(sdir))
        except Exception:
            return 0

    counts = [(s, _count(s)) for s in session_dirs]
    nonzero = sorted(c for _, c in counts if c > 0)
    median = nonzero[len(nonzero) // 2] if nonzero else 0
    threshold = GROSS_UNDERCOUNT_FRACTION * median
    active_dirs = [
        s for s, c in counts
        if c > 0 and not (len(nonzero) >= 2 and median > 0 and c < threshold)
    ]
    {"n_supplied": len(session_dirs), "n_used": len(active_dirs),
     "median_trials": median, "undercount_threshold": threshold,
     "n_excluded": len(session_dirs) - len(active_dirs)}
    return (active_dirs,)


@app.cell
def _(active_dirs, read_stopit_stop_signal):
    pooled = []
    for _s in active_dirs:
        pooled.extend(read_stopit_stop_signal(_s))
    _go = sum(1 for t in pooled if t.get("condition") == "go")
    _stop = sum(1 for t in pooled if t.get("condition") == "stop")
    {"pooled_trials": len(pooled), "go": _go, "stop": _stop}
    return (pooled,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. The timer-glitch trials (why RT hygiene matters)

        A small number of trials carry physiologically impossible "RTs" — `omission == False`
        responses recorded at tens or hundreds of **seconds**. These are timeout / stuck-trial
        bookkeeping artifacts, not behavior. The cell quantifies them; §5 shows their effect on
        PES with and without the plausibility window.
        """
    )
    return


@app.cell
def _(RT_PLAUSIBLE_MAX_MS, pooled):
    rts_all = [float(t["rt"]) for t in pooled if t.get("rt") is not None]
    over_5s = [r for r in rts_all if r > RT_PLAUSIBLE_MAX_MS]
    {
        "n_responses": len(rts_all),
        "max_rt_ms": round(max(rts_all), 1) if rts_all else None,
        "max_rt_seconds": round(max(rts_all) / 1000, 1) if rts_all else None,
        "n_rt_over_5000ms": len(over_5s),
    }
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. PES — with vs without the plausibility window

        `hand_pes_windowed` is the shipped computation (`[150, 5000] ms` window).
        `hand_pes_raw` is the *old* behavior (no window). The raw version is dominated by a
        single multi-second post-error trial → a nonsense ~225 ms PES; the windowed version is
        ~18.5 ms (in the published `[10, 50] ms` range). Both are checked: the windowed value
        equals the library/oracle.
        """
    )
    return


@app.cell
def _(RT_PLAUSIBLE_MAX_MS, RT_PLAUSIBLE_MIN_MS, np, pooled, post_error_slowing_magnitude):
    def _pes(trials, window: bool):
        valid = [t for t in trials if t.get("rt") is not None]
        pe, pc = [], []
        for i, t in enumerate(valid):
            if i == 0:
                continue
            if t.get("correct") is not True:
                continue
            rt = float(t["rt"])
            if window and not (RT_PLAUSIBLE_MIN_MS <= rt <= RT_PLAUSIBLE_MAX_MS):
                continue
            prev = valid[i - 1]
            if prev.get("correct") is False:
                pe.append(rt)
            elif prev.get("correct") is True:
                pc.append(rt)
        if not pe or not pc:
            return float("nan")
        return float(np.mean(pe) - np.mean(pc))

    pes_raw = _pes(pooled, window=False)
    pes_hand = _pes(pooled, window=True)
    pes_lib = post_error_slowing_magnitude([t for t in pooled if t.get("rt") is not None])
    {
        "pes_raw_no_window_ms": round(pes_raw, 1),
        "pes_windowed_hand_ms": round(pes_hand, 3),
        "pes_windowed_lib_ms": round(pes_lib, 3),
    }
    return pes_hand, pes_lib


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6. Metric — SSRT (integration method)

        Identical to the expfactory stop-signal notebook:
        `SSRT = quantile(go_RT, p_respond) - mean_SSD`, with go-RTs clamped to `[150, 5000] ms`
        inside `ssrt_integration`. Inputs come from the platform's own `signal`, `rt`, `SSD`.
        """
    )
    return


@app.cell
def _(RT_PLAUSIBLE_MAX_MS, RT_PLAUSIBLE_MIN_MS, np, pooled, ssrt_integration):
    go_rts, ssd_samples = [], []
    stop_total = stop_responded = 0
    for t in pooled:
        c = t.get("condition")
        if c == "go":
            if t.get("rt") is not None:
                go_rts.append(float(t["rt"]))
        elif c == "stop":
            stop_total += 1
            if not t.get("omission"):
                stop_responded += 1
            if t.get("ssd") is not None:
                ssd_samples.append(float(t["ssd"]))
    p_respond = stop_responded / stop_total
    mean_ssd = sum(ssd_samples) / len(ssd_samples)
    go_windowed = [r for r in go_rts if RT_PLAUSIBLE_MIN_MS <= r <= RT_PLAUSIBLE_MAX_MS]
    ssrt_hand = float(np.quantile(np.array(go_windowed), p_respond)) - mean_ssd
    ssrt_lib = ssrt_integration(go_rts, p_respond, mean_ssd)
    {
        "p_respond_given_stop": round(p_respond, 4),
        "mean_ssd_ms": round(mean_ssd, 2),
        "ssrt_hand_ms": round(ssrt_hand, 3),
        "ssrt_lib_ms": round(ssrt_lib, 3),
    }
    return ssrt_hand, ssrt_lib


@app.cell
def _(mo):
    mo.md(r"""## 7. Cross-check against the oracle + norms ranges""")
    return


@app.cell
def _(NORMS, active_dirs, read_stopit_stop_signal, validate_session_set):
    report = validate_session_set(
        paradigm_class="interrupt",
        session_dirs=active_dirs,
        norms=NORMS,
        trial_loader=read_stopit_stop_signal,
    )
    oracle_metrics = {
        m.name: {"bot_value": m.bot_value, "range": m.published_range, "pass": m.pass_}
        for p in report.pillar_results.values()
        for m in p.metrics.values()
    }
    {"overall_pass": report.overall_pass, "n_used": report.n_used, "metrics": oracle_metrics}
    return (oracle_metrics,)


@app.cell
def _(math, oracle_metrics, pes_hand, pes_lib, ssrt_hand, ssrt_lib):
    def _close(a, b, tol=1e-3):
        if a is None or b is None:
            return a is b
        if any(isinstance(x, float) and math.isnan(x) for x in (a, b)):
            return all(isinstance(x, float) and math.isnan(x) for x in (a, b))
        return abs(a - b) <= tol

    checks = {
        "ssrt hand==lib": _close(ssrt_hand, ssrt_lib, 1e-6),
        "ssrt hand==oracle": _close(ssrt_hand, oracle_metrics["ssrt"]["bot_value"]),
        "pes(windowed) hand==lib": _close(pes_hand, pes_lib, 1e-6),
        "pes(windowed) hand==oracle": _close(pes_hand, oracle_metrics["post_error_slowing"]["bot_value"]),
    }
    assert all(checks.values()), checks
    checks
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 8. Code-review verdict

        Assertions pass: the **windowed** hand-rolled PES and SSRT equal the library and oracle.
        Reviewer notes:

        - **The RT-hygiene fix is correct and load-bearing here.** §5 makes the failure mode
          concrete: without `[150, 5000] ms`, one multi-second post-error trial drove PES to
          ~225 ms; the window restores it to ~18.5 ms (in range). The same window now guards the
          ex-Gaussian fit, PES, and the SSRT go-RT quantile — one consistent rule.
        - **SSRT remains the not-framework-controlled metric (L20)**; its marginal miss (~1–2 ms
          over the 280 ceiling) is staircase-driven, and the window barely moved it — confirming
          the SSRT miss is *not* RT contamination.
        - **All inputs are from `experiment_data.csv`** (the platform export), preserving G4
          anti-circularity.
        """
    )
    return


if __name__ == "__main__":
    app.run()
