# Run artifact contract

Write UTF-8 JSON and Markdown. Use paths relative to the run directory in
artifacts. `null` means unknown or unavailable; `[]` means no items observed.
Every run, including an incomplete run, has:

```text
<run>/
  run.json          provenance, status, data availability, artifact hashes
  ontology.json     task entities, relationships, evidence, unresolved questions
  events.jsonl      append-only observations and actions
  summary.md        what the task required and what happened
  protocol/         exact skill instructions used for this attempt
  evidence/        saved instruction/state text, screenshots, completion evidence
  data/            original platform export, only if obtained
```

## Ontology

Use this shape, filling it from observations rather than a task catalog:

```json
{
  "schema_version": "1.0",
  "task": {"url": "<supplied URL>", "title": null},
  "nodes": [],
  "relations": [],
  "evidence": [],
  "unknowns": []
}
```

A node has `id`, `kind`, `label`, `attributes` (an object), `status`
(`observed` or `inferred`), and `evidence_refs` (evidence IDs). Choose kinds to
fit the observed task: for example `phase`, `stimulus`, `response`, `rule`,
`feedback`, `timing`, or `completion`. These are structural categories, not a
closed vocabulary of paradigms. IDs remain stable throughout the run.

A relation has `subject`, `predicate`, `object`, `status`, and `evidence_refs`.
Both endpoints refer to node IDs. Relations express the task: a phase presents
a stimulus, a rule applies in a phase, a rule maps a stimulus to a permitted
response, or feedback follows a response. Preserve conditional mappings as
rule nodes with their conditions and scope in `attributes`; do not flatten
different blocks into one global key map.

An evidence entry has `id`, `path`, `locator`, `source_type`, `observed_at`,
and `description`. `path` identifies a saved file; `locator` identifies its
relevant lines, event, image region, or export row. Source types include
`visible_text`, `screenshot`, `audio`, and `native_export`. Use actual UTC
observation timestamps, not invented trial-onset times.

Every node and relation needs at least one resolvable evidence reference.
Record an unsupported possibility in `unknowns` instead of asserting it.
Split assertions with different evidence or status into separate nodes.
Inference means an interpretation of cited observations; it does not turn
an unsupported claim into a fact. An unknown has `question` and
`reason`; add `related_ids` when relevant. Preserve conflicting observations
with their phase/session context and an unresolved question until resolved.

Before finalizing, account for the instructions, observed phase progression,
response channels and mappings, feedback, and ending. Record deadlines,
interruptions, sequence presentation, adaptation, or randomization only when
observed or explicitly described. Unseen blocks stay unknown. A page's claim
about its procedure is evidence of that instruction, not proof every trial
followed it. Numeric task settings are structural facts when evidenced;
estimated human behavioral parameters do not belong here.

## Event trace

One JSON object per line, appended as the session progresses. Each has:

- `index`: strictly increasing event number.
- `at`: UTC timestamp of this observation or action.
- `kind`: `observation`, `action`, `feedback`, `error`, or `completion`.
- `phase_id`, `trial_id`: known IDs, otherwise `null`; do not invent a native
  trial ID from an agent counter.
- `observation`: concise participant-visible content, or `null`.
- `action`: input type and value/target, or `null`.
- `outcome`: observed effect, including delivery uncertainty, or `null`.
- `evidence_refs`: IDs of saved evidence when available.
- `timing`: measured timestamps/durations and their clock/source, or `null`.

Save sufficient visible evidence to reconstruct which instructions and stimuli
were available for each decision. Text may live in the event itself; screenshots
are needed when text loses the stimulus information. Record chosen actions and
brief observable reasons when helpful, not private chain-of-thought. Never label
an agent timestamp difference as native RT. Preserve exact native export fields
without editing them to match this event format.

## Manifest

`run.json` has these fields:

| Field | Meaning |
|---|---|
| `schema_version` | `"1.0"` |
| `run_id` | Unique directory/session ID |
| `purpose` | `participation` or `discovery`; choose before running, retain all native data in either case |
| `mode` | `"direct_browser"` or `"generated_visible_policy"`; the latter follows execution.md |
| `input_url`, `final_url` | Supplied URL and last observed URL |
| `started_at`, `ended_at` | Actual UTC timestamps; end may initially be null |
| `status` | `running`, `completed`, `partial`, or `blocked` |
| `status_reason` | Evidence-based explanation |
| `model` | Reported provider/model/version, unknown fields null |
| `browser` | Tool and available browser/version/viewport information |
| `observation_boundary` | `"participant_visible"` |
| `skill_sha256` | Map of skill file names to SHA-256 of exact bytes saved in protocol/ and used |
| `seed` | Null unless a seed was actually supplied and used; record its scope |
| `reproducibility` | What was recorded; direct agent sessions do not promise deterministic replay |
| `completion_evidence_refs` | Evidence IDs establishing the terminal state; empty if unconfirmed |
| `data_export` | `status`: `available`, `unavailable`, or `not_attempted`; plus `paths` and `reason` |
| `submission` | `status`: `not_required`, `confirmed`, `failed`, or `unconfirmed`; plus observed evidence/reason; local completion does not prove remote receipt |
| `counts` | Separate observed response opportunities/actions from native export trial rows; unknown counts null |
| `limitations` | Timing, modalities, missed observations, incomplete export, other observed constraints |
| `artifacts_sha256` | Map of finalized relative file paths to exact-byte SHA-256 |

For generated-policy runs, also record `policy_sha256`, `policy_path`,
`authoring_prompt_path`, `gate_report_path`, `seed` (with its scope), and
`parent_attempt` when a failed direct attempt motivated this mode. Store the
policy, prompt, mechanical checks, and any failed candidates in `policy/`.
Record `authoring_context` as `inherited_agent_context` or `isolated_model_call`,
with the full transcript path when available and an explicit limitation when
not. A prompt instruction file does not by itself capture the full model context.
Record the actual input delivery method and observation interface. Seeded
policy decisions do not make a live web session deterministically replayable.

`completed` means the terminal state was observed, not that every response was
correct or that native data was obtainable. `partial` means participation began
but completion was not confirmed. `blocked` means a prerequisite prevented
participation. Explain the last state and any safe resumption point.

Hash all saved artifacts except `run.json` itself (avoids self-reference).
Never hash nonexistent files or reuse a hash after editing the file. Capture
the skill hashes at the start so later edits cannot change the reported
instructions. Preserve supplied session parameters locally; redact sensitive
URL parameters and participant details in user-facing summaries.

## Summary and verification

`summary.md` explains the task in plain language, observed progression, outcome,
export availability, unresolved ontology questions, and limitations. Link its
claims to relative evidence files. State that this is a synthetic participant.
Keep behavioral validity and browser completion distinct.

Before returning the directory, use `scripts/check_run.py` from the skill to
validate JSON/JSONL, IDs, relations, evidence paths, and hashes. Its `--seal`
option writes hashes only after structural checks pass; it never changes the
run's outcome. Save further reports before sealing; adding or editing a file
after sealing invalidates the manifest. The script checks integrity, not the
truth or completeness of the ontology.
Read any native export to establish whether it contains trial records, a
summary only, or an incomplete payload, and report that distinction. Export
inspection happens after participation and must not drive reruns or selection.
