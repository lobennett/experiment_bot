# Offline isolated-glyph OCR validation

Native macOS Vision with a tighter pixel crop and fast recognition recovered the requested g, v, t, blank, and + fixtures. An extended set passed 13/14 exact-case comparisons and 14/14 case-insensitive comparisons. The only mismatch was uppercase V recognized as lowercase v. Raw OCR output is retained, without case conversion or character replacement.

The case-insensitive interpretation is valid for this particular task because its saved participant-visible instructions say capitalization does not matter (`preview5/attempt-05/evidence/004-instructions.png`). That does not establish case fidelity for other tasks.

## Artifacts

- `vision-matrix.swift` and `vision-matrix.jsonl`: 120 OCR requests covering three supported Vision revisions, accurate/fast recognition, language correction off/on, and full/cropped input for five initial fixtures. These files contain no task answers or participant logic.
- `ocr-fast.swift`, `validate.py`, and `fast-validation.json`: fixed generic diagnostic configuration and 14 extended fixtures. Expected strings are assertion data and are never passed to OCR.
- `validate-shared.py` and `shared-helper-validation.json`: the reusable helper's `--fast` option produces the same 13/14 exact-case and 14/14 case-insensitive results; its default accurate mode preserves all three previous reading/blank fixture results.

No participant policy, task source, hidden state, or native response data was read. No live task was run for this diagnosis. No dependency was installed.

## Selected generic mechanism

The shared helper at `skills/behavioral-participant/scripts/ocr.swift` now accepts:

```text
participant-ocr image.png [--crop x y width height] [--fast]
```

The crop is supplied explicitly by the caller using actual source-image pixels with top-left origin. The helper preserves input bytes, returns boxes in full source-image coordinates, and reports its effective recognition configuration. It has no task names, word lists, letter substitutions, case normalization, or fixed crop coordinates. Accurate recognition remains the default; `--fast` changes only the Vision recognition level. Language correction remains disabled.

For the supplied 960×800 fixture files, the same observed central region `(320, 250, 320, 320)` contains every tested glyph. For original 1280×900 full frames, the central region `(600, 413, 80, 80)` recognized t and + without resizing; a separate blank region `(280, 413, 80, 80)` returned no text. These rectangles describe these fixtures only and are not defaults in the helper.

The initial matrix explicitly used Vision revision 3, English, minimum text height zero, and language correction off for the selected fast results. The shared helper preserves the framework's language, revision, and minimum-height defaults; its effective settings are included in the JSON and independently passed the same fixture checks. Do not assume changing the recognition level alone repairs arbitrary input sizes: fast mode on the original wide fixture region missed several glyphs.

## Provenance and limits

The g/v PNG fixtures supplied by the earlier adapter were already enlarged 4× with Pillow. Their 960×800 pixels were used exactly as stored. Original raw cropped PNG bytes were not retained, and filenames refer to earlier raw screenshot hashes rather than the displayed enlarged file bytes. This diagnosis records actual SHA-256 values for the supplied files. The full t/blank/+ control frames are unscaled source captures.

All validated source files retained their SHA-256 values. Cropping selected existing pixels without additional scaling or color transformations. The V/v ambiguity remains unresolved for case-sensitive tasks. The fixture set does not establish universal recognition accuracy or live response timing.

The configuration matrix's five fast cropped Vision requests took approximately 6–8 ms each after framework warmup; this excludes process launch, screenshot acquisition, transport, and model decision time. It is not a claim about end-to-end response latency.

Primary reference: [Apple's VNRecognizeTextRequest API](https://developer.apple.com/documentation/vision/vnrecognizetextrequest). The findings above come from the saved local screenshots and reports.
