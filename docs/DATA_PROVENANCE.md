# Data Provenance

This document records, for each data source NeuroSurgEpiAgent consumes,
**what the public repository actually contains** versus what only the local
researcher's machine contains. It is the audit trail a reviewer reads before
believing any number in the paper.

## What "metadata-only" means here

For every inspected data file, the public repository carries:

- The **relative name** of the file inside the user's data root
  (e.g. `wonder_stroke_us.csv`). Local absolute paths are replaced by the
  literal token `<user-supplied>` at the adapter boundary.
- The **SHA-256** of the file bytes.
- The **byte size** of the file.
- The **header / column list** parsed from the file (for SEER) or the
  **column list + WONDER provenance block** parsed from the file (for
  CDC WONDER).
- The **provenance** captured from the file's own metadata: dataset
  name, group-by, standard population, rate basis, query date, ICD-10
  selection, and an indication of whether the export is UCD (Underlying
  Cause of Death) or MCD (Multiple Cause of Death).

What the public repository does **not** carry:

- The file itself.
- Any participant row or case listing.
- Any aggregate cell value (count, rate, confidence interval) computed from
  the file.
- Any column-level frequency, distribution, or unique-value list.
- Any absolute path that would let a reviewer infer the local layout.

## Per-source provenance

### NHANES

- **Local-only.** CDC NHANES public `.XPT` files cached under
  `data/cache/nhanes/` (git-ignored).
- **In the public repo.**
  - `case_studies/nhanes_stroke_2017_2018/` driver code (downloads the
    two required `.XPT` files into the cache, then merges + emits
    aggregates).
  - Variable registry entries in `config/variables/nhanes_demo.yaml`,
    each tagged `verified` / `illustrative` / `needs review`.
  - Aggregate outputs (`results.json`, `provenance.json`, `report.md`)
    produced by the case-study driver — each describes the cache state
    and the source URLs but never contains the `.XPT` bytes.
- **Provenance fields written.**
  - Source URL pattern (`https://wwwn.cdc.gov/nchs/nhanes/...`).
  - Cycle letters (G/H/I/J for NHANES 2011-2018; J for the case study).
  - Sample size after inclusion criteria.
  - Weighted prevalence (descriptive only — no complex-survey variance
    in the lightweight case study).

### CDC WONDER

- **Local-only.** `02_data_raw/cdc_wonder/` (git-ignored). Contains
  `wonder_stroke_us.csv`, `wonder_cns_tumor_us.csv`,
  `wonder_neuro_injury_us.csv.csv`, plus three `.xls` files for ICD-10
  subcategories I60 / I61 / I63.
- **Filename anomaly.** One file is named
  `wonder_neuro_injury_us.csv.csv` (double `.csv` suffix). This appears
  to be a local download artifact, not a WONDER naming convention. The
  adapter records the anomaly in `provenance` (`filename_note`) but
  does not modify the source filename; any renaming happens in a
  derived working directory, never in `02_data_raw/`.
- **In the public repo.**
  - `CDCWonderAdapter` source (`src/neurosurg_epi_agent/adapters/cdc_wonder.py`).
  - Synthetic-only test fixtures (CSV generated in-process).
  - Disclosure-checked aggregate outputs (downstream artifacts; never
    derived from cells with `Deaths <= 9`).
- **Provenance fields written.**
  - Dataset (e.g. `Underlying Cause of Death, 2018-2024, Single Race`).
  - ICD-10 selection (e.g. `I60-I69` for cerebrovascular diseases).
  - Group-by (e.g. `Year`).
  - Standard population (e.g. `2000 U.S. Std. Population`).
  - Rate basis (e.g. `100,000`).
  - Query date as written by WONDER.
  - `database_family`: `UCD` or `MCD`.
  - Suppressed / unstable status carried over verbatim from the WONDER
    `Notes` column.

### SEER

- **Local-only.** `E:\Nhance\SEERdatabase\` (13 CSV files totalling
  ~26.77 GB, each ~269 columns, ~9,686-character headers). Excluded
  from git by `/SEERdatabase/` plus `export_C*.csv` in `.gitignore`.
- **In the public repo.**
  - `SEERAdapter` source (`src/neurosurg_epi_agent/adapters/seer.py`)
    — metadata-only streaming reader; never loads case rows.
  - `SEER_DATA_DICTIONARY.md` and `SEER_STUDY_CONTRACT.md`
    documenting what an analysis would require.
  - Synthetic-only test fixtures.
  - User-supplied release / submission / registry-set / SEER*Stat
    version metadata captured by the adapter (or marked
    `needs_verification` if not provided).
- **Provenance fields written (per file).**
  - Relative file name (no absolute path).
  - Byte size.
  - SHA-256 (computed streaming; optional via `--with-sha256`).
  - Column count.
  - Schema fingerprint = MD5 of the canonicalized header.
  - First row of the file is **never** read.

### CHARLS

- **Local-only.** Restricted; no fixtures shipped.
- **In the public repo.** Adapter scaffold + variable contract, future
  use.

## How to record a new local-only version

When a researcher updates their local data files (a new WONDER query, a new
SEER submission), they run:

```powershell
neurosurg-epi inspect-database --database CDC_WONDER --data-root <root> --output manifests/cdc_wonder.vYYYYMMDD.json
neurosurg-epi inspect-database --database SEER --data-root <root> --output manifests/seer.vYYYYMMDD.json
```

The `manifests/` directory itself is git-ignored (`manifests/local/`). The
output is then reviewed, disclosure-checked, and **only the redacted /
aggregate-safe subset** is staged for commit under
`manifests/public/<filename>`. The full inspection JSON, which may include
WONDER query dates, stays on the local machine.