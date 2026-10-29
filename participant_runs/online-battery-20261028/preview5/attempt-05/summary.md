# Preview 5 — partial generated-policy attempt

Synthetic participant. **Partial:** the terminal task state was not reached. The native export is available; remote submission is unconfirmed.

The [instructions](evidence/004-instructions.json) require case-insensitive comparison of each displayed letter to the letter one or two trials earlier: comma for mismatch, period for match. The observed [practice](evidence/005-practice-instructions.json) uses delay 1, with mismatch on its first trial. Each visible letter is an image; a DOM text observer alone cannot read it. The final adapter uses a screenshot crop grounded in the visible center of the screen and generic macOS Vision OCR.

The unchanged policy issued 11 letter responses over 16 observed image presentations. The [native export](data/experiment_data.json) contains 69 rows, including 16 practice response opportunities and 11 recorded responses. Native data gives a 1,000 ms letter display and 1,500 ms response window; no timing fields were altered. These are software timings, not evidence of human timing fidelity.

Vision passed saved `t`, blank, and fixation fixtures, but returned no text for clearly visible [g](evidence/pixel-1857233f96723708.png) and [v](evidence/pixel-0ab24edf988e0a6a.png). The task twice [reported omissions and repeated practice](evidence/review-86.json). The driver continued observing while the agent reviewed feedback, then stopped during the automatically started third practice. The [last captured screen](evidence/008-final.png) is ordinary Correct feedback, not completion.

The first mechanically passing participant.py from attempt-03 was retained byte-for-byte. Attempts 04 and 05 changed only perception/driver mechanics, each with evidence-backed repair records. Policy generation inherited the working agent context; a full model transcript is unavailable and the prompt file does not claim to contain that full context. Only this task's participant-visible instructions, pixels, and history informed its responses. Native data inspection occurred after participation ended.

Remaining limitations: empty OCR can mean an unread glyph, and missed glyphs impair the sequence history used by later comparisons. A future adapter must detect nonblank unread pixels and validate more than one glyph before treating OCR as adequate. Later test blocks and delay-2 execution remain unobserved. Completion or resemblance to human behavior is not claimed.
