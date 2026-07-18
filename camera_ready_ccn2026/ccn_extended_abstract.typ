// -----------------------------------------------------------------------
// CCN 2026 Extended Abstract — camera-ready (deanonymized)
// Submission 436: Agentic AI Can Generalize to Multiple Speeded Tasks
// -----------------------------------------------------------------------

#import "ccn.typ": ccn

#show: ccn.with(
  mode: "extended-abstract",

  title: [Agentic AI Can Generalize to Multiple Speeded Tasks with Human-Like Behavior],

  authors: (
    (name: "Logan J. Bennett",   affil: (1,)),
    (name: "Russell A. Poldrack", affil: (1,)),
    (name: "Patrick G. Bissett",  affil: (1,)),
  ),
  affiliations: (
    "Department of Psychology, Stanford University",
  ),
  emails: "logben@stanford.edu",
)

// Camera-ready has no line numbers. The LaTeX `ccn.cls` gates `\linenumbers`
// to submission mode only (cls lines 180-188); the Typst class applies them
// in every mode, so we disable them here at the document level (the official
// class file is left unmodified).
#set par.line(numbering: none)

= Introduction

There is growing evidence that online experiments may be contaminated by
AI-based bots. One source of data that is particularly susceptible to AI bots
are self-report surveys, which involve verbal prompts and verbal responses with
minimal emphasis on response speed, making them particularly susceptible to
large language model (LLM)-based bots. Westwood (2025) recently showed that an
LLM-based synthetic respondent could pass attention checks, produce a coherent
demographic persona with memory of its past responses, and produce plausible
survey based responses on a variety of prompts. This suggested that self-report
survey results from online experiments may already be contaminated by bots.

Recent work has suggested that even speeded tasks may be susceptible to agentic
AI bots, but this existing work has key shortcomings. Huskey et al. (2026)
recently used a Claude Opus 4.6 (Anthropic) based bot to complete the Attention
Network Task (Fan et al., 2002), a prominent speeded RT task, with performance
that matched many patterns in human data. However, this solution was tailored to
a single online task, required considerable training and iteration, and some key
bot behaviors diverged from humans (e.g., long tails of the RT distribution). In
a brief preprint and a set of demonstration videos, Ozudogru et al. (2026)
showed that a prompt-only approach could produce human-like RT distributions and
mean RTs in 3 different cognitive tasks. However, they provide minimal
explanation of the bots architecture and minimal evaluation of the
correspondence with human behavior.

Here, we present an agentic AI bot that addresses these shortcomings with
minimal training and iteration, has the ability to generalize across multiple
tasks and multiple implementations of each task, and it reproduces specific
human behavioral patterns including trial-by-trial sequential effects.

= Methods

Given only an experimental URL, our agentic AI bot scrapes the page source and
runtime JavaScript state and passes this to Claude Opus 4.6 (Anthropic) in a
single API call. Claude analyses the source by identifying the task paradigm and
generating a task schema that specifies: response distributions (ex-Gaussian mu,
sigma, and tau per experimental condition), per-condition accuracy and omission
rate targets, sequential RT effects, and between-subject performance variance.
Parameter selection is determined by Claude's knowledge of the task literature
and without any task-specific prompting from the researcher.

Two aspects constitute the researcher's contribution on bot performance: the
choice of distribution family (ex-Gaussian) and selection of six available
sequential RT effects (autocorrelation, fatigue drift, post-error slowing,
condition repetition, 1/f noise, and post-stop-signal slowing) from which Claude
selects and parameterizes as appropriate for the identified task. A brief
automated pilot session (≈20 trials) validates Claude's stimulus detection
selectors against the live experiment DOM, triggering a refinement loop if
selectors fail. The resulting configuration is cached and reused for all
subsequent runs without additional API calls.

