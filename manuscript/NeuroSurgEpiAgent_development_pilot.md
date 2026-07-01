# Toward Trustworthy and Low-Cost AI Agents for Healthcare Research Planning: Development and Evaluation of NeuroSurgEpiAgent

## Abstract

Healthcare research increasingly relies on large language model (LLM) agents to plan analyses of public clinical databases, but deployment is constrained by trustworthiness, reproducibility, and cost. We developed NeuroSurgEpiAgent, an open-source, resource-conscious AI-agent framework for healthcare research planning with public clinical databases, implemented first as an NHANES adapter and motivated by neurosurgical epidemiology. Trustworthiness is engineered through deterministic feasibility gating, database routing, a versioned variable registry with provenance labels, survey-design guardrails, structured outputs, benchmark integrity checks, and aggregate-only execution; interpretability comes from inspectable routing rationales, validation findings, provenance, and refusals, not model-internal explanation. The framework also blocks unsupported causal language from cross-sectional data without performing causal inference. In a 10-task development pilot, the gated arm achieved 10/10 routing accuracy, 10/10 feasibility assessment, 10/10 correct refusal, 7/10 hard-error-free plans, and 8/10 registry-code compliance, whereas an unconstrained baseline achieved 6/10 routing, 9/10 feasibility, 9/10 correct refusal, 0/10 hard-error-free plans, and 0/10 registry compliance. The gated arm made 70% fewer model calls (3 versus 10); token usage, latency, energy, and monetary cost were not measured, so low-cost is an architectural aim, not demonstrated cost-effectiveness. A 30-task benchmark was frozen with SHA-256 verification, but all gold assertions remain pending expert review. An aggregate-only NHANES 2017-2018 case study reproduced descriptive weighted self-reported stroke prevalence among 5,559 eligible participants (3.35% overall, 3.80% female, 2.87% male) without complex-survey confidence intervals or p values. Because the 10 tasks are an authored development set, the router was tuned on them, the baseline was reused nonconcurrently, and there is no external validation, findings support only technical feasibility, not generalizable performance.

## Introduction

Large language model (LLM) agents have emerged as promising tools for accelerating healthcare research, from drafting analysis plans to generating hypotheses and navigating complex biomedical data[1][2][3]. For investigators who use public clinical databases, the appeal is considerable: an agent could translate a clinical question into a feasible, design-aware analysis plan without the months of codebook and survey-method study that such databases usually demand. Realizing this promise at the point of deployment, however, is constrained by recurring barriers. Unconstrained LLM planners operate as black boxes, may hallucinate plausible but nonexistent variables, and incur avoidable computational cost when invoked on questions that a small number of deterministic rules could have rejected[4][5]. Evaluations of LLM responses about disease epidemiology have also identified accuracy concerns[6]. These limitations make it difficult for researchers and reviewers to trust agent-generated plans, reproduce them later, or compare them fairly across systems.

Public clinical databases magnify these risks because their valid use depends on database-specific design rules that are easy to overlook. NHANES, for example, requires survey weights matched to the target subpopulation (interview, mobile examination, or fasting subsample), clustering and stratification variables such as SDMVPSU and SDMVSTRA for variance estimation, multi-cycle weight rescaling when cycles are pooled, and careful provenance tracking for every variable used[10][11]. Cross-sectional surveys also constrain interpretation, so a plan stating that an exposure "causes" or "proves" an outcome overstates what the data can support. In our own development outputs, we observed that plausible-looking variable names and analytic choices routinely contradicted the local registry or the survey's weighting rules, producing plans that would fail silently if executed unchanged.

Existing LLM agent frameworks and benchmarks have advanced capabilities for data-driven scientific discovery, hypothesis generation, and automated reproducibility[4][7][8], and recent clinical work has shown the value of structured validation and rule-based constraints when testing hypotheses from electronic health records[3][9]. These efforts, however, generally validate outputs after generation or assume that a posed question is answerable, and they rarely encode the database-specific survey-design knowledge that public-database research requires. As a result, malformed or infeasible plans are detected only after an expensive model call, if at all, and the reasons behind a routing or feasibility decision often remain opaque to the user. A gap therefore remains for agents that prevent design violations before generation, make their decisions inspectable, and avoid spending model calls on questions a given database cannot answer.

