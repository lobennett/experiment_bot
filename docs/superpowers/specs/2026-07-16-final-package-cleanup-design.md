# Final-package cleanup — design

_2026-07-16. Goal: the repo in a final state — the executable package,
examples, science-first documentation, and evidence of performance; nothing
else. User directive with conservative resolutions (user AFK at decision
time): keep the full test suite, keep all raw evidence in-repo, keep both
the frozen prereg and the paper draft._

## Documentation (the main work)

1. **New `docs/how-it-works.md`** — one comprehensive narrative, URL to
   scored dataset, science over function names: the research question; why
   prompt neutrality / no behavioral iteration / pre-registration are the
   integrity design; what each stage does and what it is forbidden from
   doing; the provenance model; the evidence (pre-registered dev-4,
   held-out flanker probe, exploratory 12-task battery) with honest misses;
   limitations. Absorbs `docs/pipeline.md` (deleted) and the durable
   content of the sequence-response spec.
2. **README.md** — concise front door: what/why, quickstart, five CLIs,
   evidence summary table, repo layout, links. The long "How It Works"
   body moves to the new doc.
3. **Pointer fixes** — "expert arm lives on `main`" → the
   `expert-arm-final` tag (CLAUDE.md, README, PROVENANCE sidecar, paper
   draft provenance line). The frozen prereg is not touched.

## Removals

- `docs/pipeline.md` (superseded), `docs/superpowers/` (process specs and
  plans, including this file — history preserves them),
  `scripts/ingest_rdoc_behavioral.py` (one-shot; its column policy is
  already documented in `data/human/rdoc/README.md`, which drops the
  script reference), empty untracked `examples/` dir.

## Explicitly kept

- Full test suite (integrity + correctness evidence).
- All raw evidence: `output_naive/` (180 sessions), `naive_programs/`
  (programs + transcripts + gate reports), `taskcards/`,
  `analysis_out_naive/`, `data/` (matrices + placeholders + registry).
- `scripts/naive_run.sh` (production collection), `scripts/check_doc_links.py`
  (CI), `data/bot/rdoc/run_rdoc_beh.py` (evidence regeneration).
- Frozen prereg + PROVENANCE sidecar; paper draft.
- Untracked personal dirs (`camera_ready_ccn2026/`, `figures_meeting/`,
  PDF) untouched; untracked generated leftovers (`output/`,
  `output_expert_v2/`, `output_frozen/`, `.reasoner_work/`) reported, not
  deleted.

## Acceptance

`scripts/check_doc_links.py` passes; full suite green; a newcomer can read
README → how-it-works.md and understand the system end to end, including
where every piece of evidence lives.
