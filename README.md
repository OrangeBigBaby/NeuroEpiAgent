# NeuroSurgEpiAgent

A reproducible, publication-oriented planning and validation layer for
**neurosurgical epidemiology** using public clinical databases. **NHANES-first
MVP with Phase 2 offline evaluation capabilities.**

The agent turns a clinical question into a validated, auditable analysis plan —
mapping exposures/outcomes to real database variables, enforcing NHANES
survey-design rules deterministically, and emitting a reproducibility manifest.
It is a **planner and explainer**, never the source of truth for variable names
or statistical validity.

> **Repository slug.** The GitHub repository name is `NeuroEpiAgent` for
> historical reasons; the product, Python package, and manuscript all use
> **NeuroSurgEpiAgent**. We recommend renaming the GitHub repository to
> `NeuroSurgEpiAgent` so the URL matches the rest of the artifact; until
> then, the mapping is documented here and in `CITATION.cff`.

> Status: v0.2 deterministic gate implemented - router with conservative refusal,
> Arm A pre-planner feasibility check, minimal plans for infeasible questions, and
> Arm B token reuse. v0.1 baseline preserved in `experiments/pilot_glm47_dev/`.
> See [v0.2 Implementation](#v02-deterministic-gate-implementation).

## Capability matrix

| Capability | NHANES | CDC WONDER | SEER | CHARLS |
| --- | --- | --- | --- | --- |
| **Deterministic routing** | supported | n/a (public aggregate) | planned / infeasible | planned / infeasible |
| **Planning adapter** | implemented / supported | implemented / supported | planned / not supported | planned / not supported |
| **Metadata inspection** | implemented / supported | implemented / supported | implemented / supported | implemented / supported |
| **Clinical analysis execution** | light case study only | not in this repo | not implemented (contract only) | not in this repo |
| **Publication-ready evidence** | descriptive case study | aggregate + disclosure-checked only | none (study contract required) | none |

"Metadata inspection" means a metadata-only JSON describing the local
files (sizes, hashes, schema fingerprints, query parameters). It never
emits a participant row, a value frequency, or a cell value from the
underlying file.

## What is *not* public in this repository

- Local raw data directories (`/02_data_raw/`, `/03_data_processed/`,
  `data/cache/`, `SEERdatabase/`).
- `.codex/` session caches and `.venv/` Python environments.
- Generated logs, PIDs, and intermediate `.duckdb` / `.parquet` artifacts.
- SEER case listings, SEER\*Stat matrices, and any analytic dataset that
  contains one or more records per tumor.
- API keys, tokens, passwords, or absolute filesystem paths.

See `docs/DATA_GOVERNANCE.md` for the full policy and the rationale for
each exclusion.

---

## Why this exists

LLM agents can draft an epidemiology plan in seconds — and silently invent a
NHANES variable code, misuse a fasting-subsample weight, or claim a cross-sectional
survey "proves" a causal effect. NeuroSurgEpiAgent removes those failure modes
by construction:

- **Evidence-backed variable mapping** — a versioned YAML registry with an
  explicit per-variable `status` (`verified` / `illustrative` / `needs review`).
  Only `verified` is ground truth.
- **Deterministic statistical guardrails** — rules (not heuristics) for NHANES
  `SDMVPSU`/`SDMVSTRA` design, multi-cycle weight rescaling
  (`WTMEC2YR / N`), and fasting-subsample (`WTSAF2YR`) weight matching.
- **Causal-language policy** — `proves`/`causes`/`first ever` etc. are blocked
  on any draft claim, with the conservative rewrite surfaced.
- **Reproducibility manifest** — every plan writes a YAML record of which rules
  fired and which variables were used, with provenance. It records *findings*,
  not *results* — there are no numbers to fabricate.
- **Adapter-ready architecture** — CHARLS / GBD / SEER are scaffolded as
  `planned`; the MVP routes to them as infeasible until their adapter ships.

## Non-goals

- **Not** a four-database product. MVP is NHANES-only; other databases are
  future adapters, not active sources.
- **Not** an execution engine. It does not run regressions, fit models, or
  touch raw NHANES data. It produces plans a human (and downstream R/Python
  templates) can execute.
- **Not** a source of clinical truth. Variable codes and citations must be
  confirmed against codebooks and primary literature by a human.
- **Not** a substitute for expert epidemiological review.

## Quickstart

```powershell
# from the NeuroSurgEpiAgent folder
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# route a question to a database
neurosurg-epi route --question "Is self-reported stroke associated with metabolic syndrome, NHANES 2011-2018?"

# validate a plan against the guardrails (see tests/ for plan shape)
neurosurg-epi validate-plan --plan my_plan.yaml --db config/databases.yaml --variables config/variables/nhanes_demo.yaml

# emit a reproducibility manifest
neurosurg-epi manifest --plan my_plan.yaml --db config/databases.yaml --variables config/variables/nhanes_demo.yaml --out run/manifest.yaml

# Phase 2: generate a plan using a planner provider
neurosurg-epi plan --provider replay --task-id stroke_01 --fixtures benchmarks/fixtures --output plan.yaml
neurosurg-epi plan --provider claude --question "Stroke and smoking" --prompt config/prompts/planner_v1.txt --registry config/variables/nhanes_demo.yaml --max-budget-usd 0.50 --output plan.yaml

# Phase 2: run live pilot experiment with checkpointing
neurosurg-epi run-pilot --tasks benchmarks/tasks.v0.1.0.yaml --registry config/variables/nhanes_demo.yaml --output pilot_results.json --dry-run
neurosurg-epi run-pilot --tasks benchmarks/tasks.v0.1.0.yaml --registry config/variables/nhanes_demo.yaml --output pilot_results.json --confirm-live --max-tasks 5

# Phase 2: efficiency telemetry options (all optional, publication-oriented)
# Record declared backend provenance (descriptive only, not auth):
neurosurg-epi run-pilot --tasks benchmarks/tasks.example.yaml --registry config/variables/nhanes_demo.yaml --output results.json --dry-run --backend-label "glm-5.2 via CC-Switch"
# Supply explicit per-million-token prices to populate estimated_cost_usd.
# NOTE: the numeric rates below are ILLUSTRATIVE EXAMPLES only, NOT current or
# verified GLM (or any vendor) pricing. They are placeholders for the rates YOU
# intend to use; always substitute real rates before trusting estimated_cost_usd.
neurosurg-epi run-pilot --tasks benchmarks/tasks.example.yaml --registry config/variables/nhanes_demo.yaml --output results.json --confirm-live --price-input 3.0 --price-output 15.0 --price-cache-read 0.3 --price-cache-creation 3.75  # <-- rates are ILLUSTRATIVE placeholders, not verified vendor prices

# Phase 2: summarize a run-pilot output into a Markdown + JSON efficiency report
neurosurg-epi efficiency-summary --input results.json --markdown-output efficiency.md --json-output efficiency.json

# Phase 2: evaluate pre-generated planner outputs (now with per-arm summaries)
neurosurg-epi evaluate --tasks benchmarks/tasks.v0.1.0.yaml --outputs pilot_results.json --prompt config/prompts/planner_v1.txt --registry config/variables/nhanes_demo.yaml --json-output eval/results.json --markdown-output eval/summary.md
```

Run the test suite:

```powershell
pytest
```

## A minimal plan (YAML)

```yaml
plan:
  title: "Stroke and metabolic syndrome, NHANES 2011-2018"
  question: "Is self-reported stroke associated with metabolic syndrome components?"
  database: NHANES
  cycles: ["G", "H", "I", "J"]
  uses_fasting_subsample: false
  design_vars:
    id: SDMVPSU
    strata: SDMVSTRA
    weight: WTMEC2YR/4   # 4 two-year cycles pooled
  outcome:
    name: stroke_ever
    label: "Ever told had a stroke"
    source_variable: MCQ160F
    source_module: MCQ
    status: illustrative
    nhanes_cycles: ["G","H","I","J"]
  steps:
    - {step: "1", description: "merge cycles + apply inclusion criteria"}
  causal_claims:
    - "Stroke history is associated with metabolic syndrome components."
```

`validate-plan` will pass; the illustrative outcome surfaces as a warning
reminding you to confirm `MCQ160F` against the codebook before any reported
result.

## Architecture

```
                            ┌──────────────┐
   clinical question ─────► │   router     │ ── NHANES (supported)
   (free text)              │ (deterministic) │   GBD/SEER/CHARLS (planned → infeasible)
                            └──────┬───────┘
                                   │
            ┌──────────────────────┴───────────────────────┐
            ▼                                              ▼
   ┌─────────────────┐                          ┌──────────────────────┐
   │ variable        │  versioned YAML on disk   │ guardrails           │
   │ registry        │ ◄── only entry point ───► │  • causal language   │
   │ (Pydantic,      │   for variable mappings   │  • survey design     │
   │  status-tagged) │                           │  • weight rescaling  │
   └─────────────────┘                           │  • fasting mismatch  │
                                                 │  • provenance/cycles │
                                                 └──────────┬───────────┘
                                                            ▼
                                                 ┌──────────────────────┐
                                                 │ manifest (YAML)      │
                                                 │ findings + provenance│
                                                 │ no results           │
                                                 └──────────────────────┘

Phase 2 Extension:
┌─────────────────────────────────────────────────────────────────────────┐
│ PLANNER LAYER                                                           │
│ ┌──────────────────┐    ┌─────────────────────┐                        │
│ │ ReplayPlanner    │    │ ClaudeCodePlanner    │                        │
│ │ (offline fixtures)│    │ (subprocess CLI)     │                        │
│ └──────────────────┘    └─────────────────────┘                        │
│          │                       │                                       │
│          └───────────┬───────────┘                                       │
│                      ▼                                                   │
│              AnalysisPlan (Pydantic)                                     │
│                      │                                                   │
└──────────────────────┼───────────────────────────────────────────────────┘
                       ▼
              ┌───────────────────────┐
              │ OFFLINE EVALUATION    │
              │ • Benchmark tasks     │
              │ • Arm outputs         │
              │ • Scoring metrics      │
              │ • Gold standard hashes │
              └───────────────────────┘
```

- `src/neurosurg_epi_agent/planner.py` — planner provider protocol and
  implementations (ReplayPlannerProvider, ClaudeCodePlannerProvider).
- `src/neurosurg_epi_agent/evaluation.py` — typed schemas and scoring logic
  for offline benchmark evaluation.
- `config/prompts/planner_v1.txt` — versioned prompt template for LLM planners.
- `benchmarks/tasks.v0.1.0.yaml` — 30 diverse neurosurgical public-database tasks
  spanning 9 clinical domains including pituitary (frozen draft v0.1.0, pending expert adjudication).
- `benchmarks/tasks.example.yaml` — Original 10-task subset for basic testing.
- `benchmarks/BENCHMARK_CARD.md` — Human-readable overview of benchmark specification.
- `benchmarks/GOLD_STANDARD_PROCESS.md` — process for expert adjudication and
  gold standard freezing.

- `src/neurosurg_epi_agent/schemas.py` — typed Pydantic models (plan, registry,
  findings, manifest, evaluation).
- `registry.py` — versioned YAML loader; the *only* place variable mappings
  enter the engine; hard-validates status, duplicates, version.
- `router.py` — deterministic database selection from a static capability table.
- `guardrails.py` — the deterministic statistical + language rules.
- `manifest.py` — builds and writes the reproducibility record.
- `cli.py` — `route` / `validate-plan` / `manifest` / `plan` / `evaluate` /
  `run-pilot` / `efficiency-summary` subcommands.

## Efficiency telemetry

`run-pilot` records publication-auditable, secret-free telemetry for every
model call, plus a deterministic efficiency summary for Arm A / Arm B /
overall. The `efficiency-summary` subcommand renders a run-pilot output JSON
into a Markdown + JSON report.

**Captured per call** (from the Claude Code `--output-format json` envelope;
each is `None` when absent, never silently zero): `usage.input_tokens`,
`usage.output_tokens`, `usage.cache_read_input_tokens`,
`usage.cache_creation_input_tokens`, `total_cost_usd` (exposed honestly as
`claude_cli_reported_cost_usd`), `duration_ms`, `duration_api_ms`, `num_turns`,
and `session_id`. No API keys, auth tokens, prompts, raw environment
variables, stdout/stderr, or participant data are persisted.

**Counting rules.** A live planner attempt counts as one model call even if
parsing or plan validation fails (token/cost data is still captured when an
envelope was returned). A deterministic Arm A refusal and a dry run count as
zero calls. Resumed (checkpoint) and reused Arm B outputs are never counted
twice.

**Estimated cost.** Optional and caller-driven: supply explicit
per-million-token prices (`--price-input`, `--price-output`,
`--price-cache-read`, `--price-cache-creation`). `estimated_cost_usd` is
`None` unless every rate required by the observed nonzero token categories is
supplied. The tool never hard-codes vendor prices; supplied rates and their
provenance are stored in experiment `metadata.pricing`.

**Backend provenance.** `--backend-label` records a descriptive route string
(e.g. `glm-5.2 via CC-Switch`) alongside the Claude-facing model alias. This
is provenance, not authentication data.

**Experiment design.** Arms run sequentially within one run (Arm A then Arm B
per task). `metadata.execution_design` records `parallel: false` and
`statistically_independent: false`; a fresh run is identifiable as same-run /
no-reuse via `metadata.arm_b_reuse`.

**Honest labeling.** `claude_cli_reported_cost_usd` is the cost the Claude CLI
reports for the session — it is NOT a vendor invoice and NOT evidence of
cost-effectiveness. Missing token/cost fields are never summed as zero;
availability and missing counts are reported alongside every total.

## v0.2 Deterministic Gate Implementation

**Status: Implemented, not yet evaluated.** The v0.2 deterministic gate architecture is complete but requires evaluation against the benchmark tasks.

### Key Changes from v0.1

**A) Router Correctness**
- Refactored deterministic router with proper precedence
- Added table-driven tests for all 10 benchmark tasks

