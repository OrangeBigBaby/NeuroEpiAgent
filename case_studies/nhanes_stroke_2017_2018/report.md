# NHANES 2017-2018 stroke prevalence case study

This is an aggregate-only reproducibility demonstration for NeuroSurgEpiAgent.

## Data sources

- `DEMO_J.XPT`: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.XPT
  - SHA-256: `c0b46e0345ea19404928656277c8b0d10b0cca348a9b2fe4fc3c67e8b7ee73ec`
- `MCQ_J.XPT`: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/MCQ_J.XPT
  - SHA-256: `79c50c805a377fcd61d44fae8b86a16af0a5741f8b1aeebda918d7d743c68f98`

## Results

- Eligible participants with MCQ160F yes/no: 5559
- Unweighted stroke yes/no counts: 273 / 5286
- Weighted stroke prevalence: 0.033522

| Sex | Eligible n | Stroke yes n | Stroke no n | Weighted prevalence |
| --- | ---: | ---: | ---: | ---: |
| Female | 2863 | 137 | 2726 | 0.037965 |
| Male | 2696 | 136 | 2560 | 0.028734 |

## Statistical note

Weighted prevalence uses WTINT2YR among participants with MCQ160F coded yes/no and positive interview weights. Confidence intervals are not reported because complex survey variance estimation with strata and PSU is not implemented in this case study.

## Privacy and reproducibility

Only aggregate summaries and source-file hashes are written. No merged participant-level records, SEQN values, or raw XPT data are written to the case_studies output directory.
