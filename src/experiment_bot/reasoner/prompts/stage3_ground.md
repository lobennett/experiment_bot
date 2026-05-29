You are grounding the citations for a cognitive task's behavioral parameters in
REAL retrieved literature. You are given (1) each parameter with its current
point-estimate value, and (2) a NUMBERED POOL of works that were actually
retrieved from OpenAlex/CrossRef, each with its abstract.

ABSOLUTE RULES:
- You may ONLY cite works from the POOL, by their `pool_idx`. You CANNOT cite a
  DOI or paper that is not in the pool. There is no other source of truth.
- Ground every `rationale` in the cited work's ABSTRACT as shown. Do NOT invent
  verbatim quotes, page numbers, or table references — they are not provided and
  must not be fabricated. The rationale is your own words about why the abstract
  supports the parameter.
- Assert a `literature_range` ONLY if a cited abstract actually states such a
  range. If no abstract gives a range, leave it null.
- Propose a `revised_value` ONLY when a cited abstract supports a value different
  from the current estimate, and ONLY within the `literature_range` you assert.
  Give `revision_reason` naming the supporting `pool_idx`. Otherwise null (the
  current value stands as a model-prior estimate).
- ABSTAIN when the pool contains nothing that genuinely supports a parameter:
  return empty `citations` and a `no_citation_reason`. An honest abstention is
  REQUIRED over citing a non-supporting paper.

Return a JSON object keyed by parameter path:
{
  "response_distributions/<cond>/mu": {
    "citations": [{"pool_idx": <int>, "rationale": "<grounded in that abstract>",
                   "confidence": "high|medium|low"}],
    "literature_range": {"mu": [<low>, <high>]} | null,
    "revised_value": {"mu": <number>} | null,
    "revision_reason": "<why, cites pool_idx>" | null,
    "no_citation_reason": "<required iff citations empty>"
  },
  ...
}

Return JSON only, no preamble.
