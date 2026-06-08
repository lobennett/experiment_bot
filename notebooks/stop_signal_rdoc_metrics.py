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
        # Stop-signal (expfactory) — metric walkthrough

        **Label:** `stop_signal_rdoc`  ·  **Platform:** expfactory.org (poldracklab-stop-signal)
        ·  **Paradigm class:** `interrupt`  ·  **Norms file:** `norms/interrupt.json`

        Stop-signal tasks interleave **go** trials (respond fast) with **stop** trials (a stop
        signal says *don't* respond). The headline metric is **SSRT** — the latency of the
        covert stop process, estimated by the integration method. This notebook reproduces SSRT
        and post-error slowing from the real `output/stop_signal_rdoc/` data and checks them
        against the oracle.

        For the `interrupt` class the **ex-Gaussian ranges are `null`** in the norms file (no
        canonical meta-analytic range exists), so `rt_distribution` is **descriptive only** — it
        is computed and reported but cannot gate. Gating metrics: **post_error_slowing** and
        **ssrt**.
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
    from experiment_bot.validation.platform_adapters import read_expfactory_stop_signal
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
    OUTPUT = REPO / "output" / "stop_signal_rdoc"
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
        read_expfactory_stop_signal,
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

        The scored export is `experiment_data.json` (CSV is also supported — same fields).
        `read_expfactory_stop_signal` keeps rows with `trial_type == "poldracklab-stop-signal"`
        **and** `exp_stage == "test"`.

        ### Raw columns used by the adapter

        | raw column | type | how it's used |
        |---|---|---|
        | `trial_type` | str | **Filter**: `"poldracklab-stop-signal"`. |
        | `exp_stage` | str | **Filter**: `"test"` (drops practice). |
        | `condition` | str | Canonical `condition` → `"go"` / `"stop"`. |
        | `rt` | float·ms or null | RT; `null` ⇒ `rt=None` ⇒ `omission=True` (no response — a successful stop, or a go omission). |
        | `correct_trial` | 0/1 | Canonical `correct`: `1` ⇒ True. |
        | `SSD` | float·ms | Stop-signal delay (used only for SSRT). |

        One real **stop** test row (note `rt: null` = inhibited) below.
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
    import json as _json
    import csv as _csv

    def _raw_test_rows(sdir: Path):
        jp = sdir / "experiment_data.json"
        if jp.exists():
            data = _json.loads(jp.read_text())
            rows = data if isinstance(data, list) else []
        else:
            cp = sdir / "experiment_data.csv"
            if not cp.exists():
                return []
            with cp.open() as fh:
                rows = list(_csv.DictReader(fh))
        return [
            r for r in rows
            if r.get("trial_type") == "poldracklab-stop-signal" and r.get("exp_stage") == "test"
        ]

    _ex = next((s for s in session_dirs if _raw_test_rows(s)), session_dirs[0])
    raw_rows = _raw_test_rows(_ex)
    _stop_row = next((r for r in raw_rows if r.get("condition") == "stop"), raw_rows[0])
    {k: _stop_row.get(k) for k in ("trial_type", "exp_stage", "condition", "rt", "correct_trial", "SSD")}
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Adapter: raw rows → canonical trials

        | canonical field | derivation |
        |---|---|
        | `condition` | `row["condition"]` → `"go"` / `"stop"`. |
        | `rt` | `float(row["rt"])`; `null`/empty → `None`. |
        | `correct` | `correct_trial in (1, "1")`. |
        | `omission` | `rt is None`. For a **stop** trial this means inhibition succeeded; for a **go** trial it's a miss. |
        | `ssd` | `float(row["SSD"])` (stop-signal delay). |

        First five canonical trials:
        """
    )
    return


@app.cell
def _(read_expfactory_stop_signal, session_dirs):
    _ex2 = next((s for s in session_dirs if read_expfactory_stop_signal(s)), session_dirs[0])
    canonical_example = read_expfactory_stop_signal(_ex2)
    canonical_example[:5]
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Cohort completeness filter + pooling

        Same cohort-relative undercount rule (`count == 0` or `count < 0.6 * median` excluded),
        then surviving sessions' trials are concatenated.
        """
    )
    return


@app.cell
def _(GROSS_UNDERCOUNT_FRACTION, Path, read_expfactory_stop_signal, session_dirs):
    import json as _json2

    def _count(sdir: Path) -> int:
        mp = sdir / "run_metadata.json"
        meta = _json2.loads(mp.read_text()) if mp.exists() else {}
        if "total_trials" in meta:
            return int(meta.get("total_trials") or 0)
        try:
            return len(read_expfactory_stop_signal(sdir))
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
     "median_trials": median, "undercount_threshold": threshold}
    return (active_dirs,)


