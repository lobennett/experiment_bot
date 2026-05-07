You are extracting canonical published norms for a behavioral paradigm class
to be used as validation gates against an automated bot's behavior.

CRITICAL: Cite ONLY meta-analyses and review articles, NOT primary studies.
The bot's parameter-setting Reasoner cites primary studies; this norms file
must come from a different evidentiary tier to avoid circularity (the bot
trivially matching norms because both came from the same papers). If a metric
has no meta-analysis or review, mark its range as null with a
no_canonical_range_reason.

Examples of acceptable source types (NOT a hint about which to use for any
specific class — choose sources appropriate to the class):
- Trends in Cognitive Sciences / Annual Review reviews
- Cochrane-style meta-analyses
- Method-consensus papers from established working groups

Output JSON conforming to this schema:
{
  "paradigm_class": "<class name passed in>",
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

## What to extract

The paradigm_class name is provided as input. The vocabulary is
open-ended — there is no closed list of recognized classes. Use your
knowledge of the literature for whatever class name is provided to
decide which metrics have well-established canonical ranges.

For ANY paradigm class, populate at minimum:

1. **RT distribution shape** (typically `rt_distribution`): the central-
   tendency and shape parameters of typical-healthy-adult RT in this
   class. If the literature reports ex-Gaussian fits, use
   `mu_range`, `sigma_range`, `tau_range`. If lognormal/Wald fits are
   the convention for this paradigm, use the appropriate parameter names.
   Cite the review/meta-analysis.

2. **Between-subject variability** (typically `between_subject_sd`): the
   standard deviation of those RT shape parameters across subjects in
   typical samples. Same parameter naming as above with `_sd_range`
   suffix when SD is reported across subjects.

3. **Sequential effects** (one entry per documented effect): any
   trial-to-trial dependencies the literature documents for this class.
   Use the metric name the meta-analysis itself uses (e.g.
   `post_error_slowing`, `switch_cost`, `masking_effect`,
   `attentional_blink`, `learning_curve`, `lag1_autocorr`). These are
   literature-convention metric NAMES, not bot-library mechanisms —
   the validation oracle dispatches by name. Include only effects
   whose literature for THIS class is established.

4. **Paradigm-specific signature metrics**: any metric that is a defining
   measurement of this paradigm class in the literature. Examples:
   `cse_magnitude` (for conflict), `ssrt` (for interrupt), drift rate
   (for perceptual decision), N-1/N-2 switch cost (for task switching),
   set-size effect (for working memory). Include only what the
   literature for THIS class actually reports; don't import metrics from
   other classes.

If the literature for this class does NOT have a meta-analytic range
for a metric you considered including, mark that metric's range as null
with a `no_canonical_range_reason` ("no meta-analysis available",
"primary studies disagree, no consensus", etc.). Do NOT guess.

Return JSON only — no preamble or explanation.