To address this gap, we developed NeuroSurgEpiAgent, a trustworthy, reproducible, and resource-conscious AI-agent framework for healthcare research planning with public clinical databases, with NHANES as the implemented first adapter and neurosurgical epidemiology as the motivating clinical domain. The framework couples a deterministic feasibility gate and keyword-based database router, a versioned variable registry that records provenance for each entry, survey-design guardrails encoding weighting, design-variable, and causal-language rules, structured planner outputs, benchmark integrity checks with SHA-256 verification, and aggregate-only execution that writes no participant-level records. Generalizability is pursued as an adapter-oriented design goal, with NHANES implemented and other databases represented as planned adapters, rather than as a demonstrated cross-database capability. Interpretability is delivered through inspectable routing rationales, validation findings, provenance records, and explained refusals, not through model-internal explanation, and resource efficiency is pursued by deterministically refusing infeasible questions before the planner is invoked. These design choices map directly onto the trustworthy, generalizable, explainable, causally cautious, and low-cost healthcare AI themes that motivate this special issue.

The objective of this study is to examine, on a 10-task development pilot, whether deterministic pre-generation gating can reduce model calls and systematic planning errors while preserving structured, auditable outputs. We state at the outset that these 10 tasks are an authored development set rather than an independent sample, that the evaluated router was tuned against the same tasks, that the comparison baseline was reused nonconcurrently rather than regenerated, and that no external validation has been performed. Within these limits, we offer a candidate trustworthy architecture and a reproducibility package, comprising a frozen 30-task draft benchmark, an integrity verifier, and an aggregate-only NHANES case study, rather than a claim of demonstrated generalizable performance, clinical validity, or proven cost-effectiveness.

## Related Work

Recent healthcare AI research has emphasized grounding large language model (LLM) outputs in external knowledge to improve reliability. Retrieval-augmented generation (RAG) has become a prominent strategy for this goal: Bang and colleagues augmented a GPT-4o-mini base model with a hybrid retrieval and re-ranking pipeline over public Drug Utilization Review data to answer drug-contraindication questions, reporting substantial accuracy improvements over an ungrounded baseline across 300 question-answer pairs spanning age-group, pregnancy, and concomitant-medication categories[12]. Their system illustrates the broader principle that constraining model generation with curated external evidence can reduce uncertainty in safety-critical healthcare tasks. NeuroSurgEpiAgent shares the goal of grounding, but it applies this principle to analysis planning for public clinical databases rather than to question answering, and it substitutes deterministic database-capability checks and a versioned variable registry with provenance labels for open-ended document retrieval.

A second strand of work evaluates LLM agents within interactive medical environments. MedAgentBench provides a realistic virtual electronic health record (EHR) environment comprising 300 physician-authored, patient-specific tasks from 10 categories, and reports that the strongest model succeeded on roughly 70% of tasks, with substantial variation across task categories[13]. General-purpose scientific-agent benchmarks such as ScienceAgentBench[7] and BioDSA-1K[8] evaluate data-driven discovery and biomedical data-science workflows, and EHR-based hypothesis-testing frameworks have demonstrated the value of structured, rule-based validation when deriving findings from patient records[9]. These benchmarks, however, assess agents that execute actions inside patient records or that evaluate outputs after generation, and they generally assume that a posed task is actionable. NeuroSurgEpiAgent targets an earlier decision point: whether a proposed analysis of a public database is feasible and design-compliant before any plan is generated.

A third line of work uses LLM agents for research reproducibility. Dobbins and colleagues deployed a team of GPT-4o-based autonomous agents to reproduce findings from five highly cited Alzheimer's disease studies using the National Alzheimer's Coordinating Center dataset, reproducing approximately half of the extracted findings on average and candidly documenting cases in which agents diverged from the original studies in numeric values or statistical methods[3]. Agent Laboratory similarly positions LLM agents as end-to-end research assistants[4]. These systems are retrospective in orientation: they reproduce or validate analyses that already exist. NeuroSurgEpiAgent is prospective, producing analysis plans and aggregate descriptive outputs for new questions, and its current pilot does not attempt the kind of automated statistical reproduction that these reproducibility systems explore.

