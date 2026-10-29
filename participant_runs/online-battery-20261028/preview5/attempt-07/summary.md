# Preview 5 — completed with attention-check omissions

Synthetic participant. **Local task completion observed; automatic remote upload failed.** The [terminal screenshot](evidence/020-completion.png) establishes both facts. The [original native JSON export](data/experiment_data.json) contains 485 rows, including the end row.

| Response-bearing phase | Opportunities | Responses | Correct responses | Omissions |
| --- | ---: | ---: | ---: | ---: |
| Practice letters |13|13|13|0|
| Test letters |135|135|135|0|
| Additional instruction checks |10|4|4|6|

All delivered responses were scored correct by the platform. The six missed checks are retained as omissions and as native incorrect scores; they are not hidden by successful letter performance. [Phase inspection](data/export-inspection.json) includes both delay conditions and every instruction-check row.

The [task instructions](evidence/004-instructions.json) require matching each image-rendered letter against one or two trials earlier, ignoring capitalization. Comma means mismatch and period means match. Practice included visible reminders and feedback; the test had ten blocks with delay cues at boundaries. An additional 15-second instruction check appeared before each test block, sometimes naming a key and sometimes naming its position in the English alphabet.

The first mechanically passing policy from attempt 03 was retained byte-for-byte. It decides all letter responses and deliberately requests immediate action. Task-local perception repairs supplied screenshot OCR and an equivalent representation of the newly observed delay-2 cue; raw visible text and canonical facts are recorded separately. The generic Vision fast/crop configuration was checked on archived glyph and blank fixtures before this run. Original screenshot crops, derived resize/crop transforms, and raw OCR candidates are preserved.

The local loop kept observing and responding when operator commands were delayed. Several short instruction checks expired before the agent could answer them. Stale Enter commands were skipped rather than applied to a new screen; missed checks were never replayed. See the [control-delay note](evidence/operator-delay-note.md). No task timer or page data was changed.

The native export supplies all behavioral results; events are diagnostic only. Native timings include OCR and browser transport, with no subtraction or human-timing claim. Authoring inherited the agent context, and a full generation/tool transcript is unavailable. These exploratory browser runs are separate from the project's frozen study. No human behavioral comparison was performed.