We evaluated bot performance on four implementations of two tasks: stop signal
(Experiment Factory, N=29 bot "subjects"; STOP-IT, N=27 bot "subjects") and
Stroop (Experiment Factory, N=29 bot "subjects"; Cognition.run, N=28 bot
"subjects"), comparing bot performance to human reference data from Eisenberg et
al. (2019), which acquired stop signal (Logan & Cowan, 1984) and Stroop (1935)
data in 522 online subjects via MTurk.

= Results

For the stop signal task, bot performance on the Experiment Factory (Sochat et
al., 2016) implementation fell within the human distribution on go RT (bot:
622 ± 47 ms; human: 585 ± 73 ms; z = +0.52) and stop accuracy (bot:
53.2 ± 2.2%; human: 52.4 ± 2.2%; z = +0.37). Estimated SSRT was faster than the
human mean (bot: 214 ± 100 ms; human: 287 ± 53 ms; z = −1.37), but SSRT in this
sample is longer than typical SSRTs (e.g., simple stop SSRT ≈ 235 ms in Bissett
et al., 2023). This pattern replicated across the STOP-IT implementation without
modification to the bot's configuration, demonstrating cross-platform
generalization. For the Stroop task, congruent RT (bot: 706 ± 42 ms; human:
672 ± 102 ms; z = +0.33), incongruent RT (bot: 798 ± 56 ms; human: 795 ± 123 ms;
z = +0.02), and the Stroop interference effect (bot: 93 ± 40 ms; human:
123 ± 61 ms; z = −0.50) all fell within the human distribution. In addition to
mean-level metrics, the bot produced positive lag-1 RT autocorrelation (stop
signal: r = .06 ± .09; Stroop: r = .09 ± .17) and post-error slowing (stop
signal: 16 ± 28 ms; Stroop: 17 ± 165 ms), comparable in direction to the human
data (autocorrelation — stop signal: r = .21 ± .14; Stroop: r = .09 ± .12;
post-error slowing — stop signal: 1 ± 51 ms; Stroop: 59 ± 136 ms). In contrast
to Ozudogru et al. (2026), these comparisons are made against a large human
reference dataset (stop signal N = 447; Stroop N = 502; Eisenberg et al., 2019)
using z-scores relative to the human distribution and not visual inspection of
RT histograms.

#figure(
  image("figure1_bot_vs_human.png", width: 100%),
  caption: [
    Bot positioning within human distributions. Violin plots show the human
    reference distributions from Eisenberg et al. (2019); colored dots represent
    individual bot "subjects" across four task implementations (top row: stop
    signal; bottom row: Stroop).
  ],
  placement: bottom,
) <fig-positioning>

#figure(
  image("figure2_sequential_effects.png", width: 100%),
  caption: [
    Sequential effects in bot and human data. Left panel: lag-1 RT
    autocorrelation; right panel: post-error slowing. Gray violins show the
    human reference distribution; colored dots represent individual bot
    "subjects" across task implementations.
  ],
  placement: top,
) <fig-sequential>

= Conclusion

This work shows that current agentic AI tools, with minimal human iteration, can
produce human-like performance across multiple tasks. This proof of concept
shows that real-world data acquisition in speeded cognitive tasks may be
susceptible to bot contamination today.

= Acknowledgments

The agentic bot described in this work uses Claude Opus 4.6 (Anthropic) for task
identification and parameter generation. The authors additionally used a
generative AI assistant (Claude, Anthropic) for software development and for
typesetting this manuscript into the CCN template; all scientific claims,
analyses, and conclusions are the authors' own.

// All references appear in the list via form:none (in-text citations are
// author-year text, matching the submitted manuscript).
#cite(<bissett2023>, form: none)
#cite(<eisenberg2019>, form: none)
#cite(<fan2002>, form: none)
#cite(<huskey2026>, form: none)
#cite(<logan1984>, form: none)
#cite(<ozudogru2026>, form: none)
#cite(<sochat2016>, form: none)
#cite(<stroop1935>, form: none)
#cite(<westwood2025>, form: none)

#bibliography("ccn_references.bib")