Across these strands, validation typically occurs after generation, posed questions are assumed to be answerable, and database-specific survey-design knowledge is rarely encoded explicitly. The gap NeuroSurgEpiAgent addresses is the prevention of design violations before generation, supported by inspectable routing rationales, validation findings, provenance labels, and explained refusals. The framework also encodes the design rules that public databases such as NHANES require, including survey-weight selection, clustering and stratification variables, and multi-cycle weight rescaling[10][11], and it blocks unsupported causal language from cross-sectional data without claiming to perform causal inference. Resource efficiency is pursued by deterministically refusing infeasible questions before the planner is invoked, which reduced model calls in the development pilot. We do not claim that this architecture has been externally validated, that it performs causal inference, or that the observed reduction in model calls constitutes demonstrated cost-effectiveness.

## Methods

### System Architecture

NeuroSurgEpiAgent v0.2 implements a three-layer architecture with deterministic pre-generation gating. The router layer uses keyword-based pattern matching without LLM invocation to route questions to databases (NHANES, CHARLS, GBD, SEER) and identify infeasible capability patterns. Routing precedence follows: explicit database names, infeasible patterns (surgery, procedures, histology, longitudinal recurrence), specialized intent patterns (regional burden, longitudinal trajectories), supported NHANES domain matches, and conservative unknown refusal.

The guardrail layer encodes NHANES design rules as deterministic checks: causal-language prohibition (words like "proves," "causes," "establishes"), PSU/strata variable requirements (SDMVPSU, SDMVSTRA), fasting subsample weight logic (WTSAF2YR versus WTMEC2YR), multi-cycle weight rescaling (WTXXX2YR/n_cycles), variable provenance (verified, illustrative, needs review), and cycle-coverage cross-checks. These rules fire deterministically and provide remediation guidance rather than auto-correcting plans.

The planner layer uses Claude Code Sonnet as a subprocess with structured JSON output, routed via CC-Switch to the GLM-4.7 model. The planner receives the research question, variable registry context (14 entries with name, source_variable, source_module, status, nhanes_cycles), and routing context (database, feasibility, rationale). The planner generates AnalysisPlan objects validated against a Pydantic schema with required fields (title, question, database, cycles, feasible) and optional fields (outcome, exposures, covariates, uses_fasting_subsample, design_vars, steps, causal_claims, rationale, guardrail_notes).

### Task Set and Registry

The task set comprised 10 authored neurosurgical epidemiology research questions: 3 stroke questions (2 expected feasible, 1 infeasible due to surgical procedure data), 3 traumatic brain injury questions (0 expected feasible, covering lifetime prevalence, global burden, and longitudinal trajectories), 3 tumor questions (0 expected feasible, covering registry survival, histology capture, and global burden), and 1 cross-domain stroke metabolic question (expected feasible). Tasks were authored by the development team based on anticipated system capabilities rather than independent expert review, representing a development set rather than an external validation sample.

The nhanes_demo.yaml variable registry contained 14 entries. Five were marked verified: SDMVPSU, SDMVSTRA, WTMEC2YR, RIDAGEYR, and RIAGENDR. Eight were illustrative: RIDRETH1, BMXBMI, BMXWAIST, BPXSY1, SMQ020, MCQ160F, LBXGLU, and LBXINS. One placeholder, TBD_CONFIRM_ITEM for TBI history, was marked needs review. The illustrative and needs-review labels mean the registry is a development artifact rather than an authoritative NHANES codebook.

### Draft Benchmark Freezing and Adjudication Workflow

After the 10-task development pilot, we created a larger 30-task benchmark draft spanning stroke, tumor, traumatic brain injury, subarachnoid hemorrhage, spine, disparities, global burden, pituitary, and hydrocephalus questions. The benchmark was frozen as version 0.1.0 with a sidecar SHA-256 digest (`0d8c88e9ee980581dacacb1bc89bfc753a7c9954cb013ff85f781b6fec3a9a85`), schema validation, declared task count checks, unique task identifier checks, and an explicit review status of `needs_expert_review` for all 30 tasks. This benchmark is not treated as a validated gold standard in the present manuscript. Instead, it is reported as a reproducibility artifact and as the substrate for subsequent independent adjudication by at least two domain reviewers: one neurosurgery or neurology expert and one epidemiology or survey-methods expert.

### Experimental Design

