# Authoring record

Authoring used the working agent's inherited conversation, not an isolated model
call. The conversation includes earlier direct-mode attempts. This record is the
explicit prompt and mechanics; it is not a claim to be the full generation
transcript or the frozen study's neutral generation context.

Write a participant policy for the observed task. Follow its instructions as
a typical attentive adult participant. Decide all responses and their timing
from the current participant-visible observation and the policy's own history.
Use a seeded local random generator if the policy makes random choices.

Observed mechanics: the introductory screen says to press Space to continue.
The next screen says to press n to see the first word, and then n for each
following word. One word is displayed at a time on a canvas. Between sentences,
the page says to wait until the next sentence. The terminal page exposes Show
data and Copy data to clipboard controls. No correctness or population targets
are supplied.

Interface: receive OCR text extracted only from the current rendered screenshot,
the screenshot identity, and previous policy history. Return a normal browser
key response, wait, done, or an unknown-screen indication. All keys are released.
Native data remain inaccessible until the run ends. Repeated observations of
one unchanged presentation must not cause repeated inputs. No hidden task state
or future text is supplied. The driver records pixel evidence and OCR before
delivering an input.
