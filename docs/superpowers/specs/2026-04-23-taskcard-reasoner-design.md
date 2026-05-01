# SP1 — TaskCard + Reasoner: Design

**Date:** 2026-04-23
**Author:** Logan Bennett (via Claude Opus 4.7)
**Status:** Approved
**Program context:** First sub-project of a 6-sub-project program to refactor experiment-bot into a defensible scientific tool. See "Program context" section below for the full decomposition.

## Goal

Define a peer-reviewable artifact (the TaskCard) that captures everything a reviewer would need to audit how the bot decided to behave on a given task: parameters with central tendency, empirically observed range, individual-differences spread, literature citations grounding each value, and a structured reasoning chain. Build a multi-stage Reasoner that produces TaskCards from a task URL using either the user's Claude Max subscription (default) or the Anthropic API.

The TaskCard replaces today's `cache/{label}/config.json`. The existing executor is updated minimally so it can read TaskCards while preserving the green test suite; full HPC and audit work is deferred to later sub-projects.

## Background

The existing experiment-bot pipeline (`Claude → cache/config.json → executor`) was hardened over a 30+ commit code-review pass (see `2026-04-21-code-review-design.md` and `2026-04-21-code-review-findings.md`). That pass closed agnosticism leaks but kept the pipeline shape unchanged. The current cached configs contain `rationale` strings produced by Claude but no structured citations, no parameter ranges, no reasoning chain, and no versioned reproducibility metadata.

A skeptical cognitive-psychology reviewer reading those files cannot verify that, e.g., `mu = 480 ms` for go-trial RT in stop-signal tasks comes from anywhere specific. The reasoning is opaque, and there is no way to distinguish parameters Claude is confident about from parameters it is guessing at. This is the gap SP1 closes.

The user's primary deliverable is a defensible scientific paper arguing that this bot poses a serious risk for online behavioral data collection on speeded-choice tasks, demonstrated on tasks the bot has never been configured for during development. SP1 produces the artifact format that defends every parameter individually.

## Program context

This spec covers SP1 only. The full program (in dependency order):

1. **SP1 (this spec): TaskCard + Reasoner.** Schema for the peer-reviewable artifact. Multi-stage Reasoner that produces it. Migration off v1 cached configs.
2. **SP2: Behavioral fidelity expansion.** A generalizable framework where Claude identifies which canonical sequential/temporal effects apply per task type and parameterizes them. CSE applies to conflict paradigms (Stroop, Flanker, Simon); switch costs to task-switching; list-length effects to memory tasks; speed-accuracy tradeoffs to forced-choice paradigms; etc. The TaskCard schema's `temporal_effects` section becomes extensible — new effect types are added as registered entries Claude can opt into per task. Distributional matching against human references. Calibration of `between_subject_sd` from human population spread (per-paradigm where reference data exists).
3. **SP3: Performer (HPC-ready).** Deterministic seeded execution. Headless cluster runtime. Slurm batch scripts. Distributed output coordination. **Platform-native data capture:** for server-uploading platforms (Expfactory, Cognition.run), intercept the network upload via Playwright's `page.on("request")` and persist the exact payload the server would have received. For client-only platforms (jsPsych without DataPipe), keep the current page-state extraction. Output includes a side-by-side comparison of platform-recorded vs locally-measured RT to characterize browser latency.
4. **SP4: Validation framework.** Statistical oracles (KS, Anderson-Darling, sequential-effect tests). Bot-vs-human comparison reports per task per metric. Power analysis. Tests run against the platform-native data (SP3 output) so the comparison is "what the platform recorded for the bot" vs "what the platform recorded for humans" — protects against the reviewer critique that bot RTs come from a different clock than human RTs.
5. **SP5: Novel paradigm acquisition.** 2–4 novel paradigms (candidates: Flanker, Simon, n-back, task-switching, lexical decision — final selection in SP5). Source URLs. Reference human data per paradigm. Replaces the under-trial cognition.run stroop with a richer paradigm.
6. **SP6: Traceability + audit.** Per-session trace logs linking every decision back to TaskCard fields. Audit reports for the paper.
7. **SP7: Analysis pipeline.** Refactor `scripts/analysis.ipynb` (currently per-platform per-task) to consume the new TaskCard + Performer output format. Column-level audit of each platform's output (verify what each column means, how RT/accuracy/condition are encoded, what timing reference each platform uses). Update analysis to use platform-native data from SP3 as the canonical source. Where possible, generalize across tasks (e.g., a generic "speeded-choice analysis" function that takes a TaskCard + output and produces the standard metric battery). Per-paradigm specializations stay specialized. Final outputs feed SP4's statistical oracles.

