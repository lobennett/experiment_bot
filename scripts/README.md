# Scripts

| Script | What it does |
|---|---|
| `naive_run.sh <n>` | generate a program once, check it, then run n sessions per configured task. Idempotent by seed, so re-running fills gaps instead of duplicating. |
| `collect_battery_stealth.sh <n> <task>...` | collect n sessions per task in real headful Chrome. This is the mode used for the committed battery, because one pass serves both the behavioral analysis and the live bot-detection check. |
| `check_doc_links.py` | fail the build if a document points at a file that does not exist. Run it after editing docs. |
