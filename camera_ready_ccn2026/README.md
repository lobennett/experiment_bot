# CCN 2026 camera-ready — submission 436

Camera-ready (poster) version of *Agentic AI Can Generalize to Multiple Speeded
Tasks with Human-Like Behavior*, rebuilt in the **official CCN 2026 template**
to address the TPC's template-compliance requirement.

## Files

- `436_camera_ready.pdf` — the compiled camera-ready (submit this).
- `ccn_extended_abstract.typ` — the source (filled-in official Typst template).
- `ccn.typ` — the official CCN 2026 class file, **unmodified** (template `v2026.3`).
- `ccn_references.bib` — references (APA).
- `figure1_bot_vs_human.png`, `figure2_sequential_effects.png` — the two figures,
  extracted from the originally submitted PDF so they match the accepted version exactly.

## Build

```
typst compile ccn_extended_abstract.typ 436_camera_ready.pdf
```

(or upload the folder to typst.app). Built and verified with Typst 0.14.2.

## What changed from the originally submitted PDF

The **content is unchanged** — same title, Introduction/Methods/Results/
Conclusion text, both figures, and references, transcribed verbatim. Only the
*production* changed:

1. Rebuilt in the official CCN 2026 extended-abstract template
   (`mode: "extended-abstract"`, the camera-ready/de-anonymized mode). This is
   the fix the TPC required.
2. Author names + affiliation now appear (correct for camera-ready; the
   double-blind anonymity requirement applied only to the review stage, which
   has passed).
3. No line numbers (the official template uses them in submission mode only;
   one document-level line — `#set par.line(numbering: none)` — disables them
   for camera-ready, matching what the LaTeX class does automatically. The
   official `ccn.typ` class file is left untouched.)
4. A generative-AI disclosure sentence was added to the Acknowledgments, which
   the template requires.

## PLEASE CONFIRM / EDIT before submitting (all near the top of the .typ)

- **Affiliations** — set to "Department of Psychology, Stanford University" for
  all three authors. Confirm or correct (e.g., if Bennett is in a different
  department/program).
- **Emails** — only the corresponding author (`logben@stanford.edu`) is listed.
  Add Poldrack's and Bissett's if you want them shown.
- **Acknowledgments / AI disclosure** — review the wording; it currently
  discloses Claude's use both as the method and as a software/typesetting
  assistant. Adjust to match your preference.
- **References** — Huskey and Ozudogru preprints render as "… & others." in APA;
  replace `and others` with the full author lists in `ccn_references.bib` if you
  have them.
- **No separate 300-word abstract block** was added (the submitted PDF had none).
  If you'd prefer one, paste your OpenReview web-form abstract into an
  `abstract: [ … ]` argument in the `ccn.with(...)` call.
