Write a participant policy for the observed task. Follow its instructions as
a typical attentive adult participant. Decide all responses and their timing
from the current participant-visible observation and the policy's own history.
Use a seeded local random generator if the policy makes random choices.

Observed instructions (the complete captured pages are in ../evidence/):
Shapes appear one at a time. Circle means comma; square means period. Respond
as quickly and accurately as possible. A star can appear around the shape,
with or shortly after its appearance; try to withhold a response on that trial.
Do not slow down to wait for the star. Practice provides feedback and reminders;
the main test removes those. An observed screenshot shows a white square on a
gray background. Accessibility text does not identify the shape.

Available interface: page.eval reads only currently rendered text and current
visible image pixels/geometry. page.press delivers normal keyboard input.
Keep current-image pixel classification distinct from response decisions.
The renderer must not use image filenames, hidden attributes, task variables,
future trials, native export data, or internal completion calls. Verify its
pixel features against a screenshot. End each segment at instruction/block
feedback or a bounded operational timeout. Reobserve before delivering an
intention and cancel if the opportunity disappeared or changed. Archive every
observation, intended response, and actual input. Seed: 91028. Segment maximum:
50 seconds (operational budget, not a behavioral parameter).
