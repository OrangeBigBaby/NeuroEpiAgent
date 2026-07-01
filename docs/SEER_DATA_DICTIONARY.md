# SEER Data Dictionary — local-tree inventory

This document is the public companion to the **metadata-only** SEER
adapter. It records the schema fingerprint of the local SEER*Stat export
directory and explains, in plain language, what each column does — without
quoting any case row, frequency, or value distribution.

The adapter that produces this inventory is
`scripts/inspect_seer_exports.py`. The output it writes is a
`manifests/local/seer_inspection.json` file that is intentionally
git-ignored (`manifests/local/`) because it embeds the caller's data
root and SHA-256s of authorized files.

## What the local tree contains (anonymized)

| Filename (relative name only) | Byte size | Column count | Schema fingerprint |
| --- | --- | --- | --- |
| `export_C00-C09.csv` | 630,418,267 | 269 | (see inspection JSON) |
| `export_C10-C14.csv` | 131,544,595 | 269 | (see inspection JSON) |
| `export_C15-C26消化器官恶性肿瘤.csv` | 5,289,334,540 | 269 | (see inspection JSON) |
| `export_C30-C39呼吸和胸腔内器官恶性肿瘤.csv` | 3,906,891,646 | 269 | (see inspection JSON) |
| `export_C40-C49.csv` | 3,983,489,441 | 269 | (see inspection JSON) |
| `export_C50 乳腺癌.csv` | 4,060,834,458 | 269 | (see inspection JSON) |
| `export_C51-C53.csv` | 334,534,938 | 269 | (see inspection JSON) |
| `export_C54-C58.csv` | 1,325,517,736 | 269 | (see inspection JSON) |
| `export_C60-C63男性生殖器官恶性肿瘤.csv` | 4,109,931,178 | 269 | (see inspection JSON) |
| `export_C64-C68.csv` | 2,253,791,128 | 269 | (see inspection JSON) |
| `export_C69-C72.csv` | 480,978,014 | 269 | (see inspection JSON) |
| `export_C73-C75.csv` | 766,085,678 | 269 | (see inspection JSON) |
| `export_C76-C80.csv` | 1,473,880,976 | 269 | (see inspection JSON) |

> The byte sizes above are an inventory; the inspection JSON is the
> authoritative copy. The 13 files all share the same 269-column schema
> (verified by the adapter's cross-file schema fingerprint test).

## Schema (the 269 column names)

The SEER*Stat CNS export (and the related site-range exports) use a
shared schema. A representative slice of the column names, in the order
they appear in the header:

```
Age recode with <1 year olds and 90+
Sex
Year of diagnosis
PRCDA 2020
Race recode (W, B, AI, API)
Origin recode NHIA (Hispanic, Non-Hisp)
Race and origin recode (NHW, NHB, NHAIAN, NHAPI, Hispanic)
Site recode ICD-O-3/WHO 2008
Behavior code ICD-O-3
TNM 7/CS v0204+ Schema (thru 2017)
TNM 7/CS v0204+ Schema recode
AYA site recode 2020 Revision
Lymphoid neoplasm recode 2021 Revision
ICCC site recode 3rd edition/IARC 2017
SEER Brain and CNS Recode
Site recode ICD-O-3 2023 Revision
Site recode ICD-O-3 2023 Revision Expanded
CS Schema - AJCC 6th Edition
Primary Site - labeled
Primary Site
Histologic Type ICD-O-3
Behavior recode for analysis
...
```

> The remaining ~248 columns follow the same pattern (recodes, derived
> variables, survival / cause-of-death fields). The full column list is
> preserved verbatim in the inspection JSON. The adapter does not truncate
> or summarize the column list — every column name appears exactly as
> SEER*Stat wrote it.

## Site-range labels are not cohort definitions

`export_C69-C72.csv` (the CNS-relevant file in the local tree) has a
filename that embeds the **literal** ICD-O-3 site range `C69-C72`. The
adapter records this as a label, but the row contents are NOT constrained
to that range: SEER*Stat exports can contain rows whose `Site recode` is
outside the filename range (for example, unknown / NOS). **Cohort
selection must use the `Site recode ICD-O-3/WHO 2008` and the `SEER Brain
and CNS Recode` columns, not the filename.**

## What the adapter does NOT include

- **No case row.** The adapter reads the file header (a few KB) and
  nothing else by default. It does not count rows.
- **No frequency / value distribution.** No `value_counts`, no unique
  values, no histogram.
- **No participant identifier value.** No `Patient ID`, `SEER Registry
  ID`, or any other linking key.
- **No absolute path.** Every emitted artifact replaces the caller's
  data root with the literal token `<user-supplied>`.

## When SHA-256 is computed

By default the adapter does NOT stream the file. The 13 files in the
local tree total ~26.77 GB; streaming all of them is not needed for
metadata inspection. To opt in:

```powershell
python scripts/inspect_seer_exports.py `
    --data-root <local-seer-directory> `
    --output manifests/local/seer_inspection.json `
    --with-sha256 `
    --sha256-max-bytes 8589934592
```

If a file exceeds `--sha256-max-bytes`, the SHA-256 is recorded as empty
and a `sha256_note` field is added to the member provenance. The file
is never partially hashed.

## Required user-supplied data-version fields

These cannot be recovered from the CSV bytes. They must be supplied by
the researcher with the SEER*Stat session that produced the export:

- `release_submission` — e.g. "November 2024 Submission"
- `product_type` — "Research" or "Research Plus"
- `registry_set` — e.g. "SEER 18 Regs"
- `seerstat_version` — e.g. "8.4.4"
- `session_type` — e.g. "Frequency Session" or "Rate Session"
- `export_date` — the date the export was generated
- `selection_statements` — the SEER*Stat selection block (text)
- `export_data_dictionary` — pointer to the data-dictionary URL or path

If any of these is missing, the adapter records it as
`needs_verification` rather than guessing. See
`docs/SEER_STUDY_CONTRACT.md` for the field-level study contract that
must be completed before any clinical analysis is written.