**B) Deterministic Gate**
- Arm A calls route(question) before planner, creates minimal plan if infeasible
- Arm B baseline remains unconstrained

**C) Guardrail Optimization**
- Infeasible plans skip analysis-execution guardrails
- Still check causal overstatement and database integrity

**D) Token Efficiency**
- Added --reuse-arm-b-from option for Arm B reuse

**E) Evaluation Report**
- Fixed per-task lookup and added coverage metrics

### Evidence Preservation

v0.1 baseline preserved in experiments/pilot_glm47_dev/.

## Benchmark Status

**Current Status**: Draft benchmark frozen at v0.1.0

The NeuroSurgEpiAgent benchmark consists of 30 diverse neurosurgical epidemiology tasks spanning 9 clinical domains. The benchmark is currently in **DRAFT** status and cannot support scientific claims.

### Benchmark Artifacts

- **Frozen Benchmark**: `benchmarks/tasks.v0.1.0.yaml` — Versioned task set with metadata and disclaimers
- **Benchmark Card**: `benchmarks/BENCHMARK_CARD.md` — Human-readable overview and specifications
- **Schema Definition**: `benchmarks/benchmark_schema.v1.json` — JSON Schema for task validation
- **Freezing Summary**: `benchmarks/FREEZING_SUMMARY.md` — Complete freezing process documentation

