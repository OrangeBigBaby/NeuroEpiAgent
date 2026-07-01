# Data Availability (suggested text)

> The text below is a suggested Data Availability statement for a
> manuscript that uses NeuroSurgEpiAgent. Edit the placeholders before
> submission.

## NHANES

The NHANES data are publicly available from the U.S. Centers for
Disease Control and Prevention (CDC) National Center for Health
Statistics (NCHS). Files were downloaded from
`https://wwwn.cdc.gov/nchs/nhanes/` using the `nhanesA` /
NHANES-XPT-download pattern. Cycle letters and variable codes are
documented in `config/variables/nhanes_demo.yaml`. No data-use
restrictions apply to NHANES public-release files.

## CDC WONDER

CDC WONDER queries produce aggregated public counts and rates under the
NCHS publication restrictions. The exported tables underlying the
manuscript's analyses are described in the
`CDCWonderAdapter.inspect()` output (schema + provenance, no cell
values). Researchers wishing to reproduce the same figures can re-run
the equivalent query at `https://wonder.cdc.gov/`; the queries are
version-stamped in the inspection JSON's `query_date` field. Aggregate
cell values with `Deaths <= 9` are suppressed by WONDER; this policy
is enforced by the adapter and propagated verbatim into any
disclosure-checked artifact.

## SEER

SEER research data are distributed under a SEER Research Data Use
Agreement (DUA) by the National Cancer Institute (NCI). Individual-level
SEER records are **not** publicly available and are **not**
redistributed by this repository. Researchers wishing to use SEER data
must apply for access via the SEER website
(`https://seer.cancer.gov/data/`) and obtain a DUA. The
`SEERAdapter` (`src/neurosurg_epi_agent/adapters/seer.py`) is
metadata-only and inspects an authorized local export directory
without reading case rows. The companion study contract
(`docs/SEER_STUDY_CONTRACT.md`) must be completed by the analyst
before any clinical analysis is performed. The data version fields
required for the contract (`release_submission`, `product_type`,
`registry_set`, `seerstat_version`, `session_type`, `export_date`,
`selection_statements`, `export_data_dictionary`) must be obtained
from the SEER\*Stat session that produced the export; they are not
recoverable from the CSV bytes alone.

## CHARLS

CHARLS (China Health and Retirement Longitudinal Study) data are
distributed under a separate DUA. The repository ships only the
adapter scaffold (`src/neurosurg_epi_agent/adapters/charls.py`); no
CHARLS data is included or redistributed.

## What this repository does NOT redistribute

- NHANES `.XPT` files (public; downloadable from CDC; not redistributed
  to keep the repository small).
- CDC WONDER export CSVs / XLS (public; produced by a query on
  wonder.cdc.gov; not redistributed to avoid leaking the user's
  query date / local notes).
- SEER `export_*.csv` files (DUA-restricted; **never** distributed).
- Any participant-level record, case listing, or aggregate cell with
  `Deaths <= 9`.
- Any absolute filesystem path, API token, or local-machine
  identifier.

The full policy is in `docs/DATA_GOVERNANCE.md`.