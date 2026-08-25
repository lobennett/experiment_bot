# RDoC Battery Results — 12 tasks, N=20 per task (exploratory)

_Committed dataset: **240 stealth sessions** (12 tasks × N=20), collected
2026-07-19 by `scripts/collect_battery_stealth.sh` on content-hashed
cards + programs. Exploratory and descriptive throughout — outside the
frozen dev-4 design (`docs/how-it-works.md` §2). Reported as observed; no
program was regenerated, edited, or selected on any number below._

_Numbers on this page were recomputed from the committed matrices on
2026-08-05. See **Scoring note** — the previously published headline
(100/149) included non-subject rows in the human reference and was the most
lenient of three defensible variants._

## The dataset

One run mode serves two purposes: the battery analyses here **and** the
live bot-detection check (Roundtable Proof-of-Human on the deployed tasks —
`docs/detection-results.md`). Stealth means headful real Chrome, GPU
renderer, no WebDriver flag, humanized key-hold. Run mode changes nothing
behavioral: 12/12 column parity with the human matrices, and the
within-1-SD total is stable against the earlier headless round.

- **Sessions:** 240 (`output_naive/<task>_rdoc/`), seeds `83xxxx`
- **Matrices:** `data/bot/rdoc/<task>.csv`, 12/12 at exact column parity
  with `data/human/rdoc/<task>.csv`
- **Programs:** one per task, all 12 passed the mechanical gate on the
  **first attempt**; transcripts in `naive_programs/<label>/`
- **Human reference:** the lab's RDoC battery matrices (501 participants,
  ~5 sessions each), produced by the lab's own preprocessing pipeline —
  the same code path that produced the bot matrices

## Results

Bot cohort mean vs the human between-subject distribution, |z| ≤ 1 human
SD, identical scoring on both cohorts.

| Task | within 1 SD |
|---|---|
| flanker | 8/8 |
| spatial_task_switching | 14/16 |
| n_back | 13/14 |
| stop_signal | 11/12 |
| spatial_cueing | 10/14 |
| ax_cpt | 10/15 |
| visual_search | 10/14 |
| cued_task_switching | 9/13 |
| go_nogo | 5/7 |
| stroop | 5/8 |
| simple_span | 2/12 |
| operation_span | 2/16 |
| **Total** | **99/149 (66%)** |

Ten of twelve tasks land at or above 60%. The two grid-recall spans account
for 24 of the 50 misses; excluding them, the battery is **95/121 (79%)**.

### Scoring note (why the number moved)

The count depends on how the human reference rows are handled. All three
variants use identical estimators on both cohorts:

| Human reference handling | Total |
|---|---|
| All rows, including `Max`/`Mean`/`Min`/`SD` summary rows | 100/149 (67%) |
| **All sessions, summary rows excluded** (reported above) | **99/149 (66%)** |
| One session per participant (true between-subject SD, N≈500) | 97/149 (65%) |

The first variant is what earlier revisions of this document reported. It is
wrong in kind — `Max` and `Min` rows are not participants, and including
them inflates the human SD, which makes the within-1-SD test more lenient.
The third is the strictest and arguably the most correct: pooling ~5
repeated sessions per participant mixes within-person variance into a
"between-subject" SD. The spread across all three is 2 percentage points,
so no conclusion here turns on the choice; the middle variant is reported
because it preserves parity with the lab pipeline's own row conventions
while dropping rows that are not subjects.

### Per-task counts do not survive from N=5

An earlier round reported per-task headlines at N=5 (spatial_task_switching
16/16, stop_signal 12/12). Those do not replicate at N=20 under a
between-subject reference: with one session per participant, stop_signal is
6/12 and spatial_task_switching 9/16. Tightening the bot cohort mean with
four times the sessions, while holding the human SD fixed, moves borderline
metrics out of range. **The stable claim is the total (65–67%) and the
task-level ordering, not any individual task's fraction.** This is the main
reason the N=5 per-task table has been removed rather than updated.

## Honest notes on the misses

- **Spans are the weakest paradigms** (2/16, 2/12) and the naive approach's
  principled ceiling — full analysis in `docs/span-failure-analysis.md`.
  Recall mechanics work; grid-navigation pacing (up to +18 z on movement
  time) and the memory model do not.
- **RT location runs slow** on stroop, spatial_cueing, cued_task_switching,
  and visual_search conjunction — the residual calibration signature of the
  no-priors rule. Internal effect structure stays intact everywhere.
- **The feedback channel went unused.** None of the twelve programs reads
  `ctx.feedback_text`. The channel is live (harness captures and delivers
  it; the gate fuzzes it), but one-shot programs did not exploit it — so
  there is no within-session adaptation in this dataset.
- **Attention checks** are answered and perfect on 11 of 12 tasks. On
  `operation_span` they are answered with the task's grid keys
  (space/enter) instead of the check's letter answer — a card/handling
  interplay on the battery's most complex trial flow, left as a documented
  defect.
- **One program per task.** Generation variance is unmeasured, so a
  per-task fraction reflects one draw from the model, not the model's
  central tendency. This is the largest open methodological gap in the
  battery (see `docs/scope-and-venue-assessment.md`).

## Provenance

- **Cards:** content-addressed under `taskcards/`; structural only, no
  behavioral content.
- **Programs:** `naive_programs/<label>/` with every attempt's full model
  transcript and gate report. Behavioral author: Claude Opus 4.8;
  structural cards: Claude Fable 5.
- **Sessions:** each `run_metadata.json` pins the triple (card hash,
  program hash, seed) for all 240 sessions.
- **History:** earlier rounds (N=5 headless v1/v2) are archived at the
  `battery-v1` and `battery-v2-data` git tags, including their matrices and
  results documents. Rounds are never pooled.
