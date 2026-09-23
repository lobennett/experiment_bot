# From URL to a generalizable experimental participant

_Design review, 22 September 2026. Based on repository inspection and a
targeted literature search. These are recommendations, not implemented
capabilities or measured improvements. No new latency benchmark or
behavioral experiment was run for this review._

## Recommendation

Keep Python for orchestration, modeling, and analysis. Use a capable LLM
to explore an experiment and construct its adapter and participant program
before execution. Keep remote model calls outside the trial timing loop.
Improve browser observation, formalize event timing, and build a separately
versioned literature-informed behavior mode.

The main limitations are the observation contract, timing boundaries, and
behavioral validation. A Rust rewrite would not by itself resolve them.

## 1. Define what “humanlike” means

Three goals require different evidence:

- **Task completion:** navigate the experiment and produce valid responses.
- **Behavioral simulation:** reproduce human distributions of responses,
  errors, and timing.
- **Cognitive task performance:** perceive stimuli, remember information,
  and make decisions using information available to a participant.

The current system primarily addresses behavioral simulation. Its
[`TrialContext`](../src/experiment_bot/behavior/provider.py) supplies the
correct key and, where applicable, the correct sequence. Successful n-back
performance under those conditions does not establish working memory.

Declare an observation policy in every run:

| Policy | Participant access | Appropriate interpretation |
|---|---|---|
| Instrumented simulation | Page state, conditions, and correct answers | Controlled behavioral simulation and experiment testing |
| Visible information | Presented stimuli, instructions, and feedback | Task performance with an explicit perceptual interface |
| Pixels and audio only | Rendered frames and presented audio | Performance without dependence on internal page representations |

Visible-information mode should keep answer keys, future stimuli, and
hidden conditions with the evaluator. Source inspection may establish how
to operate the task, but must not become a channel for passing hidden
trial information to the participant. Pixels-only operation is a useful
separate benchmark; capture and recognition latency become part of its
measurement.

Literature grounding changes the scientific objective of the existing
naive system. Preserve its neutral prompts, invariant tests, first
mechanically passing program rule, hashes, archived programs, and
historical results. Develop the informed mode with its own provenance and
evaluation rules. This proposal does not change the existing design freeze
or authorize retrospective behavioral selection in the naive arm.

## 2. Treat URL ingestion as exploration and compilation

The current [`scraper`](../src/experiment_bot/core/scraper.py) fetches the
initial HTML and directly linked scripts/styles, plus explicitly supplied
extra URLs. Resources are keyed by basename, allowing name collisions.
This does not cover dynamically loaded modules or establish live behavior
inside frames, canvas, or WebGL.

The structural reasoner already validates generated structure and pilots
it against the live page. Retain that principle, but improve the evidence
available to it:

1. **Capture the live implementation.** Open the URL in a browser and
   collect loaded resources, frame structure, instructions, screenshots,
   and available runtime interfaces. Identify resources by full URL and
   content hash. Support authenticated sessions explicitly.
2. **Explore the state machine.** Observe instructions, practice, fixation,
   stimulus, response windows, feedback, breaks, and completion. Combine
   source evidence with live probes rather than assuming that static code
   reveals every runtime transition.
3. **Compile a structural manifest and adapter.** Describe how this
   implementation exposes events and accepts actions. Include explicit
   unsupported capabilities and unresolved observations.
4. **Validate mechanically.** Exercise repeated identical stimuli,
   omissions, interruptions, block transitions, completion, and native
   export. A successful first trial is insufficient evidence of coverage.
5. **Freeze artifacts.** Pin the source snapshot, adapter, participant,
   evidence bundle, environment, and seed before evaluation.