### Critical Limitations

⚠️ **The draft benchmark CANNOT be used for:**
- Scientific publication claims about agent performance
- Comparative effectiveness evaluations between systems
- Clinical utility assessments
- Any claims requiring independently validated ground truth

### Gold Standard Requirements

To upgrade from draft to gold standard, the following must be completed per `benchmarks/GOLD_STANDARD_PROCESS.md`:

1. **Expert Recruitment**: Two independent experts (neurologist/neurosurgeon + epidemiologist)
2. **Expert Adjudication**: Consensus review of all 30 tasks
3. **Codebook Verification**: Independent confirmation of all variable codes
4. **Leakage-Controlled Evaluation**: Blinded evaluation runs with information flow control
5. **Expert Countersignature**: Final results signed off by both experts

### Task Distribution

- **9 domains**: stroke (9 tasks), tumor (4), tbi (3), sah (3), spine (3), disparities (2), global_burden (2), pituitary (2), hydrocephalus (2)
- **26 NHANES tasks** (9 feasible, 17 infeasible)
- **2 SEER tasks** (expected infeasible - adapter not implemented)
- **2 GBD tasks** (expected infeasible - adapter not implemented)

For detailed task specifications and rationales, see `benchmarks/BENCHMARK_CARD.md`.

## Public-data case study

