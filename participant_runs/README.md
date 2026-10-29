# Collected outputs

Read [the online findings](online-battery-20261028/findings.md) to compare task
outcomes. Use [the complete index](online-battery-20261028/summary.md) to inspect
an attempt. Each attempt records its own execution mode, limitations, and
available evidence.

## Collections

| Collection | Purpose | Contents |
|---|---|---|
| [Online battery](online-battery-20261028/summary.md) | Exercise distinct browser interactions and repair mechanical failures | 24 attempts across six task types, including partial and blocked runs |
| [Smoke test](skill-smoke/summary.md) | Check the initial browser and artifact workflow | Four canvas-key trials on a local fixture |
| [OCR checks](online-battery-20261028/ocr-glyph-validation/README.md) | Test pixel recognition against saved fixtures | Original inputs where available, transformations, candidates, and measured matches |

## Archive boundary

Files inside each attempt are historical records. Preserve their exact bytes,
including protocol snapshots, programs, exports, summaries, and files named in
`artifacts_sha256`. Some manifests include Python bytecode or compiled macOS OCR
helpers. Those files remain part of the record; rebuild helpers from source for
new runs.

The current skill lives under `skills/behavioral-participant/`. Its prose can
change without changing what an earlier attempt used. Read a run's `protocol/`
files when investigating its instructions, and the current skill when starting
a new run. The smoke test uses the legacy 1.0 manifest contract and has its own
validation record.

Absolute workstation paths, local browser endpoints, and temporary executable
paths in saved commands describe the original environment. Locate files by their
repository-relative paths. Historical drivers are evidence of execution, not
portable launchers. Start new participation through the current skill.

## Known gaps

The memory task’s final protocol snapshot links to `perception.md` but omitted
that file. Its other pinned files and saved observations remain intact; the
missing reference limits reconstruction of that attempt’s instructions. The
current skill includes the reference.

The smoke test records a local fixture URL whose source page was not included
in its output directory. Its observations and native export are inspectable,
but that directory alone cannot recreate the fixture.

## Provenance

The archive was copied from `lobennett/experiment_bot` at source commit
`40cdf925c36e8829756d5d9ee6e92711c4b2f095`. This records the local source revision; the
standalone branch does not contain its history.
The online evaluation used changing protocol revisions, each recorded within
its attempt. The source commit identifies the final skill before extraction;
the outputs themselves were local files outside that commit.

[archive-integrity.json](archive-integrity.json) records the imported files and
their SHA-256 hashes. It covers every attempt and the supporting evaluation
artifacts. It excludes this entry point and the branch's publication check.
Keep imported reporting scripts as historical tooling: rerunning a generator
would replace archived reports and invalidate their import hashes.
The current skill's artifact checker verifies all 25 attempts, including the
smoke test, without resealing them.

The historical report's 772 passed / 6 skipped test result belongs to the source
repository. This standalone branch carries eight skill-specific tests.
[publication-check.json](publication-check.json) records the checks run for this
branch. Native exports are the source for behavioral results; event logs are
execution diagnostics.

## Interpretation

A terminal page establishes local completion. Read response-bearing phases
separately: primary trials, practice, and short instruction checks can have
different coverage. An export can be available even when remote submission
failed or remained unconfirmed.

The accepted participant programs remained frozen while adapters were repaired.
These exploratory runs do not establish human-like behavior, isolated policy
generation, comprehension, or timing equivalence. Each run's summary states the
limits observed there.
