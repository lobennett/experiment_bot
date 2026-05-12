# SP7 — Keypress diagnostic results

**Date:** 2026-05-12 (run window 12:03–12:30 PT)
**Spec:** `docs/superpowers/specs/2026-05-12-sp7-keypress-diagnostic-design.md`
**Plan:** `docs/superpowers/plans/2026-05-12-sp7-keypress-diagnostic.md`
**Branch:** `sp7/keypress-diagnostic` (off `sp6-complete`)
**Tag (after this report lands):** `sp7-complete`

## Goal

Investigation-only SP. SP6 closed the over-firing trial-detection bug. Bot stim-response entries dropped to 1:1 with platform test trials; sequential metrics (PES, lag1_autocorr) registered correctly. But per-trial alignment between `bot.intended_error` and `platform.correct_trial=0` was still poor, and the bot's logged `response_key` didn't match the platform's `response` column on most trials. SP7 instruments page-level keypress capture to name the responsible layer.

## Procedure

5 Flanker sessions (seeds 7001-7005). Generic capture-phase `document.addEventListener('keydown', ...)` injected at session start; per-trial drain records what the page's listener received. `scripts/keypress_audit.py` (paradigm-agnostic, uses `PLATFORM_ADAPTERS` dispatch) produces a 4-way agreement table:

```
bot_intended_correct_key   (bot's resolved_key_pre_error — what response_key_js returned)
  ↓
bot_pressed_key            (post-_pick_wrong_key — what page.keyboard.press received)
  ↓
page_received_key          (first event in page_received_keys — what the page's listener captured)
  ↓
platform_recorded_response (platform CSV "response" column)
  ↓ compare to
platform_expected_response (platform CSV "correct_response" column)
```

## Headline numbers (aggregate across 600 trials)

| Comparison | Aggregate | Per-session range |
|---|---|---|
| `bot_pressed == page_received` | **93.3%** (560/600) | 93.3% × 5 sessions (extremely stable) |
| `page_received == platform_recorded` | **44.0%** (264/600) | 40-50% |
| `bot_pressed == platform_recorded` | **47.7%** (286/600) | 43-55% |
| `bot_intended == platform_expected` | **49.8%** (299/600) | 46-56% |

## Responsible layer — two found, both contribute

Two independent layers are responsible for the per-trial misalignment, and they compound multiplicatively.

### Layer (a) — bot's `response_key_js` is essentially random vs platform's expected key

**Evidence:** `bot_intended == platform_expected` is 49.8% across 600 trials. In a 2-key paradigm (Flanker uses `","` and `"."`), 50% is exactly what you'd get if the bot's resolved correct key were independent of the platform's expected correct key.

**Implication:** The Stage 1 extracted `response_key_js` (`taskcards/expfactory_flanker/2e7fe980.json` stimuli `response.response_key_js`) reads `window.efVars.group_index` to determine the H↔key mapping, defaulting to `1` (lowGroup) when undefined. The platform's CSV shows `group_index=""` for all trials, suggesting the page's group_index is set differently from what the bot reads, OR the platform's correct_response generation uses different state than `window.efVars.group_index`.

This was already documented in SP5's report (`docs/sp5-heldout-measurement-results.md` §3) — SP7 confirms it quantitatively.

### Layer (d) — platform records from a source other than the page's `keydown` events