The pilot compared two arms: Arm A (v0.2 deterministic gate: router, constrained planner, and guardrails) versus Arm B (v0.1 unconstrained generation baseline). Both arms used GLM-4.7 through the Claude Code Sonnet role routed by CC-Switch. Arm A applied deterministic router pre-filtering before generation and guardrail validation afterward. Arm B used a baseline prompt without the routing decision or registry constraints; the same guardrail engine was applied afterward for evaluation. The Arm B outputs were reused from v0.1 rather than regenerated concurrently with v0.2, representing a methodological limitation.

### Evaluation Metrics

Metrics included routing accuracy (correct database selection), feasibility assessment (correct identification of feasible versus infeasible questions), hard error-free rate (plans without severity=ERROR guardrail findings), correct refusal (infeasible tasks appropriately refused without planner invocation), registry code compliance (variables using verified or illustrative status rather than unresolved/needs review), and plan reconstructability (all plans parseable as valid AnalysisPlan objects). Resource efficiency was measured as model call count; token usage and monetary cost were not measured.

### Aggregate-Only NHANES Case Study

To demonstrate that the repository can support reproducible public-data execution without committing participant-level records, we implemented an aggregate-only NHANES 2017-2018 case study. The script downloads public `DEMO_J.XPT` and `MCQ_J.XPT` files from CDC NHANES, verifies local SHA-256 hashes, reads XPT files with pandas, merges records in memory by `SEQN`, and writes only aggregate JSON and Markdown outputs. The case study used `MCQ160F` as the self-reported stroke history item, `RIAGENDR` for sex strata, and `WTINT2YR` for descriptive weighted prevalence among participants with yes/no `MCQ160F` values and positive interview weights. We did not compute confidence intervals or p values because the lightweight case study does not implement Taylor-linearized complex survey variance using strata and PSU; the output is therefore descriptive and exploratory rather than inferential.

### Guardrail Error Categories

Guardrail findings were classified by severity (ERROR, WARNING) and error code. ERROR codes included: CAUSAL_LANGUAGE (prohibited causal words), FASTING_WEIGHT_MISMATCH (fasting subsample with WTMEC2YR instead of WTSAF2YR), UNRESOLVED_VARIABLE (variables with status "needs review"), WEIGHT_RESCALE (incorrect multi-cycle weight expression), NHANES_PSU (incorrect PSU variable), NHANES_STRATA (incorrect strata variable), FASTING_SUBSAMPLE_UNDECLARED (fasting labs without fasting declaration), and NO_CYCLES (missing cycle declarations). WARNING codes included ILLUSTRATIVE_VARIABLE (variables not verified against codebooks), CYCLE_COVERAGE (requested cycles not in variable registry), and FASTING_WEIGHT_UNEXPECTED (WTSAF2YR without fasting subsample).

## Results

### Overall Performance

Arm A achieved 10/10 routing accuracy (100%), 10/10 feasibility assessment (100%), 7/10 hard-error-free (70%), 10/10 correct refusal (100%), 8/10 registry code compliance (80%), and 10/10 plan reconstructability (100%). Arm B achieved 6/10 routing accuracy (60%), 9/10 feasibility assessment (90%), 0/10 hard-error-free (0%), 9/10 correct refusal (90%), 0/10 registry code compliance (0%), and 10/10 plan reconstructability (100%). Arm A made 3 model calls (for the 3 feasible tasks) compared to Arm B's 10 model calls (for all tasks), representing a 70% reduction in model calls.

### Arm A Error Analysis

Arm A produced 3 tasks with hard errors: stroke_01, stroke_03, and cross_01. Stroke_01 showed FASTING_WEIGHT_MISMATCH (fasting subsample with WTMEC2YR instead of WTSAF2YR) and 9 ILLUSTRATIVE_VARIABLE warnings. Stroke_03 showed UNRESOLVED_VARIABLE (sarcopenia status marked "needs review" with NOT_IN_REGISTRY source) and 3 ILLUSTRATIVE_VARIABLE warnings. Cross_01 showed FASTING_WEIGHT_MISMATCH, WEIGHT_RESCALE (unrecognized weight expression format), a registry-code failure (composite source string "LBXGLU, LBXINS" not triggering UNRESOLVED_VARIABLE), and multiple ILLUSTRATIVE_VARIABLE warnings. Two tasks failed registry compliance because cross_01 used composite source strings without triggering the unresolved-variable guardrail.

