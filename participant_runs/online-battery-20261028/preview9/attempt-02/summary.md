# Preview 9: generated-policy adapter failure

Partial run, with 52 native rows and 11 recorded practice opportunities. No policy trial responses were delivered. The first generated policy passed its offline mechanical gate, but real tool calls exposed an installed API defect: raw page.wait and selector click evaluations can fail with `fn is not a function`, sometimes after navigation already occurred. Ambiguous deliveries were inspected rather than blindly retried.

The fixed probe used string-form page.eval and a host JavaScript timer. It extracted visible square pixels with occupancy 0.999, consistent with the previously observed white square; a following screenshot was already blank, emphasizing short presentation windows. No source code or hidden task state was used to respond. Native export was read only after abandoning participation.

The [policy](policy/participant.js) remains frozen. A new attempt is warranted for a documented adapter defect, not behavioral results. See [native data](data/experiment_data.json), [failing probe](evidence/09_visual_verification.txt), and [fixed probe](evidence/12_visual_verification_fixed.txt).
