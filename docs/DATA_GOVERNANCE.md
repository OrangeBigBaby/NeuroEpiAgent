# Data Governance

This document defines how NeuroSurgEpiAgent handles data sources, who owns
decisions about each source, and what is and is not allowed in the public
repository.

## Scope

NeuroSurgEpiAgent supports three public-database sources (NHANES, CDC WONDER,
SEER) plus a non-public CHARLS adapter scaffolded for future use. The
governance rules below apply to all four; they are not database-specific.

## Guiding principles

1. **The repository is metadata-first.** No participant row, individual cell
   value, case listing, or extracted microdata file may be committed to the
   repository under any branch or tag.
2. **Aggregates must clear the source's own disclosure rules.** Each source
   defines its own minimum-cell-size or suppression policy. The repository
   re-enforces the policy in code at the boundary between an adapter and
   any artifact that could be published.
3. **Paths, tokens, and machine identity are stripped at the adapter
   boundary.** Absolute filesystem paths, API keys, usernames, and the local
   working directory are never written into metadata outputs, manifests, or
   documentation.
4. **What the public repo never sees.** Local raw data directories
   (`/02_data_raw/`, `/03_data_processed/`, `data/cache/`, `SEERdatabase/`),
   `.codex/`, `.venv/`, generated logs, PIDs, and intermediate `.duckdb` /
   `.parquet` artifacts are excluded by `.gitignore` and never staged for
   commit. Belt-and-suspenders filename rules (`*.XPT`, `*.xpt`, `*.dta`,
   `*.sas7bdat`, `*.parquet`, `*.duckdb`, `*.feather`, `export_C*.csv`)
   protect against accidental drag-and-drop.
5. **Git LFS is not a workaround.** Raw data must not be uploaded as an LFS
   object. The data-use agreements for SEER and CDC WONDER-derived files
   forbid redistribution, and LFS does not change that.

## Per-source responsibilities

### NHANES

- **Access model.** Public. NHANES `.XPT` files may be downloaded by anyone.
- **Repository role.** The repo ships a `case_studies/nhanes_stroke_2017_2018`
  driver that downloads two public files into `data/cache/` and emits
  aggregate-only outputs (`results.json`, `provenance.json`, `report.md`).
- **Allowed public artifacts.** Aggregate outputs, manifest records, and
  variable-registry entries.
- **Excluded.** `.XPT` files (excluded by `.gitignore`), and any output
  containing record-level values.

### CDC WONDER

- **Access model.** Public. CDC WONDER exports aggregated public counts and
  rates; participant-level records are never distributed through WONDER.
- **Repository role.** The `CDCWonderAdapter` reads WONDER's exported CSV /
  XLS into schema + provenance only. Aggregate cell values are left to
  downstream loaders.
- **Disclosure rules re-enforced in code.**
  - Cells with `Deaths <= 9` are suppressed by WONDER; the adapter
    propagates `Notes` / `Suppressed` / `Unreliable` status fields
    verbatim and never tries to recover a suppressed count.
  - Cells with `Deaths < 20` are flagged `unstable / unreliable` by WONDER
    and must carry that flag in any published artifact.
  - Underlying Cause of Death (UCD) and Multiple Cause of Death (MCD)
    exports are **not** head-to-head comparable; `provenance.database_family`
    makes the distinction explicit.
- **Allowed public artifacts.** Schema, provenance (dataset, ICD-10
  selection, group-by, standard population, rate basis, query date),
  SHA-256 of the export file, query parameter templates, data dictionaries,
  and aggregated results that have been disclosure-checked.
- **Excluded.** The original `.csv` / `.xls` files themselves, even though
  they are public, because they embed WONDER query dates / user notes and
  local paths may leak via CI runners.

### SEER

- **Access model.** Restricted. SEER research data are distributed under a
  SEER Research Data Use Agreement (DUA). Individual-level records are not
  publicly available.
- **Repository role.** The `SEERAdapter` is metadata-only and emits no
  record-level output. Its capabilities are explicitly split into
  `metadata-inspection` (implemented, supported) and `clinical-analysis`
  (planned, not yet supported).
- **Allowed public artifacts.** File-by-file schema fingerprint,
  byte size, SHA-256 of the export file, header column list, the
  `SEER_DATA_DICTIONARY.md`, and the `SEER_STUDY_CONTRACT.md` that must be
  filled in by a researcher before any clinical analysis is written.
- **Excluded.** Every `export_C*.csv` (and any other SEER*Stat export
  shape) is excluded by `.gitignore`. Case listings, SEER*Stat matrices,
  and any analytic dataset that contains one or more records per tumor
  are excluded. Local SEERdirectory layout and file names are excluded
  from any committed artifact.

### CHARLS (scaffolded, not active)

- **Access model.** Restricted. CHARLS requires a separate DUA.
- **Repository role.** Adapter code exists for the planning layer's
  future use but is not exercised by any public case study.

## What can never appear in a commit

| Category | Examples | Why |
| --- | --- | --- |
| Raw microdata | `.XPT`, `.xpt`, `.dta`, `.sas7bdat`, `export_C*.csv` | Source DUA forbids redistribution. |
| Suppressed counts | CDC WONDER `Deaths <= 9` cells | WONDER-suppression policy. |
| Reconstructed IDs | any cross-source row linkage | Individual-level inference is out of scope. |
| Absolute paths | `E:\Nhance\...`, `C:\Users\...`, `/Users/...` | Local-machine leakage. |
| API tokens | `api_key`, `apikey`, `token`, `Bearer`, `password` | Secret leakage. |
| Codex artifacts | `/codex/`, `.codex/` | Local-session internals. |
| Environment files | `.env`, `.env.local`, `.env.*` (except `.env.example`) | May contain tokens or local paths. |

## Reviewer checklist (every commit)

1. `git diff --cached --name-only` contains none of the excluded paths or
   filename globs above.
2. No individual file larger than 50 MB.
3. No file larger than 5 MB unless it is a tracked binary fixture or a
   documentation image committed intentionally.
4. The .gitignore covers every directory or filename pattern that the local
   working tree has but the public repo must not.

This document is owned by the project maintainers. Changes to the data
governance rules are themselves a release-blocker — they require a version
bump in `pyproject.toml` and a corresponding entry in
`docs/REPOSITORY_RELEASE_CHECKLIST.md`.