# Generated visible policy

Use this mode when direct model/tool latency prevents meaningful participation
and autonomous completion or design iteration is authorized. The model authors
a participant program once; the program decides live responses locally. Record
and announce this change before starting a new attempt.

## Prepare observations

Apply the participant-visible boundary in [SKILL.md](SKILL.md). Derive
perception and response logic from observed instructions and screens. Store
task-specific logic in the run, keeping the reusable skill task-agnostic.

Separate discovery from participation when a task starts before preparation is
complete. Preserve and end the discovery session, build from its evidence, then
open a prepared participation session. Choose discovery purpose at the outset;
a failed run remains a failed run. Finish driver setup before advancing a screen
that can start unattended trials.

Rendered text, computed colors and geometry, and displayed pixels are eligible
observations. For DOM extraction, check opacity, CSS visibility, viewport
intersection, and relevant occlusion. Bare
[`checkVisibility()`](https://developer.mozilla.org/en-US/docs/Web/API/Element/checkVisibility)
omits opacity and CSS visibility checks by default. Verify the extracted
representation against screenshots and exercise visible and hidden fixtures.
A selector locates an element; its name does not establish stimulus identity.
For pixel text, read [perception.md](perception.md) before choosing OCR settings.

This step ends when saved fixtures establish what the adapter can observe and
which visible transitions identify response opportunities. Include repeated
identical stimuli: disappearance/reappearance or another visible boundary must
distinguish consecutive presentations. Record unresolved detection limits.

## Author and freeze the policy

Save the actual prompt, observed instructions, source, and mechanical checks.
Record whether authoring inherited agent context or used an isolated model call.
Preserve the full transcript when available. An instruction file alone does not
capture the full generation context.

Use this neutral behavioral instruction:

> Write a participant policy for the observed task. Follow its instructions as
> a typical attentive adult participant. Decide all responses and their timing
> from the current participant-visible observation and the policy's own history.
> Use a seeded local random generator if the policy makes random choices.

Supply observed mechanics and the observation/input interface. Desired effects,
population parameters, timing targets, and behavioral templates are prohibited.
Keep decisions inside the generated file. Author from current evidence rather
than copying archived programs or selecting among candidates by behavior.

Make timing explicit as a requested delay/action time or a time-indexed state
machine. Immediate action is a valid choice when recorded as such. Save intended
timing beside actual delivery. The transport supplies no behavioral timing.
Check timing for finiteness and legality, not a desired human range.

Before live use, check syntax, interface compatibility, legal inputs, bounded
execution, and seeded reproducibility against observed or instruction-derived
fixtures. Retain the first candidate that passes this mechanical gate. Allow
at most two replacements for gate failures and archive each failed candidate
and its reason. Pin the accepted file by exact-byte SHA-256.

This step ends with the prompt, context declaration, gate result, and frozen
policy recorded. Preserve an already accepted policy when later documentation
changes; its observed behavior is not grounds for replacement.

## Prove the transport

Read the installed tool's scripting help and exercise the real adapter on an
instruction screen. Use the same observation path as the live driver, inspect
the returned shape, and verify required navigation input. Syntax checks and
mocked interfaces do not prove that the browser API works.

With `chrome-devtools-axi run`, inspect `run --help` before using `page.eval`,
`page.press`, or `page.click`. If the installed interface fails its probe, use an
isolated persistent browser with a working API, such as Playwright. Preserve the
failed attempt and accepted policy.

Test the operator channel across a tool yield. A persistent driver must accept
a later command; some runners close stdin unless a PTY or another persistent
channel is used. Obtain required execution permissions before the last
instruction screen. Preparation ends when observation, input, and later control
work through the actual transport.

## Keep the local loop running

Keep observation, policy, and input delivery separable in the saved code:

1. Observe the rendered state and timestamp it with the clock used.
2. Update participant memory and ask the policy for an action or continued wait.
3. Continue observing while waiting. Cancel stale intentions when their response
   opportunity ends; let the policy process task-presented interruptions.
4. Deliver ordinary browser input, release held input, and log the observation,
   intended action, actual delivery, and missed opportunities.
5. Notify the agent at new instructions and natural boundaries. Feed ordinary
   trial feedback to the unchanged policy and update the structural ontology.

Route unexpected actionable text to the agent immediately. Separate persistent
reminders, fixation, and routine feedback from new instructions using observed
layout and phase transitions. Keep observing while awaiting the agent; a handoff
can outlast a short response window. Record agent-issued instruction responses
separately from policy-issued trial responses. Recheck the visible prompt before
sending a queued key, then resume the same participant instance.

Preserve participant history and random-generator state across tool batches.
Use a long-lived driver during timed blocks, expose progress, and check it at
short intervals. Agent review belongs at natural boundaries. Record operational
limits separately from behavioral parameters.

Preserve task deadlines and native timing. Simulation APIs, internal completion
callbacks, data edits, and transport delays chosen to target a behavioral pattern
are prohibited. Waiting requested by the frozen policy remains part of its
behavior and is recorded separately from transport overhead.

## Repair mechanics and retain outcomes

A missed visible stimulus, stuck key, or stale action is a mechanical problem.
An error rate or timing pattern is a behavioral result. An adapter repair needs
saved evidence, a focused reproduction, and an archived code/configuration hash.
It must preserve policy preferences and timing decisions.

Repair recoverable adapters within the same session at a natural boundary.
Record when each revision becomes active, and save raw observations beside the
derived facts delivered to the policy. Preserve participant state when later
blocks introduce new instructions. Start a new attempt when restarting the task
or changing mode, not for every repair.

Deduplicate navigation within one observed presentation. Repeated instruction
text can be a new page or retry. Let the agent inspect it instead of imposing a
fixed reading delay. If practice repeats after unmet performance criteria, keep
the same policy while participation remains meaningful. Stop repeated failure
without a new mechanical cause; retain every outcome.

Finish through the main skill's completion and export steps. Include every
attempt in the evaluation index. Successful local-policy execution establishes
what that program and browser did; direct per-trial model cognition and human
validity require separate evidence.
