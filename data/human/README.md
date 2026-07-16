# Human Reference Data

Trial-level human reference data the bot cohort is compared against
(`experiment-bot-per-subject`). Bot and human pass through identical
estimators (see `src/experiment_bot/analysis/per_subject.py`).

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

Pass the paths to the analysis CLI via `--human-stop` / `--human-stroop`.

## Reference

Eisenberg, I. W., Bissett, P. G., Enkavi, A. Z., Li, J., MacKinnon, D. P.,
Marsch, L. A., & Poldrack, R. A. (2019). Uncovering the structure of
self-regulation through data-driven ontology discovery. *Nature
Communications*, 10(1), 2319.
