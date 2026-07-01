# Claim–Evidence Matrix

Every manuscript claim must trace to one of three evidence states:

- `supported` — backed by code + tests + a result file in this repo, or
  by an external citation the manuscript names.
- `needs evidence` — plausible but not yet backed; queued for future
  work and explicitly flagged as such in the manuscript.
- `inferred` — a derived statement that follows from a `supported` claim
  by a documented rule (e.g. an aggregation, an implication).

This file is updated every time a new claim is added or an evidence
state changes.

## Claims in the methods/tooling paper

### Architecture / safety claims

| # | Claim | State | Evidence |
| --- | --- | --- | --- |
| C1 | The router refuses / flags infeasible tasks rather than fabricating a mapping. | supported | `src/neurosurg_epi_agent/router.py`; `tests/test_router.py` |
| C2 | Causal overstatement (`proves`, `causes`, `first ever`, …) is blocked by guardrails. | supported | `src/neurosurg_epi_agent/guardrails.py`; `tests/test_guardrails.py` |
| C3 | NHANES survey-design rules (SDMVPSU / SDMVSTRA, multi-cycle weight rescaling, fasting-subsample mismatch) are enforced deterministically. | supported | `src/neurosurg_epi_agent/guardrails.py`; `tests/test_guardrails.py` |
| C4 | Variable names enter the engine only through the versioned YAML registry; status tags (`verified` / `illustrative` / `needs review`) are hard-validated. | supported | `src/neurosurg_epi_agent/registry.py`; `config/variables/nhanes_demo.yaml`; `tests/test_registry.py` |
| C5 | The reproducibility manifest records findings and provenance, never estimates. | supported | `src/neurosurg_epi_agent/manifest.py`; `tests/test_manifest.py` |

### Data-handling claims

| # | Claim | State | Evidence |
| --- | --- | --- | --- |
| D1 | The CDC WONDER adapter inspects an export and emits only schema + provenance (no cell value). | supported | `src/neurosurg_epi_agent/adapters/cdc_wonder.py`; `tests/test_cdc_wonder_adapter.py` (sentinel cell value never appears) |
| D2 | The CDC WONDER adapter does not attempt to recover a Suppressed count and propagates WONDER's Notes status verbatim. | supported | `tests/test_cdc_wonder_adapter.py::TestDisclosureGuardrails` |
| D3 | The CDC WONDER adapter distinguishes UCD vs MCD exports in `provenance.database_family`. | supported | `tests/test_cdc_wonder_adapter.py::test_ucd_vs_mcd_distinction_preserved` |
| D4 | The SEER adapter inspects a SEER\*Stat export and emits only header + schema + (optional) SHA-256 — no row content. | supported | `src/neurosurg_epi_agent/adapters/seer.py`; `tests/test_seer_adapter.py` (synthetic row content never appears) |
| D5 | The SEER adapter's `clinical-analysis` capability is intentionally NOT exposed; metadata-inspection is implemented. | supported | `SEERAdapter.identity.capabilities`; `tests/test_seer_adapter.py::TestCapabilitySplit` |
| D6 | The SEER adapter marks every data-version field the researcher did not supply as `needs_verification` rather than guessing. | supported | `tests/test_seer_adapter.py::TestDataVersion` |
| D7 | The repository's `.gitignore` excludes raw data, `.codex/`, `.venv/`, generated logs, and SEER CSVs in any path. | supported | `.gitignore`; CI secret-scan + size-check jobs |
| D8 | The repository's CI never downloads NHANES / SEER / CDC WONDER raw data. | supported | `.github/workflows/tests.yml` (only `pip install -e ".[dev]"` + `pytest`) |
| D9 | The CDC WONDER adapter enforces the numeric disclosure rule independently of the Notes cell: `Deaths` 0-9 are flagged as suppression violations, 10-19 as unreliable, and non-numeric Deaths cells are never coerced to 0. | supported | `tests/test_cdc_wonder_adapter.py::TestIndependentNumericDisclosure` |
| D10 | The SEER adapter honors `members` filtering, treats `max_member_bytes` as an inspection cap distinct from `sha256_max_bytes`, reports the filename (not `.`) for single-file input, isolates unknown `data_version` keys, and emits an explicit `schema_consistent` flag. | supported | `tests/test_seer_adapter.py` (`TestMembersFilter`, `TestMaxMemberBytesInspectionCap`, `TestSingleFileInput`, `TestDataVersionValidation`, `TestSchemaConsistencyFlag`) |