Use platform APIs where available, DOM observation for ordinary pages,
and visual recognition for canvas or WebGL. Playwright provides useful
mechanisms for [frame access](https://playwright.dev/python/docs/frames)
and [initialization scripts](https://playwright.dev/python/docs/api/class-page).
Those mechanisms do not guarantee universal task coverage.

Generalizability should mean that the execution engine has a stable
contract across adapters, not that one selector schema works everywhere.
Platform-specific mechanics belong in adapters; paradigm-specific
behavior belongs in participant artifacts.

## 3. Separate the schema from the participant program

A large configuration schema can become an awkward programming language.
Retain the existing strength of an executable, stateful participant
program. Use schemas to constrain interfaces and record provenance.

| Artifact | Responsibility |
|---|---|
| Task manifest | Phases, transitions, inputs, observation policy, timing definitions, completion, export |
| Platform adapter | Translate the website into normalized events and deliver actions |
| Evidence bundle | Retrieved studies, extracted estimates, applicability, uncertainty |
| Participant program | Memory, decisions, errors, timing, adaptation |
| Run manifest | Versions, hashes, seed, environment, validation results |

The runtime interface should support:

- **Observation events:** session, block, trial, and event IDs; event type;
  onset and observation timestamps; clock domain; presented content;
  response-window state; and observation uncertainty.
- **Action plans:** a trial-bound token, key or click target, deadline
  relative to onset, optional action sequence, and cancellation or
  replacement semantics.
- **Delivery records:** separate decision, scheduling, delivery, and
  platform acknowledgment, all associated with the same trial.

An estimated onset must be labeled as an estimate. Withholding must be
distinguishable from a crash, expired window, or unobserved stimulus. A
late action must never enter the next trial. Stop signals may cancel a
pending response only before a defined commitment point.

Generated programs also need bounded execution and isolation. Import
checks and deterministic-seed checks are useful mechanical gates; an
import whitelist alone is not a security sandbox.

## 4. Allocate LLMs, vision, and local execution by role

Use a code-reasoning LLM to interpret source and instructions, generate
adapters, select candidate behavioral models, author participant programs,
and repair mechanical failures. Use vision when the task's representation
cannot be reliably recovered from source or DOM information.

An LLM and VLM need not be separate products: one multimodal model may
perform both setup roles. Once simple recurring stimuli are understood,
prefer a validated local recognizer or deterministic extractor where
possible. Recognition errors should be measured separately from the
participant model's intended errors.

Execute the generated participant locally during trials. A remote agent
that reasons and acts on each trial is not the recommended default for
precision timing. Its inference and network delays would become part of
the behavioral measurement.

Compare candidate Astra/OpenAI/Claude configurations on unseen task
implementations. Measure completion, repair rate, source-grounding
accuracy, behavioral validity, setup cost, and setup latency. This review
does not establish a winning model. Keep model selection independent of
the task execution interface.

## 5. Ground a generative model, not just a mean response time

Sampling a plausible RT and occasionally choosing the wrong key can match
averages while missing the defining dynamics of a task. Model choices and
responses jointly, with state across trials where warranted.

### Flanker

Candidate conflict models should account for choices and RT together,
including how interference changes across the RT distribution. Examine
conditional accuracy and RT quantiles across congruency conditions.
Diffusion models for conflict tasks are one candidate family, not a
universal default or source of universal parameters.
[Ulrich et al. (2015)](https://www.sciencedirect.com/science/article/pii/S0010028515000195)
provides a starting point; its
[corrigendum](https://doi.org/10.1016/j.cogpsych.2016.11.003)
clarifies the diffusion scaling parameter.

### Stop signal

A pending go response must compete with stopping initiated by the actual
signal. A fixed stopping probability cannot reproduce the dependence on
signal delay. Preserve the experiment's adaptive staircase and examine
inhibition functions, failed-stop RTs, and the assumptions underlying SSRT
estimation. The
[Verbruggen et al. (2019) consensus guide](https://elifesciences.org/articles/46323)
explains why task design and analysis details matter.

### N-back

Maintain ordered stimulus history and a fallible memory representation.
Evaluate hits, false alarms, load dependence, and lure effects rather than
overall accuracy alone. Research on
[an analog N-back task](https://pmc.ncbi.nlm.nih.gov/articles/PMC11618482/)
supports investigating interference during retrieval. Its estimates do
not automatically transfer to categorical letter n-back tasks; evidence
must match the actual variant.

### Evidence pipeline

For every extracted parameter, preserve:

- The retrieved source passage, table, or data artifact supporting it.
- Population, task variant, stimulus properties, response mapping,
  deadlines, practice, and other relevant conditions.
- Units, preprocessing, estimation method, transformations, and uncertainty.
- Whether the value is directly reported, estimated from data, or assumed.

A valid DOI establishes source identity, not support for a claimed number.
Means and standard deviations alone do not uniquely determine a
distribution. Prefer accessible trial-level data and fitted parameter
uncertainty. Keep participant differences, trial noise, and uncertainty
about model parameters distinct.

In the informed mode, compare candidate models using held-out predictive
performance. Avoid selecting against the same human data used to report
success. When evidence is weak or mismatched, preserve that uncertainty
instead of generating unsupported precision. These practices do not relax
the naive mode's prohibition on behavioral iteration.

## 6. Measure the timing path before changing languages

The current [`_execute_trial`](../src/experiment_bot/core/executor.py)
starts a host clock after stimulus detection and derives signal delay
from polling. Improve those timing boundaries before attributing error to
Python computation.

Measure four intervals separately:

1. Stimulus onset to observation.
2. Observation to decision readiness.
3. Scheduled deadline to input delivery.
4. Input delivery to platform-recorded response.

Timestamp near the event source, record the clock domain, reconcile
browser and host clocks, and schedule against absolute deadlines. Page
state changing is not necessarily identical to physical display onset;
declare what the timestamp represents.

As an illustration, an event arriving uniformly within a fixed 20 ms
polling cycle has an average detection delay of 10 ms, before browser
calls and other overhead. This is a calculation, not a measured result
for this repository.

Browser timers can fire late, and animation callbacks follow display
frames rather than arbitrary millisecond deadlines. Moving scheduling
into JavaScript does not create hard real-time execution.
[Browser timer documentation](https://developer.mozilla.org/en-US/docs/Web/API/Window/setTimeout)
and [jsPsych timing guidance](https://www.jspsych.org/v8/overview/timing-accuracy/)
describe relevant constraints.

In-page synthetic events and browser-level input are different delivery
paths. Validate the supported path against the actual task and its native
recording; do not assume an in-page event is interchangeable with a
keyboard response.

| Language/runtime choice | Recommendation |
|---|---|
| Python plus browser-side JS/TypeScript observation | Start here; retain modeling, NumPy, orchestration, and analysis |
| Browser-local JavaScript or WASM participant | Consider if measured process-boundary costs fail timing budgets; require runtime parity checks |
| Rust execution kernel | Consider for demonstrated computation bottlenecks, resource control, or a WASM target |
| Full Rust rewrite | Not justified by the evidence gathered in this review |

Measure bias, p95/p99 timing residuals, missed events, and deadline failures
under intended concurrency. Calibrating a mean offset cannot eliminate
jitter or recover missed signals. The
[timing mega-study, Bridges et al. (2020)](https://peerj.com/articles/9414.pdf)
motivates configuration-specific validation; it does not establish this
bot's timing. Claims about physical display/input timing additionally
require external hardware measurement.

## 7. Validate three independent properties

1. **Mechanical correctness:** complete the task, observe the correct
   events, deliver legal actions, and obtain complete native exports.
2. **Timing fidelity:** meet declared onset, interruption, and response
   tolerances without cross-trial contamination.
3. **Behavioral validity:** reproduce held-out human choice/RT structure,
   including distributions, task effects, and individual differences.

Continue analyzing platform exports rather than the bot's self-log.
Use logs to diagnose the delivery path. Agreement with human behavior is
not proof of a matching cognitive mechanism.

Evaluate a task-by-platform matrix with unseen implementations, rather
than treating success across tasks on one framework as platform
generalization. Preserve separate development and evaluation sets.

## 8. Priorities for this repository

1. **Browser-based acquisition and source provenance.** Extend the static
   scraper with runtime resource capture and collision-safe identities.
   The [structural reasoner](../src/experiment_bot/reasoner/stage1_structural.py)
   currently truncates source inputs and records high confidence after
   structural validation. Replace confidence declarations with explicit
   source coverage and live-probe evidence.
2. **Normalized events and timing instrumentation.** Establish event IDs,
   onset definitions, clock handling, cancellation, and delivery readback.
   Measure before deciding whether to move participant execution.
3. **Explicit observation policies.** Introduce a visible-information
   contract in the new mode while retaining instrumented simulation.
4. **Separate informed generation and evaluation.** Add retrieved evidence,
   uncertainty, model comparison, and held-out validation without changing
   the naive experiment's integrity guarantees.

The first engineering milestone should be one event contract exercised
across several implementations of flanker, stop signal, and n-back.
Independent evidence of completion, timing fidelity, and behavioral
agreement will establish whether broader observation support, better
models, or a faster execution kernel deserves the next investment.

This is an architectural direction, not a complete implementation plan.
Its literature search identifies useful mechanisms and design constraints;
it is not a systematic review or a validated parameter catalog.
