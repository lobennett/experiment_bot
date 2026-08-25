# Scope and venue assessment

_Written 2026-08-05. A decision memo, not a results document: what this
project has actually established, how satisfying it is as a product, what
its scope should be, and whether it should be a tweet, a blog post, or a
preprint._

**Verdict up front: preprint, with a companion blog post, after roughly two
to three weeks of targeted work.** Not a tweet. The reasoning is below, as
is the specific list of what to do first — two of the gaps are cheap to
close and are the difference between an interesting lab report and a
publishable methods paper.

---

## 1. What exists

A task-agnostic pipeline that turns an experiment URL into scored
behavioral data, with no task-specific code anywhere in the library:

| Stage | Artifact | Integrity property |
|---|---|---|
| Structural reasoning | content-addressed TaskCard | structural only; no behavioral content |
| Program authorship | content-hashed Python program + full model transcript | one neutral prompt, enforced by invariant tests |
| Mechanical gate | gate report | legality only, never "does this look human" |
| Execution | hermetic session (card hash + program hash + seed) | platform's own export is the record |
| Analysis | per-subject measures | identical estimators on bot and human |

Scale, as committed: **12 RDoC tasks × 20 sessions = 240 sessions**, plus
the four dev-4 implementations (Experiment Factory, STOP-IT,
Cognition.run) at N=30 each and a first-shot flanker probe. 770 tests.
Every program, transcript, gate report, card, and session is in the repo.

Three bodies of result:

1. **Pre-specified comparison (dev-4).** 22 of 28 measures within 1 human
   SD against a trial-level human reference (Eisenberg et al., 2019,
   N=522). *(Cited from the existing draft; not re-verified in this
   pass.)*
2. **Exploratory battery.** 99/149 measures within 1 human SD (66%);
   95/121 (79%) excluding the two grid-recall spans. *(Re-verified from
   the committed matrices today — see §3.)*
3. **Detection and discrimination.** One commercial detector auto-rejects
   1 of 240 clean-environment sessions; a blind expert labels bot-vs-human
   at chance on four tasks.

## 2. The one genuinely novel result

Everything else here is a demonstration. This is a finding:

> Given no behavioral priors, the model's stop-signal programs implemented
> an actual **closed-loop race** — per-trial stopping latency competing
> against the go process. Because the race is closed-loop, the platform's
> own adaptive staircase converges, and per-subject SSRT is statistically
> indistinguishable from human SSRT (KS p ≈ 0.3). The
> expert-parameterized comparison arm — tuned distributions, explicit
> effect modules, far more human knowledge injected — **cannot** do this:
> its inhibition is a configured probability independent of signal delay,
> so the staircase never converges and SSRT collapses (KS p ≈ 10⁻⁴⁶). No
> parameter setting repairs it.

That is a claim about **representational adequacy**, not about bots: a
generative program can express closed-loop task dynamics that a parameter
template cannot, and a language model supplies the right dynamics
unprompted. It is interesting to a cognitive scientist who does not care
about bots at all, and it is the only result here that no competing paper
has. It should be the spine of any write-up.

Secondary, weaker, but still worth reporting: the programs contain
hierarchical individual differences, autocorrelated attentional states,
practice and fatigue drift, and congruency-sequence modulation — none of
it named in the prompt.

## 3. What changed in this pass (and why it matters)

Recomputing the battery from the committed matrices moved the headline and
exposed a scoring bug:

- The previously published **100/149 (67%)** included `Max`/`Mean`/`Min`/`SD`
  **summary rows** in the human reference. Those are not participants, and
  including them inflates the human SD, which makes a within-1-SD test more
  lenient. Corrected: **99/149 (66%)**. With one session per participant (a
  true between-subject SD rather than one pooled across ~5 repeated
  sessions): **97/149 (65%)**.
- **Per-task fractions do not survive a change of N.** The earlier N=5
  round reported stop-signal 12/12 and spatial task-switching 16/16.
  Neither replicates at N=20 under a strict between-subject reference (6/12
  and 9/16). Quadrupling sessions tightens the bot cohort mean against a
  fixed human SD and pushes borderline metrics out of range.

Neither correction changes any conclusion — the spread is two percentage
points — but both matter for how the work should be written up. **Report
the total and the task ordering; do not report per-task fractions as
findings.** The earlier N=5 per-task table has been deleted rather than
updated, because updating it would have implied a stability it does not
have.

