# Revision plan for the HISS special issue

Target collection: *Toward Trustworthy and Generalizable AI in Healthcare:
Advances in Explainability, Causal Learning, and Cost-effectiveness*.

Target journal: *Health Information Science and Systems*.

Date: 2026-06-29.

## Downloaded example papers

The following full-text PDFs have been downloaded into
`docs/literature/hiss_special_issue_examples/`:

| Local file | Source | Why it matters for NeuroSurgEpiAgent |
| --- | --- | --- |
| `rag_drug_contraindications_bang_2026_arxiv.pdf` | Bang et al., "Retrieval Augmented Large Language Model System for Comprehensive Drug Contraindications" | Useful template for framing an LLM system as a reliability-improving healthcare AI pipeline with public knowledge sources and benchmarked question-answer outputs. |
| `medagentbench_2025_arxiv.pdf` | Jiang et al., "MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents" | Useful template for medical-agent benchmark framing, task categories, human-authored tasks, executable environment, and transparent performance limits. |
| `llm_agents_research_reproducibility_alzheimers_2025_arxiv.pdf` | Dobbins et al., "Large Language Model-Based Agents for Automated Research Reproducibility: An Exploratory Study in Alzheimer's Disease" | Closest conceptual comparator for autonomous research reproducibility, honest failure analysis, and cautious conclusions. |

The following HISS examples were identified but not downloaded as full-text PDFs
because accessible local downloads were blocked or full text appeared to be
subscription-restricted. They should still be cited or discussed from official
metadata/abstract pages where appropriate:

| Paper | Link | Planned use |
| --- | --- | --- |
| Cong et al., "Multiple feature selection based on an optimization strategy for causal analysis of health data" | https://link.springer.com/article/10.1007/s13755-024-00312-8 | Model for aligning with the special issue's causal-learning language. We should borrow its explicit Purpose/Methods/Results/Conclusion framing and avoid claiming causal discovery when our actual contribution is causal-overclaim prevention. |
| "KSDKG: construction and application of knowledge graph for kidney stone disease based on biomedical literature and public databases" | https://link.springer.com/article/10.1007/s13755-024-00309-3 | Model for public-database + structured biomedical knowledge framing. We should position the variable registry and database capability table as lightweight knowledge infrastructure. |
| "Explainable federated learning scheme for secure healthcare data sharing" | https://link.springer.com/article/10.1007/s13755-024-00306-6 | Model for explainability/security/privacy framing. We should emphasize explainable refusals, guardrail reports, and aggregate-only outputs. |

## Revised positioning

The paper should be repositioned from a narrow neurosurgical epidemiology agent
development pilot to a trustworthy healthcare AI systems paper:

> NeuroSurgEpiAgent is a guardrail-driven, reproducible, low-cost AI agent
> framework for healthcare research planning in public clinical databases, with
> an NHANES-first implementation and neurosurgical epidemiology as the initial
> clinical domain.

This positioning maps directly onto the special issue as follows:

| Special issue theme | NeuroSurgEpiAgent evidence |
| --- | --- |
| Trustworthy AI | Deterministic router, variable registry, survey-design guardrails, causal-language blocking, manifest provenance. |
| Generalizable AI | Adapter-oriented architecture with NHANES implemented first and GBD/SEER/CHARLS represented as planned infeasible adapters. |
| Explainability | Explicit routing rationales, refusal reasons, guardrail findings, and variable-status labels. |
| Causal learning | Conservative causal-overclaim prevention for cross-sectional survey planning; do not claim causal discovery. |
| Cost-effectiveness | Pre-generation gating reduces model calls by 70% in the development pilot; add token/cost logging before final submission. |
| Benchmarking/reproducibility | Frozen 30-task draft benchmark, SHA-256 sidecar, integrity verifier, tests, reproducible case study. |
| AI agent-enabled proactive health | The agent proactively detects infeasible questions and prevents invalid plans before expensive generation. |

## Specific manuscript changes

### Title and abstract

Recommended title:

**Toward Trustworthy and Low-Cost AI Agents for Healthcare Research Planning:
Development and Evaluation of NeuroSurgEpiAgent**

The abstract should make the special issue connection explicit in one sentence:

> We designed NeuroSurgEpiAgent around deterministic explainability,
> reproducibility, and model-call cost reduction rather than unconstrained
> black-box generation.

