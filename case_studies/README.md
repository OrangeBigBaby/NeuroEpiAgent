# Case studies

This directory contains aggregate-only public-database demonstrations for
NeuroSurgEpiAgent. Raw participant-level files are cached outside this directory
and are ignored by git.

## NHANES 2017-2018 self-reported stroke prevalence

Run:

```bash
python -m neurosurg_epi_agent.case_studies.nhanes_stroke_2017_2018 --output-dir case_studies/nhanes_stroke_2017_2018 --cache-dir data/cache/nhanes
```

The script downloads public CDC NHANES XPT files if absent, merges `DEMO_J` and
`MCQ_J` in memory by `SEQN`, and writes only:

- `results.json`
- `provenance.json`
- `report.md`

The case study reports exploratory descriptive weighted prevalence using
`WTINT2YR`. It does not report confidence intervals because complex survey
variance estimation with strata and PSU is not implemented in this lightweight
demonstration.