An aggregate-only NHANES 2017-2018 stroke prevalence case study is available as
a reproducibility demonstration:

```powershell
pip install -e ".[case-study]"
python -m neurosurg_epi_agent.case_studies.nhanes_stroke_2017_2018 --output-dir case_studies/nhanes_stroke_2017_2018 --cache-dir data/cache/nhanes
```

The case study downloads public CDC XPT files (`DEMO_J.XPT`, `MCQ_J.XPT`) if
absent, merges records in memory by `SEQN`, and writes only aggregate outputs:
`results.json`, `provenance.json`, and `report.md`. It reports descriptive
weighted prevalence using `WTINT2YR`; confidence intervals are intentionally not
reported because complex survey variance estimation is not implemented in this
lightweight demonstration.

## Safety limitations

- **Variable codes must be confirmed.** Even `verified` entries should be
  checked against the specific cycle codebook you analyze; the registry is a
  structured starting point, not an oracle.
- **No execution, no estimates.** The agent will not produce odds ratios,
  confidence intervals, or p-values. Anything numeric must come from your own
  downstream analysis.
- **Routing is keyword-based and conservative.** It refuses/cautions rather
  than guesses; a question it cannot classify is routed to NHANES with a
  caveat to confirm feasibility.
- **NHANES cannot answer neurosurgical-caseload or histology questions.** The
  router and guardrails say so explicitly rather than fabricating a mapping.
