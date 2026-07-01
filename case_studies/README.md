# Case studies

This directory contains aggregate-only public-database demonstrations for
NeuroSurgEpiAgent. Raw participant-level files are cached outside this directory
and are ignored by git.

## Available case studies

| Name | Source | Type | Status |
| --- | --- | --- | --- |
| `nhanes_stroke_2017_2018` | NHANES 2017-2018 | Real-data descriptive (aggregate only) | Shipped |
| `cdc_wonder_synthetic_demo` | CDC WONDER (synthetic) | Disclosure-checked aggregate workflow | Shipped |
| `seer_metadata_feasibility` | SEER (synthetic tree; metadata-only) | Adapter inspection contract | Shipped |

The two synthetic case studies exist to demonstrate the analysis-implementation
contract (`docs/ANALYSIS_IMPLEMENTATION_PRINCIPLES.md`) without touching any
real CDC WONDER or SEER data. They are runnable on a fresh clone and
require no DUA.

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

## CDC WONDER synthetic-data case study (disclosure-checked)

Run:

```bash
python -m neurosurg_epi_agent.case_studies.cdc_wonder_synthetic_demo --output-dir case_studies/cdc_wonder_synthetic_demo/results
```

The numbers in this case study are entirely synthetic. The script:

- Demonstrates the disclosure posture: any cell with `Deaths <= 9` is
  dropped before any output is written; cells with `Deaths < 20` are
  flagged `Unreliable` and carried through with that status.
- Distinguishes UCD vs MCD rows; they are not combined in the same table.
- Applies the conservative-language policy to the rendered report
  (no `proves`, `causes`, `first ever`, `comprehensive`, `unprecedented`).
- Records Python version, package versions, and a random seed in
  `provenance.json`.

## SEER metadata/feasibility case study

Run:

```bash
python -m neurosurg_epi_agent.case_studies.seer_metadata_feasibility --output-dir case_studies/seer_metadata_feasibility/results
```

The script:

- Writes 13 placeholder SEER-shaped CSVs into a temp directory (the
  user's real SEER tree is NEVER touched).
- Calls `SEERAdapter.inspect()` on that temp directory.
- Emits a `results.json` that contains only file-level metadata:
  member name, byte size, schema fingerprint, and (optional) SHA-256.
- Emits a `provenance.json` that records the synthetic-seed value,
  Python / package versions, the data-version field status, and the
  adapter capability split (`metadata-inspection` supported;
  `clinical-analysis` planned).
- Does NOT read a single case row. The synthetic rows the script
  itself wrote are never propagated to the case-study outputs.
- Does NOT exercise any clinical analysis. To do that, the analyst
  must fill in `docs/SEER_STUDY_CONTRACT.md`.

