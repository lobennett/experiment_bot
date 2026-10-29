# Six task types, with operational and behavioral limits

All six task types reached terminal states and yielded native exports. The 24 attempts include failures, partial runs, and terminal runs with missed observations. Every attempt is retained in [summary.md](summary.md) and [results.json](results.json). Artifact hashes and ontology references verify for all 24 attempts.

The table describes the most recent terminal run for each task. It is a development report, not a cohort selected for analysis. In particular, Stroop attempt 06 is a later partial attempt and remains in the index.

| Task and evidence | Main result from native export | Other response-bearing phases | Timing and interpretation |
|---|---|---|---|
| [Stop signal, attempt 03](preview9/attempt-03/summary.md) | GO: 118/120 correct, 2 omissions. STOP: 33/60 withheld, 27 responses. | 12 practice trials retained, including setup omissions; attention checks 1/3 answered. | Main GO median 887.5 ms. Task feedback reported slow responses. Withholding is an observed outcome, not a human-validity score. |
| [Stroop, attempt 05](preview10/attempt-05/summary.md) | Test: 120/120 correct. | Practice: 4/4 correct; attention checks 0/3 answered. | Response median 19 ms, range 6–49 ms. Immediate policy classification does not establish human-like behavior. |
| [Tower of Hanoi, attempt 02](tower-hanoi/attempt-02/summary.md) | Seven ordinary mouse drags; both native mistake counters zero. | No separate attention-check phase observed. | Native cumulative duration 81,424 ms includes model/tool time. Direct browser participation. |
| [Self-paced reading, attempt 05](self-paced-reading/attempt-05/summary.md) | Five sentences; 28/28 words matched in native order; zero 9,999 ms timeout intervals. | No separate attention-check phase observed. Earlier terminal runs had incomplete or absent word observations. | Median 395 ms, range 369–433 ms. OCR coverage, not direct per-word LLM comprehension. |
| [Memory / n-back, attempt 07](preview5/attempt-07/summary.md) | Test: 135/135 correct. | Practice: 13/13 correct; attention checks 4/10 answered, 6 omitted. | Screenshot/OCR and input latency are included. Immediate additional waiting was the frozen policy's choice. |
| [Visual search, attempt 01](preview28/attempt-01/summary.md) | Test: 192/192 correct. | Practice: 4 responses scored correct, 4 omissions with unknown correctness; attention checks 2/3 answered. | Response median 19 ms, range 5–41 ms. Immediate policy classification does not establish human-like behavior. |

Five task types required a local model-authored policy to meet their deadlines; Tower of Hanoi used direct model decisions and browser input. Each accepted policy stayed frozen. Changes addressed observation, input delivery, session persistence, OCR, or instruction handling. All attempts, failed adapters, and available native exports remain archived. No program was tuned to match human behavioral data.

## What changed in the skill

- Separated direct participation from generated-policy execution and made the distinction part of each manifest.
- Added real browser and control-channel preflight, persistent participant memory, stale-input guards, and session isolation for parallel workers.
- Added rendered-visibility checks and optional OCR with source-image provenance and saved-image fixtures.
- Required instruction handoffs to preserve ongoing observation and report missed short prompts.
- Strengthened ontology evidence links, protocol snapshots, policy pins, and artifact validation.
- Required phase-specific results so successful primary trials cannot conceal missed practice or attention checks.

The skill remains task-agnostic: task mappings and response programs live inside run directories. Its entry point links to execution, perception, and artifact contracts rather than requiring the original repository harness. The original frozen study and its cohorts were not changed.

## Limits that remain

The most important remaining failure is agent handoff latency: short novel instructions can expire while a model/tool round trip is delayed. A terminal page therefore does not establish satisfactory participant performance. Remote uploads failed for stop signal and memory, and acknowledgment was unconfirmed for Stroop and visual search. Local native exports are preserved; no remote acceptance is claimed.

This battery covers six tasks across two platforms. It does not establish unseen-task generalization, audio support, human behavioral validity, or timing equivalence. Inline program authoring inherited agent context rather than using an isolated generation call; complete generation/tool transcripts were unavailable. Native timings were neither adjusted nor filtered to resemble human data. These exploratory artifacts remain separate from the project's frozen study.

Validation: 772 tests passed, 6 skipped, with 7 existing AsyncMock runtime warnings. Skill metadata and documentation links passed validation. The OCR helper matched 13/14 glyph fixtures exactly and 14/14 ignoring case; its one case ambiguity is disclosed in [glyph validation](ocr-glyph-validation/README.md), not silently corrected. See [verification.json](verification.json).
