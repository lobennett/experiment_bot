# Reading: terminal state reached without perceptual coverage

The persistent Playwright browser reached [export controls](evidence/003_key.png) after the model/tool loop stalled between instruction handling and its next action. No word was observed. This is terminal completion with **zero perceptual coverage**, not successful reading.

The [native export](data/export-0.txt) has five sentence rows and 29 intervals, all exactly 9999 ms. It was read only after task completion. Browser action/screenshot operations measured 74–568 ms, but outer tool/model delays were much longer. The task continued running throughout; no clocks or data were changed.

The separate attempt-02 startup screenshot bug was fixed by testing visibility before capturing the canvas. That adapter repair did not solve the model-turn latency boundary. No further direct-mode repetitions are justified without another mechanical change.
