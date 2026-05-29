You will receive a list of behavioral parameter point estimates for a cognitive
task. For EACH parameter, attach supporting references — HONESTLY.

CRITICAL HONESTY RULES (read first):
- ONLY cite real, published work you are genuinely confident exists, identified
  by a correct DOI + authors + year + title. If you are not confident a DOI is
  real and correct, DO NOT invent one.
- DO NOT fabricate verbatim quotes, page numbers, or table/figure references.
  You cannot have read the page; do not pretend to. There is NO `quote` or
  `page` field — provide a `rationale` instead: your own prose reasoning for why
  this source supports (or bounds) the parameter, in your own words.
- ABSTAIN when you cannot honestly cite. If you do not know of a real published
  source for a parameter, return an empty `citations` list and a
  `no_citation_reason` (e.g. "no source I can cite without fabricating"). An
  honest abstention is REQUIRED over a fabricated citation. The parameter's
  value then stands as a model-prior estimate, which is acceptable and honest.
- `literature_range` / `between_subject_sd` are OPTIONAL. Provide them only when
  they reflect what the cited literature actually reports — not a bracket you
  draw around the already-chosen point estimate. If you are not deriving them
  from a real source, omit them (leave null).

For EACH parameter produce:

1. `citations`: a list (possibly EMPTY) of objects
   {doi, authors, year, title, rationale, confidence}. Every listed citation
   must be a real published work identified by a correct DOI. `confidence`
   reflects how sure you are the DOI + attribution are correct.
2. `no_citation_reason` (string): required when `citations` is empty; why you
   abstained.
3. `literature_range` (optional): {param_name: [low, high]} ONLY if traceable to
   a cited source; otherwise omit/null.
4. `between_subject_sd` (optional): {param_name: <sd>} ONLY if reported by a
   cited source; otherwise omit/null.

Return a JSON object keyed by `<section>/<key>/<param>`:
{
  "response_distributions/<condition_label>/mu": {
    "citations": [
      {"doi": "<real doi>", "authors": "<real authors>", "year": <year>,
       "title": "<real title>", "rationale": "<your reasoning, not a quote>",
       "confidence": "high|medium|low"}
    ],
    "literature_range": {"mu": [<low>, <high>]},
    "between_subject_sd": {"mu": <sd_value>}
  },
  "response_distributions/<other>/sigma": {
    "citations": [],
    "no_citation_reason": "no source I can cite without fabricating; value is a model-prior estimate"
  },
  ...
}

The bracketed placeholders (`<condition_label>`, `<low>`, `<high>`, `<sd_value>`)
are deliberately not concrete numbers — do not pattern-match on them. Prefer an
honest empty-citations abstention over any citation you are not confident is
real. Return JSON only, no preamble.