Each gets its own brainstorm → spec → plan → implementation cycle. SP2, SP3, and SP6 can be parallelized after SP1 lands; SP4 needs SP2's schema additions and SP3's platform-native capture; SP5 needs everything; SP7 is last because it consumes the final output format.

## Architecture

```
URL ──> Reasoner (5 stages) ──> TaskCard.json (versioned, immutable)
                                       │
                                       ▼
                            Performer (executor, HPC)
                                       │
                                       ▼
                              session_data.* + trace_log.json
```

**Reasoner** runs offline. Once per task URL. Writes a versioned `taskcards/{label}/{first_8_chars_of_hash}.json`. Requires internet (Claude + OpenAlex DOI lookup). Deterministic given (model, prompt, scraper version, source bytes).

**Performer** runs at session time. Reads a TaskCard, executes via Playwright, writes data + trace. No Claude API at runtime. SP3 turns it HPC-ready; SP1 just keeps it compatible with the new TaskCard layout.

**SP1 delivers:** the TaskCard schema, the 5-stage Reasoner with both LLM client implementations, full regeneration of the 4 train tasks, executor adaptation to read TaskCards. SP1 does NOT deliver Slurm scripts, statistical oracles, new behavioral mechanics, or new paradigms.

## TaskCard schema

The TaskCard is a strict superset of the current `TaskConfig`. Today's executor can read every legacy field unchanged; new fields are consumed by Performer/audit tooling.

### Top-level structure

```jsonc
{
  // Versioning + reproducibility metadata
  "schema_version": "2.0",
  "produced_by": {
    "model": "claude-opus-4-7",
    "prompt_sha256": "abc123...",
    "scraper_version": "1.2.0",
    "source_sha256": "def456...",
    "timestamp": "2026-04-23T12:34:56Z",
    "taskcard_sha256": "789xyz..."
  },

  // Legacy fields (current TaskConfig schema, unchanged)
  "task": {...},
  "stimuli": [...],
  "navigation": {...},
  "runtime": {...},
  "task_specific": {...},
  "performance": {...},

  // EXTENDED: response_distributions becomes provenance-aware
  "response_distributions": {
    "go": {
      "distribution": "ex_gaussian",
      "value": {"mu": 480, "sigma": 60, "tau": 80},
      "literature_range": {
        "mu": [430, 530],
        "sigma": [40, 80],
        "tau": [50, 110]
      },
      "between_subject_sd": {"mu": 50, "sigma": 10, "tau": 20},
      "citations": [
        {
          "doi": "10.1016/j.cognition.2008.07.011",
          "authors": "Whelan, R.",
          "year": 2008,
          "title": "Effective analysis of reaction time data",
          "table_or_figure": "Table 2",
          "page": 481,
          "quote": "Healthy adults on go trials: mu=460 ms, sigma=55 ms, tau=85 ms",
          "confidence": "high",
          "doi_verified": true,
          "doi_verified_at": "2026-04-23T12:34:58Z"
        }
      ],
      "rationale": "Go-trial RT in stop-signal tasks for healthy adults...",
      "sensitivity": "high"
    }
  },

  // Same provenance shape on temporal_effects and between_subject_jitter
  "temporal_effects": {...},
  "between_subject_jitter": {...},

  // Structured reasoning trace
  "reasoning_chain": [
    {
      "step": "task_identification",
      "input_hash": "...",
      "inference": "Source code references jsPsych plugin-stop-signal...",
      "evidence_lines": ["plugin-stop-signal.js line 47", "main.js line 213-217"],
      "confidence": "high"
    }
    // ... one entry per major decision
  ],

  // Pilot validation results (currently external; now stored in TaskCard)
  "pilot_validation": {
    "passed": true,
    "iterations": 1,
    "trials_completed": 22,
    "selectors_fired_at_least_once": true,
    "all_target_conditions_observed": true
  }
}
```

### Three-tuple parameter representation

Every numeric behavioral parameter has three views:

