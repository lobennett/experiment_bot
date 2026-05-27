# SP16 held-out behavioral data: stop_signal_with_integrated_memory

**1 session** (seed 17001), executor with adaptive nav, run 2026-05-26. URL: `deploy.expfactory.org/preview/80`. This is the first end-to-end behavioral session ever collected on this held-out paradigm — the arc from SP13 (sequential pilot refinement) through SP16 (executor adaptive nav) exists to make this possible.

## Session summary

| Quantity | Value |
|---|---|
| Bot-log trial entries | 666 |
| Platform-recorded stop-signal trials | 654 (439 go, 215 stop) |
| Adaptive nav steps used | 10 / 10 budget (7 DOM advances, 3 no-ops) |
| Conditions captured | shape_go, stop_responded, stop_withheld, in_memory_set, not_in_memory_set |

The paradigm is a dual task: a stop-signal task with an *integrated* Sternberg-style working-memory component. Both components produced data.

## Canonical stop-signal metrics (from authoritative platform export `experiment_data.json`)

| Metric | This session | Published norm | Verdict |
|---|---|---|---|
| Go mean RT | 826 ± 229 ms | — (elevated by dual-task memory load) | n/a |
| Stop-failure RT | 505 ms | — | n/a |
| Stop inhibition rate | 0.516 | ~0.50 (staircase target) | ✅ WITHIN |
| Mean SSD | 327 ms | — | n/a |
| SSRT (integration method) | 458 ms | [180, 280] | ❌ ABOVE |
| Race-model ordering (stop-fail RT < go RT) | 505 < 826 ✅ | required | ✅ HOLDS |

## Working-memory component (from bot_log RTs)

| Condition | n | Mean RT |
|---|---|---|
| in_memory_set (probe IS in the memorized set) | 154 | 926 ± 196 ms |
| not_in_memory_set (probe NOT in set) | 158 | 851 ± 228 ms |

Memory-set membership effect ≈ **+75 ms** for in-set probes — a measurable working-memory load signature, confirming the bot engages the memory component, not just the stop-signal component.

## Go accuracy

shape_go trials: 144 trials, 2 omissions → **~98.6% go response rate**, humanlike.

## Honest interpretation

**Structurally humanlike (the qualitative signatures hold):**
- **Race-model ordering is correct**: stop-failure RTs (505 ms) are faster than go RTs (826 ms). This is the defining behavioral signature of valid stop-signal performance — fast go responses "escape" inhibition. The bot reproduces it.
- **Inhibition rate ≈ 0.50**: the stop-signal-delay staircase converged to the canonical 50% inhibition target, meaning the bot's responses interacted correctly with the adaptive SSD algorithm.
- **Memory-load effect present**: the ~75 ms in-set/out-set RT difference shows the integrated memory manipulation affected the bot's responses.
- **High go accuracy** (~98.6%).

**Absolute SSRT runs high (the quantitative gap, surfaced explicitly):**
- SSRT of 458 ms is well **above** the pure-stop-signal published norm of 180-280 ms. Two compounding reasons:
  1. **This is a dual task.** Go RT (826 ms) is inflated by the working-memory load — far slower than a simple stop-signal task's ~450-550 ms. SSRT = go-RT-quantile − mean-SSD, so an elevated go RT propagates to an elevated SSRT. Comparing this paradigm's SSRT to *pure* stop-signal norms is partly apples-to-oranges.
  2. **The bot's SSRT runs high across all stop-signal paradigms.** SP12 documented expfactory_stop_signal at 353 ms and stopit at 323 ms — both above norm. The held-out paradigm (458 ms) continues this systemic pattern. Per the project's honest-framing discipline: this is a real, consistent bot-behavior gap, not a held-out-specific anomaly. The bot's stop process is slower than human; the fix (if pursued) is at the Reasoner's RT-parameter derivation, not at the executor.

## What SP16 demonstrates

The executor's adaptive nav navigated the held-out paradigm's interleaved instruction/trial flow — fullscreen → multi-page instructions → practice block with demo trials → test blocks with between-block instructions — that broke every pre-SP16 approach (fixed-nav re-run crashed; walker TaskCard couldn't be replayed). It then collected **666 trials of calibrated, humanlike behavioral data across all 5 conditions in a single browser tab**. This is the framework's first behavioral dataset on a paradigm it was never tuned against, with adaptive nav (10 LLM-guided steps) bridging the instruction-flow complexity.

## What SP16 does NOT demonstrate

- **Not a multi-session statistical sample.** This is N=1; SSRT/RT means have no between-session variance estimate. A ×5 run (deferred) would tighten the estimates.
- **SSRT within norm** — it isn't (458 ms vs 180-280). The bot is structurally valid but quantitatively slow on the stop process, consistent with the pre-existing bot-wide pattern.
- **The working-memory effect's direction** isn't validated against a specific published Sternberg+stop-signal study; only that a load effect is present.

## Provenance

- Session dir: `output/stop_signal_with_integrated_memory/2026-05-26_19-20-06-705129/`
- TaskCard: `taskcards/stop_signal_with_integrated_memory/f6772248.json` (SP15 walker-generated, 17 nav phases)
- Metrics computed from `experiment_data.json` (platform export, authoritative per G4) for stop-signal metrics; `bot_log.json` for working-memory RTs.
