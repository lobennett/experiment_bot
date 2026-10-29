# Tower of Hanoi: blocked transport baseline

The synthetic participant opened the public demo and read both instruction screens. The task requires dragging three discs from the left peg to the right peg, one at a time, without placing a larger disc on a smaller one. [Instructions](evidence/06_instruction_screen.png).

The browser accessibility tree exposes only a single canvas. The preferred CLI can drag one accessible element onto another, but cannot specify coordinates within a canvas. No puzzle move was attempted and no native trial data was generated or collected. A separate attempt uses ordinary Playwright mouse input; this is a mechanical transport repair, not a result-selected retry.
