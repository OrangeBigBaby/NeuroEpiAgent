# Final Report — Public Release

Date: 2026-07-01
Tags: `v0.2.0` (initial public baseline) and `v0.3.0` (with case studies)
Remote: https://github.com/OrangeBigBaby/NeuroEpiAgent

> **Correction notice (added for v0.3.1).** This report was written for the
> v0.3.0 acceptance and is preserved as a historical record — do not treat its
> CI-green status row as a live claim. v0.3.0's remote CI was in fact **red**
> on the tagged commit: the in-workflow secret scan self-triggered on its own
> grep expression, and the symlink-escape pytest tests ran (and failed) on CI
> runners even though they skip on hosts without OS symlink privilege. v0.3.1
> fixes both (see `CHANGELOG.md` and the v0.3.1 release notes). For the current
> CI status, see the live GitHub Actions tab and the most recent release; no
> release of this project should be described as CI-green unless the Actions
> run for its tagged commit is actually green.

> **Current release report:** v0.3.1 remediation and final verification are
> recorded in `docs/V0.3.1_ACCEPTANCE_REPORT.md`. This v0.3.0 report remains
> below as historical evidence and is not the current acceptance statement.

## 1. Acceptance summary

| Criterion | Result |
| --- | --- |
| `pytest` passes from a clean clone | ✅ 392 passed, 2 skipped (+50 vs baseline 342 / 2) |
| Working copy clean | ✅ no untracked / unstaged changes |
| No raw data, `.codex`, `.venv`, caches, logs, or absolute paths tracked | ✅ all 12 sensitive-path checks return 0 |
| Largest tracked file ≤ 50 MB | ✅ largest is 0.9 MB (literature PDF) |
| No API keys, tokens, secrets in tracked tree | ✅ only the policy documents describe the forbidden strings |
| CI runs cross-platform without data downloads | ✅ GitHub Actions matrix (Ubuntu + Windows × py3.10/3.11/3.12) |
| CDC WONDER disclosure posture verified | ✅ 22+12 = 34 tests; suppressed + unstable + UCD/MCD paths covered |
| SEER no-row / metadata-only posture verified | ✅ 23+8 = 31 tests; no synthetic row value ever appears in output |
| Manuscript claims trace to evidence | ✅ `manuscript/CLAIM_EVIDENCE_MATRIX.md` enumerates every claim with status |

## 2. Files modified / created

### Phase 0 — security baseline
- `.gitignore` (rewritten to cover `.codex/`, `.venv/`, all `.xpt`/`.dta`/`.parquet`/`.duckdb`/`.feather`, `02_data_raw/`, `03_data_processed/`, `data/cache/`, `manifests/local/`, `results/private/`, `eval_results.json`, `*.log`, `*.pid`).
- `.env.example` (template with placeholder roots).
- `docs/DATA_GOVERNANCE.md` (new — per-source public/private boundary).
- `docs/DATA_PROVENANCE.md` (new — what each source contributes to the public repo).
- `docs/REPOSITORY_RELEASE_CHECKLIST.md` (new — pre-release gate).

### Phase 3 — CDC WONDER hardening
- `src/neurosurg_epi_agent/adapters/cdc_wonder.py` — removed overclaim about aggregate privacy sensitivity; added WONDER Notes status propagation (Suppressed / Unreliable); added `database_family` UCD/MCD distinction; added per-file provenance for ICD-10 definition, Group By, standard population, rate basis, query date, dataset version; added disclosure summary (suppressed_row_count, unreliable_row_count, deaths_lt_20_row_count, notes_phrases); detect `.csv.csv` filename anomaly without rewriting; version bumped 0.1.0 → 0.3.0.
- `tests/test_cdc_wonder_adapter.py` — added 7 new synthetic-fixture tests in `TestDisclosureGuardrails`.

