# Preview 9: direct-browser baseline

**Partial run.** The agent entered real practice but could not respond within the presentation windows. No main test or terminal completion was reached. The owned task tab was closed after export to stop further unattended trials.

Instructions mapped circle to comma and square to period. A star around a shape required withholding a response, without slowing to wait for it ([mapping](evidence/06_begin.txt), [star instruction](evidence/07_instructions_next.txt)). Practice included reminders and feedback.

A [screenshot showed a square](evidence/11_practice.png); the [next screenshot was blank](evidence/12_practice.png) before a grounded key response could be sent. The [feedback screen](evidence/14_practice_feedback.txt) reported low accuracy and omitted required responses and announced an automatic practice repeat. Snapshot calls took about 0.37–0.40 s, screenshots about 0.18–0.21 s, and navigation about 0.6–1.0 s, excluding model inference. Shape identity was absent from the accessibility text.

The [native export](data/experiment_data.json) contains 55 rows, including 12 practice response opportunities: 8 required-response trials and 4 withholding trials. No response keys were recorded. All 8 required responses were omitted. The exported trial duration is 1500 ms, with stimulus duration 1000 ms. These timing settings were learned after participation ended, not used to solve trials. Practice repeated automatically while export was being arranged; no agent-requested restart occurred, and all captured rows are retained.

Export used the documented read-only [jsPsych data API](https://www.jspsych.org/6.3/core_library/jspsych-data/#jspsychdataget), retaining the exact JSON string. No source code, future trial state, or answer metadata was consulted while participating. No clock or experiment state was changed.

This synthetic direct-browser run demonstrates navigation and structural understanding but fails timely participation. A lower-latency, explicitly declared execution mode is required for this task; the result does not establish human-like behavior. Suggested skill changes concern observation transport, current-stimulus validation, and bounded segment execution, not behavioral output tuning. The [ontology](ontology.json) records the task structure and unresolved questions.