Error occurrence counts across the 10 Arm A tasks: FASTING_WEIGHT_MISMATCH appeared in 2 tasks, UNRESOLVED_VARIABLE appeared in 1 task, and WEIGHT_RESCALE appeared in 1 task. All three errors occurred in feasible tasks that proceeded to planner invocation; the 7 infeasible tasks were correctly refused by the deterministic router without model calls.

### Arm B Error Analysis

Arm B produced errors across all 10 tasks. Error types and affected task counts: CAUSAL_LANGUAGE errors in 1 task, unresolved-variable errors in 8 tasks, weight-rescaling errors in 3 tasks, fasting-weight mismatches in 1 task, missing PSU/strata variables in 2 tasks, and routing errors in 4 tasks. The lower routing accuracy (6/10) reflected incorrect database assignments: TBI and tumor questions were routed to NHANES despite requiring planned adapters (GBD, CHARLS, SEER) not active in the MVP.

### Task-Specific Results

The 3 feasible tasks (stroke_01, stroke_03, cross_01) were correctly routed to NHANES and marked feasible by both arms. Arm A's 7 infeasible tasks were deterministically refused by the router without planner invocation. Arm B attempted planning for all 10 tasks, with 1 task incorrectly marked feasible (tbi_01, a TBI lifetime prevalence question with no comparable NHANES item). The routing errors in Arm B included incorrect NHANES assignments for tbi_02, tbi_03, tumor_01, and tumor_03, which should have been routed to planned databases (GBD, CHARLS, SEER).

### Resource Efficiency

The 70% reduction in model calls derived entirely from deterministic refusal of infeasible tasks without planner invocation. Arm A called the planner for 3 feasible tasks (stroke_01, stroke_03, cross_01). Arm A's 7 infeasible tasks received immediate refusal responses from the router. Arm B called the planner for all 10 tasks, including the 7 infeasible tasks that generated malformed plans. Token usage and monetary cost per call were not measured; only model call count was tracked.

### Benchmark Integrity Artifacts

The 30-task draft benchmark integrity verifier passed all checks. The sidecar expected SHA-256 digest matched the actual benchmark file digest (`0d8c88e9ee980581dacacb1bc89bfc753a7c9954cb013ff85f781b6fec3a9a85`), the declared task count matched the 30 tasks present in the YAML file, all task identifiers were unique, all tasks carried the consistent `needs_expert_review` status, and the frozen timestamp was `2026-06-29T00:00:00Z`. These checks establish file integrity and reproducibility of the task set, not correctness of the authored gold assertions.

### Aggregate-Only NHANES Case Study Results

The NHANES case-study runner downloaded and verified two public files: `DEMO_J.XPT` (3,412,720 bytes; SHA-256 `c0b46e0345ea19404928656277c8b0d10b0cca348a9b2fe4fc3c67e8b7ee73ec`) and `MCQ_J.XPT` (5,420,800 bytes; SHA-256 `79c50c805a377fcd61d44fae8b86a16af0a5741f8b1aeebda918d7d743c68f98`). `DEMO_J` contained 9,254 rows, `MCQ_J` contained 8,897 rows, and the in-memory merge by `SEQN` produced 8,897 records. Among 5,559 participants with yes/no `MCQ160F` responses, 273 reported ever being told they had a stroke and 5,286 did not. Descriptive weighted prevalence using `WTINT2YR` was 3.35% overall. By sex, weighted prevalence was 3.80% among females (137 yes, 2,726 no; eligible n=2,863) and 2.87% among males (136 yes, 2,560 no; eligible n=2,696). The generated case-study directory contains only `results.json`, `provenance.json`, and `report.md`; raw XPT files remain in a gitignored cache and no merged participant-level dataset is written.

### Development-Set Limitations

These results reflect iterative development-set optimization. The v0.2 router rules were refined against these same 10 tasks during system development, creating potential overfitting where the 100% routing accuracy and 100% feasibility assessment may not generalize to unseen question patterns. The tasks were authored by the development team rather than independent experts, potentially overrepresenting patterns the system was designed to handle. Baseline outputs were reused from v0.1 rather than regenerated concurrently with v0.2, introducing potential version mismatch and temporal inconsistency. No statistical significance testing was performed; results are descriptive only.

