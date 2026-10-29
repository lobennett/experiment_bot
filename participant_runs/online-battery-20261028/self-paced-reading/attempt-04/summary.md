# Reading with a generated visible policy

A synthetic participant reached the native export controls. The [native data](data/native-export.tsv) contain 5 sentence rows and 28 word intervals. The local OCR observations match **27/28 words** in native sequence order. Recognition coverage is incomplete; the original native data remain unchanged. See [coverage check](coverage.json).

The model authored the participant program once, and the first mechanically passing candidate was frozen before live use. It reads OCR extracted from current screenshots, follows the observed Space/n/wait instructions, and delivers ordinary browser key presses and releases. Screenshots and recognized text are saved before each response. It cannot access task variables, future text, hidden answers, source, or native data during participation. Native export is captured only after completion.

This is `generated_visible_policy`, **not direct per-word LLM comprehension**. The authoring record acknowledges inherited conversation context rather than claiming an isolated neutral generation call. The retained policy hash is `9c0a9c7c3c5eab07596e1ac072a7b88df9812fcf84662eb5ef7afe822560f539`.

The saved frame `evidence/053_frame.png` visibly contains the short word “is”, while OCR returned no text. This caused one 9999-ms interval. Offline adapter probes show full-frame accurate/fast recognition failed, while the observed word-band crop succeeded; the repair and all probes are preserved in `adapter-repair/`. The participant policy was not edited.

There are 1 native intervals equal to 9999 ms. Native intervals range from 363 to 9999 ms; these values include OCR and browser transport and were neither adjusted nor selected to match human response times. No human reading validity is established. Every earlier attempt remains archived.
