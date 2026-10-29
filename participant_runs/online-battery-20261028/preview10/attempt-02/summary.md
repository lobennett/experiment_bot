# Preview 10 attempt 02: adapter failure

The first policy candidate passed its mechanical policy gate and was frozen. No policy changes were made. The native export contains 75 rows, including 18 practice/test response trials with no response. The task advanced automatically while the browser adapter was being diagnosed; no completion is claimed.

The `run` script failed with `fn is not a function` ([failure](evidence/15_practice_segment.txt)); a [string expression probe](evidence/16_string_probe.txt) returned the correct URL. Installed CLI implementation inspection showed that `page.wait(ms)` sends a raw Promise as an evaluate-script function, and `page.click(selector)` sends a raw IIFE. The next attempt must probe adapter operations individually on a non-task page, then use the same frozen participant policy. The adapter alone may be repaired. The full [partial platform export](data/experiment_data.json) was saved before the isolated session was closed.

This is a transport failure and preserved failed attempt, not a behavioral rejection or evidence about human validity. Protocol files, authoring prompt, candidate, gate, and failed script are archived here.