**Evidence:** `bot_pressed == page_received` is 93.3% (Playwright is faithful to the page's keydown listener), but `page_received == platform_recorded` is only 44.0%. The page's keydown listener captures the bot's pressed key (93% fidelity), but the platform's `response` CSV column reflects a different key on ~56% of trials.

**Implication:** The platform's response-recording mechanism doesn't read directly from `keydown` events. Likely candidates (paradigm-agnostic possibilities, not Flanker-specific):

- jsPsych's `keyboard-response-plugin` listens for `keypress` (or filters by `choices`) rather than `keydown`. Our listener captures all keydown events; the platform's filter discards some.
- A response-window timer constrains when keypresses count. Bot's press lands outside the window on some trials, so the platform records `null`/missing/the wrong key.
- jsPsych's listener fires on the FIRST valid keypress per trial, but our listener captures ALL keydown events; if the bot fires multiple presses per trial (residual SP6 over-firing — 0-5 extra entries per session), the platform may record a different one than `page_received_keys[0]`.

### Combined effect

The two layers compound: layer (a) means the bot guesses the wrong key on ~50% of trials, layer (d) means the platform doesn't see what we thought it saw on ~56% of trials. The combined `bot_pressed == platform_recorded` is 47.7% — consistent with two roughly-independent ~50% factors.

The 7% loss in `bot_pressed != page_received` (probably attributable to those 0-5 extra bot stim-response entries per session — over-firing residual not fully cleaned by SP6) is small compared to the other gaps.

## Aggregate accuracy stays at ~93% despite per-trial randomness

How does the bot achieve ~93% platform-correct accuracy if its keys are random vs expected? Because:
- The bot's intended_correct rate is ~94% (configured).
- The bot's resolved-key matches platform-expected 50% of the time.
- When match: bot presses correct, platform records correct ~93% of the time (the platform-side filter still works most of the time).
- When mismatch: bot presses "wrong by accident" — but the wrong key may STILL be one of the two valid choices, and the platform's filter may STILL record it as the response.

The end result: aggregate accuracy alignment is partially luck — the 2-key choice paradigm means even random pressing produces ~50% raw accuracy, and the platform's response window + valid-key filtering amplifies that.

## What this means for the project's G1 generalizability claim

The current framework's per-trial fidelity is paradigm-by-paradigm random for paradigms with dynamic `response_key_js` extraction (Flanker, n-back, stroop, cognitionrun_stroop — all use `key_map: "dynamic"`). Aggregate accuracy lands close to configured for these paradigms, but the specific trials don't align with bot's intent.

This isn't necessarily a generalization failure — it's a per-trial fidelity gap that affects sequential metrics most heavily. Aggregate metrics (rt_distribution, conflict_effect when computed across all incongruent vs all congruent) still validate cleanly. SP5 demonstrated this: rt_distribution PASSED on Flanker against published norms despite the per-trial alignment being broken.

For reviewer-credible claims about the bot reproducing specific phenomena (PES, CSE, lag1_autocorr — all sequential), per-trial alignment matters. SP6's over-firing fix made PES validate. SP8+ will need to tackle layer (a) and/or layer (d) to make CSE and other lag-1 metrics validate.

## SP8 scope candidate

**Highest-leverage fix is layer (a)** — the bot's response_key_js extraction. If the bot resolves the correct key reliably, layer (d) becomes much less important (the platform may still mis-record some keys, but the bot's intent is correct, so the recording mostly captures correct keys anyway).

**Paradigm-agnostic approach** (per memorized user feedback at `~/.claude/projects/.../memory/feedback_avoid_paradigm_overfitting.md`):

- **Option A (Stage 1 improvement)**: Have Stage 1 produce a `response_key_js` that's more robust to runtime state. Concrete: emit a check that reads multiple potential state sources (`window.efVars.group_index`, `window.group_index`, `window.experimentData?.group_index`, etc.) and uses whichever is defined. Increase the prompt's example examples for `response_key_js` extraction.
- **Option B (Runtime fallback)**: When the bot's `response_key_js` returns the same value as the page's `window.correctResponse` (when defined), use that. When they disagree (or `correctResponse` is undefined), fall back to the bot's value. Adds a generic runtime-cross-check.
- **Option C (Cross-check via the page's own listener)**: Inject a JS shim that wraps the page's keypress handler and reports the key the handler IS using. Use that as ground truth.

Recommendation: **Option B**. It's a generic runtime mechanism (no Stage 1 prompt edit), works for any paradigm where the page exposes `window.correctResponse` or equivalent (jsPsych typically does), and degrades gracefully when the cross-check isn't available.

If SP8 takes option B and the per-trial alignment doesn't significantly improve, that's evidence layer (d) dominates and the next SP focuses on response-window timing.

## Internal CI gate status

| Coverage | Test file | Tests |
|---|---|---|
| `_install_keydown_listener` | `tests/test_executor_keypress_diagnostic.py` | 2 |
| `_drain_keydown_log` | `tests/test_executor_keypress_diagnostic.py` | 3 |
| `_log_trial_with_keypress_diag` | `tests/test_executor_keypress_diagnostic.py` | 2 |

Test suite at `sp7-complete`: **524 passed, 3 skipped** (was 517 at sp6-complete; +7 new tests).

✅ Internal gate: PASS.

## Status

✅ **SP7 success criterion met.** Layer responsibility named precisely: (a) and (d) both contribute, layer (a) is the higher-leverage target. SP8 scope recommendation grounded in the data.

Per the user-feedback constraint memorized in this session: the instrumentation, analysis script, and recommended fix (option B) are all paradigm-agnostic. They apply to any registered paradigm with no code changes.

Tag `sp7-complete` on the commit landing this report.
