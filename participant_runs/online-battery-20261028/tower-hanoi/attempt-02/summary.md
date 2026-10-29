# Tower of Hanoi: completed with coordinate input

The synthetic participant completed the public PsyToolkit demo using seven ordinary browser mouse drags. Each move was selected from a fresh screenshot. The task showed all three discs on the third peg and then automatically displayed export controls ([final arrangement](evidence/011_drag.png), [ending](evidence/012_observe.png)).

The [instructions](evidence/003_click.png) require moving one disc at a time, never placing a larger disc on a smaller one, and minimizing moves. The ontology records the three pegs, disc sizes, drag response, placement rule, move feedback, and ending. No task source, hidden state, answer key, or internal completion function was used.

The [native data](data/native-export.tsv) has seven rows. Final cumulative time is 81,424 ms, move count 7, and the two mistake counters are both 0. Column meanings come from the [official demo documentation](https://www.psytoolkit.org/library/tower_hanoi.html). Values and tab/newline separators were copied exactly from the visible Show data table; the entire displayed page text is retained in [evidence](evidence/013_click_text.txt).

Attempt 01 stopped before any puzzle move because the preferred CLI cannot drag between coordinates inside one canvas. This attempt changed only browser input transport to Playwright mouse events, at a 1200×900 viewport with matching screenshot dimensions. There was no behavioral selection, task-clock alteration, policy script, or delay tuning. Screenshots, inference, and tool latency contribute to the native times, so completion does not establish human timing or planning validity.
