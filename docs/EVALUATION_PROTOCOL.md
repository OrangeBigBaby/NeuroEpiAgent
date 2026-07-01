# Evaluation Protocol

This protocol defines how we will *falsify* the claims in
`PROJECT_CHARTER.md`. It evaluates **planning/validation safety**, not clinical
effect sizes. No power calculation here asserts a clinical finding; the
sample-size rationale is for the *evaluation study itself*.

## Comparison arms

| Arm | Description |
|---|---|
| **A — NeuroSurgEpiAgent** | LLM planner + deterministic registry + guardrails + manifest. |
| **B — Unconstrained LLM baseline** | Same LLM, same prompts, no registry or guardrails; free-form plan + prose. |
| **C — Human expert (reference)** | A trained epidemiologist writes the gold-standard plan per task. Used only to author/validate the gold standard, not as a scored arm in every run. |

Arm C fixes the gold standard; A and B are scored against it. The same
underlying LLM is used in A and B so the comparison isolates the
registry+guardrail layer, not model choice.

## Blinded benchmark tasks

The 10 tasks live in [`../benchmarks/tasks.example.yaml`](../benchmarks/tasks.example.yaml),
covering **stroke**, **TBI**, and **tumor**, plus the NHANES feasibility
limits (surgery, histology, TBI-item absence) and cross-cutting items.

- Tasks are **domain-labeled** but scorers are blind to which arm produced an
  output.
- Tasks deliberately include **infeasible** items; an arm that fabricates a
  mapping to "solve" an infeasible task is scored as a failure.
- Each task pins `expected_database`, `expected_feasible`, and a
  `guardrail_focus` so scoring is rule-based, not vibes-based.

## Gold standard

For each task, the gold standard records:

1. `expected_database` and `expected_feasible` (from the YAML).
2. The set of guardrail codes that **must** fire (e.g.
   `FASTING_SUBSAMPLE_UNDECLARED`) and those that **must not** fire on a clean
   plan.
3. The list of variable codes that are **acceptable** (codebook-confirmed) and
   a flag for whether the task permits **any** variable at all (infeasible
   tasks permit none).

The gold standard is authored from the published NHANES codebook structure and
the project's survey-design conventions — **not** from running either arm.

## Metrics

Per task, scored independently:

- **Routing accuracy** — `database` and `feasible` match gold.
- **Hard-error count** — number of `ERROR`-severity guardrail findings
  (`CAUSAL_LANGUAGE`, `NHANES_PSU`, `NHANES_STRATA`, `WEIGHT_RESCALE`,
  `FASTING_WEIGHT_MISMATCH`, `FASTING_SUBSAMPLE_UNDECLARED`,
  `UNRESOLVED_VARIABLE`). Target for arm A: **0** on feasible tasks.
- **Infeasibility handling** — for infeasible tasks, did the arm refuse/flag
  rather than fabricate? Binary.
- **Hallucination rate** — fraction of emitted variable codes that are not in
  the acceptable set (gold) or not codebook-plausible. Target for arm A:
  **0**.
- **Citation validity** — any citation emitted is checked against a primary
  source; invented citations count as failures. Target for arm A: **0**
  invented.
- **Manifest reconstructability** — can a second reviewer reproduce the rule
  firings from the manifest alone? Binary per task.

Reported as counts and proportions per arm, with exact binomial 95% intervals
(Wilson). We report **per-error-class** breakdowns, not only an aggregate
score, because the claim is about *specific* failure modes.

## Error taxonomy

| Code | Class | Severity | Meaning |
|---|---|---|---|
| `CAUSAL_LANGUAGE` | language | error | Overclaiming / causal wording on observational data. |
| `NHANES_PSU` / `NHANES_STRATA` | design | error | Wrong or missing survey-design variable. |
| `WEIGHT_RESCALE` | design | error | Multi-cycle weight not divided by number of cycles pooled. |
| `FASTING_WEIGHT_MISMATCH` | design | error | Fasting labs used without `WTSAF2YR`. |
| `FASTING_SUBSAMPLE_UNDECLARED` | design | error | Fasting labs referenced but subsample flag false. |
| `UNRESOLVED_VARIABLE` | provenance | error | A `needs review` variable used as if confirmed. |
| `ILLUSTRATIVE_VARIABLE` | provenance | warning | Variable used is illustrative, not verified. |
| `CYCLE_COVERAGE` | provenance | warning | Variable requested in cycles its registry does not cover. |
| `FASTING_WEIGHT_UNEXPECTED` | design | warning | `WTSAF2YR` used without a declared fasting analysis. |
| `DATABASE_MISMATCH` | integrity | error | Plan DB ≠ routed/registry DB. |

A separate, **outcome-level** taxonomy (for arm B's free-form output) maps
prose to the same codes so A and B are comparable: e.g. any baseline sentence
that implies a causal claim maps to `CAUSAL_LANGUAGE`.

## Statistical analysis

- Development comparison: hard-error count per task, arm A vs. arm B. For the
  10-task pilot, task-level pass/fail (0 hard errors = pass) is the unit; we
  report counts and Wilson intervals descriptively. The pilot is a coverage
  and counterexample-finding exercise, not a powered superiority study.
- Paper primary comparison: expand and freeze an expert-reviewed benchmark
  before any scored run (target 30--50 tasks, with the final number justified
  from expected paired discordance). Compare paired pass/fail outcomes with a
  paired method such as McNemar's exact test and report the paired difference
  with a confidence interval.
- Secondary: hallucination rate (0/non-zero per task) and citation validity,
  reported descriptively per arm.
- Pre-registration: the `expected_*` fields in `tasks.example.yaml` constitute
  the pre-specified gold standard. We will not edit them after an arm is run.

## Sample-size rationale (for the evaluation, not a clinical result)

- **Why 10 tasks?** The benchmark's job is to *falsify* claim C1 ("zero
  hard errors on feasible tasks") and C4 ("no invented codes"), which are
  *deterministic* claims — a single counterexample falsifies them, so the
  burden is coverage of distinct error classes, not statistical power. The 10
  tasks span all six hard-error codes plus three infeasible patterns, giving
  at least one probe per failure mode.

- **Precision of the 10-task pilot.** Even 0 errors in 10 tasks leaves a wide
  uncertainty interval for the underlying error probability (the familiar
  rule-of-three upper bound is roughly 30%). Therefore the pilot cannot support
  a claim that errors are rare in general; it can only expose counterexamples
  and verify that each pre-specified rule is exercised. A formal power and
  sample-size analysis will be performed for the frozen, expanded benchmark
  using the expected paired discordance between arms. **No clinical power,
  effect size, or sample size is asserted or implied.**

- **Scaling.** The task set is designed to be extensible; an external expert
  evaluation (see `ROADMAP.md`) may expand it to ~30–50 tasks to tighten the
  Wilson intervals. Any expansion is added to the YAML *before* re-running.

## Reporting

- Per-task table: arm × {routed DB, feasible, hard errors, hallucinations,
  citations, manifest reconstructable}.
- Per-arm aggregates with Wilson intervals.
- A "what would falsify each claim" section mapping the data back to C1–C4.
- All manifests and raw arm outputs archived alongside the report so a reviewer
  can re-derive every cell.

The report will state explicitly that the evaluation measures planning-safety,
not the clinical validity of any NHANES study produced with the tool.
