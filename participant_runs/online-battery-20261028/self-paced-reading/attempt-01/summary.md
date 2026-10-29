# Self-paced reading: completed with incomplete word coverage

A synthetic participant completed the public PsyToolkit demo and reached [native export controls](evidence/33_next.png). The [instructions](evidence/04_instructions.png) say to press n to show the first word and then each following word. The introduction uses Space, words appear on a canvas, and each sentence is followed by a wait screen.

The [native export](data/native-export.tsv) contains five sentence rows and 29 word intervals. Its exact displayed table text was saved after completion; the [serialized extraction](evidence/36_export.txt) and [table screenshot](evidence/35_show_data.png) are retained. There were 24 n commands and one Space command. No task source or hidden state was read.

This is not a clean observation-fidelity success. The first sentence was captured word by word, but later words sometimes advanced between observations. Six native intervals equal 9999 ms, consistent with a per-word time limit that was not stated on the instruction screen. The exact sentinel meaning remains unknown because task source was not inspected. Missing words were not reconstructed as if they had been observed, and no response times were altered.

The skill should not infer indefinite stimulus persistence from a self-paced task label. It should detect autonomous transitions from observed state changes, record incomplete stimulus coverage separately from terminal completion, and choose a faster observation/input mechanism when required. A new run would be a documented mechanical-method iteration, not a replacement for this retained result.

Native intervals include model, logging, screenshot, and browser transport overhead. They establish neither human reading speed nor human behavioral validity. [Official task documentation](https://www.psytoolkit.org/library/pacedreading1.html).