## Discussion

This development pilot provides candidate evidence that deterministic pre-generation gating can improve efficiency and reduce systematic NHANES design errors in research planning. The Arm A architecture eliminated several error patterns that appeared in Arm B: incorrect database routing, inappropriate feasibility declarations, missing PSU/strata variables, and causal language overstatement. The 70% reduction in model calls while maintaining routing accuracy and feasibility assessment suggests the approach may be promising for scaling to larger task volumes, though generalizability remains unknown without proper external validation.

The additional artifacts created after the development pilot strengthen the reproducibility package but do not eliminate the need for external validation. The frozen 30-task benchmark, sidecar digest, integrity verifier, preregistered analysis plan, and adjudication templates make the next evaluation auditable before model runs occur. The NHANES case study shows that the repository can execute a public-data workflow and preserve aggregate-only outputs with source hashes and row-count provenance. Together, these elements move the project from a prompt-and-output demonstration toward a reproducible research software artifact. However, neither artifact should be overinterpreted: the benchmark remains unaudited by independent experts, and the case study reports descriptive prevalence without complex survey variance.

The persistent Arm A errors (fasting-weight mismatches, unresolved variables, weight-rescaling issues) reflect limitations of the current guardrail implementation and variable registry. The fasting-weight errors indicate the guardrail correctly detected the violation but the planner nevertheless generated malformed plans, suggesting the guardrail should block planning rather than post-hoc validation. The unresolved-variable errors reflect gaps in the variable registry, particularly for complex constructs like sarcopenia that require combining multiple NHANES variables not present in the registry. The weight-rescaling errors indicate the planner did not consistently follow multi-cycle pooling rules.

The development-set nature of these results necessitates cautious interpretation. The perfect routing and feasibility performance may be optimistic given that the v0.2 router was refined against these specific 10 tasks. Real-world question patterns from independent researchers may differ substantially from the authored development set. The reuse of v0.1 baseline outputs rather than concurrent generation introduces uncertainty about whether the performance differences reflect architectural improvements or model version drift.

### Threats to Validity

The primary threat is development-set overfitting. The router heuristics were tuned to patterns present in these 10 tasks, such as explicit NHANES mentions, surgery/procedure keywords, and specialized intent phrasing. Performance on unseen questions with different formulations may be lower. The task authorship bias (development team rather than independent experts) may overrepresent anticipated use cases and underrepresent edge cases. The baseline reuse limitation (v0.1 outputs not regenerated) creates potential version mismatch and temporal inconsistency. The registry limitations (8 of 14 entries illustrative, 1 needs review) mean some variable mappings remain unverified against actual NHANES codebooks. The aggregate case study also has epidemiologic limitations: it uses self-reported stroke history, reports descriptive weighted prevalence only, and does not estimate confidence intervals because survey-design variance estimation has not yet been implemented.

### Candidate Contributions

This work contributes a candidate architecture for pre-generation filtering in NHANES research planning, demonstrating that deterministic routers can identify infeasible questions without model invocation and that domain-specific guardrails can systematically enforce survey-design rules. However, these results do not provide evidence for generalizable performance across question types, clinical validity of generated plans, comparison to other systems or manual planning, or cost-effectiveness in production settings. Novelty requires systematic literature review beyond this development pilot.

### Next Steps

To address these limitations, the next experiment should complete proper external validation with methodological rigor: obtain dual-expert review of the frozen 30-task benchmark before model runs begin, preserve hashes and raw outputs for full reproducibility, use concurrent same-model arms rather than reusing historical outputs, justify sample size before inference, and employ paired descriptive comparisons with inferential analysis only after adequate power. The NHANES case-study module should also be extended to implement survey-design variance estimation before any epidemiologic confidence intervals or subgroup comparisons are reported.

## Conclusion

NeuroSurgEpiAgent provides a reproducible open-source framework for deterministic gating, registry-based variable control, guardrail validation, benchmark freezing, and aggregate-only public-data execution in neurosurgical epidemiology planning. The v0.2 development pilot showed a 70% reduction in model calls and fewer systematic planning errors on 10 authored tasks, and the repository now includes a frozen 30-task draft benchmark plus an executed NHANES 2017-2018 stroke prevalence demonstration. These findings support technical feasibility, not clinical utility or generalizable agent performance. Independent expert adjudication, concurrent held-out evaluation, expanded verified variable registries, and complex survey variance estimation are required before stronger publication claims can be made.

