# Data

| Path | Contents |
|---|---|
| `human/` | human reference data. Trial-level files are large and fetched rather than committed — see `human/README.md` for the download and checksums. |
| `human/rdoc/` | the lab's twelve-task battery matrices. Real participant identifiers, so the real files are never committed; the committed `*.placeholder.csv` files document the schema. |
| `bot/rdoc/` | the bot's matching matrices, at exact column parity with the human ones because they came out of the same preprocessing pipeline. |
| `rdoc_task_urls.tsv` | which task label points at which deployed URL. |

Two human references appear in the results, and they are not
interchangeable: trial-level data for the two-paradigm comparison, and
session-level matrices for the twelve-task battery. `docs/results.md`
explains where each is used and how much the battery headline depends on
that choice.
