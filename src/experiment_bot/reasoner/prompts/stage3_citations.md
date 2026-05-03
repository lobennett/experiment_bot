You will receive a list of behavioral parameter point estimates for a cognitive
task. For EACH parameter, produce:

1. `citations`: a non-empty list of objects {doi, authors, year, title,
   table_or_figure, page, quote, confidence}. Citations must be real published
   work; if you are not confident, set confidence="low".
2. `literature_range`: empirically observed range across studies, as
   {param_name: [low, high]}.
3. `between_subject_sd`: SD of inter-subject variability for each numeric
   sub-parameter.

Return a JSON object keyed by `<section>/<key>/<param>`:
{
  "response_distributions/congruent/mu": {
    "citations": [...],
    "literature_range": {"mu": [560, 620]},
    "between_subject_sd": {"mu": 40}
  },
  ...
}
