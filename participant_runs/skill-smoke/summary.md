# Signal Cards smoke run

A synthetic participant completed the local task through its live browser interface. The terminal screen states **Task complete**, confirms that all four responses were recorded locally, and says no submission is required ([completion evidence](evidence/15_completion.txt), [screenshot](evidence/16_completion.png)).

Block 1 instructed F for MOON and J for SUN; block 2 instructed J for MOON and F for SUN. Each block presented two cards, and every response was followed by a Continue button. Both instruction screens stated no time limit ([block 1](evidence/01_instructions.txt), [block 2](evidence/08_instructions.txt)). No separate practice, questionnaire, or break was encountered.

The observed card sequence was MOON, SUN in both blocks. The accessibility snapshots omitted the card words, so the participant viewed and saved screenshots before responding ([first](evidence/03_card_1.png), [second](evidence/06_card_2.png), [third](evidence/10_card_1.png), [fourth](evidence/13_card_2.png)). Responses were F, J, J, F, and all four received Correct feedback ([1](evidence/04_card_1_response.txt), [2](evidence/07_card_2_response.txt), [3](evidence/11_card_1_response.txt), [4](evidence/14_card_2_response.txt)).

The [native export](data/native_export.json) contains four complete trial-level records and completed=true. Its exact visible-panel text was saved as UTF-8 without reformatting, rounding, or appending a newline. The [capture](evidence/17_native_export.txt) preserves the browser tool's serialized result. The page exposed this panel after participation; no local HTML source, hidden task state, internal completion function, or network response was read.

There were four observed response opportunities, four key responses, and six navigation clicks. There was one session and no restart, retry, or outcome-based selection. No task instruction ambiguity or mechanical failure prevented completion. The ontology keeps the reversed mappings scoped to their blocks. Randomization and the implementation of the native timing clock remain unknown.

This run establishes browser completion and artifact handling on a small, untimed synthetic fixture. Native response times include observation, inference, logging, permission, and browser-transport overhead. They are preserved exactly and are not human reaction-time evidence. No scientific validity or human timing fidelity is established, and this exploratory run is separate from the frozen participant-program study. Exact model and browser versions were unavailable and remain null.

Validation parses the manifest, ontology, event lines, and native export; checks node and evidence IDs, relation endpoints, event/completion references and paths; verifies exact native text preservation; and checks all finalized artifact hashes. Results are recorded in [validation.json](validation.json).
