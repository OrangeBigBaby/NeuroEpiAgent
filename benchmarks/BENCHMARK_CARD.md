# NeuroSurgEpiAgent Benchmark Card

**Version**: 0.1.0 (DRAFT - PENDING EXPERT ADJUDICATION)
**Frozen**: 2026-06-29 (Draft freeze, pending expert sign-off)
**SHA-256**: `{PENDING_GENERATION}`
**Task Count**: 30
**Status**: ⚠️ **DRAFT - CANNOT SUPPORT SCIENTIFIC CLAIMS**

---

## Overview

This benchmark contains **30** diverse neurosurgical epidemiology tasks spanning **9** clinical domains. It tests planning and feasibility assessment for public-database research questions, with emphasis on proper NHANES survey design, variable mapping, and determination of when questions are infeasible for given data sources.

## ⚠️ Critical Limitations

**This benchmark is in DRAFT status and CANNOT be used for:**
- Scientific publication claims about agent performance
- Comparative effectiveness evaluations between systems  
- Clinical utility assessments
- Any claims requiring independently validated ground truth

**Required before scientific use:**
1. Recruitment of two independent experts (neurologist/neurosurgeon + epidemiologist)
2. Expert adjudication of all expected behaviors per `GOLD_STANDARD_PROCESS.md`
3. Independent verification of all variable codes against NHANES codebooks
4. Blinded evaluation run with leakage control
5. Expert countersignature on final results

See `benchmarks/GOLD_STANDARD_PROCESS.md` for complete requirements.

## Task Distribution

### By Clinical Domain
- **disparities**: 2 task(s)
- **global_burden**: 2 task(s)  
- **hydrocephalus**: 2 task(s)
- **pituitary**: 2 task(s)
- **sah**: 3 task(s)
- **spine**: 3 task(s)
- **stroke**: 9 task(s)
- **tbi**: 3 task(s)
- **tumor**: 4 task(s)

### By Feasibility  
- **Feasible NHANES questions**: 9 (expected to generate valid analysis plans)
- **Infeasible questions**: 21 (expected to be refused with caveats)

### Database Routing Distribution
- **NHANES**: 26 tasks
- **SEER**: 2 tasks (expected infeasible - adapter not implemented)
- **GBD**: 2 tasks (expected infeasible - adapter not implemented)

## Domains Covered

### Disparities
Racial, socioeconomic, and geographic disparities — **2** tasks

### Global_Burden
Global trends and cross-national comparisons — **2** tasks

### Hydrocephalus
Adult and pediatric hydrocephalus — **2** tasks

### Pituitary
Pituitary adenomas and hormonal dysfunction — **2** tasks

### Sah
Subarachnoid hemorrhage and aneurysms — **3** tasks

### Spine
Degenerative spine disease, fractures, stenosis — **3** tasks

### Stroke
Cerebrovascular disease and stroke outcomes — **9** tasks

### Tbi
Traumatic brain injury and concussion — **3** tasks

### Tumor
CNS tumors including glioblastoma, meningioma, metastases — **4** tasks

## Scoring Metrics

Each task is scored on six metrics against the frozen gold standard:

1. **Database Routing** - Does the plan's `database` match `expected_database`?
2. **Feasibility Assessment** - Does the plan's `feasible` match `expected_feasible`?
3. **Hard Error Free** - Did the planner generate a plan without crashing/timeout?
4. **Correct Refusal** - Did the planner correctly refuse infeasible tasks?
5. **Variable Codes** - Are all variable codes from the allowed registry set?
6. **Manifest Reconstructability** - Can the plan be serialized/deserialized correctly?

## Files

- **Frozen Benchmark**: `tasks.v0.1.0.yaml` — Versioned task set with metadata
- **Gold Standard Process**: `GOLD_STANDARD_PROCESS.md` — Expert adjudication requirements
- **Schema Definition**: `benchmark_schema.v1.json` — Task structure specification
- **Example Tasks**: `tasks.example.yaml` — Original 10-task subset

## Citation (Draft Status)

```bibtex
@misc{neurosurgepiagent_benchmark_v0_1_0,
  title={NeuroSurgEpiAgent Public-Database Planning Benchmark v0.1.0},
  author={NeuroSurgEpiAgent Development Team},
  year={2026},
  month={June},
  note={DRAFT - Authored gold assertions pending independent expert adjudication},
  url={https://github.com/your-org/NeuroSurgEpiAgent}
}
```

## Version History

- **v0.1.0** (2026-06-29) — Initial frozen draft with 30 tasks across 9 domains. Pending expert adjudication.

---

**Status**: ⚠️ **DRAFT - EXPERT ADJUDICATION REQUIRED BEFORE ANY SCIENTIFIC USE**

For questions about the benchmark status or expert adjudication process, consult `benchmarks/GOLD_STANDARD_PROCESS.md`.
