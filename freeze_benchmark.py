#!/usr/bin/env python
"""Freeze the draft 30-task benchmark into a versioned external benchmark artifact."""
import yaml
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

# Paths
BENCHMARKS_DIR = Path("benchmarks")
DRAFT_PATH = BENCHMARKS_DIR / "tasks.draft.yaml"
FROZEN_PATH = BENCHMARKS_DIR / "tasks.v0.1.0.yaml"  # Versioned frozen artifact
BENCHMARK_CARD_PATH = BENCHMARKS_DIR / "BENCHMARK_CARD.md"
SCHEMA_PATH = BENCHMARKS_DIR / "benchmark_schema.v1.json"

def load_draft_tasks():
    """Load and validate the draft tasks."""
    with open(DRAFT_PATH) as f:
        data = yaml.safe_load(f)

    tasks = data.get("tasks", [])

    # Validation
    task_ids = [t.get("id") for t in tasks]
    unique_ids = set(task_ids)

    if len(tasks) != 30:
        raise ValueError(f"Expected 30 tasks, found {len(tasks)}")

    if len(task_ids) != len(unique_ids):
        raise ValueError(f"Duplicate task IDs found")

    return tasks

def add_frozen_metadata(tasks):
    """Add schema, version, and timestamp metadata to benchmark."""
    frozen_metadata = {
        "schema_version": "1.0",
        "benchmark_name": "NeuroSurgEpiAgent Public-Database Planning Benchmark",
        "benchmark_version": "0.1.0",
        "frozen_timestamp": datetime.now(timezone.utc).isoformat(),
        "frozen_by": "NeuroSurgEpiAgent Development Team",
        "status": "DRAFT - AUTHORED GOLD ASSERTIONS PENDING INDEPENDENT EXPERT ADJUDICATION",
        "disclaimer": (
            "This benchmark contains draft gold assertions authored by the development team. "
            "These assertions have NOT been independently validated by expert adjudicators. "
            "This benchmark CANNOT support scientific claims about agent performance, clinical "
            "utility, or comparative effectiveness. The draft status is marked by all tasks "
            "having review_status='needs_expert_review'. Expert adjudication is required per "
            "benchmarks/GOLD_STANDARD_PROCESS.md before this benchmark can be used for "
            "scientific evaluation or publication."
        ),
        "task_count": len(tasks),
        "domains": list(set(t.get("domain") for t in tasks)),
        "gold_standard_requirements": {
            "expert_recruitment": "NOT_COMPLETE - Two independent experts (neurologist/neurosurgeon + epidemiologist) not recruited",
            "adjudication": "NOT_COMPLETE - No expert consensus process has occurred",
            "codebook_verification": "NOT_COMPLETE - Variable codes not independently confirmed against NHANES codebooks",
            "leakage_control": "NOT_COMPLETE - No blinded evaluation run with controlled information flow",
        },
        "registry_version": "1",  # Matches the draft's registry_version
        "tasks": tasks
    }
    return frozen_metadata

def compute_sha256(file_path):
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()

