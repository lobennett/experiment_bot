Write a participant policy for the observed task. Follow its instructions as a typical attentive adult participant. Decide all responses and their timing from the current participant-visible observation and the policy's own history. Use a seeded local random generator if the policy makes random choices.

Observed task instructions: rectangles appear, black or white. The target is a vertical white rectangle. Determine target absent versus present. Index finger/comma means absent; middle finger/period means present. Practice provides feedback and rule reminders, then these are removed. Respond as quickly and accurately as possible.

Observation interface: current visible rectangle colors and bounding geometry, with an observation-side presentation identity, or no stimulus. It excludes opacity-hidden, CSS-hidden, offscreen and occluded shapes. The policy must return a key and an explicit finite nonnegative delay in milliseconds, or null to wait. The adapter checks that the same visible presentation remains before delivery and records intended delay alongside actual input. No task variables, future stimuli, answer fields, filenames or platform data are accessible. New instructions are routed to the agent separately.

Authoring context: inline in the working agent, with inherited conversation. This file is the explicit instruction, not a full isolated model generation transcript.
