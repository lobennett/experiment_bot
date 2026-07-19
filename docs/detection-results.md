# Bot-Detection Results — Roundtable Proof-of-Human (stealth battery, N=20)

_Latest batch: the N=20 stealth RDoC battery (seeds `831xxx`), the same
sessions as `docs/rdoc-battery-results.md`'s stealth dataset. Scope is this
batch only — all 240 committed stealth sessions matched to Roundtable
dashboard rows (by task + timestamp) from the 2026-07-19 export; earlier
non-stealth and killed/partial rounds are excluded._

## Setup

Roundtable's Proof-of-Human tracker (`rt.js`) is embedded in all 12
deployed RDoC tasks (upstream `poldracklab/expfactory-experiments-rdoc`,
PR #113), each tagged by task via `data-tags`. Roundtable returns a
`risk_score` (0 auto-accept … 100 auto-reject), an aggregate
`agent_behavior` ML flag, environment flags (`bot_browser`,
`software_renderer`, VPN/Tor/VM), and granular behavioral sub-flags
(`programmatic_typing`, `teleporting_mouse`, `no_corrections`,
`all_pasted`, `center_clicks`, `jump_scrolling`, `programmatic_clicking`,
`external_input`).

## How the bot got here

| Config | Roundtable |
|---|---|
| Headless (default) | 100/100 — `bot_browser` + `software_renderer` + `agent_behavior` |
| Stealth env only (real Chrome, GPU renderer, no WebDriver flag) | ~50/100 — environment flags cleared; only `agent_behavior` |
| Stealth + humanized key-hold (this dataset) | ~50/100 — no change from keystroke timing |

The `--stealth` environment fixes (headful real Chrome, Metal GPU renderer,
`navigator.webdriver` cleared) are the decisive lever. Humanized keystroke
dwell did not move the score.

## This batch (240 sessions, all matched)

| risk_score | recommended action | count | share |
|---|---|---|---|
| 0 | auto-accept (pass) | 33 | **14%** |
| 30 | (low) | 1 | <1% |
| 50 | manual review | 201 | 84% |
| 80 | (high) | 4 | 2% |
| 100 | auto-reject | 1 | <1% |

- **Environment is clean on every session**: `bot_browser` 0/240,
  `software_renderer` 0/240.
- **Only 1 of 240 is auto-rejected.** 84% land at "manual review" — the
  detector will not call the bot a bot on a clean environment; it defers to
  a human.
- **The opaque `agent_behavior` ML is the near-universal driver** (206/240).
  The granular behavioral sub-flags almost never fire: `teleporting_mouse`
  5/240, `center_clicks` 1/240, and **every other sub-flag 0/240**
  (`programmatic_typing`, `no_corrections`, `all_pasted`, `jump_scrolling`,
  `programmatic_clicking`, `external_input`). Roundtable's rule-based
  behavioral detectors find essentially nothing.

### Per-task pass rate (risk 0)

| Task | pass / 20 |
|---|---|
| **operation_span** | **20 / 20 (100%)** |
| stroop | 4 / 20 (20%) |
| go_nogo, visual_search | 2 / 20 (10%) |
| ax_cpt, flanker, n_back, spatial_cueing, spatial_task_switching | 1 / 20 (5%) |
| cued_task_switching, simple_span, stop_signal | 0 / 20 |

## Interpretation

**operation_span passes 100% of the time — the one robust per-task result.**
At N=20 this is not noise. operation_span is the complex-span task (a math
processing sub-task interleaved with grid recall), giving the longest and
most varied interaction stream of the battery. Whatever `agent_behavior`
rewards, this task's richer, bursty keystroke structure clears it every
time, while the regular one-key-per-trial rhythm of the simple RT tasks
mostly does not.

**The mouse hypothesis remains falsified.** operation_span passes 20/20
with **zero mouse events** (it answers with arrow-key + spacebar sequences,
not clicks). `teleporting_mouse` fires on only 5/240 sessions and does not
track passing. Adding a synthetic mouse stream is not supported as the
lever.

**No specific behavioral tell to fix.** Every rule-based detector is
effectively silent; the sole residual is a holistic ML score that
auto-rejects 1/240, passes 14% outright (one task 100%), and defers the
rest to manual review. There is no exported feature that cleanly separates
passers from flagged sessions to target per task.

## Bottom line

Once the environment is indistinguishable, the leading bot-detector finds
**no specific behavioral tell** in the naive bot's task performance and
**auto-rejects 1 of 240** clean-environment sessions. It auto-accepts 14%,
passes the most complex task (operation_span) **100%** of the time, and
defers the rest to manual review. This is on-thesis
(`docs/how-it-works.md` §1): current detection reduces to environment
fingerprint plus an opaque behavioral score — not a readable signature of
non-human task behavior.

**Per-task iteration to circumvent the ML is not recommended**: there is no
exported signal to target, the obvious lever (mouse) is falsified here
(operation_span passes mouse-free), and chasing an opaque score is
adversarial ML-evasion outside the naive thesis. The N=20 measurement is
the useful result — a stable pass-rate estimate and a clear per-task
gradient (rich/long tasks pass, simple RT tasks don't) — not a target for
per-task tuning.
