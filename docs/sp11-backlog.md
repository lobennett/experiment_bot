# SP11 backlog

Issues surfaced during SP11 development that don't block any phase
of the SP11 deliverable but should be addressed in future SPs.
Phase 8's writeup references this file for the "what didn't get
fixed in SP11" section.

## Stage 4 `openalex.verify_doi` None-DOI crash

**Surfaced:** Phase 5c variance run 3 (first attempt), 2026-05-19.

**What:** `experiment_bot.reasoner.openalex.verify_doi` at line 25
crashes with `AttributeError: 'NoneType' object has no attribute
'strip'` when Stage 3 emits a citation whose `doi` field is `None`
(rather than a non-empty string or absent). The current handler
assumes a non-None string and calls `.strip()` unconditionally.

**Fix sketch:** one-line normalization at the top of `verify_doi`:

```python
if not doi:
    return False, {"error": "no_doi"}
```

That mirrors SP9b's similar normalization for the
`expected_authors` list/string ambiguity in the same module.

**Why it didn't surface earlier.** Stage 3's citation prompt
typically populates the `doi` field with a string or omits it
altogether. The None case appears only when Stage 3 emits the
key but with a null value — an LLM-output edge case that requires
many regenerations to hit. Single-shot regen rarely triggers it;
the Phase 5c variance study's repeated regenerations against the
same source surfaced it on the first attempt of run 3 in 4
samples.

**Phase 8 framing.** This is a **robustness gap identified by
methodological replication.** The variance characterization study
was designed to characterize stochastic Stroop-parameter output,
but it incidentally probed Stage 4's failure surface by giving it
four diverse Stage 3 outputs to consume. The None-DOI bug had
existed at least since SP8 (the same Stage 4 path) but went
undetected under normal single-shot use. Repeating the regen
turned a latent robustness gap into a discoverable failure mode.
This is a generic argument for replication studies — they uncover
bugs that linear test-once-and-ship pipelines miss. Phase 8 can
cite it as a side benefit of variance characterization.

**Priority for follow-up SP.** Low for SP11 (variance run 3
retried successfully; no Phase 7 sessions depend on it). Higher
for Phase 7's pre-cal arm if any TaskCard happens to be
regenerated mid-Phase-7 — but that's not the planned flow.

## Reasoner reasoning-chain granularity

**Surfaced:** Phase 5b TaskCard inspection, 2026-05-19.

**What:** Stage 2/3/4/5 reasoning_chain entries carry
`evidence_lines: []` (Stage 1 is the only stage that emits per-
line evidence). For audit / Phase 8 review, knowing which
specific source-line or citation drove a particular numerical
parameter would help a reviewer reconstruct the reasoning.

**Phase 8 implication.** Phase 8's writeup will note this as a
documented limitation; reviewers can audit Stage 1 evidence at
line-granularity but Stages 2–5 must be audited at the stage-
output level only. This is acceptable given the SP11 scope but
should be improved in a future SP if reviewer feedback requests
finer evidence trails.
