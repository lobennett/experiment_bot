# Human Reference Data

Reference datasets the bot's behavior is compared against
(`experiment-bot-compare`). Two tiers:

## Session-level summaries (committed)

- `stroop_rdoc.csv` — 2,510 rows; per-session congruent/incongruent RT,
  accuracy, omission rate.
- `stop_signal_rdoc.csv` — 2,510 rows; per-session go RT, go/stop accuracy,
  omission rate, SSD summaries (min/mean/max/final), stop-failure RT.

Provenance: RDoC behavioral battery session-level summaries. Each row is one
human session and carries three exclusion flags (`Session-Level`,
`Task-Level`, `Subject-Level Exclusions`). **Filtering to rows where all
three equal `Include` yields N=2,478 (Stroop) and N=2,412 (stop-signal) —
exactly the reference Ns reported in `Task Turing Bot Abstract.md`.** The
comparison CLI applies this filter automatically.

Human SSRT is derivable from these summaries only via the **mean method**
(`go_rt − mean_SSD`); trial-level data would be required for the integration
method. The comparison tool computes the bot-side SSRT the same way and
labels it `ssrt_mean_method` so the estimators match.

## Trial-level Eisenberg data (fetched, not committed — 142 MB / 16 MB)

Trial-level behavioral data from Eisenberg et al. (2019) Self Regulation
Battery. Download `stop_signal.csv.gz` and `stroop.csv.gz` from:
https://github.com/IanEisenberg/Self_Regulation_Ontology/tree/master/Data/Complete_02-16-2019/Individual_Measures

Uncompress into this directory as `stop_signal_eisenberg.csv` and
`stroop_eisenberg.csv`, then verify integrity:

```
shasum -a 256 -c <<'EOF'
9bf28f83863236901b266d5b629eef405c722d80690f1056e5b41b5094b10289  data/human/stop_signal_eisenberg.csv
25805782a9b9631201045ffaf6d0c0ac7cd36dae5c39a9c9a11074009645129e  data/human/stroop_eisenberg.csv
EOF
```

## Comparison maps

`comparison_maps/*.json` declare, per reference CSV, which human column maps
to which bot-side computation (generic kinds: `rt_mean`, `accuracy`,
`omission_rate`, `field_mean`, `subtract`). Paradigm-conventional knowledge
lives in these data files, not in bot-library code (goal G2).

## Reference

Eisenberg, I. W., Bissett, P. G., Enkavi, A. Z., Li, J., MacKinnon, D. P.,
Marsch, L. A., & Poldrack, R. A. (2019). Uncovering the structure of
self-regulation through data-driven ontology discovery. *Nature
Communications*, 10(1), 2319.
