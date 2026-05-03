You will receive a TaskCard's behavioral parameters. For each parameter,
classify how strongly it affects the bot's observable output (mean RT,
accuracy, distributional shape, sequential effects).

Output a JSON object keyed by parameter path, value in
{"high", "medium", "low"}:

{
  "response_distributions/congruent/mu": "high",
  "response_distributions/congruent/sigma": "medium",
  ...
}
