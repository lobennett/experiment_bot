# Bot-Detection Results — Roundtable Proof-of-Human (stealth battery)

_Latest batch: the N=5 stealth RDoC battery (seeds `831xxx`), the same
sessions as `docs/rdoc-battery-results.md`'s stealth round. Scope is this
batch only — earlier detection-test rounds (non-stealth and killed/partial
resumes) are excluded. 57 of the 60 sessions registered on the Roundtable
dashboard before the export snapshot (2026-07-19); the other 3 ran after it._

## Setup

Roundtable's Proof-of-Human tracker (`rt.js`) is embedded in all 12
deployed RDoC tasks (upstream `poldracklab/expfactory-experiments-rdoc`,
PR #113), each tagged by task via `data-tags`. Roundtable returns a
`risk_score` (0 auto-accept / 50 manual-review / 100 auto-reject), an
aggregate `agent_behavior` ML flag, environment flags (`bot_browser`,
`software_renderer`, VPN/Tor/VM), and granular behavioral sub-flags
(`programmatic_typing`, `teleporting_mouse`, `no_corrections`,
`all_pasted`, `center_clicks`, `jump_scrolling`, `programmatic_clicking`,
`external_input`).

## How the bot got here (progression)

| Config | Roundtable |
|---|---|
| Headless (default) | 100/100 — `bot_browser` + `software_renderer` + `agent_behavior` |
| Stealth env only (real Chrome, GPU renderer, no WebDriver flag) | 50/100 — environment flags cleared; only `agent_behavior` |
| Stealth + humanized key-hold (this batch) | 50/100 — no change from keystroke timing |

The environment fixes (`--stealth`: headful real Chrome, Metal GPU
renderer, `navigator.webdriver` cleared) are the decisive lever. Humanized
keystroke dwell did not move the score.

## This batch (57 sessions with results)

| Outcome | Count | Share |
|---|---|---|
| Auto-accept (risk 0, fully clean) | 9 | 16% |
| Manual review (risk 50) | 48 | 84% |
| **Auto-reject (risk 100)** | **0** | **0%** |

- **Environment is clean on every session**: `bot_browser` 0/57,
  `software_renderer` 0/57. (The 9 auto-rejects in the raw export are
  orphan sessions from earlier killed attempts that ran headless — not
  this batch; all 60 committed sessions ran headful/stealth.)
- **Only the opaque `agent_behavior` ML fires** (48/57). **Every granular
  behavioral sub-flag is 0/57** — no programmatic typing, no teleporting or
  absent mouse, no missing-corrections, no paste/center-click/scroll/click
  anomaly. Roundtable's rule-based behavioral detectors find nothing.
- Flagged sessions are **"Manual review," never auto-reject** — the
  detector will not call the bot a bot on a clean environment; it defers to
  a human.

Per-task passes (risk 0):

| Task | pass / matched |
|---|---|
| operation_span | **5 / 5** |
| ax_cpt, n_back, spatial_cueing, spatial_task_switching | 1 each |
| cued_task_switching, flanker, go_nogo, stop_signal, stroop, visual_search | 0 |
| simple_span | 0 / 2 (under-represented in export) |

## Interpretation

**There is no specific behavioral tell to fix.** Every rule-based detector
already passes; the sole residual is a holistic ML score that is marginal
(passes 16% of sessions outright) and yields manual review, not rejection.

**The mouse hypothesis is falsified by this batch.** `operation_span`
passes 5/5 while producing **zero mouse events** (it answers with
arrow-key + spacebar sequences, like the other keyboard tasks — 454
keyboard actions, 0 clicks). The mouse sub-flags never fire. So adding a
synthetic mouse stream is not supported as the lever; passing does not
track mouse presence.

**What separates passers from flagged sessions is not visible** in any
exported feature (environment, typing, mouse, corrections all identical).
The most parsimonious read at N=5 is that `agent_behavior` is a holistic,
near-threshold ML score with real session-to-session variance, not a
detector keyed on a concrete artifact of the bot's behavior.

## Bottom line

Once the environment is made indistinguishable, the leading bot-detector
finds **no specific behavioral tell** in the naive bot's task performance
and **auto-rejects none** of the clean-environment sessions — it
auto-accepts ~16%, passes one task (operation_span) outright, and defers
the rest to manual review. This is on-thesis (`docs/how-it-works.md` §1):
current detection reduces to environment fingerprint plus an opaque
behavioral score, not a readable signature of non-human task behavior.

**Per-task iteration to circumvent the ML is not recommended**: there is no
exported signal to target, the obvious lever (mouse) is falsified here, and
chasing an opaque score is both adversarial ML-evasion outside the naive
thesis and unlikely to converge. Larger N would sharpen the pass-rate
estimate; that is the useful next measurement, not per-task tuning.