- **`value`** — central tendency. Used for regression tests and as the mean of session-start sampling.
- **`literature_range`** — empirically observed range across published studies. Used as a clip on session-start draws and as the bounds reviewers compare bot output against.
- **`between_subject_sd`** — standard deviation of session-start sampling. Drives individual differences. Replaces `between_subject_jitter.rt_mean_sd_ms` for distributional parameters; the existing `between_subject_jitter` section stays in place for orthogonal effects (accuracy, omission, sigma_tau scaling) until SP2 reorganizes.

### Citations

Every numeric parameter requires a non-empty `citations` array. Each citation includes DOI, authors, year, title, table/figure pointer, page number, exact quote, confidence rating, and DOI verification status.

### Reasoning chain

A list of structured steps, each with `step` name, `inference`, `evidence_lines` pointing into the scraped source, and `confidence`. Auditable by reviewers; not consumed at runtime.

### Sensitivity tags

Each numeric parameter is tagged `sensitivity ∈ {high, medium, low}` based on how much it affects bot output metrics (mean RT, accuracy, distributional shape, sequential effects). High-sensitivity parameters drive SP4's prioritization of statistical tests.

### Versioning + hashing

`taskcard_sha256` is computed over canonicalized JSON minus the hash field itself. Filenames are `taskcards/{label}/{first_8_chars_of_hash}.json`. New regenerations produce new files; old TaskCards are preserved for reproducibility comparisons.

## Reasoner pipeline

Five stages. Each stage's output is appended to a partial TaskCard. Stages are independent and resumable: failure in stage N preserves stages 1…N−1 on disk and `--resume` continues.

| Stage | Mechanism | Input | Output | Notes |
|---|---|---|---|---|
| **1. Structural inference** | LLMClient call | Source HTML+JS bundle, schema | Stimuli, navigation, runtime, phase_detection, task_specific, pilot config | Uses `prompts/system.md` (with Phase 1 fixes). No behavioral params yet. |
| **2. Behavioral inference** | LLMClient call | Stage 1 + paradigm identification | `response_distributions[*].value`, `performance.{accuracy, omission_rate}`, `temporal_effects` (point estimates) | Point estimates only; ranges + SDs come in Stage 3. |
| **3. Citation production** | LLMClient call(s) per parameter | Stage 2 parameters | `citations[]`, `literature_range`, `between_subject_sd` per parameter | Parallelizable. Either fan-out (one call per parameter) or batched (one call returning all citations). Implementation will benchmark both; default to whichever produces higher citation quality on the 4 train tasks. |
| **4. DOI verification** | Out-of-band HTTP | Stage 3 citations | `doi_verified` flag per citation | Hits OpenAlex API (`https://api.openalex.org/works/doi:{doi}`). No LLM. Failures flagged but non-blocking. |
| **5. Sensitivity tagging** | LLMClient call | All previous output | `sensitivity` tag per numeric parameter | Considered nice-to-have for SP4; included in SP1 because the cost is modest (~30s, 1 call). |

After stage 5, the existing pilot validation loop runs (max 2 refinement iterations) and structural fields may be edited. Behavioral fields and citations are immutable post-stage-3.

### LLMClient protocol

```python
class LLMClient(Protocol):
    async def complete(
        self,
        system: str,
        user: str,
        max_tokens: int = 16384,
        output_format: Literal["text", "json"] = "text",
    ) -> str: ...
```

Two implementations:

- **`ClaudeCLIClient`** — shells out to `claude --print --output-format json -p <prompt>`. Uses the user's Max subscription via `claude login`. Default when `claude` is on PATH and authenticated. Tracks Max-window quotas via subprocess return codes / stderr; sleeps + retries on `quota_exceeded`.
- **`ClaudeAPIClient`** — wraps `anthropic.AsyncAnthropic`. Uses `ANTHROPIC_API_KEY`. Fallback when CLI is unavailable (HPC nodes, CI).

Auth selection: env var `EXPERIMENT_BOT_LLM_CLIENT=cli|api`. If unset, defaults to `cli` if `claude` is available else `api`.

## Migration

**Decision: full regeneration. No migration shim.**

The new TaskCard format is fundamentally richer than v1. Auto-upgrading would leave most TaskCards with empty citation arrays and `_legacy: true` markers; they would be regenerated anyway. Skip the intermediate state.

Concrete migration steps:

