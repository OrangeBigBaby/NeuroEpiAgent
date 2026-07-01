# Analysis Implementation Principles

This document is the contract that any future case-study analysis script
in this repository must satisfy. It is derived from the project's
methodology contract (`docs/PROJECT_CHARTER.md`), the data-governance
boundary (`docs/DATA_GOVERNANCE.md`), and the SEER study contract
(`docs/SEER_STUDY_CONTRACT.md`). Following the principles below is what
makes a case study auditable to a reviewer who does not have access to
the underlying data.

These principles are enforced by:

1. The `.github/workflows/tests.yml` CI (no tracked file > 50 MB; no
   secrets in tracked tree; no tracked raw data).
2. The `tests/` suite, which exercises the disclosure guardrails of
   every adapter.
3. The `scripts/` and `case_studies/` directories, which show the
   approved patterns.

## 1. Numbered, independently runnable scripts

Every case-study analysis is split into numbered scripts that can each
be invoked on its own:

```text
case_studies/<study>/<NN>_<step>.py
```

`NN` is a two-digit zero-padded sequence number. Each script must
import only the public surface of `neurosurg_epi_agent`, accept its
inputs via CLI arguments or environment variables, and produce its
outputs into a directory passed via CLI (default under
`case_studies/<study>/results/`).

The pattern is intentionally close to the numbered R/Python scripts in
the parent project (`ClinicalDatabaseWorkflow/`'s `01_merge_clean` →
`07_shap_xgboost` template). The numbered, step-by-step layout means a
reviewer can re-run any one step in isolation and reproduce a single
intermediate artifact.

## 2. Data root from environment variables; never from absolute paths

Every script that touches a local data file must read its data root
from an environment variable, never from a hard-coded path:

| Source | Env var |
| --- | --- |
| SEER | `NEUROSURG_EPI_SEER_ROOT` |
| CDC WONDER | `NEUROSURG_EPI_CDC_WONDER_ROOT` |
| NHANES cache | `NEUROSURG_EPI_NHANES_CACHE` |
| Output | `NEUROSURG_EPI_RESULTS_ROOT` (default `case_studies/`) |

If a variable is not set, the script refuses to run with a clear
error — it never silently falls back to a system path. The
`.env.example` template lists every variable; `.env` (the local copy)
is git-ignored.

The `inspect_seer_exports.py` and `inspect-database` CLI commands emit
the `<user-supplied>` token in place of any absolute path; analysis
scripts must follow the same rule.

## 3. Streaming reads; never load a multi-GB file into RAM

SEER files can be 0.5 GB to >5 GB. NHANES XPT files are typically tens
of MB. Scripts must:

- Read SEER / large registry exports with streaming (`csv.reader`),
  Polars lazy scan (`pl.scan_csv`), PyArrow dataset, or DuckDB
  read-only mode. Pandas full-file loads are forbidden for SEER.
- Never produce a parquet / duckdb / feather artifact that contains
  one or more rows per tumor; the on-disk cache must remain
  aggregate-only.
- Never write to `/02_data_raw/` or `/03_data_processed/` from inside
  the script. The `.gitignore` excludes both; the script should use
  a clearly-labeled scratch directory instead (e.g.
  `case_studies/<study>/results/_scratch/`), and it must `.gitignore`
  its scratch directory locally.

## 4. Fixed random seeds

Any script that uses randomness (bootstrap resampling, multiple
imputation, simulation) must:

- Read its seed from the config (`random_state: 2026` in
  `config/variables/<db>_demo.yaml`) or accept `--seed` on the CLI.
- Emit the seed used into the run's `provenance.json`.
- Re-running the script with the same seed must produce a
  byte-identical `results.json` (modulo timestamp + commit SHA).

## 5. Provenance record

Every run writes a `provenance.json` containing:

- `case_study` (study name)
- `generated_at` (UTC ISO timestamp)
- `git_commit_sha` (the commit hash the script was run from; if the
  working tree is dirty, the script refuses and tells the user to
  commit first)
- `python_version` (from `sys.version`)
- `package_versions` (`neurosurg_epi_agent.__version__`,
  `pandas.__version__`, `polars.__version__` if used, etc.)
- `data_version` (every user-supplied data-version field, copied from
  `SEERAdapter.inspect(data_version=...)` or its equivalent for the
  other adapters; missing fields stay `needs_verification`)
