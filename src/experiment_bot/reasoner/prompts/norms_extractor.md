You are extracting canonical published norms for a behavioral paradigm class
to be used as validation gates against an automated bot's behavior.

CRITICAL: Cite ONLY meta-analyses and review articles, NOT primary studies.
The bot's parameter-setting Reasoner cites primary studies; this norms file
must come from a different evidentiary tier to avoid circularity (the bot
trivially matching norms because both came from the same papers). If a metric
has no meta-analysis or review, mark its range as null with a
no_canonical_range_reason.

Examples of acceptable sources:
- Egner 2007 Trends in Cognitive Sciences (review of CSE)
- Verbruggen et al. 2019 (consensus on SSRT methods)
- Whelan 2008 (review of ex-Gaussian RT analysis)

Output JSON conforming to this schema:
{
  "paradigm_class": "<class name>",
  "metrics": {
    "<metric_name>": {
      "<range_key>": [low, high],
      "citations": [
        {"doi": "...", "authors": "...", "year": ...,
         "title": "...", "table_or_figure": "...", "page": ...,
         "quote": "...", "confidence": "high|medium|low"}
      ]
    }
  }
}

Required metrics for class "conflict":
- rt_distribution (mu_range, sigma_range, tau_range)
- between_subject_sd (mu_sd_range, sigma_sd_range, tau_sd_range)
- lag1_autocorr (range as [low, high] correlation)
- post_error_slowing (range_ms)
- cse_magnitude (range_ms; can be NEGATIVE — facilitation is conventionally negative)

Required metrics for class "interrupt":
- rt_distribution
- between_subject_sd
- lag1_autocorr
- post_error_slowing
- ssrt (range_ms; integration method)

If unsure about a value, prefer marking range null with reason rather than
guessing. Return JSON only — no preamble or explanation.
