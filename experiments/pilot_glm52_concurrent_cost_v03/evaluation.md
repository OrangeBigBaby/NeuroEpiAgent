# NeuroSurgEpiAgent Evaluation Report

**Generated:** 2026-07-01T00:14:13.350298+00:00 UTC  
**Package Version:** 0.1.0  
**Model Label:** claude-sonnet-4-6 / GLM-5.2 via CC-Switch  

## Provenance Hashes

- **Prompt:** `1de5eab65e8e0c9a...`  
- **Registry:** `d3d66aa464ac14c7...`  
- **Task Set:** `fa547777bd1e349a...`  

## Summary Statistics (Per-Arm)

### ARM_A

| Metric | Passed | Total | Proportion |
|--------|--------|-------|------------|
| database_routing | 9 | 10 | 90.00% |
| feasibility | 9 | 10 | 90.00% |
| hard_error_free | 8 | 10 | 80.00% |
| correct_refusal | 9 | 10 | 90.00% |
| variable_codes | 9 | 10 | 90.00% |
| manifest_reconstructability | 9 | 10 | 90.00% |

### ARM_B

| Metric | Passed | Total | Proportion |
|--------|--------|-------|------------|
| database_routing | 5 | 10 | 50.00% |
| feasibility | 8 | 10 | 80.00% |
| hard_error_free | 7 | 10 | 70.00% |
| correct_refusal | 8 | 10 | 80.00% |
| variable_codes | 0 | 10 | 0.00% |
| manifest_reconstructability | 8 | 10 | 80.00% |

## Per-Task Details

| Task ID | Domain | Arm | Database Routing | Feasibility | Hard Error Free |
|---------|--------|------|-------------------|--------------|-----------------|
| stroke_01 | stroke | arm_a | PASS | PASS | FAIL |
| stroke_01 | stroke | arm_b | PASS | PASS | PASS |
| stroke_02 | stroke | arm_a | PASS | PASS | PASS |
| stroke_02 | stroke | arm_b | PASS | PASS | PASS |
| stroke_03 | stroke | arm_a | FAIL | FAIL | FAIL |
| stroke_03 | stroke | arm_b | PASS | PASS | FAIL |
| tbi_01 | tbi | arm_a | PASS | PASS | PASS |
| tbi_01 | tbi | arm_b | FAIL | FAIL | FAIL |
| tbi_02 | tbi | arm_a | PASS | PASS | PASS |
| tbi_02 | tbi | arm_b | FAIL | PASS | PASS |
| tbi_03 | tbi | arm_a | PASS | PASS | PASS |
| tbi_03 | tbi | arm_b | FAIL | PASS | PASS |
| tumor_01 | tumor | arm_a | PASS | PASS | PASS |
| tumor_01 | tumor | arm_b | FAIL | PASS | PASS |
| tumor_02 | tumor | arm_a | PASS | PASS | PASS |
| tumor_02 | tumor | arm_b | PASS | PASS | PASS |
| tumor_03 | tumor | arm_a | PASS | PASS | PASS |
| tumor_03 | tumor | arm_b | FAIL | FAIL | FAIL |
| cross_01 | stroke | arm_a | PASS | PASS | PASS |
| cross_01 | stroke | arm_b | PASS | PASS | PASS |

## Experiment Coverage

- **Expected outputs:** 20 (10 tasks x 2 arms)  
- **Outputs present:** 20  
- **Coverage:** 100.0%  

> **Note:** This is a pilot evaluation with draft tasks. Results are not suitable for significance claims or publication.
