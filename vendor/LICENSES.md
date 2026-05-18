# Vendored sources — provenance and licenses

This directory contains selectively-vendored source files from open-source
platforms the bot's drivers reference. Files are vendored per major version
and serve as version-pinned API references for driver code.

## jsPsych

- **License:** MIT — https://github.com/jspsych/jsPsych/blob/main/LICENSE
- **Copyright:** Joshua de Leeuw and contributors.
- **Vendored versions:** see subdirectories under `vendor/jspsych/`.
- **Provenance:** each vendored file's top comment block lists the upstream
  GitHub URL + commit hash + retrieval date.

## Closed-source platforms

Drivers targeting closed-source platforms (e.g., cognition.run) cannot
vendor source. Those drivers live under `src/experiment_bot/drivers/<name>/`
with no corresponding `vendor/<name>/` directory; their `notes.md` documents
observed behavior. The reviewer-1 charter's scope-of-validity section lists
this limitation explicitly.