## 4. Honest liabilities, ranked by how much a reviewer will care

1. **One program per task.** Every behavioral number is a single draw from
   the model. "66% of measures within 1 SD" has no error bar and might be
   luck. This is the first question any reviewer asks and the project
   currently cannot answer it.
2. **One model family.** Everything is Claude (Fable 5 for structure, Opus
   4.8 for behavior). The natural claim — "a frontier language model can
   do this" — is supported only as "this model did it once per task."
3. **Two different human references.** dev-4 uses trial-level Eisenberg
   data; the battery uses session-level RDoC matrices at a different
   granularity, with the row-handling sensitivity in §3. Defensible, but it
   must be stated as a design choice with a sensitivity analysis rather
   than glossed.
4. **The discrimination pilot is the most quotable and least sound result.**
   Two raters, five tasks, one rater is the system's author, and one of the
   five tasks is contaminated by a harness artifact. As written it cannot
   support "passes as human"; it can only motivate a real study.
5. **Detection is one product, one batch.** Roundtable's behavioral signal
   is an opaque ML score. "1/240 auto-rejected" bounds that one product on
   that one dataset — nothing more general.
6. **The "unprompted structure" claim rests on reading the code.** It is an
   archival observation by the author, not a blinded content analysis. A
   reviewer can reasonably ask for a codebook and independent coders.
7. **The design freeze is git-based, not registered.** The docs are already
   explicit and appropriately humble about this. Keep it that way; never
   call it preregistration.
8. **Spans fail**, and the analysis showing why is good — but it also means
   the generality claim has a known boundary: serial reproduction under
   time pressure needs a motor prior the design forbids.

## 5. Scope: there are two papers tangled together

The current draft reads as a lab report because it is trying to be both of
these at once.

**Paper A — methods / cognitive science.** *LLM-authored generative
participants from task source code alone.* Core claim: generative programs
express closed-loop task dynamics that parameter templates cannot, and a
model supplies task-appropriate structure with no priors. Evidence: the
SSRT/architecture result, the 12-task breadth, the enforced-neutrality
design. Audience: *Behavior Research Methods*, *Psychological Methods*,
CogSci/CCN. Missing: generation variance, cross-model.

**Paper B — data quality / security.** *Online reaction-time research is
vulnerable to zero-shot agentic participants.* Core claim: with no priors
and no per-task tuning, generated participants evade a leading commercial
detector and a blind expert. Audience: a PNAS letter replying to Van der
Stigchel et al. (2026), or *Behavior Research Methods*. Missing: multiple
detectors, a real blinded rater panel, an ethics/disclosure section.

**Recommendation: A is the paper; B is one results section inside it.**
Paper A is where the novel and defensible contribution lives. Paper B is
timely but is being claimed right now by at least three other groups
(Westwood 2025; Van der Stigchel et al. 2026; Ozudogru et al. 2026; Huskey
et al. 2026), and this project's B-evidence is its weakest. Splitting B off
later as a short letter is reasonable once the rater panel exists; leading
with B invites direct comparison on exactly the axis where the work is
thinnest.

The competitive position on A is strong and worth stating plainly: both
prior bot demonstrations **supplied behavioral knowledge** — Ozudogru et
al.'s script referenced the literature for RT distributions; Huskey et al.
iterated code against observed behavior on a single task. This project
supplies none, tests that it supplies none, keeps the first gate-passing
program, and runs twelve tasks through one unmodified pipeline. That is a
real methodological gap in this project's favor, and it is the argument for
publishing rather than tweeting.

## 6. How satisfying is this as a product?

Split the question.

**As engineering: genuinely satisfying.** A pipeline that goes from a URL
to scored behavioral data with no task-specific code, content-addressed
artifacts, hermetic replay, enforced prompt neutrality, and 770 tests is
rare and hard. The negative results are clean and diagnostic rather than
hand-waved: the spans fail for an identified mechanical reason, RT location
drifts slow for a reason the design chose to accept, and detection reduces
to environment fingerprint plus an opaque score. The project's own rules
(no behavioral iteration, no paradigm-specific code) held under pressure —
including in this pass, where recomputation moved a headline down and the
number was changed rather than the method.