1. SP1 ships the Reasoner.
2. As part of SP1's bring-up, the Reasoner regenerates all 4 current task URLs to produce v2 TaskCards via Max CLI.
3. The 4 existing `cache/{label}/config.json` files are deleted.
4. The new `taskcards/{label}/{hash}.json` files replace them.
5. Tests are updated to read from `taskcards/`. Existing 4 cached-config contract tests become 4 TaskCard contract tests.
6. The 4 novel paradigms in SP5 are born as v2 from day 1.

**Cost / wall-clock:** With Max CLI, $0 cost. ~150–200 Claude calls across the regeneration window. Wall-clock estimate 2–3 hours of active reasoning time, possibly stretched across 2–3 five-hour Max windows depending on user's tier. Resume mechanism handles cap boundaries cleanly.

## Performer's TaskCard contract

The Performer reads a partition of TaskCard fields at runtime. All other fields are audit-only.

### Runtime fields (consumed during execution)

`task`, `stimuli`, `navigation`, `runtime`, `task_specific`, `performance`, `response_distributions[*].value`, `response_distributions[*].literature_range`, `response_distributions[*].between_subject_sd`, `temporal_effects[*].value`, `between_subject_jitter`.

### Audit fields (never read at runtime)

`schema_version`, `produced_by`, `citations[]`, `rationale`, `reasoning_chain`, `sensitivity`, `pilot_validation`.

### Session-start parameter sampling

```python
def sample_session_params(taskcard, seed):
    rng = np.random.default_rng(seed)
    sampled = {}
    for cond, dist in taskcard["response_distributions"].items():
        v = dist["value"]
        r = dist.get("literature_range")
        sd = dist.get("between_subject_sd")
        sampled[cond] = {}
        for param in ("mu", "sigma", "tau"):
            mean = v[param]
            spread = (sd or {}).get(param, 0)
            draw = rng.normal(mean, spread) if spread > 0 else mean
            if r and param in r:
                lo, hi = r[param]
                draw = max(lo, min(hi, draw))
            sampled[cond][param] = float(draw)
    return sampled
```

This replaces `jitter_distributions()` for ex-Gaussian parameters. The legacy `between_subject_jitter` section stays for non-distribution effects.

### Determinism contract

`(taskcard_hash, seed) → sampled_params → trial sequence` (modulo experiment-side stochasticity like SSD staircases or random ITIs). Same inputs reproduce the same trace. This is the property HPC needs.

### Trace log emitted at session start

```jsonc
{
  "session_id": "...",
  "taskcard_hash": "789xyz...",
  "seed": 42,
  "sampled_params": {...},
  "performer_version": "1.0",
  "trial_log": [...]
}
```

The audit tooling (SP6) joins `taskcard_hash` back to citations / reasoning chain so a reviewer can trace any single trial's RT to a specific paper.

### Minimal SP1 executor changes

1. Replace `cache.py` with `taskcard_loader.py` reading from `taskcards/{label}/{hash}.json`.
2. Replace `jitter_distributions(config)` calls with `sample_session_params(taskcard, seed)`. Existing `between_subject_jitter` keeps applying to non-distribution effects.
3. Update `cli.py` and `analyzer.py` to read/write TaskCards instead of v1 configs.
4. Update tests: ~10–20 fixture updates, four contract tests move to TaskCards.

SP1 explicitly does NOT do: Slurm scripts, distributed output, full session trace shape (only minimal version), new behavioral effects.

## Testing approach

TDD throughout. Layers, in order of speed:

### Unit (fast, mocked)

- **Dataclass round-trips** for every new TaskCard subtype (`Citation`, `ParameterValue`, `ReasoningStep`, `ProducedBy`).
- **`sample_session_params`** via Hypothesis property tests: any `(value, range, sd, seed)` produces finite, in-range, deterministic output.
- **TaskCard hashing** is stable: same content with different key ordering or whitespace produces the same hash.
- **DOI verifier** with mocked OpenAlex responses: 200 + match, 200 + mismatch, 404, network error, malformed DOI.
- **`LLMClient` protocol**: both implementations have unit tests with subprocess / API call mocked.

### Integration (slower, fake LLM)

- **Each Reasoner stage** with a fake `LLMClient` returning canned structured responses; verifies stage produces expected TaskCard fragment.
- **Pipeline chaining** with full 5-stage flow on fake client; verifies stages compose, partial failures are recoverable, `--resume` works.

### Regression

- All ~232 existing tests adapted to read TaskCards. Fixtures regenerated. Test count expected to grow to ~280.
- Four cached-config contract tests become four TaskCard contract tests.

