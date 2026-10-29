# Preview 10 attempt-05: completed

The synthetic participant used the first mechanically passing visible-color policy, unchanged from attempt 02. Its SHA-256 is `70a4958379c7c5fe8e6037f1a1b4419ccfa67cf5f35144c3aa0614824d8b48c4`. Dedicated Playwright input and rendered DOM observation replaced the failed CLI adapter; the loop stayed continuous across timed trials.

The [native export](data/experiment_data.json) contains 392 rows and 124 response trials, with 124 recorded responses and 124 recorded correct. Practice trials: 4; test trials: 120. Native RT min/median/max: 6/19.0/49 ms. These very fast program responses are an operational result, not evidence of human timing fidelity. There was no RT or accuracy tuning.

The terminal screen states Experiment Complete and Attempting to upload results ([text](evidence/completion.txt), [image](evidence/completion.png)). Task completion was observed; remote upload acceptance was not confirmed.

The [trace](events.jsonl) records instructions, feedback, rendered color/geometry, policy decisions, and ordinary keyboard delivery. The task's own instruction-reading guard caused instruction repetition. The original adapter used default checkVisibility options; subsequent adapters must explicitly exclude CSS-hidden/transparent/offscreen content and test that boundary. Original stimulus screenshots are retained for inspection.

Policy authoring occurred inline with inherited agent context. The explicit neutral [prompt](policy/authoring_prompt.md) and mechanical [gate](policy/gate.json) are archived, but they are not a separate model-call transcript or evidence of prompt isolation. This exploratory session is separate from the frozen participant-program study. Every earlier mechanical failure and the parallel partial attempt are retained.

## Attention-check failure

The native export also contains three inter-block letter-key attention checks. All three were missed: requested m/e/j responses are null (0/3 answered). The original navigation adapter did not hand these unexpected instructions to the agent. Thus 124/124 correct refers only to practice/test classification trials; this run does **not** satisfy the task’s full participant-data requirements despite reaching the terminal screen. This phase-detection limitation must be addressed in subsequent adapters without changing the frozen response policy.
