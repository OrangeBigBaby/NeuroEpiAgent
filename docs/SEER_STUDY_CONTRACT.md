# SEER Study Contract

This is the pre-registration contract that **must** be completed by the
SEER analyst before any clinical analysis is run. The SEER adapter
(`src/neurosurg_epi_agent/adapters/seer.py`) is metadata-only and exposes
no clinical-analysis capability; the contract is the explicit hand-off
between the metadata layer and a future analysis script that the
researcher writes and signs off on.

The contract is intentionally aligned with the SEER Research Data Use
Agreement (DUA) requirements and the STROBE / RECORD reporting checklist.
Filling it in is the analyst's responsibility; the agent does not fill
in any field automatically and does not generate any estimate from a
half-filled contract.

---

## A. Identification

- **Study title:**
- **Lead author / analyst:**
- **Date:**
- **SEER DUA holder (institution):**
- **SEER submission / release referenced** (e.g. "November 2024 Submission"):
- **SEER product type** (Research / Research Plus):
- **SEER registry set** (e.g. SEER 18 Regs):
- **SEER\*Stat version:**
- **Session type** (Frequency / Rate / Survival / Case Listing):
- **Export date:**
- **Export data dictionary URL / path:**

> The above fields map 1:1 to the user-supplied kwargs the
> `SEERAdapter.inspect(data_version=...)` accepts. Missing fields stay
> `needs_verification` in the inspection output and the analysis script
> refuses to run.

## B. Research question and estimand

- **Primary research question:**
- **Target population (e.g. patients diagnosed with primary CNS tumors,
  2018-2021, SEER 18 registries):**
- **Primary estimand** (e.g. 5-year cause-specific survival probability;
  hazard ratio for an exposure; standardized incidence ratio):
- **Time horizon:**
- **Secondary estimands:**

## C. Cohort definition

- **Inclusion criteria:**
- **Exclusion criteria:**
- **Inclusion / exclusion coded by which variables** (list every SEER
  variable that gates entry, e.g. `Site recode ICD-O-3/WHO 2008`,
  `Behavior code ICD-O-3`, `SEER Brain and CNS Recode`):
- **First primary vs. multiple primary rules** (cite the SEER multiple
  primary / histology coding rules in force for the export year):
- **Histology / behavior coding system** (ICD-O-3; cite the SEER ICD-O-3
  coding manual used for the export):
- **Diagnosis year range:**
- **Age range (and which recode is used):**
- **Sex / race / origin restrictions, if any:**

## D. Exposure(s) and outcome(s)

- **Primary exposure (definition + SEER variable):**
- **Secondary exposures:**
- **Primary outcome (definition + SEER variable):**
- **Secondary outcomes:**
- **Time-zero definition** (e.g. date of diagnosis):
- **Censoring rules** (last known alive; death; study end):
- **Loss-to-follow-up strategy** (right-censoring vs. exclusion):

## E. Covariates and missing data

- **Candidate covariates (list every SEER variable):**
- **Missing-data strategy** (complete-case vs. multiple imputation vs.
  indicator category):
- **Outlier / implausible-value handling:**

## F. Statistical analysis

- **Primary model** (e.g. Cox proportional hazards; competing-risks
  regression; logistic regression):
- **Time scale** (time-on-study; age; calendar time):
- **Effect measure** (hazard ratio; risk ratio; odds ratio; cumulative
  incidence):
- **Standard error / CI method:**
- **Model selection / variable screening procedure:**
- **Non-proportional hazards / time-varying effects handling (if any):**
- **Sensitivity analyses** (e.g. alternative cohort definition, alternative
  outcome definition, alternative multiple-primary rule, alternative
  missing-data strategy):
- **Subgroup analyses:**
- **Multiple-comparisons correction strategy:**

## G. Aggregate disclosure posture

- **Minimum cell size** for any published table / figure: **no fewer
  than 11 cases per cell** (a conservative interpretation of the SEER
  DUA; the analyst should confirm with the current DUA text).
- **Cells with n < 11:** the script MUST suppress the value and emit
  `<n<11 suppressed>` instead. The script MUST NOT emit a back-calculated
  value from totals.
- **Survival / incidence rates with denominator < 30 cases:** mark as
  `unstable / unreliable` and present only in supplementary tables.
- **Cohort / subgroup definitions that would produce a cell < 11:**
  collapsed or omitted, never back-calculated.
- **No individual case listing** in any artifact, supplementary
  material, or review response.

## H. Output contract (every figure / table)

For every manuscript figure and table, the script MUST emit:

- A machine-readable source file (CSV / JSON) that produced the figure.
- A SHA-256 of the source file recorded in the figure caption or a
  supplementary `provenance.json`.
- The exact SEER selection statement(s) that defined the cohort.
- The exact SEER session / submission / product type.
- An explicit statement of which estimand is reported.

## I. Sign-off

- **Analyst signature / date:**
- **Methods reviewer signature / date:**
- **DUA compliance officer signature / date (if required by institution):**

---

## How to use this contract

1. Copy this file to `docs/SEER_STUDY_CONTRACTS/<study>.md` and fill
   in every field.
2. Pass the user-supplied data-version fields to
   `SEERAdapter.inspect(data_version=...)` and capture the inspection
   JSON in `manifests/local/`.
3. Write the analysis script. The script MUST refuse to run if any
   required contract field is empty or if the inspection output is
   `needs_verification` for the data-version fields.
4. The script MUST apply the disclosure posture in section G before
   writing any table / figure.
5. Section H output contract fields are part of the figure / table
   itself, not an after-thought.

## Why this exists

- **Auditable.** A reviewer can read the contract, find the analysis
  script, and reproduce the table without reading the LLM at all.
- **Falsifiable.** Every published number traces to a script + a result
  file + a SHA-256.
- **DUA-compliant.** The contract makes the SEER DUA's restrictions
  (no participant-level data, no small cells, no case listings) part
  of the script, not a documented intention.