### End-to-end (gated)

- **One live regeneration test** (`@pytest.mark.live`, default-skipped, runs only with `RUN_LIVE_LLM=1`): hits real Claude (CLI or API), runs full Reasoner against `expfactory_stop_signal` URL, verifies TaskCard output.
- **One executor smoke against a regenerated TaskCard** (also `@pytest.mark.live`): runs the existing executor for a partial trial loop. Catches schema-drift bugs.

### TDD ordering

1. `Citation`, `ParameterValue`, `ReasoningStep` dataclasses with round-trips.
2. TaskCard top-level struct with hashing.
3. `LLMClient` protocol; `APIClient` first, `CLIClient` second.
4. Reasoner stages 1 → 2 → 3 → 4 → 5, each with full test before implementation.
5. `sample_session_params`.
6. Migration of executor + cli (minimal changes).
7. Live regeneration of 4 train tasks.

## Out of scope

| Deferred to | Items |
|---|---|
| **SP2** | A generalizable framework for canonical sequential/temporal effects per task type. Claude identifies which apply (CSE on conflict, switch costs on task-switching, etc.). Schema extensibility for new effect types. Distributional matching. Calibration of `between_subject_sd` from human population data. |
| **SP3** | Slurm batch scripts, distributed output coordination, headless cluster runtime. **Platform-native data capture:** intercept server uploads via Playwright network listening for server-uploading platforms; keep page-state extraction for client-only platforms. Side-by-side platform-recorded vs locally-measured RT in output. Full session trace log shape; deterministic seed coordination across nodes. |
| **SP4** | Statistical oracles (KS, Anderson-Darling, sequential-effect tests), bot-vs-human comparison reports against platform-native data, power analysis. |
| **SP5** | Specific novel paradigms (candidates: Flanker, Simon, n-back, task-switching, lexical decision). Sourcing URLs. Acquiring human reference data. Choosing the cognition.run replacement. |
| **SP6** | Full audit reports linking trace → TaskCard → citation. Per-session forensic trace logs. Reproducibility verification harness. |
| **SP7** | Analysis pipeline refactor: column-level audit of each platform's output, refactor of `scripts/analysis.ipynb` to consume new TaskCard + Performer output format, generalization across tasks where possible, integration with SP4 oracles. |
| **SP1.5** | Curated literature corpus per paradigm. Replaces stage 3's training-data-only citation production with corpus-grounded production. |
| **Other** | Full executor refactor with formal Protocols (deferred — current executor reads new fields and continues to work). Performance optimization beyond keeping the test suite under 30s. |

### Three explicit non-goals for SP1

1. **No new behavioral mechanics.** SP1 changes how parameters are *expressed and produced*; it does not change how the bot behaves at runtime. The 4 cached configs, when regenerated as TaskCards, should produce statistically equivalent bot behavior to today (within session noise). Testable.
2. **No HPC-specific code.** SP1's Performer changes are minimal. SP3 builds the cluster wrappers.
3. **No new tasks.** The 4 existing tasks are the regeneration targets. New paradigms wait for SP5.

## Risks

- **Hallucinated citations.** Stage 4's DOI verification catches the most egregious cases (DOIs that don't exist), but a real DOI with mismatched authors/year/title slips through unless stage 4 also checks metadata. Mitigation: stage 4 verifies authors and year match within tolerance; flagged-but-real citations make it into the TaskCard with `doi_verified: false` and the audit report surfaces them.
- **Max quota stalls.** Regenerating 8 tasks × ~25 calls could span 2–3 five-hour windows. Mitigation: `--resume` flag in the Reasoner CLI lets a partial regeneration continue across cap boundaries.
- **CLI subprocess fragility.** `claude --print --output-format json` is a stable interface, but version drift could break parsing. Mitigation: pin CLI version in tests; CI runs the live test on a manual trigger to catch drift early.
- **Test surface growth.** Adding Reasoner + DOI verifier + LLMClient implementations adds ~50 tests. The existing 232 tests need fixture updates. Mitigation: TDD ordering above keeps each step's tests bounded; total test runtime expected to stay under 30 seconds.
- **Schema drift from current configs.** Adapting the executor to read TaskCards risks subtle behavior changes (e.g., float precision differences in sampling). Mitigation: a regression test that regenerates one task and verifies bot's output metrics on a recorded session match the pre-SP1 baseline within 2 SE.
