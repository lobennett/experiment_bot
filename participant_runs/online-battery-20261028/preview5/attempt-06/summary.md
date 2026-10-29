# Preview5 — partial, new phase discovered

Synthetic participant. The unchanged policy with repaired fast OCR completed delay-1 practice and reached [delay-2 instructions](evidence/review-57.json). These specify mismatch for the first two trials. The adapter did not recognize the new cue wording or [delay-2 reminder](evidence/review-58.json), so delay-2 trials went unanswered before the attempt was stopped. [Final feedback](evidence/008-final.json) and the [native export](data/experiment_data.json) are retained.

Phase outcomes, including omissions and unknown correctness, are in [export inspection](data/export-inspection.json):

```json
{
  "practice delay 1": {
    "opportunities": 6,
    "responses": 6,
    "omissions": 0,
    "known_correct": 6,
    "known_incorrect": 0,
    "unknown_correctness": 0
  },
  "practice delay 2": {
    "opportunities": 7,
    "responses": 0,
    "omissions": 7,
    "known_correct": 0,
    "known_incorrect": 7,
    "unknown_correctness": 0
  }
}
```

The policy remains byte-identical to attempt03. A next attempt can repair the visible-instruction representation using these observed facts; neither response preferences nor timing will change. No terminal completion or remote receipt was observed.
