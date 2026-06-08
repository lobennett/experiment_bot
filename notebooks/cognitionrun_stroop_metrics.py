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
        # Stroop (cognition.run) — metric walkthrough

        **Label:** `stroop_online_(cognition.run)` (URL alias `cognitionrun_stroop`)
        ·  **Platform:** cognition.run  ·  **Paradigm class:** `conflict`
        ·  **Norms file:** `norms/conflict.json`

        Same conflict-class metrics as the expfactory Stroop, but a **different platform export**
        and two important wrinkles:

        1. **Correctness is not recoverable offline.** cognition.run's `condition` column is a
           numeric code, and the key→colour map lives only in the live page. The adapter
           therefore derives congruency from `text == colour` and marks every *responded* trial
           `correct = True`. Consequence: there are ~no "errors", so **post-error slowing is
           `NaN` (not computable)** for this task — by design, not a bug.
        2. **Short sessions (15 trials)** + occasional **timer-glitch RTs** (multi-second/“stuck”
           trials). These make the `[150, 5000] ms` plausibility window load-bearing: it's why
           the ex-Gaussian `tau` is sane despite raw RTs up to ~900 s in the pool.

        Gating metric here: **rt_distribution** (mu/sigma/tau).
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
    from experiment_bot.validation.platform_adapters import read_cognitionrun_stroop
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

    REPO = Path(experiment_bot.__file__).resolve().parents[2]
    OUTPUT = REPO / "output" / "stroop_online_(cognition.run)"
    NORMS = json.loads((REPO / "norms" / "conflict.json").read_text())
    return (
        GROSS_UNDERCOUNT_FRACTION,
        NORMS,
        OUTPUT,
        Path,
        fit_ex_gaussian,
        math,
        np,
        post_error_slowing_magnitude,
        read_cognitionrun_stroop,
        RT_PLAUSIBLE_MAX_MS,
        RT_PLAUSIBLE_MIN_MS,
        validate_session_set,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. The data on disk

        `output/stroop_online_(cognition.run)/<timestamp>/experiment_data.csv` is the scored
        export. `read_cognitionrun_stroop` keeps rows where `trial_type == "html-keyboard-response"`
        with a non-null `rt` and non-empty `text`/`colour`.

        ### Raw columns used by the adapter

        | raw column | type | how it's used |
        |---|---|---|
        | `trial_type` | str | **Filter**: keep `"html-keyboard-response"`. |
        | `rt` | float·ms | Response time. Rows with empty/NaN `rt` are dropped entirely. |
        | `text` | str | The word shown. Lower-cased. |
        | `colour` | str | The ink colour. Lower-cased. |
        | `response` | str | Key pressed. Non-empty ⇒ `correct=True` (see note above). |
        | `condition` | numeric | **Ignored** — not a usable Stroop label on this platform. |

        Canonical `condition` = `"congruent"` if `text == colour` else `"incongruent"`.
        """
    )
    return


@app.cell
def _(OUTPUT):
    session_dirs = sorted(p for p in OUTPUT.iterdir() if p.is_dir())
    f"{len(session_dirs)} session directories under {OUTPUT}"
    return (session_dirs,)


@app.cell
def _(session_dirs):
    import csv as _csv

    def _raw_rows(sdir):
        p = sdir / "experiment_data.csv"
        if not p.exists():
            return []
        with p.open() as fh:
            rows = list(_csv.DictReader(fh))
        return [r for r in rows if r.get("trial_type") == "html-keyboard-response"]

    _ex = next((s for s in session_dirs if _raw_rows(s)), session_dirs[0])
    raw_rows = _raw_rows(_ex)
    sample_raw_row = {
        k: raw_rows[0].get(k) for k in ("trial_type", "rt", "text", "colour", "response", "condition")
    }
    sample_raw_row
    return (raw_rows,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Adapter: raw rows → canonical trials

        | canonical field | derivation |
        |---|---|
        | `condition` | `"congruent"` if `text.lower() == colour.lower()` else `"incongruent"`. |
        | `rt` | `float(row["rt"])` (rows with no rt are already dropped). |
        | `correct` | `True` if `response` is non-empty (a key was pressed). *Cannot* reflect true accuracy offline. |
        | `omission` | `not responded`. |

        First five canonical trials from a session:
        """
    )
    return


