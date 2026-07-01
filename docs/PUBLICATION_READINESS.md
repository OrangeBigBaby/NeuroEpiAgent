# Publication readiness assessment

Date: 2026-06-29

## Current readiness

NeuroSurgEpiAgent is close to a credible preprint or software-focused methods
manuscript, but it is not yet ready for strong empirical claims in a clinical
informatics, epidemiology, or neurosurgery journal. The repository now supports
three defensible claims: the system architecture is implemented and tested; the
10-task development pilot suggests deterministic pre-generation gating can
reduce model calls and hard planning errors; and a real NHANES 2017-2018
aggregate-only case study can be reproduced with source hashes and provenance.

The strongest current manuscript positioning is therefore:

> We present an open-source, reproducible framework for guarded LLM-assisted
> neurosurgical epidemiology planning in public clinical databases, with a
> development pilot, a frozen draft benchmark awaiting expert adjudication, and
> an aggregate-only NHANES reproducibility case study.

The manuscript should not yet claim validated generalizable agent performance,
clinical utility, superiority to other systems, or formal epidemiologic inference.

## Completed artifacts

- Core agent architecture: deterministic router, variable registry, NHANES
  guardrails, manifest generation, planner provider interface, replay provider,
  and Claude Code provider.
- Development pilot: 10 authored tasks, two-arm comparison, guardrail-based
  evaluation, and preserved outputs under `experiments/pilot_glm47_gate_v02/`.
- Frozen draft benchmark: 30 tasks, version 0.1.0, sidecar SHA-256 digest,
  schema validation, and explicit `needs_expert_review` status.
- Statistical utilities: Wilson intervals, McNemar testing scaffolds,
  multiple-comparison correction, and adjudication support.
- Ablation/adjudication scaffolds: arm definitions, concurrency safeguards,
  dry-run support, and inter-rater reliability placeholders.
- NHANES case study: public DEMO_J/MCQ_J download, SHA-256 provenance, in-memory
  merge, aggregate weighted prevalence, and aggregate-only outputs.
- Manuscript draft: IMRAD manuscript updated with benchmark integrity artifacts
  and NHANES case-study results.
- Test suite: 220 collected tests passing.

## Current verification

- `python -m pytest -q` passes.
- `python benchmarks\verify_benchmark_integrity.py --verbose` passes.
- `python -m neurosurg_epi_agent.case_studies.nhanes_stroke_2017_2018 --output-dir case_studies/nhanes_stroke_2017_2018 --cache-dir data/cache/nhanes` runs successfully.

## Main blockers before a stronger submission

1. Independent expert adjudication is still missing. The 30-task benchmark is
   frozen but not a gold standard until at least two independent experts review
   feasibility labels, database routing, and variable assertions.
2. The 10-task pilot remains a development-set result. The router was refined
   against those same tasks, so performance may be optimistic.
3. The baseline comparison was not concurrent. Arm B outputs were reused from a
   prior run rather than regenerated under the same model/session conditions.
4. Token usage and actual cost were not measured. The current resource claim is
   model-call reduction only.
5. The NHANES case study does not implement complex survey variance estimation,
   so it should not report confidence intervals or subgroup inference.
6. Several registry entries remain illustrative or need review. A stronger
   manuscript needs more codebook-verified variables.

## Recommended next experiment

The next publishable experiment should use the frozen 30-task benchmark only
after expert adjudication. Runs should be concurrent, same-model, hash-preserved,
and preregistered. The primary endpoints should be hard-error-free rate,
correct refusal, routing accuracy, registry compliance, and model-call count.
Token and cost logging should be added before the live run. Inferential testing
should be limited to paired comparisons that are justified by the final sample
size; otherwise, report descriptive estimates with confidence intervals for
proportions.

## Suggested near-term target

For immediate dissemination, the safest target is a preprint plus GitHub release
or a software/methods venue that accepts development-stage tools. For a
clinically oriented journal, complete the adjudicated 30-task evaluation first.

