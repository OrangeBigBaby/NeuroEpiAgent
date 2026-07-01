# Final Report — Public Release Preparation

Date: 2026-07-01
Tag: `v0.2.0`
Remote: https://github.com/OrangeBigBaby/NeuroEpiAgent

## 1. Acceptance summary

| Criterion | Result |
| --- | --- |
| `pytest` passes from a clean clone | ✅ 372 passed, 2 skipped (+30 vs baseline 342 / 2) |
| Working copy clean | ✅ no untracked / unstaged changes |
| No raw data, `.codex`, `.venv`, caches, logs, or absolute paths tracked | ✅ all 12 sensitive-path checks return 0 |
| Largest tracked file ≤ 50 MB | ✅ largest is 0.9 MB (literature PDF) |
| No API keys, tokens, secrets in tracked tree | ✅ only the policy documents describe the forbidden strings |
| CI runs cross-platform without data downloads | ✅ GitHub Actions matrix (Ubuntu + Windows × py3.10/3.11/3.12) |
| CDC WONDER disclosure posture verified | ✅ 22 tests; suppressed + unstable + UCD/MCD paths covered |
| SEER no-row / metadata-only posture verified | ✅ 23 tests; no synthetic row value ever appears in output |
| Manuscript claims trace to evidence | ✅ `manuscript/CLAIM_EVIDENCE_MATRIX.md` enumerates every claim with status |

## 2. Files modified / created

### Phase 0 — security baseline
- `.gitignore` (rewritten to cover `.codex/`, `.venv/`, all `.xpt`/`.dta`/`.parquet`/`.duckdb`/`.feather`, `02_data_raw/`, `03_data_processed/`, `data/cache/`, `manifests/local/`, `results/private/`, `eval_results.json`, `*.log`, `*.pid`).
- `.env.example` (template with placeholder roots).
- `docs/DATA_GOVERNANCE.md` (new — per-source public/private boundary).
- `docs/DATA_PROVENANCE.md` (new — what each source contributes to the public repo).
- `docs/REPOSITORY_RELEASE_CHECKLIST.md` (new — pre-release gate).

### Phase 3 — CDC WONDER hardening
- `src/neurosurg_epi_agent/adapters/cdc_wonder.py` — removed overclaim about aggregate privacy sensitivity; added WONDER Notes status propagation (Suppressed / Unreliable); added `database_family` UCD/MCD distinction; added per-file provenance for ICD-10 definition, Group By, standard population, rate basis, query date, dataset version; added disclosure summary (suppressed_row_count, unreliable_row_count, deaths_lt_20_row_count, notes_phrases); detect `.csv.csv` filename anomaly without rewriting; version bumped 0.1.0 → 0.2.0.
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

### Phase 8 — release artifacts
- `pyproject.toml` — version 0.1.0 → 0.2.0.
- `docs/CODE_AVAILABILITY.md` (new) — suggested manuscript paragraph.
- `docs/DATA_AVAILABILITY.md` (new) — per-source statement for NHANES / CDC WONDER / SEER / CHARLS.
- Git tag `v0.2.0` pushed to `origin`.

### Phase 0 cleanup (post-acceptance)
- `docs/PHASE_A_COMPLETION_SUMMARY.md` — replaced one absolute path with a generic placeholder.
- `verify_tests.py` — derive `cwd` from `__file__` instead of hard-coded local path.

## 3. Test results

```
372 passed, 2 skipped in ~4 s
```

Breakdown of the +30 new tests vs the 342 baseline:

| File | Tests | Purpose |
| --- | --- | --- |
| `tests/test_cdc_wonder_adapter.py` | +7 | Disclosure guardrails: Suppressed recovery refusal, Unreliable marking, malformed footer, missing query params, UCD vs MCD distinction, double `.csv` filename, no-path-leak. |
| `tests/test_seer_adapter.py` | +23 | Header parsing (Chinese filename, very-wide header), schema fingerprint, no-data-row-in-output, no-path-leak, no-row-count, filename site-range label, SHA-256 opt-in + size cap, non-CSV skip, symlink escape, data-version verbatim/partial/missing, capability split, cross-file consistency (13 files), CLI. |

## 4. Git history (public)

```
e120581  chore: scrub remaining local-machine paths from committed files
e04f819  release: prepare v0.2.0 publication archive
fb9dbd1  docs: align manuscript plan, research contracts, and benchmark draft
3a87d7d  ci: add cross-platform test workflow
9789829  chore: establish reproducible project baseline
```

Tag `v0.2.0` is annotated and pushed to `origin`.

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
   is generated.
3. **Fill in `docs/SEER_STUDY_CONTRACT.md`** with the SEER analyst's
   study specifics before any SEER clinical analysis is written. The
   metadata-only feasibility case study (Section C of `RESEARCH_CONTRACTS.md`)
   can be run now without that fill-in.
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
  followed by `pytest` runs 372 tests without downloading any data.
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
- **No clinical-results CDC WONDER figures** — the user has not
  signed off on `manuscript/RESEARCH_CONTRACTS.md` § B.
- **No claim that the agent outperforms an unconstrained LLM** — the
  benchmark is not yet gold-standard; no peer-reviewed comparison
  has been run.

These are explicitly flagged in `manuscript/CLAIM_EVIDENCE_MATRIX.md`
as `needs evidence`, and the manuscript plan forbids making the
claims until the evidence exists.