@app.cell
def _(read_cognitionrun_stroop, session_dirs):
    _ex2 = next((s for s in session_dirs if read_cognitionrun_stroop(s)), session_dirs[0])
    canonical_example = read_cognitionrun_stroop(_ex2)
    canonical_example[:5]
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Cohort completeness filter

        Identical rule to the other paradigms: drop `count == 0` or
        `count < 0.6 * median` (cohort-relative gross undercount). Trial counts come from
        `run_metadata.json["total_trials"]` (fallback `len(adapter(dir))`). With 15-trial
        sessions the median is ~15 and the threshold ~9.
        """
    )
    return


@app.cell
def _(GROSS_UNDERCOUNT_FRACTION, Path, read_cognitionrun_stroop, session_dirs):
    import json as _json

    def _count(sdir: Path) -> int:
        mp = sdir / "run_metadata.json"
        meta = _json.loads(mp.read_text()) if mp.exists() else {}
        if "total_trials" in meta:
            return int(meta.get("total_trials") or 0)
        try:
            return len(read_cognitionrun_stroop(sdir))
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
    {
        "n_supplied": len(session_dirs),
        "n_used": len(active_dirs),
        "median_trials": median,
        "undercount_threshold": threshold,
    }
    return (active_dirs,)


@app.cell
def _(active_dirs, read_cognitionrun_stroop):
    pooled = []
    for _s in active_dirs:
        pooled.extend(read_cognitionrun_stroop(_s))
    f"{len(pooled)} pooled canonical trials across {len(active_dirs)} sessions"
    return (pooled,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Metric — RT distribution (ex-Gaussian) + the plausibility window

        Same computation as the expfactory Stroop: gather RTs (skip omissions), fit ex-Gaussian
        by L-BFGS-B MLE. The cell first shows how many pooled RTs fall **outside** the
        `[150, 5000] ms` window — these timer-glitch / stuck-trial RTs are dropped by
        `fit_ex_gaussian` before fitting, which is why `tau` stays in the tens-to-low-hundreds
        of ms even though the raw max RT is multiple seconds.
        """
    )
    return


@app.cell
def _(RT_PLAUSIBLE_MAX_MS, RT_PLAUSIBLE_MIN_MS, fit_ex_gaussian, pooled):
    gathered_rts = [
        float(t["rt"]) for t in pooled
        if not t.get("omission") and t.get("rt") is not None
    ]
    n_implausible = sum(
        1 for r in gathered_rts if not (RT_PLAUSIBLE_MIN_MS <= r <= RT_PLAUSIBLE_MAX_MS)
    )
    exgauss = fit_ex_gaussian(gathered_rts)
    {
        "n_rts_gathered": len(gathered_rts),
        "max_raw_rt_ms": round(max(gathered_rts), 1) if gathered_rts else None,
        "n_dropped_by_window": n_implausible,
        "mu": round(exgauss["mu"], 2),
        "sigma": round(exgauss["sigma"], 2),
        "tau": round(exgauss["tau"], 2),
    }
    return (exgauss,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. Metric — post-error slowing (NaN here, and why)

        `_compute_pes` runs exactly as in the expfactory notebook (drop `rt=None`, require
        current `correct is True` and RT in window, bucket by previous trial). But because the
        adapter marks **every responded trial `correct=True`** (true accuracy isn't recoverable
        offline), there are no `prev.correct is False` trials → the post-error bucket is empty →
        the result is `NaN`. The oracle reports it as a non-gating "not computable" entry.
        """
    )
    return


@app.cell
def _(math, pooled, post_error_slowing_magnitude):
    n_errors = sum(1 for t in pooled if t.get("correct") is False)
    pes = post_error_slowing_magnitude([t for t in pooled if t.get("rt") is not None])
    {"n_error_trials_in_pool": n_errors, "pes_is_nan": isinstance(pes, float) and math.isnan(pes)}
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 6. Cross-check against the oracle + norms ranges

        Run `validate_session_set` and confirm the ex-Gaussian values match, and PES is reported
        as `None` (NaN → no bot_value, non-gating).
        """
    )
    return


@app.cell
def _(NORMS, active_dirs, read_cognitionrun_stroop, validate_session_set):
    report = validate_session_set(
        paradigm_class="conflict",
        session_dirs=active_dirs,
        norms=NORMS,
        trial_loader=read_cognitionrun_stroop,
    )
    oracle_metrics = {
        m.name: {"bot_value": m.bot_value, "range": m.published_range, "pass": m.pass_}
        for p in report.pillar_results.values()
        for m in p.metrics.values()
    }
    {"overall_pass": report.overall_pass, "n_used": report.n_used, "metrics": oracle_metrics}
    return (oracle_metrics,)


@app.cell
def _(exgauss, math, oracle_metrics):
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
        "pes not computable (None)": oracle_metrics["post_error_slowing"]["bot_value"] is None,
    }
    assert all(checks.values()), checks
    checks
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 7. Code-review verdict

        Assertions pass: the ex-Gaussian values match the oracle, and PES is correctly reported
        as not computable. Reviewer notes specific to this task:

        - **PES is structurally `NaN`**, not a fidelity failure — the offline adapter can't
          recover true accuracy on this platform, so it has no errors to condition on. Reported
          as a non-gating "not computable" entry. The expfactory Stroop *can* measure PES.
        - **The plausibility window earns its keep here**: the cell above shows several raw RTs
          far outside `[150, 5000] ms` that would otherwise wreck the fit. This is the exact
          inconsistency the recent oracle fix closed for PES/SSRT.
        - **Stability at N≥10**: with 15-trial sessions, a single session's ex-Gaussian is
          unstable; the gating uses the *pooled* cohort, which is why this task passes at
          cumulative N but produced fit-noise FAILs at N=5.
        """
    )
    return


if __name__ == "__main__":
    app.run()
