# Text presented as pixels

Use local OCR when a program needs text that is actually drawn in a canvas or
image. Preserve the original screenshot bytes before producing crops or resized
derivatives. Record their source rectangle and scale. A screenshot and a DOM
snapshot taken separately may straddle a transition; retain acquisition times
and verify the response still belongs to that visible presentation.

On macOS, the optional [scripts/ocr.swift](scripts/ocr.swift) helper uses native
Vision. Compile it with `swiftc` into the run directory or a temporary directory;
use a temporary module-cache directory if the default compiler cache is not
writable. It has no task vocabulary, answer substitutions, or task-specific
regions. Other systems can use an available local OCR tool with equivalent
evidence and visibility constraints.

```text
participant-ocr screenshot.png [--crop x y width height] [--fast]
```

Crop values are integer pixels of the supplied image, with origin at its top
left. Default recognition is accurate; `--fast` selects the alternative native
recognizer. JSON output preserves raw recognized text, confidence, candidate
alternatives, source-image boxes, image/region dimensions, and effective OCR
settings. The helper reads its input without modifying it. Save the source hash,
invocation, output, and the exact helper version used.

Choose regions from the actual displayed layout. Validate the chosen settings
on saved visible text and negative controls before live use. Include short
words or isolated glyphs if the task presents them; success on a sentence does
not establish single-character recognition. Recognition settings and cropping
are mechanical adapter choices, not behavioral parameters.

Empty OCR does not prove the screen is blank. Distinguish a blank/fixation frame,
nonblank unrecognized content, and a tool/service error. Surface unknown content
and preserve its pixels rather than silently treating it as an absent stimulus.
Case and character ambiguities must remain explicit. Apply equivalence only
when the task's observed instructions define it; never silently normalize OCR
to match an expected answer or read task data to correct recognition.
