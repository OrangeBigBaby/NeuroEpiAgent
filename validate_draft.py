#!/usr/bin/env python
"""Validate draft benchmark tasks."""
import yaml
from pathlib import Path

# Load the draft tasks
draft_path = Path("benchmarks/tasks.draft.yaml")
with open(draft_path) as f:
    data = yaml.safe_load(f)

tasks = data.get("tasks", [])
print(f"Total tasks: {len(tasks)}")

# Check unique IDs
task_ids = [t.get("id") for t in tasks]
unique_ids = set(task_ids)
print(f"Unique task IDs: {len(unique_ids)}")
print(f"All unique: {len(task_ids) == len(unique_ids)}")

# Count by domain
domains = {}
for t in tasks:
    domain = t.get("domain", "unknown")
    domains[domain] = domains.get(domain, 0) + 1

print(f"\nDomains:")
for domain, count in sorted(domains.items()):
    print(f"  {domain}: {count}")

# Check required fields
print(f"\nRequired field validation:")
required_fields = ["id", "domain", "question", "expected_database", "expected_feasible", "rationale"]
for field in required_fields:
    missing = [t for t in tasks if field not in t]
    print(f"  {field}: {'OK' if not missing else f'MISSING in {len(missing)} tasks'}")

# Check metadata fields
print(f"\nMetadata validation:")
review_statuses = set(t.get("review_status", "missing") for t in tasks)
print(f"  review_status values: {review_statuses}")

requires_codebook = sum(1 for t in tasks if t.get("requires_nhanes_codebook", False))
print(f"  tasks requiring codebook: {requires_codebook}")
