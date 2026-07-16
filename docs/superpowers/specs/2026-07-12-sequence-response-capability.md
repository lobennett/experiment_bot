# Sequence-response capability (general serial-reproduction support)

_Scope decision, 2026-07-12. Motivated by simple_span / operation_span: both
are grid-recall tasks (watch a spatial sequence → reproduce it by clicking
cells in order). The current one-action-per-trial contract cannot express
them. The GENERAL capability — not overfit to grids — is **multi-action
trials driven by a target sequence**._

## The gap

`respond(ctx) → (key, rt_ms) | ("click", idx, rt_ms)` delivers exactly one
action per trial. Serial-reproduction tasks (spatial span, Corsi blocks,
digit-span-by-click, sequence-repro) require the participant to emit an
ordered *sequence* of responses within one trial. And because the bot does
not perceive the stimulus, it needs the trial's target sequence exposed the
same way `correct_key` is exposed for choice trials.

## Design (all naming generic — no task/grid vocabulary in library code)

### 1. Sequence return from `respond`
`respond(ctx)` MAY return a **list of actions** instead of a single action.
Each action is the existing `(key, rt_ms)` or `("click", element_index,
rt_ms)`. Backward compatible: a bare single action = a 1-element sequence;
all existing programs unchanged. An empty list = no response (withhold).
The executor delivers actions in order, waiting each action's `rt_ms` as the
inter-action interval (first rt = onset→first action; subsequent rts =
gap before that action). Every action is validated (existing `_validate`);
a new `_validate_sequence` wraps it.

### 2. Target sequence in `TrialContext`
`ctx.correct_sequence: tuple[int, ...] | None` — the ordered indices into
`ctx.response_elements` that constitute the correct reproduction for THIS
trial (None for non-sequence trials). Exposed by the card via
`correct_sequence_js` (a JS expression returning the ordered element
indices/labels), resolved by the executor per trial exactly as
`response_key_js` resolves `correct_key`. The bot does not perceive the
stimulus; it reproduces `correct_sequence` under its own accuracy/omission/
order-error model — same "draw against a target" philosophy as choice
accuracy.

### 3. Stage-1 emission (the half of Wave B never exercised)
When a task collects responses by clicking on-screen elements, Stage 1
emits `response_elements` (each `{label, selector}`); when the task tests
reproduction of a sequence, it additionally emits `correct_sequence_js`.
Prompt additions are MECHANICAL (how to enumerate clickable elements and
expose the target order) — no phenomenon names, neutrality invariants hold.

### 4. Executor delivery
`_execute_trial_via_provider` handles a sequence return: resolve
`response_elements` + `correct_sequence`, pass them in `ctx`, then deliver
each returned action (click via the element's selector, keypress as now),
waiting per-action rt. Log the full action sequence in the trial record
(`response_sequence`), platform captures natively. Single-action returns
take the existing path unchanged.

### 5. Gate
`simgate` synthesizes sequence trials when the card has
`correct_sequence_js` / response_elements; validates each action; fuzzes
empty sequence, out-of-range index within a sequence, over-long sequence,
non-list/tuple. Purely mechanical.

## Non-goals / boundaries
- No perception: the bot reproduces the exposed target with a noise model;
  it does not "remember" a sequence it never saw.
- No grid geometry in library code — a grid is just N response_elements; the
  capability is sequence-of-clicks, geometry-agnostic.
- Multi-action does not change choice/interrupt tasks (single action stays
  the default and the tested-identical path).

## Acceptance
- All existing programs/tests pass unchanged (backward compat).
- simple_span produces trials whose platform export carries a click sequence
  per recall trial; operation_span captures BOTH its processing keypresses
  and its recall clicks.
- New tests: sequence validation, executor sequence delivery, target-sequence
  resolution, gate sequence + fuzz, Stage-1 emission invariants, neutrality
  invariants still green.
