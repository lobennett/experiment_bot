# SP21 — Naive-Builder Experiment: design spec

_Approved in brainstorm 2026-07-02. Origin: the SP20 adversarial design review
found the bot's behavioral realism rests on expert-designed scaffolding (a
closed 3-family RT-distribution menu, a fixed 8-mechanism temporal-effects
registry, expert-authored priors). This experiment tests whether that
scaffolding is necessary: can a frontier model, given no cognitive-control
scaffolding at all, supply the behavioral model itself?_

## Question and claim under test

**Can a "naive builder" — a frontier LLM with no expert behavioral scaffolding
— produce a participant model whose data is as human-like as the expert
pipeline's?** Either outcome is a result: if naive ≈ expert (vs the human
reference), the generalizability claim strengthens dramatically and the
scaffolding can shrink; if naive < expert, the gap *quantifies what the expert
scaffolding contributes*, and the four generated programs become design
evidence for the planned generative-TaskCard grammar (the next SP).

## Decisions fixed during brainstorm

| Decision | Choice |
|---|---|
| Naive output format | Freeform generative **Python program** (no mechanism menu, no family list, no behavioral schema) |
| Scaffolding scope | **Behavior-only substitution**: existing structural TaskCard supplies navigation / stimulus detection / data capture; the program replaces `response_distributions`, `temporal_effects`, `between_subject_jitter`, `performance` |
| Model | Naive arm: **claude-fable-5**. Expert arm: existing pinned Opus-4.8 TaskCards, unchanged |
| Paradigms / N | **Dev-4 × N=30 per arm**; expert arm re-collected under the SP20-fixed executor (`output_expert_v2/`), naive arm to `output_naive/` |
| Rigor | Full pre-registration (`docs/preregistration-naive.md`) committed **before** any generation call; destined for the next paper / R01 evidence |
| Program cardinality | **One program per paradigm**, generated once, content-hashed, archived with its full generation transcript; 30 seeded sessions execute the pinned program. Between-subject variance must come from inside the program (it receives the seed) |
| Integration | **Approach A**: live in-process behavior-provider hook in `TaskExecutor` (rejected: trace replay — cannot react to the live SSD staircase; subprocess RPC — isolation overhead without a threat model for 4 reviewed artifacts) |

## Architecture

### New module: `src/experiment_bot/behavior/`

**Provider contract.** A generated program is a Python file exposing:

```python
def make_participant(seed: int) -> Participant: ...

class Participant:  # duck-typed protocol, not a required base class
    def respond(self, ctx: TrialContext) -> Response: ...
    # Required only when the task has an interrupt signal:
    def on_interrupt(self, ctx: TrialContext, ssd_ms: float,
                     intended: Response) -> Response | None: ...
```

- `Response(key: str | None, rt_ms: float)`; `key=None` = withhold.
- `TrialContext` carries exactly what the executor already knows per trial —
  `condition`, `correct_key`, `available_keys`, `trial_index`, and
  previous-trial outcome (`prev_condition`, `prev_correct`, `prev_rt_ms`,
  `prev_interrupted`). Information parity with the expert arm; nothing more.
- **Interrupt handoff**: the executor calls `respond()` at stimulus onset as
  usual; if an interrupt signal is detected mid-trial it calls
  `on_interrupt(ctx, ssd_ms, intended)` → withhold (`None`) or a commission
  response. The stop/go race is decided entirely by the program — the executor
  imposes no race-model structure on the naive arm.

**Loading and provenance.** Programs live at
`naive_programs/<label>/<sha256>.py` with `<sha>.transcript.json` (full
prompt, model id, raw response) and `<sha>.simgate.json` (gate report)
alongside — content-addressed like TaskCards, loadable by full or unambiguous
hash prefix. Each session records the program hash + seed in `run_metadata`.

### Executor integration

`TaskExecutor(behavior_provider=...)`. When set, `_execute_trial` bypasses
`_should_respond_correctly`, `ResponseSampler`, temporal effects, and
between-subject jitter, and asks the provider instead. Navigation, stimulus
detection, keypress delivery, and data capture are untouched. Provider calls
are in-process (microseconds — no RT-delivery-timing risk). Run CLI gains
`--behavior-program <path-or-hash>`.

### Generation CLI: `experiment-bot-naive-gen <url> --label <L>`