### Benchmark / evaluation claims

| # | Claim | State | Evidence |
| --- | --- | --- | --- |
| B1 | The benchmark currently consists of 30 tasks across 9 clinical domains. | supported | `benchmarks/tasks.v0.1.0.yaml`; `benchmarks/BENCHMARK_CARD.md` |
| B2 | The benchmark is in draft and cannot support scientific publication claims about agent performance. | supported | `benchmarks/BENCHMARK_CARD.md` § Critical Limitations; `docs/PROJECT_CHARTER.md` Scope Boundaries |
| B3 | The agent outperforms an unconstrained LLM baseline on the benchmark. | needs evidence | Awaiting two-expert adjudication per `benchmarks/GOLD_STANDARD_PROCESS.md` |
| B4 | Routing accuracy is independently validated. | needs evidence | Awaiting independent reviewer run per `benchmarks/GOLD_STANDARD_PROCESS.md` |
| B5 | The benchmark is a gold standard. | needs evidence | Expert countersignature not yet complete |

### Case-study claims

| # | Claim | State | Evidence |
| --- | --- | --- | --- |
| K1 | The NHANES 2017-2018 stroke prevalence case study reports a descriptive weighted estimate (an applied-survey-weighted prevalence). It is NOT a causal estimate, a diagnostic measure, or clinical decision support, and complex-sampling variance is not implemented in this case study. | supported | `case_studies/nhanes_stroke_2017_2018/results.json`; explicit limitations in `provenance.json` |
| K2 | The CDC WONDER synthetic-data case study demonstrates the disclosure-checked aggregate workflow: `Deaths <= 9` cells are dropped; `Deaths < 20` cells are flagged `Unreliable`; UCD vs MCD are not combined. | supported | `case_studies/cdc_wonder_synthetic_demo/` (synthetic only); `tests/test_cdc_wonder_synthetic_demo.py` |
| K3 | The SEER metadata/feasibility case study inspects a synthetic SEER-shaped tree and emits only file-level metadata (no row, no frequency, no unique value). | supported | `case_studies/seer_metadata_feasibility/`; `tests/test_seer_metadata_feasibility.py` |
| K4 | The CDC WONDER neurology-mortality-trends clinical case study (with real CDC WONDER data) produces disclosure-checked outputs. | needs evidence | Awaiting user sign-off of `manuscript/RESEARCH_CONTRACTS.md` § B and analyst run |
| K5 | The SEER CNS feasibility case study on the user's real SEER\*Stat export enumerates row counts per year / behavior / SEER Brain and CNS Recode without ever emitting a case row. | needs evidence | Awaiting user sign-off of `manuscript/RESEARCH_CONTRACTS.md` § C and analyst run |
| K6 | The published article cites a software release with a tagged version, a commit SHA, and a dependency lock. | needs evidence | Requires finalizing the v0.2.0 release per `docs/REPOSITORY_RELEASE_CHECKLIST.md` |

### Out-of-scope claims (must NOT be made)

- The agent is "clinically validated".
- The agent "proves" anything.
- The agent is "comprehensive" or "unprecedented" — language explicitly
  blocked by the conservative-language policy in `docs/MANUSCRIPT_PLAN.md`.

## Update procedure

When you add a new manuscript claim:

1. Pick the right section.
2. Add a row. State = `supported` / `needs evidence` / `inferred`.
3. Cite the file(s) the claim traces to.
4. If `supported`, the cited file(s) must exist in the repository at
   the time of submission.
5. If `needs evidence`, the manuscript text must say so explicitly.
6. If `inferred`, write the documented rule that derives the claim
   from a `supported` claim.