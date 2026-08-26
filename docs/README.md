# Documentation

Four documents. Read them in this order.

| Document | What it tells you |
|---|---|
| [how-it-works.md](how-it-works.md) | What the system does and how each stage works, from a URL to scored data |
| [results.md](results.md) | What the bot's behavior looks like next to human behavior, where it fails, and whether a detector catches it |
| [assessment.md](assessment.md) | What the project has actually established, what is still missing, and whether it should be a tweet, a blog post, or a preprint |

Start with `how-it-works.md` if you want to understand or run the system.
Start with `assessment.md` if you want to know whether the science is
ready to publish.

## The one-paragraph version

Give the system a web address for a cognitive experiment. It reads the
page's code, asks Claude to write a small Python program that plays the
part of a participant, then runs that program against the live experiment
in a real browser. The program decides every keypress and every reaction
time. Nobody tells it what human data looks like: the prompt names no
effects, no distributions, and no numbers, and automated tests enforce
that. The experiment's own software records the results, and the same
analysis code scores the bot and real people side by side.

## What lives where in the repository

| Directory | Contents |
|---|---|
| `src/experiment_bot/` | The pipeline. No task-specific code anywhere in it. |
| `taskcards/` | One structural description per experiment, named by content hash |
| `naive_programs/` | Generated participant programs, each with the full model transcript and its gate report |
| `output_naive/` | Every recorded session, 240 of them |
| `analysis_out_naive/` | Per-subject measures and bot-vs-human comparisons |
| `data/` | Human reference data and the bot's matching matrices |
| `scripts/` | Collection scripts and the docs link checker |
| `tests/` | 770 tests, including the ones that police the prompt |
