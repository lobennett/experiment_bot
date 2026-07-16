# RDoC Battery Results — 12 Tasks, N=5 (Exploratory)

_Collected 2026-07-12 → 2026-07-16. **Exploratory/descriptive — outside the
pre-registered scope of `docs/preregistration-naive.md`** (which covers the
dev-4 stroop/stop-signal comparison at N=30). Same framing as the flanker
held-out probe in the paper draft: the pipeline pointed at URLs, no
task-specific code, results reported as observed._

This is the single results file for the battery. Deliverable provenance
(which pipeline produced the matrices, column parity, regeneration script)
lives in `data/bot/rdoc/README.md`; numbers are not duplicated there.

## Collection

All 12 RDoC Experiment Factory tasks (registry: `data/rdoc_task_urls.tsv`)
collected at **N=5 seeded sessions each**, hermetically pinned (card hash +
program hash + seed in each session's `run_metadata.json`). Human reference:
the lab's session-level behavioral matrices (`data/human/rdoc/`, N≈2,510
sessions/task; gitignored, committed placeholders carry the schema).

**Program generation record** (no behavioral iteration — first gate-passing
program is the program):

- **11 of 12 task programs passed the mechanical gate on the first
  attempt.** `cued_task_switching` required 2 regenerations, both triggered
  by mechanical gate failures — within the pre-registered max-2-retries
  rule; all attempts archived under `naive_programs/expfactory_cued_ts/`.
- `operation_span` and `simple_span` are grid-recall (serial-reproduction)
  tasks and required the **sequence-response capability**
  (`docs/how-it-works.md` §4):
  multi-action trials driven by a card-exposed target sequence, delivered
  as arrow-key navigation + spacebar selections. The capability is generic
  (no grid geometry in library code); both spans then collected real recall
  data first-shot. Caveat: the Stage-1 prompt's target-reconstruction
  guidance was iteratively refined against these two span implementations,
  and its generality has not been exercised on a serial-reproduction task
  outside this battery.

**Deliverable:** `data/bot/rdoc/<task>.csv` — 12/12 tasks at exact column
parity with `data/human/rdoc`, produced by the lab's own preprocessing
pipeline (lobennett/rdoc-beh) on the bot's platform-native exports. One
honest gap: `operation_span`'s `8x8_grid_asymmetric_rt` is empty.

## Behavioral comparison (descriptive)

Bot cohort mean vs the human between-subject distribution, per metric:
counted "within range" if |z| ≤ 1 human SD. N=5 per task — treat as
descriptive, not inferential.

| Task | Within 1 SD | Excluding attention-check |
|---|---|---|
| stop_signal | **12/12** | 12/12 |
| flanker | 7/8 | **7/7** |
| ax_cpt | 12/15 | 12/14 |
| visual_search | 10/14 | 10/13 |
| spatial_cueing | 9/14 | 9/13 |
| cued_task_switching | 9/13 | 9/12 |
| spatial_task_switching | 9/16 | 9/15 |
| stroop | 5/8 | 5/8 |
| go_nogo | 4/7 | 4/6 |
| n_back | 4/14 | 4/13 |
| operation_span | 2/16 | 2/15 |
| simple_span | 1/12 | 1/11 |
| **Total** | **84/149 (56%)** | **84/139 (60%)** |

### Patterns in the misses (honest summary)

**1. Attention checks unanswered on 10 of 12 tasks (structural, not
behavioral).** The executor treats attention-check stimuli as structural
non-trials by design; on the 10 newly generated cards, Stage 1 classified
the battery's attention-check trials that way, so the bot never responds →
`attention_check_mean_accuracy = 0.0`. On the two dev-card tasks (stroop,
stop_signal) the checks are answered and accuracy is **1.0** — when the bot
does answer them, it answers perfectly. This is a Stage-1 card-classification
variance, a framework finding, not a property of the generated programs.

**2. RT location runs slow — the known calibration pattern.** The same
uniform miss as the pre-registered battery (paper draft, Results): RTs are
directionally correct but shifted slow (spatial_cueing +2.4 to +3.0 z;
spatial_task_switching / cued_task_switching stay-RTs +2.2 to +3.9 z;
stroop congruent +2.1 z; visual_search conjunction +2.1 z). Internal effect
structure survives the shift — e.g., Stroop incongruent > congruent,
AX-CPT AY > AX, visual-search conjunction > feature, valid < invalid cueing.

**3. Inhibition again strongest.** stop_signal is the only task with every
metric in range (12/12), consistent with the pre-registered headline
(race-model programs converge the SSD staircase). flanker misses only the
attention check.

**4. Working-memory tasks weakest.** n_back (4/14): systematic omissions
(~6–10% vs human ~1%) plus slow RTs. The spans (2/16, 1/12): recall is
real but degraded relative to humans — fewer responses per trial (2.9 vs
4.0), lower order accuracy (0.36–0.61 vs 0.76–0.92), and much slower
grid navigation (movement/response times +1.5 to +15 z). The capability
delivers the mechanics; the generated programs' memory models underperform
the human reference. go_nogo under-inhibits (nogo accuracy 0.556 vs
0.878±0.109).

### Not done, by rule

Per the no-behavioral-iteration rule, no program was regenerated, edited,
or selected because of any number above. The misses stand as the one-shot
result.
