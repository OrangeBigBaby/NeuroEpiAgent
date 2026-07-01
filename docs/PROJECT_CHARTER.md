# Project Charter

## Research question (primary)

Can an LLM-assisted agent produce **correct and reproducible** neurosurgical
epidemiology analysis plans from public databases — where "correct" means
real variable mappings, valid survey-design statistics, and no causal
overstatement — *when the LLM is structurally barred from being the source of
truth for variable names or statistical validity*?

The engineering claim: deterministic schemas + a versioned registry +
rule-based guardrails are sufficient to make an LLM planner safe enough for a
publication workflow. The evaluation claim: this configuration reduces the
specific, reproducible error classes that unconstrained LLM planners make.

## Target users

1. **Clinical/epidemiology researchers** drafting NHANES-based studies who want
   a structured, auditable plan instead of a free-form LLM draft.
2. **Methods reviewers / supervisors** who need to see *why* a plan is
   statistically sound (the manifest is the audit trail).
3. **Trainees** learning NHANES survey-design conventions, for whom a guardrail
   that explains the rule is itself pedagogical.

Secondary, post-MVP: researchers working with CHARLS, GBD, or SEER once
adapters ship.

## Minimum viable product (NHANES-first)

In scope:

- NHANES variable registry with explicit `verified` / `illustrative` /
  `needs review` status per entry.
- Deterministic routing (NHANES supported; GBD/SEER/CHARLS planned/infeasible).
- Deterministic guardrails: causal language, NHANES `SDMVPSU`/`SDMVSTRA`
  design, multi-cycle weight rescaling (`WTMEC2YR / N`), fasting-subsample
  weight matching (`WTSAF2YR`), variable provenance, cycle coverage.
- CLI: `route`, `validate-plan`, `manifest`.
- Reproducibility manifest (findings + provenance, no results).
- A 10-task blinded benchmark across stroke/TBI/tumor + feasibility limits.
- Tests for routing, registry validation, guardrails, manifest.

Explicitly out of MVP scope (see README non-goals): execution/estimation,
raw-data download, the three non-NHANES adapters, ML prediction.

## Novelty (what is genuinely new here)

This is not "another LLM research assistant." The contribution is an
**architecture in which the LLM cannot be the source of truth for the things
LLMs get wrong in epidemiology**:

1. **Evidence-backed variable mapping as a first-class artifact** — status tags
   and codebook pointers, not free text, and the registry is the only entry
   point for variable names.
2. **Deterministic statistical guardrails** — survey-design and weight rules
   enforced as hard checks (errors), with conservative language policy.
3. **Reproducibility manifest** — a diff-able record of rules-fired and
   provenance, designed so a reviewer can audit a plan without re-running the
   LLM.

The literature review will test whether prior systems combine all three for
survey-weighted epidemiology. Until that review is complete, this intersection
is a candidate contribution rather than a priority or novelty claim.

## Falsifiable paper claims

Each claim is written so it can be *refuted by the evaluation*, not just
supported:

- **C1 (correctness):** On the blinded benchmark, NeuroSurgEpiAgent produces
  **zero** hard guardrail errors (wrong design var, wrong weight divisor,
  fasting mismatch) on feasible tasks, and correctly refuses/flags infeasible
  tasks. *Falsified if any feasible benchmark task yields a hard error, or any
  infeasible task is marked feasible.*
- **C2 (safety vs. baseline):** An unconstrained LLM-only baseline makes a
  non-trivial rate of the specific error classes above on the same tasks;
  NeuroSurgEpiAgent's guardrails eliminate that class of error. *Falsified if
  the baseline error rate is already zero, or if the agent introduces a new
  error class the baseline avoids.*
- **C3 (reproducibility):** Two independent runs on the same plan + registry
  produce byte-identical manifests (modulo hash), and a reviewer can recreate
  the rule firings from the manifest alone. *Falsified by non-determinism or an
  unreconstructable manifest.*
- **C4 (honesty about limits):** The agent never emits an invented variable
  code or citation across the benchmark. *Falsified by any invented code or
  citation in any output.*

Claims C1–C4 are about **planning/validation safety**, not about the clinical
merit of any specific study. We will not claim the agent improves clinical
outcomes.

## Scope boundaries (what we will not claim)

- We do **not** claim NHANES can answer neurosurgical questions it cannot
  (procedures, histology, caseload). The router and guardrails enforce this.
- We do **not** claim the variable registry is exhaustive or authoritative; it
  is a structured, status-tagged starting point.
- We do **not** report any clinical association, effect size, or performance
  number as part of the tool itself.
- We do **not** claim the LLM is unnecessary — it remains the
  planner/explainer; we claim its failure modes are removed by construction.

## Decision log

- **NHANES-first, not four databases.** Decided 2026-06. Rationale: a single,
  well-documented survey lets us harden guardrails and evaluation before
  generalizing; shipping four shallow adapters would dilute the correctness
  story.
- **LLM is planner/explainer only.** Decided 2026-06. Rationale: LLM
  hallucination of NHANES codes is the primary failure mode we are removing.
- **No invented citations or results, ever.** Decided 2026-06. Enforced in the
  output contract and CONTRIBUTING.
