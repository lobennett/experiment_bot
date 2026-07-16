# Provenance — `docs/preregistration-naive.md`

The pre-registration is frozen at its state in commit `d75cd69`
(2026-07-03 08:17 PDT), which predates the first program-generation call
(2026-07-03 09:00 PDT; earliest archived transcript timestamp,
`naive_programs/expfactory_stroop/…transcript.json`). That ordering — the
document committed before any generation — is the experiment's integrity
evidence, so the file itself is never edited.

Two notes that would otherwise live in the file:

- **Expert-arm references.** The assets the pre-registration cites —
  the expert-arm pre-registration, the SP21 design spec, the frozen
  collection script,
  and the expert pipeline/dataset — live on the `main` branch
  (`check_doc_links.py` exempts the frozen file for this reason).
- **Restoration record.** Commit `6a1ff45` (2026-07-06) added a bracketed
  provenance note at the top of the frozen file. The pre-registered content
  beneath it was byte-unaltered, but the edit violated the freeze rule, so
  the final pre-merge review had the file restored to its `d75cd69` bytes
  and the note moved here. `git log -- docs/preregistration-naive.md` shows
  both edits; `git diff d75cd69 HEAD -- docs/preregistration-naive.md`
  is empty.