## Data and Code Availability

The source code, experimental configuration, benchmark integrity verifier, adjudication templates, and evaluation data for this pilot are available at [repository URL to be added]. The raw model outputs, task definitions, and detailed guardrail findings are preserved in the experiments/pilot_glm47_gate_v02/ directory. Variable registry specifications, router rules, guardrail implementations, statistical utilities, and case-study code are documented in the src/neurosurg_epi_agent/ module. The aggregate NHANES case-study outputs are preserved in case_studies/nhanes_stroke_2017_2018/ as results.json, provenance.json, and report.md. Public NHANES XPT files are downloaded from CDC at runtime into a gitignored cache and are not committed to the repository.

## Ethics Statement

This development study processed authored research questions and generated plans. The NHANES case study used publicly released deidentified survey files and wrote only aggregate summaries, source hashes, and row-count provenance; no merged participant-level dataset or protected health information was committed to the repository. No clinical decision support or patient-care intervention was involved. Future evaluations involving human expert raters, restricted clinical data, or nonpublic datasets may require institutional review according to local policy.

## Conflicts of Interest

The authors declare no conflicts of interest related to this work.

## Funding

[placeholder for funding acknowledgments]

## References

1. Titus AJ. NHANES-GPT: Large Language Models (LLMs) and the Future of Biostatistics. medRxiv. 2023. doi:10.1101/2023.12.13.23299830.

2. Li D, He Y, Hu Y, Tian Y, Li J. Can LLM Agents Generate Real-World Evidence? Evaluating Observational Studies in Medical Databases. arXiv:2603.22767. 2026.

3. Dobbins N, Xiong C, Lan K, Yetisgen M. Large Language Model-Based Agents for Automated Research Reproducibility: An Exploratory Study in Alzheimer's Disease. arXiv:2505.23852. 2025.

4. Schmidgall S, Su Y, Wang Z, et al. Agent Laboratory: Using LLM Agents as Research Assistants. arXiv:2501.04227. 2025.

5. Peasley D, Kuplicki R, Sen S, Paulus M. Leveraging Large Language Models and Agent-Based Systems for Scientific Data Analysis: Validation Study. JMIR Ment Health. 2025;12:e68135. doi:10.2196/68135.

6. Zhu K, Zhang J, Klishin A, et al. Evaluating the Accuracy of Responses by Large Language Models for Information on Disease Epidemiology. Pharmacoepidemiol Drug Saf. 2025;34(2):e70111. doi:10.1002/pds.70111.

7. Chen Z, Chen S, Ning Y, et al. ScienceAgentBench: Toward Rigorous Assessment of Language Agents for Data-Driven Scientific Discovery. arXiv:2410.05080. 2024.

8. Wang Z, Danek B, Sun J. BioDSA-1K: Benchmarking Data Science Agents for Biomedical Research. arXiv:2505.16100. 2025.

9. Gim N, Gim I, Jiang Y, et al. An LLM-assisted framework for accelerated and verifiable clinical hypothesis testing from electronic health records. medRxiv. 2026. doi:10.64898/2026.02.10.26346008.

10. Centers for Disease Control and Prevention, National Center for Health Statistics. NHANES Weighting Tutorial. Accessed June 29, 2026. https://wwwn.cdc.gov/nchs/nhanes/tutorials/weighting.aspx

11. Centers for Disease Control and Prevention, National Center for Health Statistics. NHANES Sample Design Tutorial. Accessed June 29, 2026. https://wwwn.cdc.gov/nchs/nhanes/tutorials/sampledesign.aspx

12. Bang B, Yoon J, Chang DJ, Park S, Lee YO. Retrieval Augmented Large Language Model System for Comprehensive Drug Contraindications. arXiv:2508.06145. 2025.

13. Jiang Y, Black KC, Geng G, et al. MedAgentBench: A Realistic Virtual EHR Environment to Benchmark Medical LLM Agents. arXiv:2501.14654. 2025.