1. Scrape page source with the existing Stage-1 scraper.
2. From the pinned structural TaskCard extract *mechanical* facts only:
   condition labels, key map, trial counts, interrupt-signal presence — the
   same facts `TrialContext` carries at runtime.
3. Build the generation prompt: page source + protocol signatures (verbatim) +
   mechanical facts + the spare behavioral instruction:

   > "Write a Python participant model whose platform-recorded data would be
   > indistinguishable from a typical healthy adult participant completing
   > this task. You decide every aspect of the behavioral model — what varies,
   > across what, and by how much. Each seed is a distinct participant."

   Plus hard mechanical constraints: stdlib + numpy only, deterministic per
   seed, no I/O, no network, no clock access.
4. Call the model (default `claude-fable-5`), archive program + transcript
   under the content hash.

### Neutrality guardrails (the scientific core)

- The prompt template contains **no mechanism names** (nothing in
  `EFFECT_REGISTRY`), **no distribution-family names**, **no phenomenon
  names** (post-error slowing, congruency sequence, SSRT, …), **no numeric
  behavioral priors**. Enforced by invariant tests scanning the template
  against the live registry plus a banned-terms list (SP20 `system.md` test
  pattern).
- **No behavioral iteration (pre-registered):** the first program per paradigm
  that passes the simulation gate IS the program. Regeneration is permitted
  only on mechanical failure (gate crash / protocol violation), max 2 retries,
  every retry archived. We never regenerate because we dislike the behavior.

### Simulation gate: `experiment-bot-naive-sim <program>`

Runs the program against ~1,000 synthetic trials built from the structural
card's condition stream (including interrupt trials where applicable).
Mechanical checks only — never evaluates whether behavior looks human:
no exceptions; RTs finite, in (0 ms, 60 s); keys ∈ available set or withhold;
same seed → identical output; different seeds → non-identical output; import
scan confirms stdlib + numpy only (no I/O, network, or clock modules).
Report archived as `<sha>.simgate.json`.

## Experiment protocol

**Pre-registration** (`docs/preregistration-naive.md`, committed before any
generation call — the generation transcript is itself data):

- **Arms:** naive (Fable programs, fixed executor) and expert-v2 (pinned
  Opus TaskCards, re-collected under the fixed executor). Dev-4 × N=30 each,
  explicit seeds, hermetic.
- **Primary (confirmatory, descriptive):** each arm vs the Eisenberg human
  reference on the existing battery (per-subject metrics, z, within-1-SD),
  same estimators, same code.
- **Exploratory:** SD ratio, two-sample KS, naive-vs-expert contrast
  (within-1-SD counts, dispersion). Arms are never gated against each other;
  the human reference is the yardstick for both.
- **Exclusions:** frozen-run rules (`.incomplete`, completeness flag) plus:
  live program crash → session hard-fails, is excluded and counted; ≥3 live
  failures for a paradigm after gate pass → that paradigm reported as a
  naive-arm failure, not retried into submission (SP3 honest-failure
  precedent).

**Collection:** `scripts/naive_run.sh` (generate → gate → 30 seeds/paradigm →
`output_naive/`) and expert re-collection via the existing
`scripts/frozen_run.sh` pattern into `output_expert_v2/`. Both resume-by-seed
idempotent,
4 parallel streams. Analysis: the existing `experiment-bot-per-subject` CLI
applies to all arms unchanged (naive sessions produce platform-native exports
through the untouched capture path).

## Error handling

- Program crash mid-session → hard-fail with traceback in `run_metadata`
  (zero-trial guard already exists).
- Protocol violations (key outside available set, NaN/negative RT) raise
  immediately at the provider boundary — no silent coercion.
- Gate-passed programs that fail live are counted under the pre-registered
  exclusion policy.

## Testing

- **Unit:** provider loading by hash; protocol conformance errors; executor
  bypass (provider called; sampler/jitter/accuracy paths not); interrupt
  handoff; simulation-gate checks (each failure mode has a fixture program);
  prompt-neutrality invariants; provenance recording.
- **Integration:** a hand-written toy program driven through the mocked
  executor end-to-end.
- No live-network tests in CI.

## Non-goals

No new analysis estimators; no adapter changes (dev-4 adapters exist); no
generative-TaskCard grammar work (next SP, to be informed by the four
generated programs); no held-out paradigm (no trial-level human reference
exists for it).
