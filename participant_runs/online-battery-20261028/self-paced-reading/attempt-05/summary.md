# Reading with a generated visible policy

A synthetic participant reached the native export controls. The [native data](data/native-export.tsv) contain 5 sentence rows and 28 word intervals. The local OCR observations match **28/28 words** in native sequence order. Every native word matches the saved OCR observations in order. See [coverage check](coverage.json).

The model authored the participant program once, and the first mechanically passing candidate was frozen before live use. It reads OCR extracted from current screenshots, follows the observed Space/n/wait instructions, and delivers ordinary browser key presses and releases. Screenshots and recognized text are saved before each response. It cannot access task variables, future text, hidden answers, source, or native data during participation. Native export is captured only after completion.

This is `generated_visible_policy`, **not direct per-word LLM comprehension**. The authoring record acknowledges inherited conversation context rather than claiming an isolated neutral generation call. The retained policy hash is `9c0a9c7c3c5eab07596e1ac072a7b88df9812fcf84662eb5ef7afe822560f539`.

The preceding run exposed a short-word OCR detection defect. This attempt keeps the exact same participant policy and adds an OCR fallback to the visibly established canvas word band when full-frame recognition is empty. The adapter passed saved-image fixtures, including the previously missed word and a blank frame, before live use (`adapter-check.json`). No expected answer or word vocabulary is injected.

There are 0 native intervals equal to 9999 ms. Native intervals range from 369 to 433 ms; these values include OCR and browser transport and were neither adjusted nor selected to match human response times. No human reading validity is established. Every earlier attempt remains archived.
