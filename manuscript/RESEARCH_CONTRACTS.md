# Manuscript Research Contracts (draft, awaiting user sign-off)

This document records the **three case-study contracts** that the methods
paper would draw on. Each contract is intentionally narrow and
pre-registered so the manuscript's claims trace to a script + a result
file rather than to a free-form LLM draft. Per the Phase 5 instructions,
this file is a **draft**. The user must confirm each contract before any
clinical conclusion is generated.

> **Status: awaiting user sign-off.** Nothing in this file is a
> committed clinical result. The agent's role is to lay the framework,
> surface the choices, and wait for confirmation.

---

## Case study A — NHANES stroke prevalence (already exists)

This case study is already implemented in
`case_studies/nhanes_stroke_2017_2018/`. The contract is:

- **Research question.** Self-reported stroke prevalence in adults
  (NHANES 2017-2018).
- **Population.** Adults aged ≥18 with `MCQ160F` non-missing.
- **Exposure.** None (descriptive).
- **Outcome.** `MCQ160F == 1` (self-reported stroke).
- **Survey design.** `SDMVPSU` / `SDMVSTRA` / `WTMEC2YR` (single cycle;
  no rescaling).
- **Output.** Aggregate weighted prevalence with caveats that complex
  survey variance is not implemented in the lightweight case study.

The published artifact is `results.json` + `provenance.json` +
`report.md`. This case study ships in this repository and is the only
publication-ready evidence at the time of writing.

## Case study B — CDC WONDER neurology mortality trends (draft)

> **Status: awaiting sign-off.** No analytical output has been produced.
> The framework below describes what an analyst would do, not what has
> been done.

- **Research question.** Are age-adjusted U.S. mortality rates for
  selected neurologic disease categories (cerebrovascular diseases
  [I60-I69], intracranial injury [S06], malignant CNS neoplasms
  [C70-C72]) changing year-over-year?
- **Population.** U.S. residents (deaths from the WONDER Underlying
  Cause of Death database).
- **Exposure.** Calendar year (group-by).
- **Outcome.** Age-adjusted mortality rate (WONDER-supplied; carries
  `Deaths <= 9` suppression and `Deaths < 20` instability flag).
- **Disclosure posture.** The script refuses to emit any cell with
  `Deaths <= 9`. Any cell with `Deaths < 20` is presented only in
  supplementary material, with the `unstable / unreliable` flag carried
  forward. UCD vs MCD exports are never mixed in the same figure.
- **Output.** Disclosure-checked trend figures (line plots, age-adjusted
  rate with confidence interval, year on x-axis). Each figure has a
  matching JSON with SHA-256.

## Case study C — SEER CNS registry metadata / feasibility (draft)

> **Status: awaiting sign-off and DUA.** The SEER adapter currently
> emits only metadata; the contract below describes what an analyst
> would do after the user fills in `docs/SEER_STUDY_CONTRACT.md`.

- **Research question (metadata / feasibility only).** What is the
  cohort composition of `export_C69-C72.csv` as it stands today,
  expressed as a row count per `Year of diagnosis`, per `Behavior code
  ICD-O-3`, and per `SEER Brain and CNS Recode`?
- **Population.** Every row in the file (one row per tumor record).
- **Exposure / outcome.** None (feasibility / cohort description).
- **Disclosure posture.** Cell counts are subject to the SEER DUA
  minimum cell size (see `docs/SEER_STUDY_CONTRACT.md` § G). Counts < 11
  are suppressed and shown as `<n<11 suppressed>` in every table.
- **Output.** A feasibility table (`results/seer_c69_c72_feasibility.csv`)
  with row counts, plus the inspection JSON written by
  `scripts/inspect_seer_exports.py`. No individual case row, no
  identifier, no frequency of any other variable.

### Why a metadata/feasibility case study, not a clinical-results one

- SEER is a registry under a DUA. Individual-level redistribution is
  forbidden.
- A clinical-results case study needs the SEER analyst to fill in
  `docs/SEER_STUDY_CONTRACT.md`. The user has not done that yet.
- A metadata/feasibility case study is publication-ready *now*: it
  demonstrates the SEER adapter's behavior on a real file, with no
  record-level disclosure risk.

---

## What the manuscript can claim once each contract is signed off

| Claim | Evidence | Status |
| --- | --- | --- |
| The agent's CDC WONDER adapter inspects an export without reading a single death count into output. | `tests/test_cdc_wonder_adapter.py` (sentinel cell value never appears); `CDCWonderAdapter.inspect()` source. | supported |
| The agent's SEER adapter inspects a SEER\*Stat export without reading a case row. | `tests/test_seer_adapter.py` (synthetic row content never appears); `SEERAdapter.inspect()` source. | supported |
| The agent ships disclosure-checked aggregate outputs from CDC WONDER. | `tests/test_cdc_wonder_adapter.py` (`TestDisclosureGuardrails`). | supported (code), needs evidence (real-world runs) |
| The agent improves on an unconstrained LLM baseline on a blinded benchmark. | `benchmarks/GOLD_STANDARD_PROCESS.md` (expert adjudication). | needs evidence |
| The agent is clinically effective at neurosurgical epidemiology. | (not a claim we make). | out of scope |

Every claim in the manuscript must be traceable to one of these rows
(or be marked `needs evidence` and queued for future work).