### Introduction

Rewrite the introduction around three barriers emphasized by the special issue:

1. Generalizability barriers in healthcare AI caused by heterogeneous databases
   and database-specific design rules.
2. Trust barriers caused by black-box LLM planning, hallucinated variables, and
   unsupported causal language.
3. Cost/scalability barriers caused by invoking expensive models on infeasible
   questions that deterministic database rules could reject.

The final paragraph should state the contribution as a trustworthy healthcare
AI system, not simply as a neurosurgery tool.

### Related work

Add a formal related-work section with four paragraphs:

1. Healthcare LLM systems and RAG reliability, using Bang et al. as a close
   example of public-knowledge grounding.
2. Medical LLM agent benchmarks, using MedAgentBench as the benchmark-quality
   comparator.
3. Research reproducibility agents, using the Alzheimer's reproducibility
   paper as the closest application-neighbor.
4. Explainability, causal caution, and public-database knowledge infrastructure,
   using HISS causal-feature-selection and knowledge-graph examples.

### Methods

Restructure methods to mirror the example systems papers:

1. System overview and design requirements.
2. Deterministic routing and feasibility gate.
3. Registry-grounded planner interface.
4. Survey-design and causal-language guardrails.
5. Benchmark development and integrity verification.
6. Evaluation arms and metrics.
7. Cost metrics.
8. Aggregate-only NHANES case study.

Add cost metrics before submission:

| Metric | Definition |
| --- | --- |
| Model calls/task | Number of planner invocations divided by task count. |
| Token usage/task | Input + output tokens per task, if provider exposes usage. |
| Estimated API cost/task | Provider-reported or price-table-derived cost. |
| Wall-clock seconds/task | End-to-end elapsed runtime per task. |

### Results

Report results in four tables:

1. Development pilot performance by arm.
2. Guardrail error taxonomy and counts.
3. Cost/model-call efficiency table.
4. NHANES aggregate-only case-study output.

Move benchmark integrity to a short reproducibility subsection, and state clearly
that expert gold labels are pending.

### Discussion

Discussion should be organized around the special issue themes:

1. Trustworthy-by-design healthcare AI.
2. Explainability through deterministic refusals and guardrail findings.
3. Generalizability as an adapter design rather than an achieved external claim.
4. Low-cost operation through pre-generation filtering.
5. Limits: development-set overfitting, no expert-adjudicated benchmark yet,
   no complex survey variance, and incomplete verified registry.

## Experiments to add before submission

Minimum additional work for a defensible submission:

1. Add token/cost/time logging to live evaluation.
2. Run a same-model concurrent Arm A versus Arm B experiment on the existing
   10-task development set to remove the historical-baseline limitation.
3. Add a table showing model-call reduction, token reduction, estimated cost
   reduction, and hard-error-free rate.
4. Expand the registry for at least the variables used in the NHANES case study:
   `MCQ160F`, `RIAGENDR`, `WTINT2YR`, `SDMVPSU`, and `SDMVSTRA` should all be
   verified against source codebooks.

Recommended work for a stronger submission:

1. Recruit two experts and adjudicate the 30-task frozen benchmark.
2. Run concurrent same-model evaluation on the adjudicated 30-task benchmark.
3. Add inter-rater agreement and consensus-resolution reporting.
4. Implement complex survey variance estimation before reporting NHANES
   confidence intervals.

## Figures to create

1. Graphical abstract: trustworthy AI agent pipeline from clinical question to
   explainable refusal or reproducible analysis plan.
2. System architecture figure: router, registry, guardrails, planner provider,
   benchmark verifier, and case-study executor.
3. Evaluation flow figure: authored tasks, routing gate, planner invocation,
   guardrail scoring, and model-call accounting.
4. Results figure: model-call reduction and hard-error-free rate by arm.

## Cover-letter angle

The cover letter should emphasize that the manuscript directly fits three
collection topics: robust/generalizable/low-cost AI systems; benchmarking and
reproducibility; and AI agent-enabled proactive health. The key sentence should
be:

> This manuscript contributes a practical, open-source example of trustworthy
> healthcare AI engineering: rather than asking an LLM to generate unrestricted
> medical research plans, NeuroSurgEpiAgent uses deterministic database
> capability checks, variable provenance, and survey-design guardrails to reduce
> invalid generations before they occur.