- `source_files` (relative path; SHA-256 of each)
- `input_schema_fingerprint` (MD5 of the canonicalized header column
  list, as `SEERAdapter` computes it)
- `random_seed` (if randomness was used)
- `commands_invoked` (the exact command lines used, including
  `--seed`, `--output-dir`, etc.)

## 6. Input schema fingerprint

For SEER, the script must call `SEERAdapter` (or directly
`seer._schema_fingerprint(...)`) to compute the schema fingerprint of
each input file, and write the fingerprint into the provenance. This
proves that the script ran against the same schema that the inspection
recorded. A mismatch is a stop-ship error.

## 7. Software versions recorded

The script must record `python_version` and the versions of every
dependency it imports (pandas, numpy, polars, scipy, pyarrow, duckdb)
into the provenance. This makes the run a reproducible unit: a
reviewer can `pip install` the exact versions and re-run.

## 8. Original data is never overwritten

The script must:

- Refuse to write to `/02_data_raw/` (raw data is read-only).
- Refuse to overwrite an existing output file unless `--force` is
  passed explicitly.
- Use `tempfile.TemporaryDirectory()` for any intermediate buffers
  that contain more than aggregate counts.

## 9. Output goes to a clear, tracked-when-aggregate results directory

Aggregate, disclosure-checked outputs go to
`case_studies/<study>/results/`. This directory is **not** git-ignored
*only when* its contents pass the disclosure checks. The
`disclosure_check()` helper in
`src/neurosurg_epi_agent/case_studies/_disclosure.py` is the canonical
gate.

## 10. Aggregate-level cross-source comparison only

When comparing SEER to CDC WONDER (or any other source):

- Compare aggregate public totals only — never row-level linking.
- Note the case-selection difference (UCD vs MCD; SEER Behavior code
  ICD-O-3 vs ICD-10 cause-of-death codes).
- Frame the comparison as "triangulation of aggregate signals", not as
  individual-level inference.
- Use conservative language (`is associated with`, `suggests`, `may`).
  Do not use `proves`, `causes`, `confirms`, `first ever`, `comprehensive`,
  `unprecedented`.

## 11. Disclosure posture (specific rules)

### CDC WONDER

- Cells with `Deaths <= 9` MUST NOT appear in any table, figure, or
  result file.
- Cells with `Deaths < 20` MUST carry an `unstable / unreliable` flag
  in their row metadata, and the figure caption MUST explain the
  flag.
- UCD and MCD exports MUST NOT be combined in the same figure without
  a clear in-figure annotation that the case-selection basis differs.

### SEER

- Cells with fewer than 11 cases MUST be replaced by `<n<11 suppressed>`.
- No case row, no case listing, no SEER\*Stat matrix appears in any
  committed artifact.
- The user-supplied `SEER_STUDY_CONTRACT.md` MUST be filled in and
  referenced by the script before any clinical analysis is run.

### NHANES

- Aggregate outputs only.
- Confidence intervals based on simple / unweighted methods are
  forbidden; if complex-survey variance is implemented, it must
  reference the cycle design variables.

## 12. Skip on permission / data unavailability

If the user has not supplied a required data root, the script exits
with a non-zero status and a message pointing at the env var. It does
not silently fall back to a different source.

## 13. Tests must run without real data

The `tests/` suite must run on a fresh checkout without any local
data. Adapter tests use synthetic in-process fixtures. The CI
workflow (`.github/workflows/tests.yml`) confirms this: it does not
download or copy any real data.

## 14. Each script is one step in a numbered pipeline

A new case study is structured like this:

```text
case_studies/<study>/
  01_inspect.py        # run SEERAdapter.inspect + write provenance
  02_validate.py       # cross-check schema fingerprint vs study contract
  03_aggregate.py      # compute the disclosed aggregates
  04_disclosure.py     # apply <=9 / <20 / <11 rules
  05_render.py         # write the figure / table
  99_run_all.py        # orchestrate 01-05 end-to-end
  results/             # aggregate outputs (when disclosure-checked)
```

Each step is independently runnable. Step 99 is just glue.

## 15. The "do not claim" list

Case-study outputs MUST NOT include claims like:

- "The agent proves that …"
- "This is the first ever …"
- "These results are comprehensive."
- "Clinically, this means …" (without explicit methods-reviewer sign-off).

The conservative-language policy in `docs/MANUSCRIPT_PLAN.md` is
binding; the script's report.md writer must apply it.