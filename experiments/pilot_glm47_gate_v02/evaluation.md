# NeuroSurgEpiAgent Evaluation Report

**Generated:** 2026-06-29T06:13:09.009282+00:00 UTC  
**Package Version:** 0.1.0  
**Model Label:** GLM-4.7 via CC-Switch; deterministic gate v0.2  

## Provenance Hashes

- **Prompt:** `1de5eab65e8e0c9a...`  
- **Registry:** `d3d66aa464ac14c7...`  
- **Task Set:** `fa547777bd1e349a...`  

## Summary Statistics (Per-Arm)

### ARM_A

| Metric | Passed | Total | Proportion |
|--------|--------|-------|------------|
| database_routing | 10 | 10 | 100.00% |
| feasibility | 10 | 10 | 100.00% |
| hard_error_free | 7 | 10 | 70.00% |
| correct_refusal | 10 | 10 | 100.00% |
| variable_codes | 8 | 10 | 80.00% |
| manifest_reconstructability | 10 | 10 | 100.00% |

### ARM_B

| Metric | Passed | Total | Proportion |
|--------|--------|-------|------------|
| database_routing | 6 | 10 | 60.00% |
| feasibility | 9 | 10 | 90.00% |
| hard_error_free | 0 | 10 | 0.00% |
| correct_refusal | 9 | 10 | 90.00% |
| variable_codes | 0 | 10 | 0.00% |
| manifest_reconstructability | 10 | 10 | 100.00% |

## Per-Task Details

| Task ID | Domain | Arm | Database Routing | Feasibility | Hard Error Free |
|---------|--------|------|-------------------|--------------|-----------------|
| stroke_01 | stroke | arm_a | ✓ | ✓ | ✗ |
| stroke_01 | stroke | arm_b | ✓ | ✓ | ✗ |
| stroke_02 | stroke | arm_a | ✓ | ✓ | ✓ |
| stroke_02 | stroke | arm_b | ✓ | ✓ | ✗ |
| stroke_03 | stroke | arm_a | ✓ | ✓ | ✗ |
| stroke_03 | stroke | arm_b | ✓ | ✓ | ✗ |
| tbi_01 | tbi | arm_a | ✓ | ✓ | ✓ |
| tbi_01 | tbi | arm_b | ✓ | ✗ | ✗ |
| tbi_02 | tbi | arm_a | ✓ | ✓ | ✓ |
| tbi_02 | tbi | arm_b | ✗ | ✓ | ✗ |
| tbi_03 | tbi | arm_a | ✓ | ✓ | ✓ |
| tbi_03 | tbi | arm_b | ✗ | ✓ | ✗ |
| tumor_01 | tumor | arm_a | ✓ | ✓ | ✓ |
| tumor_01 | tumor | arm_b | ✗ | ✓ | ✗ |
| tumor_02 | tumor | arm_a | ✓ | ✓ | ✓ |
| tumor_02 | tumor | arm_b | ✓ | ✓ | ✗ |
| tumor_03 | tumor | arm_a | ✓ | ✓ | ✓ |
| tumor_03 | tumor | arm_b | ✗ | ✓ | ✗ |
| cross_01 | stroke | arm_a | ✓ | ✓ | ✗ |
| cross_01 | stroke | arm_b | ✓ | ✓ | ✗ |

## Experiment Coverage

- **Expected outputs:** 20 (10 tasks × 2 arms)  
- **Outputs present:** 20  
- **Coverage:** 100.0%  

> **Note:** This is a pilot evaluation with draft tasks. Results are not suitable for significance claims or publication.