def create_benchmark_card(tasks, sha256_hash, frozen_path):
    """Create a human-readable benchmark card."""
    # Domain counts
    domain_counts = Counter(t.get("domain") for t in tasks)
    feasibility_counts = Counter("feasible" if t.get("expected_feasible") else "infeasible" for t in tasks)

    card_content = f"""# NeuroSurgEpiAgent Benchmark Card

**Version**: 0.1.0 (DRAFT - PENDING EXPERT ADJUDICATION)
**Frozen**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
**SHA-256**: `{sha256_hash}`
**Task Count**: {len(tasks)}
**Status**: ⚠️ **DRAFT - CANNOT SUPPORT SCIENTIFIC CLAIMS**

---

## Overview

This benchmark contains **{len(tasks)}** diverse neurosurgical epidemiology tasks spanning **{len(domain_counts)}** clinical domains. It tests planning and feasibility assessment for public-database research questions, with emphasis on proper NHANES survey design, variable mapping, and determination of when questions are infeasible for given data sources.

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
"""

    for domain, count in sorted(domain_counts.items()):
        card_content += f"- **{domain}**: {count} task(s)\n"

    card_content += f"""
### By Feasibility
- **Feasible NHANES questions**: {feasibility_counts['feasible']} (expected to generate valid analysis plans)
- **Infeasible questions**: {feasibility_counts['infeasible']} (expected to be refused with caveats)

### Database Routing Distribution
- **NHANES**: {sum(1 for t in tasks if t.get('expected_database') == 'NHANES')} tasks
- **SEER**: {sum(1 for t in tasks if t.get('expected_database') == 'SEER')} tasks (expected infeasible - adapter not implemented)
- **GBD**: {sum(1 for t in tasks if t.get('expected_database') == 'GBD')} tasks (expected infeasible - adapter not implemented)

## Domains Covered

"""

    domain_descriptions = {
        "stroke": "Cerebrovascular disease and stroke outcomes",
        "tbi": "Traumatic brain injury and concussion",
        "tumor": "CNS tumors including glioblastoma, meningioma, metastases",
        "pituitary": "Pituitary adenomas and hormonal dysfunction",
        "sah": "Subarachnoid hemorrhage and aneurysms",
        "hydrocephalus": "Adult and pediatric hydrocephalus",
        "spine": "Degenerative spine disease, fractures, stenosis",
        "disparities": "Racial, socioeconomic, and geographic disparities",
        "global_burden": "Global trends and cross-national comparisons"
    }

    for domain in sorted(domain_counts.keys()):
        description = domain_descriptions.get(domain, "No description available")
        task_count = domain_counts[domain]
        card_content += f"### {domain.title()}\n{description} — **{task_count}** tasks\n\n"

    card_content += f"""
## Scoring Metrics

Each task is scored on six metrics against the frozen gold standard:

1. **Database Routing** - Does the plan's `database` match `expected_database`?
2. **Feasibility Assessment** - Does the plan's `feasible` match `expected_feasible`?
3. **Hard Error Free** - Did the planner generate a plan without crashing/timeout?
4. **Correct Refusal** - Did the planner correctly refuse infeasible tasks?
5. **Variable Codes** - Are all variable codes from the allowed registry set?
6. **Manifest Reconstructability** - Can the plan be serialized/deserialized correctly?

## Files

- **Frozen Benchmark**: `{frozen_path.name}` — Versioned task set with metadata
- **Gold Standard Process**: `GOLD_STANDARD_PROCESS.md` — Expert adjudication requirements
- **Schema Definition**: `benchmark_schema.v1.json` — Task structure specification
- **Example Tasks**: `tasks.example.yaml` — Original 10-task subset

## Citation (Draft Status)

```bibtex
@misc{{neurosurgepiagent_benchmark_v0_1_0,
  title={{NeuroSurgEpiAgent Public-Database Planning Benchmark v0.1.0}},
  author={{NeuroSurgEpiAgent Development Team}},
  year={datetime.now().year},
  month={datetime.now().strftime('%B')},
  note={{DRAFT - Authored gold assertions pending independent expert adjudication}},
  url={{https://github.com/your-org/NeuroSurgEpiAgent}}
}}
```

## Version History

- **v0.1.0** ({datetime.now().strftime('%Y-%m-%d')}) — Initial frozen draft with 30 tasks across 9 domains. Pending expert adjudication.

---

**Status**: ⚠️ **DRAFT - EXPERT ADJUDICATION REQUIRED BEFORE ANY SCIENTIFIC USE**

For questions about the benchmark status or expert adjudication process, consult `benchmarks/GOLD_STANDARD_PROCESS.md`.
"""

    with open(BENCHMARK_CARD_PATH, 'w') as f:
        f.write(card_content)

