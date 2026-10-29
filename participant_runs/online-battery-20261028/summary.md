# Online behavioral skill evaluation

Evaluate browser task operation and refine mechanical skill design; no human behavioral validity claim.

Every attempt is retained. Completion, perceptual coverage, native data availability, and human behavioral validity are separate claims.

The table distinguishes the latest terminal run from the latest attempt. These are developmental attempts, not a selected scientific cohort. See [findings.md](findings.md) for phase-specific outcomes and limitations.

| Task | Latest terminal run | Latest attempt | Mode of latest attempt | Artifact integrity | Native export |
|---|---|---|---|---|---|
| [preview9](https://deploy.expfactory.org/preview/9/) | [attempt-03](preview9/attempt-03/summary.md) | [completed](preview9/attempt-03/summary.md) | generated_visible_policy | verified | available |
| [preview10](https://deploy.expfactory.org/preview/10/) | [attempt-05](preview10/attempt-05/summary.md) | [partial](preview10/attempt-06/summary.md) | generated_visible_policy | verified | available |
| [tower-hanoi](https://www.psytoolkit.org/library/experiment_tower_hanoi.html) | [attempt-02](tower-hanoi/attempt-02/summary.md) | [completed](tower-hanoi/attempt-02/summary.md) | direct_browser | verified | available |
| [paced-reading](https://www.psytoolkit.org/library/experiment_pacedreading1.html) | [attempt-05](self-paced-reading/attempt-05/summary.md) | [completed](self-paced-reading/attempt-05/summary.md) | generated_visible_policy | verified | available |
| [preview5](https://deploy.expfactory.org/preview/5/) | [attempt-07](preview5/attempt-07/summary.md) | [completed](preview5/attempt-07/summary.md) | generated_visible_policy | verified | available |
| [preview28](https://deploy.expfactory.org/preview/28/) | [attempt-01](preview28/attempt-01/summary.md) | [completed](preview28/attempt-01/summary.md) | generated_visible_policy | verified | available |

## All attempts

- [preview10/attempt-01](preview10/attempt-01/run.json): **partial**, direct_browser; Practice timed stimuli advanced between observation and model-directed key delivery; task reported omissions and repeated practice. Isolated session stopped before main-test completion.
- [preview10/attempt-02](preview10/attempt-02/run.json): **partial**, generated_visible_policy; Browser run adapter failed with fn is not a function before policy responses could be delivered.
- [preview10/attempt-03](preview10/attempt-03/run.json): **blocked**, generated_visible_policy; CLI could not open or select a blank preflight page; task never opened.
- [preview10/attempt-04](preview10/attempt-04/run.json): **blocked**, generated_visible_policy; Transport preflight passed, but policy source injection failed before fullscreen/task participation: SyntaxError Unexpected token if.
- [preview10/attempt-05](preview10/attempt-05/run.json): **completed**, generated_visible_policy; Observed terminal page
- [preview10/attempt-06](preview10/attempt-06/run.json): **partial**, generated_visible_policy; Stopped without confirmed completion
- [preview28/attempt-01](preview28/attempt-01/run.json): **completed**, generated_visible_policy; Observed terminal task page
- [preview5/attempt-01](preview5/attempt-01/run.json): **partial**, direct_browser; Direct attempt missed timed stimuli after browser scripting error; no terminal state observed.
- [preview5/attempt-02](preview5/attempt-02/run.json): **blocked**, direct_browser; Persistent driver stdin reached EOF in non-PTY execution immediately after initial fullscreen capture; no task responses delivered.
- [preview5/attempt-03](preview5/attempt-03/run.json): **partial**, generated_visible_policy; At first fixation, persistent reminder text made the frozen policy yield for review; driver stopped observing timed practice. No letter response was delivered.
- [preview5/attempt-04](preview5/attempt-04/run.json): **partial**, generated_visible_policy; Rendered center letter is absent from DOM text observations; no letter responses. Screenshot proves a lowercase t while text representation contains only reminders.
- [preview5/attempt-05](preview5/attempt-05/run.json): **partial**, generated_visible_policy; Two completed practice rounds produced repeated omission feedback because OCR failed on visible glyphs. Stopped during the automatically started third practice; terminal task state never observed.
- [preview5/attempt-06](preview5/attempt-06/run.json): **partial**, generated_visible_policy; Completed delay-1 practice, then newly visible delay-2 cue/reminder wording was unsupported by the perception framing. No delay-2 response was delivered; native export retained.
- [preview5/attempt-07](preview5/attempt-07/run.json): **completed**, generated_visible_policy; Observed task thank-you and Experiment Complete terminal state after both practices and ten test blocks. Six attention checks were missed; automatic remote upload failed.
- [preview9/attempt-01](preview9/attempt-01/run.json): **partial**, direct_browser; Practice advanced faster than direct screenshot/inference/action could respond. Native feedback reported omissions. Participation ended and the task tab was closed; terminal task completion was not reached.
- [preview9/attempt-02](preview9/attempt-02/run.json): **partial**, generated_visible_policy; Adapter failure: compound run calls delivered navigation before a later fn-is-not-a-function error. Practice advanced during diagnosis; archived before retry with repaired transport and identical policy.
- [preview9/attempt-03](preview9/attempt-03/run.json): **completed**, generated_visible_policy; Observed Experiment Complete after all three main blocks. Local task completed; automatic remote upload failed as reported by terminal page.
- [self-paced-reading/attempt-01](self-paced-reading/attempt-01/run.json): **completed**, direct_browser; Five sentence sequences progressed to the native Show data/Copy data controls; completion is confirmed, but some word displays were missed.
- [self-paced-reading/attempt-02](self-paced-reading/attempt-02/run.json): **blocked**, direct_browser; Transport screenshot preflight tried to capture a hidden initial canvas; browser closed before participation.
- [self-paced-reading/attempt-03](self-paced-reading/attempt-03/run.json): **completed**, direct_browser; Task autonomously reached native export controls while the model/tool loop was delayed; zero word displays were observed. Terminal completion is not successful participation.
- [self-paced-reading/attempt-04](self-paced-reading/attempt-04/run.json): **completed**, generated_visible_policy; Frozen OCR policy observed terminal export controls. Recognized 27/28 words in native sequence order.
- [self-paced-reading/attempt-05](self-paced-reading/attempt-05/run.json): **completed**, generated_visible_policy; Frozen OCR policy observed terminal export controls. Recognized 28/28 words in native sequence order.
- [tower-hanoi/attempt-01](tower-hanoi/attempt-01/run.json): **blocked**, direct_browser; The preferred CLI supports element-to-element dragging only; task discs and target pegs are all in one canvas. No puzzle move was attempted. A coordinate-input fallback is needed.
- [tower-hanoi/attempt-02](tower-hanoi/attempt-02/run.json): **completed**, direct_browser; Seven ordinary pointer drags produced the instructed final arrangement; task then automatically displayed native export controls.

## Design changes grounded in these runs

- Direct model/tool round trips missed brief stimuli; the skill now explicitly distinguishes direct participation from a frozen, model-authored visible-state policy.
- Canvas planning required coordinate drag input; the skill now checks input capabilities and permits an isolated browser transport with the needed capability.
- Installed CLI scripting and session failures require a real adapter preflight, page-identity checks, and observation before retrying uncertain delivery.
- Participant memory and random state persist across tool segments; continuous blocks do not pause for agent narration.
- Reading exposed missed observations despite a self-paced label; direct participation now emphasizes persistent transport and compact stimulus screenshots.
- A portable artifact checker validates evidence links, frozen policy pins, protocol snapshots, and all finalized artifact hashes.

See [selection.json](selection.json) for the task selection and completion criteria, [results.json](results.json) for full counts and limitations, and each attempt's summary for evidence. This battery does not compare outputs with human reference data.
