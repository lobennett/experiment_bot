# Task cards

One file per experiment, describing how to *operate* the page — never how
to behave on it.

A card says where each stimulus appears, how to click through the
instructions, which keys the task accepts, where the current trial's
correct answer can be read out of the page, and whether a stop signal can
interrupt a trial. It contains no reaction times, no accuracies, and no
effects.

Files are named by the hash of their own contents, so
`stroop_rdoc/a1b2c3d4.json` is that exact card and nothing else. Sessions
record the hash they ran against, which is what makes a past run
reproducible.

Some directories also hold a `pilot_observations.json`. That is a
by-product of validating the card against the live page, not a card.

Cards are written by `experiment-bot-reason`. See `docs/how-it-works.md`.
