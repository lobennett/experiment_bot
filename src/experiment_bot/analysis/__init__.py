"""Per-subject behavioral analysis for external (cognitive-control) review.

Computes one row of behavioral metrics per "subject" (per session for the bot;
per worker for the human reference) for the stop-signal and Stroop tasks, with
bot and human passed through the SAME estimators so the comparison is
apples-to-apples. This is a faithful, tested port of the legacy
`scripts/analysis.ipynb` computations that produced the submitted abstract
(current estimators: mean-method SSRT, simple post-error-minus-post-correct
PES, within-block lag-1 RT autocorrelation), so the per-subject numbers are
reproducible from committed code.
"""