def create_schema_definition():
    """Create JSON schema definition for benchmark tasks."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "$id": "https://neurosurgepiagent.org/schemas/benchmark_task-v1.json",
        "title": "NeuroSurgEpiAgent Benchmark Task",
        "description": "Schema for a single benchmark task in the NeuroSurgEpiAgent evaluation framework",
        "type": "object",
        "required": ["id", "domain", "question", "expected_database", "expected_feasible", "rationale"],
        "properties": {
            "id": {
                "type": "string",
                "description": "Unique task identifier",
                "pattern": "^[a-z_][a-z0-9_]*$"
            },
            "domain": {
                "type": "string",
                "description": "Clinical domain (stroke, tbi, tumor, etc.)",
                "enum": ["stroke", "tbi", "tumor", "pituitary", "sah", "hydrocephalus", "spine", "disparities", "global_burden"]
            },
            "question": {
                "type": "string",
                "description": "Free-text research question"
            },
            "expected_database": {
                "type": "string",
                "description": "Expected database routing from deterministic router",
                "enum": ["NHANES", "SEER", "GBD", "CHARLS"]
            },
            "expected_feasible": {
                "type": "boolean",
                "description": "Expected feasibility assessment (true=can generate plan, false=should refuse)"
            },
            "rationale": {
                "type": "string",
                "description": "Rationale for expected behavior"
            },
            "domain_specific_notes": {
                "type": ["string", "null"],
                "description": "Domain-specific implementation notes"
            },
            "review_status": {
                "type": "string",
                "description": "Validation status",
                "enum": ["needs_expert_review", "expert_validated", "draft"],
                "default": "needs_expert_review"
            },
            "requires_nhanes_codebook": {
                "type": "boolean",
                "description": "Whether NHANES codebook verification is expected",
                "default": false
            }
        }
    }

    with open(SCHEMA_PATH, 'w') as f:
        json.dump(schema, f, indent=2)

def main():
    """Main freezing process."""
    print("=" * 70)
    print("NEUROSURGEPIAGENT BENCHMARK FREEZING PROCESS")
    print("=" * 70)

    # Step 1: Validate and load draft tasks
    print(f"\n[1/6] Loading and validating draft tasks from {DRAFT_PATH}")
    tasks = load_draft_tasks()
    print(f"     ✓ Loaded {len(tasks)} tasks with unique IDs")

    # Step 2: Add frozen metadata
    print(f"[2/6] Adding frozen metadata (schema version, timestamp)")
    frozen_data = add_frozen_metadata(tasks)
    print(f"     ✓ Schema version: {frozen_data['schema_version']}")
    print(f"     ✓ Benchmark version: {frozen_data['benchmark_version']}")
    print(f"     ✓ Frozen at: {frozen_data['frozen_timestamp']}")

    # Step 3: Write frozen artifact
    print(f"[3/6] Writing frozen benchmark artifact to {FROZEN_PATH}")
    with open(FROZEN_PATH, 'w') as f:
        yaml.dump(frozen_data, f, default_flow_style=False, sort_keys=False)
    print(f"     ✓ Frozen benchmark written")

    # Step 4: Compute SHA-256
    print(f"[4/6] Computing SHA-256 hash of frozen artifact")
    sha256_hash = compute_sha256(FROZEN_PATH)
    print(f"     ✓ SHA-256: {sha256_hash}")

    # Step 5: Create benchmark card
    print(f"[5/6] Creating human-readable benchmark card")
    create_benchmark_card(tasks, sha256_hash, FROZEN_PATH)
    print(f"     ✓ Benchmark card written to {BENCHMARK_CARD_PATH}")

    # Step 6: Create schema definition
    print(f"[6/6] Creating JSON schema definition")
    create_schema_definition()
    print(f"     ✓ Schema written to {SCHEMA_PATH}")

    print("\n" + "=" * 70)
    print("BENCHMARK FREEZING COMPLETE")
    print("=" * 70)
    print(f"\nArtifacts created:")
    print(f"  • Frozen benchmark: {FROZEN_PATH}")
    print(f"  • Benchmark card:   {BENCHMARK_CARD_PATH}")
    print(f"  • Schema definition: {SCHEMA_PATH}")
    print(f"  • SHA-256 hash:     {sha256_hash}")
    print(f"\n⚠️  STATUS: DRAFT - PENDING INDEPENDENT EXPERT ADJUDICATION")
    print(f"    This benchmark CANNOT support scientific claims.")
    print(f"    See {BENCHMARK_CARD_PATH} for details.")

if __name__ == "__main__":
    main()
