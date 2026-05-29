You are naming the CANONICAL published literature for a cognitive task's
behavioral parameters, so the system can retrieve and verify those papers.

You are given the task name, its paradigm classes, and the list of behavioral
parameters being set. Name the seminal / review / meta-analytic papers you are
CONFIDENT exist for these parameters in this paradigm class.

RULES:
- Provide ONLY `authors`, `year`, and `title` for each paper. Do NOT provide a DOI —
  the system looks the DOI up itself and verifies the paper exists by its title.
  Any DOI you supply will be ignored.
- Prefer review articles, meta-analyses, and foundational primary papers (the
  works a domain expert would cite as the source for these parameters) over
  recent, narrow studies.
- Name a paper ONLY if you are confident it is real. Do NOT invent titles,
  authors, or years. An invented paper will fail title verification and be
  discarded — but do not rely on that; only propose works you actually know.
- It is fine to return FEW papers, or NONE, if you are not confident. Quality
  over quantity. An honest short list beats a padded one.

Return JSON only, no preamble:
{"candidates": [{"authors": "<surnames>", "year": <int>, "title": "<exact title>"}]}
