# Manuscript Plan

This is a **methods/tooling paper**, not a clinical-results paper. The
manuscript argues an architecture claim and supports it with the evaluation in
`EVALUATION_PROTOCOL.md`. No clinical association, effect size, or performance
number is reported as a result of the tool.

## Candidate titles

1. "NeuroSurgEpiAgent: deterministic guardrails that make an LLM planner safe
   for reproducible NHANES epidemiology."
2. "An LLM-assisted, registry-constrained planning layer for public-database
   epidemiology: design, guardrails, and a blinded evaluation."
3. "Removing the failure modes of LLM research planning in survey-weighted
   epidemiology: variable provenance, design rules, and reproducibility
   manifests."

Working title: **NeuroSurgEpiAgent: A Registry-Constrained LLM Workflow with
Deterministic Guardrails for Reproducible NHANES Epidemiology.**

## Paper type

Methods / software tool paper with a blinded comparative evaluation against an
unconstrained LLM baseline. Target venue categories below.

## Outline

1. **Background & motivation.** LLM agents draft epidemiology plans quickly but
   hallucinate NHANES variable codes, misuse fasting-subsample weights, and
   make causal claims on cross-sectional data. These are specific, reproducible
   failure modes.
2. **Related work.** General LLM data-analysis agents; reproducible-research
   tooling for survey data; structured analysis plans/registries. Position the
   contribution as the *intersection* (registry + design guardrails +
   manifest), not any single element.

   **Placeholders for related-work comparison (not verified novelty claims):**

   ### vs NHANES-GPT
   - **Our contribution**: Neurosurgical-specific benchmark with registry-constrained
     variable mapping and complex-survey guardrails.
   - **NHANES-GPT focus**: General-purpose NHANES querying with natural language.
   - **Key difference**: Our evaluation framework explicitly prohibits variable code
     invention and enforces survey-design rules.

   ### vs RWE-bench
   - **Our contribution**: Public-database epidemiology planning with provenance
     hashing and gold-standard adjudication process.
   - **RWE-bench focus**: Real-world evidence extraction from EHR data.
   - **Key difference**: We evaluate planning quality, not execution accuracy; our
     benchmark requires expert adjudication, not automated reference matching.

   ### vs LATCH
   - **Our contribution**: Token-efficient, auditable planning layer with explicit
     refusal mechanisms for infeasible tasks.
   - **LATCH focus**: Long-context clinical question answering with retrieved evidence.
   - **Key difference**: We use blocking and deterministic validation rather than
     long-context retrieval; our refusal is explicit, not implicit.

   > **Important**: These are placeholder comparisons for manuscript planning, not
   > verified novelty claims. Actual related work comparison requires systematic
   > literature review and expert consultation.

3. **Design.** The planner/explainer-but-not-source-of-truth architecture.
   Registry as sole entry point for variable names; status tags; deterministic
   guardrails; reproducibility manifest; adapter-ready routing.
4. **Implementation.** Typed schemas, versioned YAML registry, deterministic
   router, guardrail rule set, CLI, manifest format. Dependencies minimal
   (Pydantic, PyYAML).
5. **Evaluation.** Comparison arms, 30 blinded benchmark tasks across 9 domains
   (stroke/TBI/tumor/SAH/hydrocephalus/spine/disparities/global burden/pituitary)
   + feasibility limits), gold standard, metrics, error taxonomy, statistical
   analysis (per `EVALUATION_PROTOCOL.md`).
6. **Results.** Per-task and per-arm outcomes against the falsifiable claims
   C1–C4. Report what was *not* falsified and any counterexamples found.
7. **Limitations.** Keyword routing; NHANES scope; registry is a starting
   point, not authoritative; planner still LLM-dependent; no execution/estimate
   validation; deterministic routing and planning adapters are NHANES-only
   (CDC WONDER / SEER / CHARLS are **metadata-inspection only**; their planning
   adapters and clinical-analysis execution are not active).
8. **Future work.** External expert evaluation; planning adapters for
   CHARLS/GBD/SEER (routing today is planned/infeasible for these);
   execution-layer integration with reproducible R/Python templates.

## Figures and tables (planned; evidence to be generated, not assumed)

- **Table 1 — Error taxonomy.** Guardrail codes, class, severity, meaning, and
  which claim each probes. *(Evidence: this repo, `guardrails.py` + this
  doc.)*
- **Table 2 — Benchmark tasks.** The 30 tasks, domain, expected DB,
  expected feasibility, guardrail focus. *(Evidence: `benchmarks/`.)*
- **Table 3 — Per-task results.** Arm A vs. B: routed DB, feasible, hard-error
  count, hallucinations, citations, manifest reconstructable. *(Evidence: to
  be produced by running the evaluation — no numbers asserted here.)*
- **Table 4 — Aggregate.** Per-arm pass proportion with Wilson intervals,
  hallucination rate, citation validity. *(Evidence: produced by the
  evaluation.)*
- **Figure 1 — Architecture.** Router → registry + guardrails → manifest
  diagram. *(Evidence: `README.md` architecture section.)*
- **Figure 2 — Example manifest.** A redacted manifest showing findings +
  provenance, illustrating "records findings, not results." *(Evidence: a real
  run output.)*

Every figure/table is labeled with the evidence it requires; **none are filled
in with fabricated values.** Table 3/4 numbers come only from running the
protocol.

## Target-journal categories

- **Methods/software journals** (e.g. *Journal of Medical Internet Research -
  Medical Informatics*, *BMC Medical Research Methodology*, *Journal of
  Clinical Epidemiology* methods sections, *SoftwareX*, *Journal of Open
  Source Software*).
- **Health-informatics venues** with methods scope.
- We will **not** target clinical-results journals, because the paper makes no
  clinical claim. Final venue selection deferred until the evaluation is run;
  this list states categories only.

## Evidence needed (and explicitly not yet held)

- Run the evaluation protocol to populate Tables 3–4.
- Independent confirmation of every `verified` registry entry against the
  target cycle codebook.
- At least one external epidemiologist review of the gold standard (see
  `ROADMAP.md`, external expert evaluation).

We will not write the Results section until this evidence exists. Claims C1–C4
in `PROJECT_CHARTER.md` stand as pre-specified, falsifiable targets.