### Phase 4 — SEER metadata adapter
- `src/neurosurg_epi_agent/adapters/seer.py` (new) — streaming header reader; no case rows ever read; SHA-256 opt-in only; cross-file schema fingerprinting; filename site-range labeled but flagged as not-cohort-defining; data-version fields marked `needs_verification` when user doesn't supply them; clinical-analysis capability intentionally NOT exposed.
- `tests/test_seer_adapter.py` (new, 23 tests) — synthetic data only, full coverage of streaming / no-row / fingerprint / data-version / capability split / cross-file consistency / CLI.
- `scripts/inspect_seer_exports.py` (new) — one-file audit-friendly CLI.
- `config/variables/seer_demo.yaml` (new) — illustrative registry (all entries `status: planned`).
- `docs/SEER_DATA_DICTIONARY.md` (new) — public description of the local SEER tree (no row content).
- `docs/SEER_STUDY_CONTRACT.md` (new) — pre-registration template the analyst fills in before any clinical analysis.

### Phase 2 — CI + repo hygiene
- `.github/workflows/tests.yml` (new) — cross-platform pytest + secret-scan + size-check.
- `CITATION.cff` (new).
- `CONTRIBUTING.md`, `SECURITY.md` (updated to reference the data-governance boundary).

### Phase 5 + 7 — manuscript + benchmark
- `manuscript/RESEARCH_CONTRACTS.md` (new, draft) — three case-study contracts (NHANES already shipped, CDC WONDER and SEER awaiting user sign-off).
- `manuscript/CLAIM_EVIDENCE_MATRIX.md` (new) — every manuscript claim mapped to supported / needs evidence / inferred with file pointers.
- `benchmarks/tasks.v0.2.0-draft.yaml` (new) — 7 new tasks for CDC WONDER + SEER metadata; **does NOT modify** frozen v0.1.0.
- `benchmarks/BENCHMARK_CARD.md` (updated) — reflects both versions; v0.2.0 stays DRAFT.

### Phase 6 — analysis-implementation principles + synthetic case studies
- `docs/ANALYSIS_IMPLEMENTATION_PRINCIPLES.md` (new) — 15 numbered rules any future case-study script must satisfy (env-var data root, streaming reads, fixed seed, provenance, schema fingerprint, software versions, disclosure posture, conservative language).
- `src/neurosurg_epi_agent/case_studies/cdc_wonder_synthetic_demo.py` (new) — synthetic demonstration of the disclosure-checked aggregate workflow. `Deaths <= 9` cells dropped before any output; `Deaths < 20` flagged `Unreliable`; UCD vs MCD kept separate.
- `src/neurosurg_epi_agent/case_studies/seer_metadata_feasibility.py` (new) — synthetic 13-file SEER-shaped temp tree inspected by `SEERAdapter`. Outputs contain only file-level metadata (no row, no frequency, no unique value).
- `tests/test_cdc_wonder_synthetic_demo.py` (new, 12 tests).
- `tests/test_seer_metadata_feasibility.py` (new, 8 tests).
- `case_studies/README.md` (updated) — describes all three case studies.

### Phase 8 — release artifacts
- `pyproject.toml` — version bumped through 0.1.0 → 0.2.0 → 0.3.0 (current).
- `docs/CODE_AVAILABILITY.md` (updated) — cites v0.3.0 and the three case studies.
- `docs/DATA_AVAILABILITY.md` (new) — per-source statement for NHANES / CDC WONDER / SEER / CHARLS.
- Git tags `v0.2.0` and `v0.3.0` both pushed to `origin`.

### Phase 0 cleanup (post-acceptance)
- `docs/PHASE_A_COMPLETION_SUMMARY.md` — replaced one absolute path with a generic placeholder.
- `verify_tests.py` — derive `cwd` from `__file__` instead of hard-coded local path.

## 3. Test results

```
392 passed, 2 skipped in ~4 s
```

Breakdown of the +50 new tests vs the 342 baseline:

| File | Tests | Purpose |
| --- | --- | --- |
| `tests/test_cdc_wonder_adapter.py` | +7 | Disclosure guardrails: Suppressed recovery refusal, Unreliable marking, malformed footer, missing query params, UCD vs MCD distinction, double `.csv` filename, no-path-leak. |
| `tests/test_seer_adapter.py` | +23 | Header parsing (Chinese filename, very-wide header), schema fingerprint, no-data-row-in-output, no-path-leak, no-row-count, filename site-range label, SHA-256 opt-in + size cap, non-CSV skip, symlink escape, data-version verbatim/partial/missing, capability split, cross-file consistency (13 files), CLI. |
| `tests/test_cdc_wonder_synthetic_demo.py` | +12 | Disclosure thresholds, row annotation, run-end-to-end, no-suppressed-in-output, conservative-language, no-path-leak. |
| `tests/test_seer_metadata_feasibility.py` | +8 | Synthetic tree builder (13 files, identical fingerprint), no-row-in-output, partial data_version = needs_verification, capability split. |

## 4. Git history (public)

```
ca860ed  feat: add analysis-implementation standard and two synthetic case studies
ab96625  docs: add final acceptance report (v0.2.0)
e120581  chore: scrub remaining local-machine paths from committed files
e04f819  release: prepare v0.2.0 publication archive
fb9dbd1  docs: align manuscript plan, research contracts, and benchmark draft
3a87d7d  ci: add cross-platform test workflow
9789829  chore: establish reproducible project baseline
```

Tags `v0.2.0` and `v0.3.0` are both annotated and pushed to `origin`.

## 5. Remote URL

https://github.com/OrangeBigBaby/NeuroEpiAgent

Recommended follow-up: rename the GitHub repository to
`NeuroSurgEpiAgent` so the URL matches the product name and the
`CITATION.cff` `repository-code` field. Until then, the mapping is
documented in `README.md` and `CITATION.cff`.

## 6. Outstanding decisions the user must make

1. **Confirm the GitHub repository rename** to `NeuroSurgEpiAgent`.
2. **Sign off on the CDC WONDER case-study contract**
   (`manuscript/RESEARCH_CONTRACTS.md` § B) before any clinical output
   is generated from real CDC WONDER data.
3. **Fill in `docs/SEER_STUDY_CONTRACT.md`** with the SEER analyst's
   study specifics before any SEER clinical analysis is written.
4. **Two-expert adjudication** of the v0.2.0-draft benchmark tasks
   before any scientific claim about agent performance.
5. **Real SEER / CDC WONDER / NHANES versions** to cite in the
   manuscript — currently the inspection layer records
   `needs_verification` for every data-version field the user has
   not supplied.

## 7. What is paper-ready today

- **Architecture description.** The deterministic-gate / registry /
  manifest architecture is fully documented and tested.
- **Data-handling boundary.** Documented in three governance docs and
  enforced in code + CI.
- **Adapter inventory.** NHANES + CDC WONDER + SEER + CHARLS
  adapters are present and tested; capability status per adapter is
  documented in the README capability matrix.
- **Reproducibility.** From a clean clone, `pip install -e ".[dev]"`
  followed by `pytest` runs 392 tests without downloading any data.
- **Disclosure posture.** CDC WONDER suppressed cells and unstable
  rates are handled by code; SEER case rows are never read; absolute
  paths and secrets never appear in any tracked artifact.
- **Suggested manuscript paragraphs.** `docs/CODE_AVAILABILITY.md`
  and `docs/DATA_AVAILABILITY.md` provide ready-to-edit text.

## 8. What is NOT paper-ready today (and why)

- **No clinical-results case study** for SEER — the analyst has not
  signed off on `docs/SEER_STUDY_CONTRACT.md`.
- **No benchmark evaluation results** — the v0.1.0 benchmark is in
  draft; v0.2.0-draft adds 7 new tasks that need the same expert
  adjudication.
- **No real-data CDC WONDER figures** — the user has not signed off
  on `manuscript/RESEARCH_CONTRACTS.md` § B; the synthetic case study
  ships in the meantime as a workflow demonstration.
- **No claim that the agent outperforms an unconstrained LLM** — the
  benchmark is not yet gold-standard; no peer-reviewed comparison
  has been run.

These are explicitly flagged in `manuscript/CLAIM_EVIDENCE_MATRIX.md`
as `needs evidence`, and the manuscript plan forbids making the
claims until the evidence exists.
