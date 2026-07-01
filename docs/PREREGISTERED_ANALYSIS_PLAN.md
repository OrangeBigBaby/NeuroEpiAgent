# Preregistered Analysis Plan for NeuroSurgEpiAgent Benchmark Evaluation

**Plan Version**: 1.0
**Plan ID**: NEPIBENCH_ANALYSIS_001
**Status**: PREREGISTERED (Authored - Pending Expert Review)
**Created**: 2026-06-29
**Authors**: NeuroSurgEpiAgent Development Team

---

## Disclaimer

**This analysis plan is authored by the development team and reflects planned analyses for benchmark evaluation. These analyses are exploratory (n=30 tasks) and have NOT undergone independent statistical review or expert adjudication. Results from these analyses are NOT suitable for clinical claims, publication assertions, or comparative effectiveness statements without independent validation and expert review per `benchmarks/GOLD_STANDARD_PROCESS.md`.**

---

## Research Questions

### Primary Questions

1. **PQ-001**: Does the full NeuroSurgEpiAgent system (with router, registry, and guardrails) achieve higher accuracy on database routing decisions compared to an unconstrained baseline?

2. **PQ-002**: Does the full system achieve higher accuracy on feasibility assessment compared to an unconstrained baseline?

### Secondary Questions

1. **SQ-001**: What is the magnitude of improvement (risk difference) between the full system and individual ablation configurations?

2. **SQ-002**: How does the performance of different ablation configurations rank relative to each other?

3. **SQ-003**: What is the inter-rater reliability between expert adjudicators when evaluating the same tasks?

### Exploratory Questions

1. **EQ-001**: Which clinical domains show the largest performance differences between arms?

2. **EQ-002**: Are error types systematically different across ablation configurations?

---

## Hypotheses

### Primary Hypotheses

1. **H-001**: The full system will have higher accuracy on database routing than the unconstrained baseline.
   - **Direction**: Greater
   - **Test**: McNemar exact test (paired)
   - **Alpha**: 0.05 (two-sided)

2. **H-002**: The full system will have higher accuracy on feasibility assessment than the unconstrained baseline.
   - **Direction**: Greater
   - **Test**: McNemar exact test (paired)
   - **Alpha**: 0.05 (two-sided)

### Secondary Hypotheses

1. **H-003**: The full system will show higher accuracy than any single-component ablation (no_router, no_registry, no_guardrails).
   - **Direction**: Greater
   - **Test**: Risk difference with bootstrap CI
   - **Alpha**: 0.05 (Holm-corrected)

---

## Study Design

### Design Type

**Paired comparison design** with ablation study component.

- **Primary design**: Paired comparison of 5 arms on the same 30 tasks
- **Secondary design**: Inter-rater reliability study for expert adjudication

### Sample Size

- **n = 30 tasks**
- **Justification**: Exploratory study with draft benchmark. Power analysis not conducted as this is an authored exploratory analysis.
- **Note**: This sample size is NOT sufficient for confirmatory conclusions. Results are exploratory and pending expert adjudication.

### Unit of Analysis

- **Primary unit**: Individual task (paired across arms)
- **Secondary unit**: Expert rating (paired across raters)

### Randomization

- **Task order**: Fixed (deterministic order from benchmark file)
- **No randomization**: This is an analysis of deterministic system outputs on fixed benchmark tasks

### Blinding

- **Rater blinding**: Planned for expert adjudication phase (blinded to system identity)
- **Analyst blinding**: Not applicable (automated analysis)

---

## Data Sources

### Primary Sources

1. **DS-001**: Benchmark tasks file (`benchmarks/tasks.v0.1.0.yaml`)
   - **Type**: Benchmark tasks
   - **Version**: 0.1.0 (DRAFT)
   - **n_observations**: 30 tasks
   - **Inclusion criteria**: All tasks with review_status='needs_expert_review'

2. **DS-002**: Evaluation results from 5 experimental arms
   - **Type**: Evaluation results
   - **Arms**: full_gate, no_router, no_registry, no_guardrails, unconstrained_baseline
   - **n_observations**: 30 tasks × 5 arms = 150 paired observations

3. **DS-003**: Expert ratings (future - not collected)
   - **Type**: Expert ratings
   - **n_observations**: 30 tasks × 2 raters = 60 paired ratings
   - **Status**: NOT COLLECTED - Pending expert recruitment

---

## Outcome Measures

### Primary Outcomes

1. **O-001**: Database routing accuracy
   - **Type**: Binary (correct/incorrect)
   - **Definition**: Match between system's `database` output and `expected_database` from benchmark
   - **Measurement**: Automated comparison
   - **Range**: 0 (incorrect) to 1 (correct)

2. **O-002**: Feasibility assessment accuracy
   - **Type**: Binary (correct/incorrect)
   - **Definition**: Match between system's `feasible` output and `expected_feasible` from benchmark
   - **Measurement**: Automated comparison
   - **Range**: 0 (incorrect) to 1 (correct)

