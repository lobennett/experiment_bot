# SP10 — Driver implementation investigation

**Date:** 2026-05-17
**Spec:** `docs/superpowers/specs/2026-05-15-sp10-driver-architecture-design.md`
**Plan:** `docs/superpowers/plans/2026-05-15-sp10-driver-architecture.md`

This document records implementation findings made during Phase 3 (JsPsychDriver build). Each section lands as part of the corresponding plan task.

## Task 10 — jsPsych version probe on the 4 dev paradigms

### Findings

| URL | jsPsych version | pluginAPI shape | Note |
|---|---|---|---|
| `deploy.expfactory.org/preview/10/` (stroop) | **7.3.1** | 7.x | `getKeyboardResponse`, `cancelKeyboardResponse`, `getRootElement`, `areResponsesCaseSensitive`, `heldKeys` present |
| `deploy.expfactory.org/preview/5/` (n-back) | **7.3.1** | 7.x | Same shape |
| `deploy.expfactory.org/preview/9/` (stop-signal) | **7.3.1** | 7.x | Same shape |
| `kywch.github.io/STOP-IT/.../experiment-transformed-first.html` (stop-it) | **None** (`.version()` is not a function) | **6.x** | Has `convertKeyCharacterToKeyCode` + `convertKeyCodeToKeyCharacter` — these are jsPsych 6 APIs removed in 7.x |

### Implications

- **JsPsychDriver targets jsPsych 7.3.1 first.** Vendor anchor files for that version (Task 11). 3 of 4 dev paradigms covered.
- **Stop-it kywch (jsPsych 6.x) falls to DiagnosticDriver.** The bot writes `driver_version_needed.md` describing what 6.x anchors are needed. Adding 6.x anchors + extending JsPsychDriver to dual-version is a follow-up scope item (SP10b candidate).
- **`#jspsych-display-element`** was not present at probe time on any URL. Likely it's only created after the experiment begins (jsPsych 7.x defaults). Driver code reading `getRootElement` at runtime will return the actual element when one exists; we shouldn't hardcode the selector.

### Decision

JsPsychDriver supports only jsPsych 7.3.1 in Phase 3. SUPPORTED_VERSIONS = `("7.3.1",)`. Other 7.x versions can be added easily once anchors land; jsPsych 6.x requires a separate `vendor/jspsych/6.x/` anchor set and code paths (the API names differ).

This means SP10's empirical validation (Phase 5) targets 3/4 paradigms for hard-gate pass. Stop-it produces a `driver_version_needed.md` report describing the 6.x anchors needed — a clean SP10b contribution path.

## Task 11 — Vendored anchor files

(To be filled in when Task 11 lands.)

## Task 17 — End-to-end smoke run

(To be filled in when Task 17 lands.)
