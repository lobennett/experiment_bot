# Generated visible policy

Use this branch when direct model/tool latency prevents meaningful participation
and the user has authorized autonomous completion or skill design iteration.
This changes who decides each live response: the model authors a policy once,
then that program responds locally. Record this distinction before starting.

## Keep the boundary

Create a new attempt and preserve the earlier run. The observation boundary
remains participant-visible. Derive task-specific perception and response logic
from instructions and screens actually observed. Keep that logic in the run's
policy file, not in the reusable skill or library. No task catalog is needed.

Rendered text, computed colors and geometry, and pixels of displayed stimuli
are eligible observations. Scope DOM queries to visible elements; do not use
hidden attributes as an answer channel. For DOM extraction, check opacity,
CSS visibility, viewport intersection, and occlusion where relevant; bare
[`checkVisibility()`](https://developer.mozilla.org/en-US/docs/Web/API/Element/checkVisibility)
does not check opacity or CSS visibility by default. Exercise visible and hidden
fixtures in the adapter gate. Verify that the extracted representation
matches a screenshot before relying on it. A CSS selector may locate a visible
element; its name alone is not perceptual evidence of a stimulus identity.
Task state, future stimuli, correctness variables, trial source, and platform
data APIs are unavailable to the responding policy. Export is a separate
post-session operation.

## Author once, check mechanically

Save the actual authoring prompt, observed instructions, policy source, and
mechanical check results. Record whether authoring inherited the working agent's
conversation or used an isolated model call. Preserve the full transcript when
available; an instruction file alone is not the full generation context. Inline
authoring must not claim the frozen study's prompt isolation. The explicit
behavioral instruction is neutral:

> Write a participant policy for the observed task. Follow its instructions as
> a typical attentive adult participant. Decide all responses and their timing
> from the current participant-visible observation and the policy's own history.
> Use a seeded local random generator if the policy makes random choices.

Provide only the observed task mechanics and the available observation/input
interface. Do not add desired effects, population parameters, response-time
targets, or behavioral templates. Keep all policy decisions inside the generated
file. Do not copy archived task programs or choose among candidates by behavior.

Represent timing explicitly in the policy interface, either as a requested
delay/action time or as a time-indexed state machine. A deliberate immediate
action is valid but must be recorded as that choice. The transport must not
silently supply behavioral timing. Save intended timing beside actual delivery
so fast classification is not mistaken for modeled response timing. Check timing
values for finiteness and legality, never against a desired human range. This
contract applies to new policies; it does not invalidate or replace a previously
accepted policy because of the response times it produced.

Before live use, check syntax, interface compatibility, legal input types,
bounded execution, and seeded reproducibility using observed or instruction-
derived observation fixtures. This is a mechanical gate, not a human-likeness
test. Retain the first candidate that passes. At most two replacement candidates
may fix mechanical gate failures; archive each candidate and the reason.
Pin the chosen policy by exact-byte SHA-256 before the live attempt.

Exercise the actual browser adapter while still on an instruction screen:
perform a read-only observation through the same scripting path, verify its
returned shape, and verify ordinary navigation input where required. A syntax
check or mocked interface does not establish that the installed tool API works.
Archive adapter failures and repairs separately from the frozen policy.
Prepare and obtain any required execution permissions before advancing the last
instruction screen: a ready screen or practice can start advancing on its own
while the agent is still setting up the driver.

## Execute a short local loop

Use the browser tool's documented scripting/batching facility to eliminate a
model round trip for every response. With `chrome-devtools-axi run`, a script can
await `page.eval(...)` for rendered observations and `page.press(...)` or
`page.click(...)` for browser input. Read `run --help` for the actual interface.
This API is illustrative, not a requirement on other browser tools.

If the installed scripting API cannot pass the adapter probe, use an isolated
persistent browser with a working automation API, such as Playwright. Preserve
the failed attempt and frozen policy. Tool preference does not make a broken
interface adequate for timed input.

Keep observation, policy, and input delivery separable in the saved code:

1. Observe the rendered state and timestamp it with the clock actually used.
2. Update policy memory and let the policy decide an action or continued waiting.
3. While waiting, continue observing relevant visible changes. Cancel stale
   intended actions when their response opportunity ends; let the policy handle
   task-presented interruptions. Never answer a new stimulus with an old decision.
4. Deliver input through the browser's keyboard/pointer interface, then release
   held input. Log the observation, intended action, actual delivery, and any
   missed opportunity. Transport latency is preserved in platform data.
5. Yield at instruction, feedback, and block boundaries for the agent to inspect
   and update the structural ontology. Ordinary trial feedback can feed policy
   history; the agent must not rewrite the policy to improve its scores.

Route unexpected nonempty visible text to the agent immediately when it does
not match the known stimulus or routine feedback. A new instruction can have
its own short deadline. Absence of the expected stimulus is not proof the page
is waiting. Record any agent-issued response to that new instruction separately
from policy-issued trial responses, then resume the unchanged policy.

Detect response opportunities from visible transitions, not hidden trial
counters. The same stimulus can repeat on consecutive trials, so comparing only
stimulus text is insufficient: account for observed disappearance/reappearance,
replacement, or another visible boundary. If the tool cannot distinguish
opportunities or meet the observed deadlines, retain the limitation.

Keep one participant instance, its history, and its random-generator state for
the whole session. A tool batch ending must not reset that state. For timed
blocks, keep a long-lived driver running while the agent's tool yields; expose
progress and wait in short intervals. Pause for agent review at natural task
boundaries, rather than leaving trials unattended between arbitrary segments.
Bound execution and expose progress so a stalled task can be stopped. Record
operational limits separately from behavioral parameters.
Do not simulate trials, invoke internal completion callbacks, edit experiment
data, change deadlines, or add transport-layer delays to target a desired data
pattern. Waiting requested by the frozen participant policy remains part of
that policy's behavior and is recorded separately from transport overhead.

## Diagnose without behavioral selection

A selector that misses a visibly displayed stimulus, a stuck key, or a stale
action is a mechanical problem. A participant's error rate or response-time
pattern is a behavioral result. Freeze the accepted policy's behavior. An
adapter repair needs saved evidence of the mechanical problem, a focused
reproduction, and a new archived code hash/attempt; it must not change response
preferences or timing decisions to improve outcomes.

While still before timed participation, repair a recoverable adapter in the
same browser session and archive each code revision. A new attempt is needed
when restarting the task or changing execution mode, not for every setup fix.
Repeated instruction text can be a legitimate new page or retry; deduplicate
inputs within one observed presentation rather than suppressing that text for
the entire run. Let the agent review instructions instead of guessing a fixed
reading delay to satisfy the task's navigation checks.

If the task repeats practice after unmet performance criteria, record the
feedback and let the unchanged policy continue only while the task remains
meaningfully executable. Stop a repeated failure with no new mechanical cause;
do not tune until the task accepts the participant. Report incomplete tasks as
such, even when other tasks in the battery finish.

Completion and native export use the main skill's evidence requirements.
Assess operation across distinct observed mechanics and retain every attempt
in the battery index. Successful generated-policy execution is evidence about
that program and browser, not direct per-trial LLM cognition or human validity.