### Secondary Outcomes

1. **O-003**: Hard error rate
   - **Type**: Binary (error-free/error)
   - **Definition**: System crashed, timed out, or raised exception
   - **Measurement**: Error logging
   - **Range**: 0 (error) to 1 (error-free)

2. **O-004**: Variable code compliance
   - **Type**: Binary (compliant/non-compliant)
   - **Definition**: All variable codes present in allowed registry set
   - **Measurement**: Registry validation
   - **Range**: 0 (non-compliant) to 1 (compliant)

3. **O-005**: Expert agreement (future)
   - **Type**: Nominal (agreement categories)
   - **Definition**: Expert rater agreement on correctness
   - **Measurement**: Inter-rater reliability
   - **Range**: -1 (complete disagreement) to 1 (complete agreement)

---

## Planned Analyses

### Analysis 001: Primary Paired Comparison (Full vs Baseline)

**Purpose**: Test primary hypotheses H-001 and H-002

**Method**: McNemar exact test (two-sided)

**Parameters**:
- Confidence level: 95%
- Two-sided: Yes
- Discordant pairs: Use binomial distribution

**Data Requirements**:
- Source: DS-002 (evaluation results)
- Outcomes: O-001 (database routing), O-002 (feasibility)
- Arms: full_gate vs unconstrained_baseline

**Assumptions**:
- Paired observations (same tasks)
- Binary outcomes
- Independence across tasks

**Decision Rule**:
- Reject H0 if p < 0.05 (two-sided)
- Report exact p-values (never p = 0.0)

**Multiple Testing Correction**:
- Holm-Bonferroni across 2 primary outcomes
- Family-wise alpha: 0.05

**Missing Data Handling**:
- Complete case analysis (exclude tasks with errors in either arm)

**Output**:
- McNemar p-value (original and Holm-corrected)
- Discordant pair counts
- 2×2 contingency tables

---

### Analysis 002: Alation Study Risk Differences

**Purpose**: Quantify performance differences between ablation configurations

**Method**: Risk difference with bootstrap confidence intervals

**Parameters**:
- Bootstrap samples: 10,000
- Confidence level: 95%
- Random seed: 20260628 (fixed for reproducibility)

**Data Requirements**:
- Source: DS-002 (evaluation results)
- Outcomes: O-001, O-002, O-003
- Comparisons: All pairwise comparisons among 5 arms

**Assumptions**:
- Paired observations
- Bootstrap distribution approximates sampling distribution

**Decision Rule**:
- CI excludes 0 → statistically significant difference
- Report magnitude and direction of effects

**Multiple Testing Correction**:
- Holm-Bonferroni across all comparisons
- Report both raw and corrected p-values

**Missing Data Handling**:
- Pairwise deletion (include all valid pairs for each comparison)

**Output**:
- Risk differences with 95% bootstrap CIs
- Wilson CIs for individual arm proportions
- Effect sizes

---

### Analysis 003: Descriptive Statistics by Domain

**Purpose**: Exploratory analysis of performance patterns across clinical domains

**Method**: Descriptive statistics with Wilson confidence intervals

**Parameters**:
- Confidence level: 95%
- Group by: Clinical domain (9 domains)

**Data Requirements**:
- Source: DS-001 (tasks), DS-002 (results)
- Outcomes: O-001, O-002, O-003
- Grouping variable: domain

**Assumptions**:
- Sufficient sample size per domain for reasonable CI width
- Note: Some domains have small n (n=2-3), CIs will be wide

**Decision Rule**:
- No formal hypothesis testing (exploratory)
- Report descriptive patterns

**Output**:
- Proportions with Wilson 95% CIs by domain
- Sample sizes by domain
- Exploratory observations

---

### Analysis 004: Inter-Rater Reliability (Future)

**Purpose**: Quantify agreement between expert adjudicators

**Method**: Cohen's kappa (unweighted)

**Parameters**:
- Confidence level: 95%
- Weight matrix: None (unweighted)

**Data Requirements**:
- Source: DS-003 (expert ratings) - NOT COLLECTED
- Outcomes: O-005 (expert agreement)
- Missing data handling: Explicit undefined case handling

**Assumptions**:
- Independent ratings
- Categorical outcomes

**Decision Rule**:
- kappa > 0.8: excellent agreement
- kappa 0.6-0.8: substantial agreement
- kappa < 0.6: less than substantial agreement

**Output**:
- Cohen's kappa with 95% CI
- Observed vs expected agreement
- Warning if undefined cases present

---

## Data Management

### Data Collection

- **Automation level**: Fully automated (LLM API calls)
- **Validation**: Post-collection checksums and schema validation

### Data Cleaning