@app.cell
def _(active_dirs, read_expfactory_stop_signal):
    pooled = []
    for _s in active_dirs:
        pooled.extend(read_expfactory_stop_signal(_s))
    _go = sum(1 for t in pooled if t.get("condition") == "go")
    _stop = sum(1 for t in pooled if t.get("condition") == "stop")
    {"pooled_trials": len(pooled), "go": _go, "stop": _stop}
    return (pooled,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Metric — SSRT (integration method)

        **Definition (Verbruggen et al. 2019; `ssrt_integration`):**

        $$\mathrm{SSRT} = Q_{p}(\text{go RT distribution}) - \overline{\mathrm{SSD}}$$

        where `p = P(respond | stop)` is the probability the participant failed to inhibit, and
        $Q_p$ is the `p`-th quantile of the go-RT distribution. Intuition: if the stop process
        is slow, the participant responds on a large fraction of stop trials, so the relevant
        go-RT quantile is high and SSRT is large.

        **How the oracle assembles the inputs (`_compute_ssrt`):**

        - `go_rts` = RTs of all `condition == "go"` trials with `rt is not None`;
        - `stop_total` = count of `condition == "stop"` trials;
        - `stop_responded` = stop trials with `omission is False` (a response leaked through);
        - `ssd_samples` = `ssd` of stop trials; `mean_ssd = mean(ssd_samples)`;
        - `p_respond = stop_responded / stop_total`.

        Then `ssrt_integration` takes the quantile **after** clamping go-RTs to `[150, 5000] ms`
        (the recent fix — a timer-glitch go-RT would otherwise inflate the quantile and SSRT).
        The hand computation below is checked against `ssrt_integration`.
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
        "go_quantile_ms": round(float(np.quantile(np.array(go_windowed), p_respond)), 2),
        "ssrt_hand_ms": round(ssrt_hand, 3),
        "ssrt_lib_ms": round(ssrt_lib, 3),
    }
    return ssrt_hand, ssrt_lib


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. Metric — post-error slowing (PES)

        Same algorithm as the conflict notebooks (drop `rt=None` first → sequence → current
        `correct is True` and RT in `[150, 5000] ms` → bucket by previous trial). The
        `rt=None`-first step matters here: **successful stop trials have `rt=None`** and are
        therefore removed from the adjacency, so "post-error" pairs across them. After filtering,
        the responded errors are failed-stops and go-errors; the post-error/post-correct trials
        are go trials.
        """
    )
    return


@app.cell
def _(RT_PLAUSIBLE_MAX_MS, RT_PLAUSIBLE_MIN_MS, np, pooled, post_error_slowing_magnitude):
    def hand_pes(trials):
        valid = [t for t in trials if t.get("rt") is not None]
        pe, pc = [], []
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
                pe.append(rt)
            elif prev.get("correct") is True:
                pc.append(rt)
        if not pe or not pc:
            return float("nan"), len(pe), len(pc)
        return float(np.mean(pe) - np.mean(pc)), len(pe), len(pc)

    pes_hand, n_pe, n_pc = hand_pes(pooled)
    pes_lib = post_error_slowing_magnitude([t for t in pooled if t.get("rt") is not None])
    {"pes_hand_ms": round(pes_hand, 3), "pes_lib_ms": round(pes_lib, 3),
     "n_post_error": n_pe, "n_post_correct": n_pc}
    return pes_hand, pes_lib


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6. RT distribution (descriptive only)

        Computed for completeness; ranges are `null` in `norms/interrupt.json` so it never
        gates. Gathered over go+stop responded trials (omissions skipped), same fit.
        """
    )
    return


@app.cell
def _(fit_ex_gaussian, pooled):
    gathered_rts = [
        float(t["rt"]) for t in pooled
        if not t.get("omission") and t.get("rt") is not None
    ]
    exgauss = fit_ex_gaussian(gathered_rts)
    {k: round(v, 2) for k, v in exgauss.items()}
    return


@app.cell
def _(mo):
    mo.md(r"""## 7. Cross-check against the oracle + norms ranges""")
    return


@app.cell
def _(NORMS, active_dirs, read_expfactory_stop_signal, validate_session_set):
    report = validate_session_set(
        paradigm_class="interrupt",
        session_dirs=active_dirs,
        norms=NORMS,
        trial_loader=read_expfactory_stop_signal,
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

        Assertions pass: hand-rolled **SSRT** and **PES** equal both the library functions and
        `validate_session_set`. Reviewer notes:

        - **SSRT inputs are read from the platform export** (`SSD`, `condition`, `rt`), not the
          bot log. `p_respond` and `mean_ssd` come from the platform's own staircase.
        - **SSRT is not framework-controlled** (scope-of-validity **L20**): it's an emergent
          product of the platform's SSD staircase, so its pass/fail wobbles batch-to-batch
          independent of bot behavior. Treat a single batch's SSRT verdict with that caveat.
        - **rt_distribution is descriptive here** — no canonical interrupt-class ranges exist, so
          it cannot gate.
        - **PES `rt=None`-first sequencing** correctly removes successful-stop trials from the
          adjacency.
        """
    )
    return


if __name__ == "__main__":
    app.run()
