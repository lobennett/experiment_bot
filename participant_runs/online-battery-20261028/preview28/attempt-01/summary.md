# Preview 28: completed

This synthetic participant performed the rectangle target-presence task through a dedicated browser. The observed instructions defined a vertical white rectangle as the target, comma for absent, and period for present. The saved [ontology](ontology.json) connects the stimulus array, target, response rules, three-block progression, and instruction checks.

The first generated policy passed a purely mechanical gate and remained unchanged (SHA-256 `b088c11f48c0e4f99a8ce44242847179cb116b17c60bcf860e6e80d045234973`). It uses only displayed rectangle color and geometry, with explicit intended delay_ms=0. Strict opacity, CSS visibility, viewport and occlusion checks were used; [matching screenshot](evidence/live-rectangles.png) and [rendered geometry](evidence/live-rectangles.json) confirm the actual representation. No asset filenames, hidden answers, future trials or task variables were used.

The [native export](data/experiment_data.json) has 622 rows: 8 practice and 192 test response trials. Total responses: 196/200; omissions: 4. Correct test trials: 192/192. Native RT min/median/max for recorded responses: 5/19.0/41 ms. These program latencies do not establish human timing validity.

Attention checks: 2/3 correct. The first m prompt was missed while an additional snapshot/poll consumed its 15-second window; a delayed m subsequently went during fixation. The later semantic alphabet instruction was answered y and the literal j instruction was answered j through guarded agent commands while visible. Native results and exact check RTs are in [native_metrics.json](native_metrics.json). This quality failure is preserved rather than concealed by main-trial accuracy.

The task automatically progressed into practice while inline policy authoring was still underway; initial omissions and practice repetitions remain in the same session. The explicit [authoring prompt](policy/authoring_prompt.md) was produced in inherited agent context and is not an isolated model-call transcript. Policy source, gate, transport preflight, controls and append-only events are retained. No behavioral tuning or selection occurred.

The terminal [page](evidence/completion.txt) and [screenshot](evidence/completion.png) establish task completion. Remote upload acknowledgment was not confirmed. These results establish operation on this task with the stated limitations, not acceptable human participant data or scientific validity.