**As science: one strong finding plus a broad, shallow demonstration.**
The asymmetry is the defining feature of the project right now: the
engineering quality is well ahead of the statistical power of the claims.
The central breadth number is one draw per task, and the most rhetorically
attractive result (a blind expert at chance) rests on two raters.

The encouraging part is that this asymmetry is **cheap to fix**, precisely
because the infrastructure exists. Generation variance and a cross-model
comparison are compute, not code — the pipeline already takes a model
argument and already archives every attempt.

## 7. What to do before preprinting

Ranked by reviewer impact per unit of effort.

| # | Work | Effort | Why it matters |
|---|---|---|---|
| 1 | **Generation variance**: 5 independent programs per task on a 4-task subset (20 generations), report between-program spread on the headline measures | ~2 days, mostly compute | Converts "one draw" into a distribution. Answers the killer question. No new code. |
| 2 | **Cross-model**: repeat the 4-task subset with one non-Claude frontier model | ~1 day | Turns "an LLM" into a claim with external validity |
| 3 | **Fix the AX-CPT advance-key artifact**, then re-run that task | ~half day | It is a real harness bug that contaminates both the detection story and the discrimination pilot |
| 4 | **Blinded rater panel**: 5–8 raters, none of them authors, on the artifact-free tasks | ~1 week incl. recruiting | Converts the weakest result into a real estimate |
| 5 | **State the two-reference design explicitly** with the sensitivity table (§3 is most of this already) | hours | Pre-empts the obvious methods objection |
| 6 | **Add a dual-use / responsible-disclosure section**, and decide the release posture (§8) | ~1 day incl. discussion | Every competing paper addresses this; a reviewer will require it |

Items 1 and 2 are the gate. Without them the preprint is a demonstration;
with them it is a measurement.

## 8. Release posture — decide this deliberately

The repository is **public** and has **no LICENSE file**. It contains a
working, general-purpose, environment-stealthed participant bot that
evades a commercial detector, together with the programs and cards needed
to reproduce it on twelve deployed tasks.

That is a defensible choice — the docs argue, correctly, that a
vulnerability demonstration should be public and reproducible, and the
detection findings are more useful to platform builders than to abusers.
But it should be an explicit, argued decision in the write-up rather than a
default, and it needs at minimum:

- a LICENSE (absence is itself a problem: no license means no grant of use,
  which discourages exactly the defensive reuse the project wants);
- a short responsible-use statement, and a decision on whether the
  *stealth* configuration specifically stays public;
- notification of the platforms and detector vendor before the preprint
  posts, which is both courteous and materially strengthens the paper.

## 9. Why not a tweet, and why also a blog post

**Not a tweet.** The central result is a claim about representational
adequacy demonstrated through a staircase-convergence failure in a
comparison arm. That cannot survive compression to a screenshot, and
tweeting it forfeits priority in a space with three active competitors
while wasting unusually good reproducibility infrastructure. A tweet is
the *announcement vehicle* for the preprint, not the artifact.

**A blog post as companion, published the same day.** There is a genuinely
good post here that the paper cannot contain: what the model wrote
*unprompted* (the race model, the fatigue drift, the congruency-sequence
modulation), the span failure as a story about motor priors, and the
engineering of enforced prompt neutrality. That reaches the practitioner
audience — platform builders, online-experiment developers — who will never
read a methods journal. Link it to the preprint; let each do its job.

**Sequence:** close gaps 1–3 and 5–6 → post the preprint (PsyArXiv or
arXiv) → blog post and tweet the same day, both pointing at the preprint →
submit to *Behavior Research Methods* → consider Paper B as a short letter
once the rater panel exists.

## 10. One-paragraph summary

This project built infrastructure that is better than the science it has
so far been used to produce, and it contains one result that deserves a
paper: model-authored generative participants implement closed-loop task
dynamics that expert parameter templates architecturally cannot, with no
behavioral priors supplied or leaked. The breadth demonstration around that
finding is real but underpowered — one program per task, one model family,
two human references, and a two-rater discrimination pilot. Closing the two
cheapest gaps (generation variance, one cross-model comparison) takes the
work from "interesting lab report" to "publishable methods paper," and both
are compute rather than code because the pipeline already supports them.
Preprint it, blog it, and let the tweet point at both.