- **Adapter databases (GBD/SEER/CHARLS) are not active.** They appear only as
  planned/infeasible routing targets.
- **SEER is metadata-only.** The `SEERAdapter` inspects a SEER\*Stat export
  directory and emits schema + provenance only — no case row, no frequency,
  no unique value. Any clinical analysis must be backed by the signed-off
  `docs/SEER_STUDY_CONTRACT.md`.

## Data access and reproduction

The repository never redistributes source data. To reproduce a result:

| Source | Access | What the repo ships |
| --- | --- | --- |
| NHANES | public; download from CDC | aggregate case-study outputs; downloader in `case_studies/nhanes_stroke_2017_2018/` |
| CDC WONDER | public; query at wonder.cdc.gov | metadata-only inspection via `CDCWonderAdapter`; aggregated, disclosure-checked results only |
| SEER | requires SEER DUA; apply via seer.cancer.gov | metadata-only inspection via `SEERAdapter`; the user fills in `docs/SEER_STUDY_CONTRACT.md` before any analysis |

Set `NEUROSURG_EPI_SEER_ROOT` and `NEUROSURG_EPI_CDC_WONDER_ROOT` in a
local `.env` (template in `.env.example`) before running the inspection
scripts.

## Documentation

- [`docs/PROJECT_CHARTER.md`](docs/PROJECT_CHARTER.md) — research question,
  target users, MVP scope, novelty, falsifiable paper claims.
- [`docs/EVALUATION_PROTOCOL.md`](docs/EVALUATION_PROTOCOL.md) — comparison
  arms, blinded benchmark tasks, gold standard, metrics, error taxonomy.
- [`docs/MANUSCRIPT_PLAN.md`](docs/MANUSCRIPT_PLAN.md) — titles, outline,
  figures/tables, target-journal categories, evidence needed.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — Phase 1 (complete), Phase 2 (complete),
  Phase 3 (database adapters).
- [`benchmarks/GOLD_STANDARD_PROCESS.md`](benchmarks/GOLD_STANDARD_PROCESS.md) —
  expert recruitment, adjudication, leakage control, amendment policy.
- [`PHASE2_ACCEPTANCE.md`](PHASE2_ACCEPTANCE.md) — claim-to-artifact matrix for
  Phase 2 implementation verification.

## License

MIT — see [`LICENSE`](LICENSE).
