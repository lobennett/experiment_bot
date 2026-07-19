# RDoC Battery Results — v2 (12 Tasks, N=5, Exploratory)

_Collected 2026-07-17 → 2026-07-18 under a revised protocol (below). Round 1
(v1, collected 2026-07-12 → 07-16) is archived in full — sessions, matrices,
and its results document — at the git tag **`battery-v1`**. Exploratory /
descriptive throughout; outside the frozen dev-4 design (see
`docs/how-it-works.md` §2). Results reported as observed; no program was
regenerated, edited, or selected on any number below._

> **Stealth re-collection (2026-07-19).** The committed dataset is now a
> fresh N=5 **stealth** round (headful real Chrome, GPU renderer, no
> WebDriver flag, humanized key-hold), collected by
> `scripts/collect_battery_stealth.sh` on the same content-hashed
> cards+programs as v2 — so run mode is the only difference. It serves two
> purposes at once: the battery analyses below **and** the live
> bot-detection check (Roundtable Proof-of-Human on the deployed tasks). Two
> findings. (1) **Run mode does not distort the behavioral data**: 12/12
> column parity and 95/149 (64%) within 1 human SD, tracking the headless v2
> (102/150, 68%) with only fresh-N=5 sampling differences — the recorded
> RT/accuracy is unchanged by stealth. Per-subject vs Eisenberg reproduces
> the headlines (stop-signal all metrics within 1 SD incl. SSRT 256 vs 303,
> go_rt KS p ≈ 0.76; stroop 6/7, stroop-effect 97 ms). (2) **Bot-detection**:
> the environment fixes cleared Roundtable's "bot browser" and "software
> renderer" flags (100→50/100); the residual flag is its behavioral ML on
> biometrics (absent mouse stream), which a zero-mouse session can still
> sometimes pass — full analysis in `docs/detection-results.md`. The prior headless v2
> matrices/analyses are at the `battery-v2-data` tag.

## What changed from v1 (the revision, stated plainly)

v1's misses shared one thread: the participant could not perceive what the
platform tells a person at the keyboard. The revision — motivated by those
observed misses, which is why v1 and v2 are reported side by side and never
blended — made three general changes plus a model change:

1. **Attention-check emission (Stage-1 structural prompt).** Online tasks
   commonly include attention checks; the structural card must emit the
   full config (detection, question text, response derivation), not just
   the classification. A supporting harness fix: Stage 1 sometimes emits
   the config under `attention_checks` (plural); the normalize layer now
   maps that LLM alias to the canonical key (with tests). In v1, checks
   went unanswered on 10 of 12 tasks.
2. **`ctx.feedback_text` (perception channel).** The text a feedback screen
   displays now reaches the program on the next trial; the harness never
   interprets it. The mechanical gate fuzzes the field.
3. **Timing salience (generation prompt).** One neutral sentence pointing
   at the task's own timing parameters in the injected source. No numbers,
   no phenomena; neutrality invariants unchanged and green.
4. **Behavioral author: Claude Opus 4.8** (v1: Claude Fable 5), per
   protocol decision. Structural cards remain Fable-authored (10 cards
   re-reasoned under the new Stage-1 prompt; the two dev cards, already
   complete, kept). Two Fable-authored v2 programs generated before the
   model switch were superseded unused (archived in `naive_programs/`,
   their 10 sessions set aside, not in any dataset).

**Generation record:** all 12 Opus programs passed the mechanical gate on
the **first attempt**. Sessions: 60/60 collected (v2 seeds `8XX001–8XX005`,
one block per task), hermetically pinned as always.

## Results: v1 → v2

Bot cohort mean vs the human between-subject distribution (identical
matrices pipeline, identical scoring, |z| ≤ 1 human SD; N=5 — descriptive).

| Task | v1 | v2 |
|---|---|---|
| spatial_task_switching | 9/16 | **16/16** |
| n_back | 4/14 | **13/14** |
| stop_signal | 12/12 | **12/12** |
| flanker | 7/8 | **8/8** |
| spatial_cueing | 9/14 | 10/14 |
| ax_cpt | 12/15 | 10/15 |
| cued_task_switching | 9/13 | 9/13 |
| go_nogo | 4/7 | 5/7 |
| visual_search | 10/14 | 9/14 |
| stroop | 5/8 | 5/8 |
| operation_span | 2/16 | 3/17 |
| simple_span | 1/12 | 2/12 |
| **Total** | **84/149 (56%)** | **102/150 (68%)** |

**Attention checks: fixed on 11 of 12 tasks.** v1: unanswered (accuracy
0.0) on 10 tasks. v2: answered and perfect (1.0) everywhere except
`operation_span`, where the checks are responded to but with the task's
grid-navigation keys (space/enter) instead of the check's letter answer —
a card/handling interplay on the battery's most complex trial flow, left
as a documented defect.

**Deliverable:** `data/bot/rdoc/<task>.csv`, 12/12 at exact column parity
with `data/human/rdoc`. As in v1, stop_signal's `go_rt_all_responses` and
`mean_stop_failure_RT` are computed with the project's own estimator
(identical definitions) because the pipeline version does not emit them;
stop-failure RT < go RT in every session, as the race model requires.

## Honest notes on the misses that remain

- **The feedback channel went unused.** None of the twelve generated
  programs reads `ctx.feedback_text`. The channel is live (harness
  captures and delivers it; gate fuzzes it), but one-shot programs did
  not exploit it — so v2's gains come from the attention-check fix and
  the new programs' own calibration, not from within-session adaptation.
  Consistent with that, `proportion_feedback` improved only where
  baseline performance improved (spatial_task_switching 1.00 → 0.10;
  spans still 1.00 vs human 0.18–0.30).
- **RT location still runs slow** on stroop (+2.1 to +2.3 z),
  spatial_cueing (+1.1 to +2.2), cued_task_switching (+2.8 to +3.3), and
  visual_search conjunction — the residual calibration signature.
  Internal effect structure remains intact everywhere.
- **Spans remain the weakest paradigms** (3/17, 2/12): recall is real and
  order accuracy improved slightly, but grid navigation is far slower
  than human (movement/response times up to +18 z) and responses per
  trial run low. The serial-reproduction *mechanics* are solved; the
  generated programs' pacing and memory models are not.
- **ax_cpt regressed** (12/15 → 10/15; AY accuracy and several RTs) and
  visual_search dipped by one — one-shot generation variance cuts both
  ways, and is reported as observed.

## Provenance

- Cards: content-addressed under `taskcards/` (10 re-reasoned 2026-07-17,
  Fable-5-authored, live-pilot + replay-gate validated; op-span card
  re-rolled once after an incomplete first emission — cards carry no
  behavioral content and have no one-shot rule).
- Programs: `naive_programs/<label>/` — Opus 4.8 transcripts archived with
  every attempt; the session `run_metadata.json` triple (card hash,
  program hash, seed) pins each of the 60 sessions.
- v1 in full (sessions, matrices, results doc): `git show battery-v1:...`.