1. **Schema validation**: Verify all evaluation results conform to expected schema
2. **Task alignment**: Ensure paired observations aligned by task_id
3. **Outcome extraction**: Extract binary outcomes from complex result objects
4. **Error handling**: Flag and document any errors or missing data

### Quality Control

1. **Completeness check**: All 5 arms have results for all 30 tasks (or document missing)
2. **Identifier uniqueness**: All task_ids are unique and properly paired
3. **Outcome range validation**: Binary outcomes are 0/1 or True/False
4. **Reproducibility check**: Fixed seeds produce identical results

---

## Reporting Standards

### Effect Size Measures

- **Primary**: Risk differences (proportion differences)
- **Secondary**: McNemar discordant counts
- **Exploratory**: Domain-specific proportions

### Confidence Intervals

- **Report CIs**: Yes
- **Confidence level**: 95%
- **Method**: Wilson for proportions, bootstrap for risk differences
- **Always report**: Point estimate + CI + sample size

### Precision

- **Decimal places**: 4 for p-values, 4 for proportions/risk differences
- **p-value format**: Never report p = 0.0; use "p < 1e-10" for extreme values
- **Sample sizes**: Always report exact denominators

### Planned Tables

1. **T-001**: Primary paired comparison (full vs baseline)
   - McNemar test results, risk differences, CIs

2. **T-002**: Ablation study summary
   - All pairwise comparisons, risk differences, CIs

3. **T-003**: Domain-specific performance
   - Proportions with Wilson CIs by domain

4. **T-004**: Inter-rater reliability (future)
   - Cohen's kappa, agreement breakdown

### Planned Figures

1. **F-001**: Performance comparison plot
   - Bar chart of proportions with CIs by arm

2. **F-002**: Risk difference plot
   - Forest plot of pairwise risk differences with CIs

---

## Known Limitations

1. **L-001: Small sample size**
   - **Impact**: Low power, wide confidence intervals
   - **Mitigation**: Report CIs, emphasize exploratory nature

2. **L-002: Authored gold standard**
   - **Impact**: Results not independently validated
   - **Mitigation**: Clear disclaimers, pending expert adjudication

3. **L-003: Draft benchmark status**
   - **Impact**: Cannot support scientific claims
   - **Mitigation**: Status labels, disclaimers in all outputs

4. **L-004: Multiple testing inflation**
   - **Impact**: Increased Type I error rate
   - **Mitigation**: Holm-Bonferroni correction, report both raw and corrected

5. **L-005: Exploratory domain analysis**
   - **Impact**: Small n per domain, wide CIs
   - **Mitigation**: Report as exploratory, no formal inference

6. **L-006: Deterministic system outputs**
   - **Impact**: No variability within arm (same task produces same output)
   - **Mitigation**: Paired tests account for this

7. **L-007: No clinical validation**
   - **Impact**: Results reflect technical correctness, not clinical utility
   - **Mitigation**: Clear scope definition, no clinical claims

---

## Timeline

- **Start date**: 2026-06-29
- **Data collection**: Automated (immediate upon execution)
- **Analysis execution**: Immediate (automated pipeline)
- **Report generation**: 2026-06-29
- **Expert review**: NOT SCHEDULED (pending expert recruitment)

---

## Dependencies

### Software Dependencies

- Python 3.8+
- `neurosurg_epi_agent.statistics` module
- `pytest` for testing
- Standard libraries only (math, random, json, pathlib)

### External Data Dependencies

- `benchmarks/tasks.v0.1.0.yaml` (frozen benchmark)
- Evaluation outputs from 5 experimental arms
- Expert rating CSV files (future)

---

## Documentation

### Analysis Code

- **Statistics module**: `src/neurosurg_epi_agent/statistics.py`
- **CLI interface**: `src/neurosurg_epi_agent/stats_cli.py`
- **Tests**: `tests/test_statistics.py`

### Documentation

- **This document**: `docs/PREREGISTERED_ANALYSIS_PLAN.md`
- **Schema**: `docs/analysis_plan_schema.v1.json`
- **CLI usage**: `python -m neurosurg_epi_agent.stats_cli --help`

---

## Revision History

- **v1.0** (2026-06-29): Initial preregistered analysis plan (authored by development team)

---

## Status and Next Steps

**Current Status**: PREREGISTERED (Authored)

**Before Scientific Use**:
1. Independent statistical review of this analysis plan
2. Expert recruitment and adjudication per `benchmarks/GOLD_STANDARD_PROCESS.md`
3. Completion of expert inter-rater reliability study
4. Validation of all assumptions and data quality checks
5. External replication of findings

**Next Steps**:
1. Execute evaluation runs for 5 arms (dry-run mode for testing)
2. Execute statistical analyses per this plan
3. Generate tables and figures
4. Document results and limitations
5. Prepare for expert review process

---

**This analysis plan is a living document. Revisions will be versioned and dated. All results from analyses following this plan must be considered exploratory and pending independent validation.**